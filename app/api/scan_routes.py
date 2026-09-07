import asyncio
import logging
from datetime import datetime, timezone
from uuid import uuid4

from fastapi import APIRouter, File, HTTPException, Query, UploadFile
from fastapi.responses import Response, StreamingResponse
from bson import ObjectId

from ..database.mongodb import scans_collection
from ..database.gridfs_service import (
    delete_file,
    get_file,
    get_image,
    save_image,
    save_pdf,
)
from ..models.scan_model import create_scan_document
from ..services.enhanced_analysis_service import analyze_enhanced
from ..services.nlp_cleanup import nlp_reconstruct
from ..services.ocr_service import extract_text
from ..services.pdf_service import create_report_pdf


router = APIRouter(prefix="/api/v1", tags=["Scan"])
logger = logging.getLogger(__name__)
_background_scan_tasks = set()


MAX_IMAGE_SIZE = 10 * 1024 * 1024

SUPPORTED_IMAGE_TYPES = {
    "image/jpeg": (b"\xff\xd8\xff",),
    "image/png": (b"\x89PNG\r\n\x1a\n",),
    "image/webp": (b"RIFF", b"WEBP"),
}


def validate_image(file: UploadFile, image_bytes: bytes):
    if not file.filename:
        raise HTTPException(
            status_code=400,
            detail="An image filename is required",
        )

    if not image_bytes:
        raise HTTPException(
            status_code=400,
            detail="The uploaded image is empty",
        )

    if len(image_bytes) > MAX_IMAGE_SIZE:
        raise HTTPException(
            status_code=413,
            detail="Image must be 10 MB or smaller",
        )

    supplied_type = (file.content_type or "").lower()

    detected_type = None

    if image_bytes.startswith(b"\xff\xd8\xff"):
        detected_type = "image/jpeg"

    elif image_bytes.startswith(b"\x89PNG\r\n\x1a\n"):
        detected_type = "image/png"

    elif (
        image_bytes.startswith(b"RIFF")
        and image_bytes[8:12] == b"WEBP"
    ):
        detected_type = "image/webp"

    if detected_type is None:
        raise HTTPException(
            status_code=400,
            detail="The uploaded file is not a valid image",
        )

    if supplied_type not in (
        "",
        "application/octet-stream",
        detected_type,
    ):
        raise HTTPException(
            status_code=415,
            detail="The uploaded file type does not match its image content",
        )

    return detected_type


def _record_background_scan_result(task):
    """Keep task failures visible without leaving completed tasks retained."""
    _background_scan_tasks.discard(task)
    try:
        task.result()
    except Exception:
        logger.exception("Background scan processing failed")


@router.post("/scan", status_code=202)
async def scan_product(file: UploadFile = File(...)):
    """
    Upload an image and process it.

    Heavy synchronous operations are moved to a worker thread
    so that FastAPI's event loop remains responsive to health checks
    and other requests.
    """

    started_at = datetime.now(timezone.utc)

    # Read uploaded image asynchronously.
    image_bytes = await file.read()

    content_type = validate_image(
        file,
        image_bytes,
    )

    scan_id = (
        "SCAN-"
        + datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        + "-"
        + uuid4().hex[:6]
    )

    # OCR and PDF work can take longer than a browser/proxy request. Run it in
    # the background and let clients retrieve the completed scan by its ID.
    task = asyncio.create_task(
        asyncio.to_thread(
            _process_scan,
            image_bytes,
            file.filename,
            content_type,
            scan_id,
            started_at,
        )
    )
    _background_scan_tasks.add(task)
    task.add_done_callback(_record_background_scan_result)

    return {
        "success": True,
        "scan_id": scan_id,
        "message": "Image accepted for analysis",
        "processing": {"status": "processing"},
    }


def _process_scan(
    image_bytes,
    filename,
    content_type,
    scan_id,
    started_at,
):
    """
    Synchronous scan pipeline.

    This function is intentionally executed using asyncio.to_thread()
    from scan_product().
    """

    image_id = None
    document_inserted = False
    pdf_id = None

    try:
        # --------------------------------------------------
        # 1. Save uploaded image
        # --------------------------------------------------

        image_id = save_image(
            image_bytes,
            filename,
            content_type,
        )

        # --------------------------------------------------
        # 2. OCR
        # --------------------------------------------------

        raw_ocr = extract_text(image_bytes)

        # --------------------------------------------------
        # 3. NLP cleanup / reconstruction
        # --------------------------------------------------

        reconstruction = nlp_reconstruct(
            raw_ocr["text"]
        )

        cleaned_text = reconstruction[
            "human_readable_text"
        ]

        ocr_result = {
            **raw_ocr,
            "raw_text": raw_ocr["text"],
            "text": cleaned_text,
            "cleaned_text": cleaned_text,
            "human_readable_text": reconstruction[
                "human_readable_text"
            ],
            "nutrition_table_detected": reconstruction[
                "nutrition_table_detected"
            ],
        }

        # --------------------------------------------------
        # 4. Food analysis
        # --------------------------------------------------

        analysis = analyze_enhanced(
            cleaned_text
        )

        # --------------------------------------------------
        # 5. Create MongoDB document
        # --------------------------------------------------

        document = create_scan_document(
            scan_id=scan_id,
            filename=filename,
            image_id=image_id,
            content_type=content_type,
            file_size=len(image_bytes),
        )

        document.update(analysis)

        document["ocr"] = ocr_result

        document["processing"].update(
            {
                "status": "analysis_completed",
                "started_at": started_at,
            }
        )

        scans_collection.insert_one(
            document
        )

        document_inserted = True

        # --------------------------------------------------
        # 6. Generate PDF
        # --------------------------------------------------

        pdf_bytes = create_report_pdf(
            document,
            image_bytes,
        )

        pdf_id = save_pdf(
            pdf_bytes,
            f"{scan_id}.pdf",
        )

        # --------------------------------------------------
        # 7. Mark processing completed
        # --------------------------------------------------

        completed_at = datetime.now(
            timezone.utc
        )

        processing_time_ms = round(
            (
                completed_at - started_at
            ).total_seconds()
            * 1000,
            2,
        )

        scans_collection.update_one(
            {"scan_id": scan_id},
            {
                "$set": {
                    "pdf.gridfs_id": pdf_id,
                    "processing.status": "completed",
                    "processing.completed_at": completed_at,
                    "processing.processing_time_ms": processing_time_ms,
                }
            },
        )

        # --------------------------------------------------
        # 8. Return result
        # --------------------------------------------------

        return {
            "success": True,
            "scan_id": scan_id,
            "filename": filename,
            "message": (
                "Image uploaded, analyzed, "
                "and report generated"
            ),
            "ocr": ocr_result,
            **analysis,
            "image_gridfs_id": image_id,
            "pdf_gridfs_id": pdf_id,
            "processing": {
                "status": "completed",
                "processing_time_ms": processing_time_ms,
            },
            "pdf_available": pdf_id is not None,
        }

    except Exception:
        # --------------------------------------------------
        # Cleanup MongoDB document
        # --------------------------------------------------

        if document_inserted:
            try:
                scans_collection.delete_one(
                    {"scan_id": scan_id}
                )
            except Exception:
                pass

        # --------------------------------------------------
        # Cleanup uploaded image
        # --------------------------------------------------

        if image_id is not None:
            try:
                delete_file(image_id)
            except Exception:
                pass

        # --------------------------------------------------
        # Cleanup generated PDF
        # --------------------------------------------------

        if pdf_id is not None:
            try:
                delete_file(pdf_id)
            except Exception:
                pass

        raise


def _json_safe(value):
    if isinstance(value, ObjectId):
        return str(value)

    if isinstance(value, datetime):
        return value.isoformat()

    if isinstance(value, dict):
        return {
            key: _json_safe(item)
            for key, item in value.items()
        }

    if isinstance(value, list):
        return [
            _json_safe(item)
            for item in value
        ]

    return value


def _find_scan(scan_id):
    scan = scans_collection.find_one(
        {"scan_id": scan_id}
    )

    if not scan:
        raise HTTPException(
            status_code=404,
            detail="Scan not found",
        )

    return scan


@router.get("/scans")
def list_scans(
    limit: int = Query(
        20,
        ge=1,
        le=100,
    )
):
    scans = (
        scans_collection
        .find()
        .sort("uploaded_at", -1)
        .limit(limit)
    )

    return {
        "scans": [
            _json_safe(scan)
            for scan in scans
        ]
    }


@router.get("/scans/{scan_id}")
def get_scan(scan_id: str):
    return _json_safe(
        _find_scan(scan_id)
    )


@router.get("/reports/{scan_id}")
def get_report(scan_id: str):
    scan = _find_scan(scan_id)

    try:
        image_bytes = None

        image = scan.get(
            "image",
            {},
        )

        if image.get("gridfs_id"):
            try:
                img_stream = get_image(
                    image["gridfs_id"]
                )

                image_bytes = img_stream.read()

            except Exception:
                pass

        pdf_bytes = create_report_pdf(
            scan,
            image_bytes,
        )

        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={
                "Content-Disposition": (
                    f'inline; filename="{scan_id}.pdf"'
                )
            },
        )

    except Exception:
        pdf_id = (
            scan
            .get("pdf", {})
            .get("gridfs_id")
        )

        if not pdf_id:
            raise HTTPException(
                status_code=404,
                detail="Report not found",
            )

        try:
            report = get_file(
                pdf_id
            )

        except Exception as error:
            raise HTTPException(
                status_code=404,
                detail="Report not found",
            ) from error

        return StreamingResponse(
            report,
            media_type="application/pdf",
            headers={
                "Content-Disposition": (
                    f'inline; filename="{scan_id}.pdf"'
                )
            },
        )


@router.get("/scans/{scan_id}/image")
def get_scan_image(scan_id: str):
    scan = _find_scan(scan_id)

    image = scan.get(
        "image",
        {},
    )

    try:
        stored_image = get_image(
            image["gridfs_id"]
        )

    except Exception as error:
        raise HTTPException(
            status_code=404,
            detail="Image not found",
        ) from error

    return Response(
        content=stored_image.read(),
        media_type=image.get(
            "content_type",
            "application/octet-stream",
        ),
    )
