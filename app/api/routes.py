"""LabelLens REST API — doc 07 endpoint reference.

All endpoints (except /auth/*, /health, /) require a Bearer JWT.

Endpoints:
    POST   /api/v1/auth/signup
    POST   /api/v1/auth/login
    PUT    /api/v1/users/{user_id}/conditions
    GET    /api/v1/users/{user_id}/conditions
    POST   /api/v1/scan                  (multipart: front_image, back_image, [nutrition_image])
    GET    /api/v1/scan/{scan_id}        (poll)
    GET    /api/v1/product/{product_id}
    POST   /api/v1/personalize
    GET    /api/v1/compliance-report/{product_id}
    GET    /api/v1/compliance-report/{product_id}/summary
    POST   /api/v1/compare
"""

import asyncio
import logging
import re
import secrets
from io import BytesIO
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, File, Header, HTTPException, UploadFile, Request
from fastapi.responses import Response
from gridfs.errors import NoFile
from PIL import Image, UnidentifiedImageError

from .. import config
from ..database import store
from ..models.scan_model import create_scan_document
from ..services.auth_service import AuthError, login, signup, update_conditions, user_from_token
from ..services.compliance import evaluate_compliance
from ..services.compliance_pdf_service import create_compliance_pdf
from ..services.nlp_cleanup import nlp_reconstruct
from ..services.ocr_service import run_ocr_with_retries
from ..services.personalization import personalize
from ..services.scan_pipeline import run_scan_pipeline

router = APIRouter(prefix="/api/v1", tags=["LabelLens"])
logger = logging.getLogger(__name__)
_background_tasks = set()
_scan_slots = asyncio.Semaphore(2)

MAX_IMAGE_SIZE = 10 * 1024 * 1024


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------

def _error(code, message, http_status):
    return HTTPException(
        status_code=http_status,
        detail={"error": {"code": code, "message": message, "http_status": http_status}},
    )


async def _current_user(request: Request, authorization: str = Header(default=None)):
    authorization = authorization or request.cookies.get("ll_session")
    if not authorization:
        raise _error("UNAUTHORIZED", "Missing Authorization header", 401)
    token = authorization.removeprefix("Bearer ").strip()
    try:
        return user_from_token(token)
    except AuthError as error:
        raise _error(error.code, error.message, error.http_status) from error


def _validate_image(file: UploadFile, image_bytes: bytes):
    if not file.filename:
        raise _error("INVALID_IMAGE", "An image filename is required", 400)
    if not image_bytes:
        raise _error("INVALID_IMAGE", "The uploaded image is empty", 400)
    if len(image_bytes) > MAX_IMAGE_SIZE:
        raise _error("INVALID_IMAGE", "Image must be 10 MB or smaller", 413)

    detected = None
    if image_bytes.startswith(b"\xff\xd8\xff"):
        detected = "image/jpeg"
    elif image_bytes.startswith(b"\x89PNG\r\n\x1a\n"):
        detected = "image/png"
    elif image_bytes.startswith(b"RIFF") and image_bytes[8:12] == b"WEBP":
        detected = "image/webp"
    if detected is None:
        raise _error("INVALID_IMAGE", "The uploaded file is not a valid image", 400)

    supplied = (file.content_type or "").lower()
    if supplied not in ("", "application/octet-stream", detected):
        raise _error("INVALID_IMAGE", "The uploaded file type does not match its content", 415)
    try:
        with Image.open(BytesIO(image_bytes)) as image:
            if image.width * image.height > 25_000_000:
                raise _error("INVALID_IMAGE", "Photo exceeds 25 megapixels. Use a smaller image.", 413)
            image.verify()
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError) as error:
        raise _error("INVALID_IMAGE", "This image cannot be decoded. Please upload another photo.", 400) from error
    return detected


def _json_safe(value):
    if isinstance(value, dict):
        return {key: _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def _find_scan(scan_id, user):
    scan = store.scans.find_one({"scan_id": scan_id, "user_id": user["user_id"]})
    if not scan:
        raise _error("NOT_FOUND", f"Scan {scan_id} not found", 404)
    return scan


def _find_product(product_id, user):
    product = store.products.find_one({"product_id": product_id, "user_id": user["user_id"]})
    if not product:
        raise _error("NOT_FOUND", f"Product {product_id} not found", 404)
    return product


# --------------------------------------------------------------------------
# Auth (doc 07)
# --------------------------------------------------------------------------

@router.post("/auth/signup", status_code=201)
def auth_signup(body: dict, response: Response):
    try:
        result = signup(body.get("email"), body.get("password"))
        _set_session(response, result["token"])
        return result
    except AuthError as error:
        raise _error(error.code, error.message, error.http_status) from error


@router.post("/auth/login")
def auth_login(body: dict, response: Response):
    try:
        result = login(body.get("email"), body.get("password"))
        _set_session(response, result["token"])
        return result
    except AuthError as error:
        raise _error(error.code, error.message, error.http_status) from error


def _set_session(response, token):
    response.set_cookie("ll_session", token, httponly=True, secure=config.PRODUCTION,
                        samesite="strict", max_age=config.JWT_EXPIRY_HOURS * 3600, path="/")


@router.post("/auth/logout")
def auth_logout(response: Response, user=Depends(_current_user)):
    store.users.update_one({"user_id": user["user_id"]},
                           {"$set": {"token_version": user.get("token_version", 0) + 1}})
    response.delete_cookie("ll_session", path="/")
    return {"message": "Signed out"}


@router.get("/auth/me")
def auth_me(user=Depends(_current_user)):
    return {key: user.get(key) for key in ("user_id", "email", "conditions")}


@router.get("/account/export")
def export_account(user=Depends(_current_user)):
    return {"account": {key: user.get(key) for key in ("email", "conditions", "created_at")},
            "products": [_json_safe({k: v for k, v in p.items() if k != "_id"})
                         for p in store.products.find({"user_id": user["user_id"]})]}


@router.delete("/account")
def delete_account(body: dict, response: Response, user=Depends(_current_user)):
    from ..services.auth_service import _verify_password
    password = body.get("password")
    if not isinstance(password, str) or len(password) > 128 or not _verify_password(password, user["auth_hash"]):
        raise _error("UNAUTHORIZED", "Confirm your password to delete your account.", 401)
    if list(store.scans.find({"user_id": user["user_id"], "status": "processing"})):
        raise _error("SCAN_IN_PROGRESS", "Wait for your scans to finish before deleting your account.", 409)

    def _delete_file(file_id):
        # Mongo GridFS raises NoFile for an already-deleted id; cleanup must
        # stay idempotent so account deletion can never partially fail.
        try:
            store.fs.delete(file_id)
        except NoFile:
            pass

    for scan in list(store.scans.find({"user_id": user["user_id"]})):
        for file_id in scan.get("images", {}).values():
            if file_id:
                _delete_file(file_id)
        store.scans.delete_one({"scan_id": scan["scan_id"]})
    for product in list(store.products.find({"user_id": user["user_id"]})):
        store.products.delete_one({"product_id": product["product_id"]})
    store.users.delete_one({"user_id": user["user_id"]})
    response.delete_cookie("ll_session", path="/")
    return {"message": "Account and live scan data deleted"}


@router.get("/products")
def list_products(user=Depends(_current_user)):
    documents = sorted(store.products.find({"user_id": user["user_id"]}),
                       key=lambda p: p.get("created_at", ""), reverse=True)
    return {"products": [_json_safe({k: v for k, v in p.items() if k != "_id"})
                         for p in documents[:100]]}


@router.put("/users/{user_id}/conditions")
def put_conditions(user_id: str, body: dict, user=Depends(_current_user)):
    if user["user_id"] != user_id:
        raise _error("UNAUTHORIZED", "You can only update your own profile", 403)
    try:
        return update_conditions(user_id, body.get("conditions", []))
    except AuthError as error:
        raise _error(error.code, error.message, error.http_status) from error


@router.get("/users/{user_id}/conditions")
def get_conditions(user_id: str, user=Depends(_current_user)):
    if user["user_id"] != user_id:
        raise _error("UNAUTHORIZED", "You can only view your own profile", 403)
    return {"user_id": user_id, "conditions": user.get("conditions", [])}


# --------------------------------------------------------------------------
# Scan & extraction (doc 07)
# --------------------------------------------------------------------------

@router.post("/scan", status_code=202)
async def scan_product(
    front_image: UploadFile = File(...),
    back_image: UploadFile = File(...),
    nutrition_image: UploadFile = File(None),
    user=Depends(_current_user),
):
    """Accept front + back (ingredients/nutrition) photos; process async.

    ADR-3: two mandatory photos. The nutrition panel may arrive as a third
    optional photo when it sits on a separate face of the pack.
    """
    started_at = datetime.now(timezone.utc)

    payloads = []
    for name, file in (("front", front_image), ("back", back_image), ("nutrition", nutrition_image)):
        if file is None:
            payloads.append((name, None, None, None))
            continue
        image_bytes = await file.read(MAX_IMAGE_SIZE + 1)
        content_type = _validate_image(file, image_bytes)
        payloads.append((name, image_bytes, file.filename, content_type))

    scan_id = (
        "SCAN-" + started_at.strftime("%Y%m%d-%H%M%S") + "-" + secrets.token_hex(3).upper()
    )

    if len(list(store.scans.find({"user_id": user["user_id"], "status": "processing"}))) >= 3:
        raise _error("TOO_MANY_SCANS", "Wait for your current scans to finish.", 429)
    image_refs = {}
    try:
        for name, data, filename, content_type in payloads:
            if data:
                image_refs[name] = store.fs.put(data, filename=filename, metadata={"content_type": content_type})
        document = create_scan_document(scan_id, user["user_id"], image_refs)
        document["job_state"] = "queued"
        store.scans.insert_one(document)
    except Exception:
        for file_id in image_refs.values():
            store.fs.delete(file_id)
        raise
    if not config.PRODUCTION:
        task = asyncio.create_task(_run_local_scan(scan_id))
        _background_tasks.add(task)
        task.add_done_callback(_background_tasks.discard)

    return {
        "scan_id": scan_id,
        "status": "processing",
        "message": "Images accepted for analysis. Poll GET /api/v1/scan/{scan_id}.",
    }


async def _run_local_scan(scan_id):
    async with _scan_slots:
        await asyncio.to_thread(_process_scan, scan_id)


def _process_scan(scan_id):
    """Synchronous scan pipeline; runs in a worker thread."""
    document = store.scans.find_one({"scan_id": scan_id})
    image_refs = document["images"]
    user_id = document["user_id"]
    started_at = datetime.fromisoformat(document["created_at"])
    try:
        store.scans.update_one({"scan_id": scan_id}, {"$set": {"job_state": "running"}})

        # --- OCR over each provided image -------------------------------
        ocr_parts = []
        confidences = []
        per_image = {}
        for name in ("front", "back", "nutrition"):
            if not image_refs.get(name):
                continue
            raw = run_ocr_with_retries(store.fs.get(image_refs[name]).read())
            if raw.get("error"):
                raise RuntimeError(
                    f"OCR failed on the {name} photo: {raw['error']}"
                )
            reconstruction = nlp_reconstruct(raw["text"])
            per_image[name] = {
                "raw_text": raw["text"],
                "cleaned_text": reconstruction["cleaned_text"],
                "confidence": raw["confidence"],
            }
            if raw["confidence"] is not None:
                confidences.append(raw["confidence"])
            ocr_parts.append(reconstruction["human_readable_text"])

        combined_text = "\n".join(ocr_parts).strip()
        confidence_avg = round(sum(confidences) / len(confidences), 2) if confidences else None

        # --- Extraction -> structured product -> compliance -------------
        product, compliance = run_scan_pipeline(combined_text, confidence_avg)
        # Stable ID makes restarting an interrupted job idempotent.
        product_id = "p_" + scan_id
        product["product_id"] = product_id

        needs_review = False
        review_reasons = []
        if confidence_avg is not None and confidence_avg < config.LOW_OCR_CONFIDENCE_THRESHOLD:
            needs_review = True
            review_reasons.append(
                f"Average OCR confidence ({confidence_avg}) is below "
                f"{config.LOW_OCR_CONFIDENCE_THRESHOLD}. Verify values against the pack."
            )
        if product["nutrition_extraction"]["needs_review"]:
            needs_review = True
            review_reasons.append(product["nutrition_extraction"]["note"])
        if product["inr"].get("missing_fields_treated_as_zero"):
            needs_review = True
            review_reasons.append(
                "Some nutrition values were not found and were scored as zero: "
                + ", ".join(product["inr"]["missing_fields_treated_as_zero"])
            )

        saved_product = {
            "product_id": product_id,
            "scan_id": scan_id,
            **product,
            "user_id": user_id,
            "needs_review": needs_review,
            "review_reasons": review_reasons,
            "ocr_confidence_avg": confidence_avg,
            "compliance": compliance,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        if not store.products.find_one({"product_id": product_id}):
            store.products.insert_one(saved_product)

        store.scans.update_one(
            {"scan_id": scan_id},
            {"$set": {
                "status": "done",
                "job_state": "done",
                "ocr": {
                    "text": combined_text[:20000],
                    "cleaned_text": combined_text[:20000],
                    "confidence_avg": confidence_avg,
                    "per_image": per_image,
                    "nutrition_table_detected": bool(
                        re.search(r"per\s*100|nutrition", combined_text, re.IGNORECASE)
                    ),
                },
                "product": product,
                "product_id": product_id,
                "needs_review": needs_review,
                "review_reasons": review_reasons,
                "processing.completed_at": datetime.now(timezone.utc).isoformat(),
                "processing.processing_time_ms": round(
                    (datetime.now(timezone.utc) - started_at).total_seconds() * 1000, 2
                ),
            }},
        )
        return product_id
    except Exception as error:  # noqa: BLE001 - record failure on the scan
        logger.exception("Scan %s failed", scan_id)
        try:
            store.scans.update_one(
                {"scan_id": scan_id},
                {"$set": {
                    "status": "failed",
                    "job_state": "failed",
                    "error": str(error),
                    "processing.completed_at": datetime.now(timezone.utc).isoformat(),
                }},
            )
        except Exception:  # noqa: BLE001
            pass


@router.get("/scan/{scan_id}")
def get_scan(scan_id: str, user=Depends(_current_user)):
    scan = _find_scan(scan_id, user)
    status = scan.get("status")
    if status == "processing":
        return {"scan_id": scan_id, "status": "processing"}

    if status == "failed":
        stored_error = str(scan.get("error") or "")
        if "OCR failed" in stored_error or "Tesseract" in stored_error:
            message = (
                "The photo could not be processed on the server (it is likely too "
                "large for the free tier). Retake with a plainer camera angle, or try again — "
                "transient server overload causes most failures."
            )
        else:
            message = "The scan could not be completed. Please try again."
        return {
            "scan_id": scan_id,
            "status": "failed",
            "error": {
                "code": "PROCESSING_FAILED",
                "message": message,
                "http_status": 500,
            },
        }

    return {
        "scan_id": scan_id,
        "status": "done",
        "needs_review": scan.get("needs_review", False),
        "review_reasons": scan.get("review_reasons", []),
        "ocr_confidence_avg": (scan.get("ocr") or {}).get("confidence_avg"),
        "product": _json_safe(scan.get("product")),
    }


# --------------------------------------------------------------------------
# Product & compare (doc 07)
# --------------------------------------------------------------------------

@router.get("/product/{product_id}")
def get_product(product_id: str, user=Depends(_current_user)):
    product = _find_product(product_id, user)
    return _json_safe(product)


@router.post("/compare")
def compare_products(body: dict, user=Depends(_current_user)):
    def slim(pid):
        product = _find_product(pid, user)
        per100 = product.get("nutrition_per_100g", {})
        return {
            "product_id": product.get("product_id"),
            "product_name": product.get("product_name"),
            "brand": product.get("brand"),
            "inr_stars": (product.get("inr") or {}).get("rating_stars"),
            "inr_score": (product.get("inr") or {}).get("inr_score"),
            "sodium_mg": per100.get("sodium_mg"),
            "total_sugar_g": per100.get("total_sugar_g"),
            "saturated_fat_g": per100.get("saturated_fat_g"),
            "energy_kcal": per100.get("energy_kcal"),
        }

    id_a = body.get("product_id_a")
    id_b = body.get("product_id_b")
    if not id_a or not id_b:
        raise _error("VALIDATION_ERROR", "product_id_a and product_id_b are required", 400)
    return {"product_a": slim(id_a), "product_b": slim(id_b)}


# --------------------------------------------------------------------------
# Personalization (doc 07)
# --------------------------------------------------------------------------

@router.post("/personalize")
def personalize_product(body: dict, user=Depends(_current_user)):
    product_id = body.get("product_id")
    conditions = body.get("conditions")
    if conditions is None:
        conditions = user.get("conditions", [])
    if not product_id:
        raise _error("VALIDATION_ERROR", "product_id is required", 400)

    product = _find_product(product_id, user)
    try:
        result = personalize(product, conditions)
    except ValueError as error:
        raise _error("INVALID_CONDITION", str(error), 422) from error

    return {
        "product_id": product_id,
        "product_name": product.get("product_name"),
        **result,
    }


# --------------------------------------------------------------------------
# Compliance report (doc 07)
# --------------------------------------------------------------------------

@router.get("/compliance-report/{product_id}")
def compliance_report_pdf(product_id: str, regenerate: bool = False, user=Depends(_current_user)):
    product = _find_product(product_id, user)
    compliance = product.get("compliance")
    if regenerate or not compliance:
        structured = build_compliance_structured(product)
        compliance = evaluate_compliance(structured, category=product.get("category", "I"))
        store.products.update_one(
            {"product_id": product_id},
            {"$set": {"compliance": compliance}},
        )

    pdf_bytes = create_compliance_pdf(
        product,
        compliance,
        scan_meta={"scan_id": product.get("scan_id"), "created_at": product.get("created_at")},
    )
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="compliance-{product_id}.pdf"'},
    )


@router.get("/compliance-report/{product_id}/summary")
def compliance_report_summary(product_id: str, user=Depends(_current_user)):
    product = _find_product(product_id, user)
    compliance = product.get("compliance")
    if not compliance:
        structured = build_compliance_structured(product)
        compliance = evaluate_compliance(structured, category=product.get("category", "I"))
        store.products.update_one(
            {"product_id": product_id},
            {"$set": {"compliance": compliance}},
        )
    return {
        "product_id": product_id,
        "regulation_version": compliance["regulation_version"],
        "font_size_summary": compliance["summary"]["font_size"],
        "declarations_summary": compliance["summary"]["declarations"],
        "overall_note": compliance["overall_note"],
    }


def build_compliance_structured(product):
    from ..services.scan_pipeline import build_compliance_input

    return build_compliance_input(product, product.get("ocr_text", ""), None)


# --------------------------------------------------------------------------
# Legacy-style convenience: image retrieval
# --------------------------------------------------------------------------

@router.get("/scan/{scan_id}/image/{position}")
def get_scan_image(scan_id: str, position: str, user=Depends(_current_user)):
    scan = _find_scan(scan_id, user)
    gridfs_id = (scan.get("images") or {}).get(position)
    if not gridfs_id:
        raise _error("NOT_FOUND", f"No '{position}' image stored for scan {scan_id}", 404)
    try:
        data = store.fs.get(gridfs_id).read()
    except Exception as error:  # noqa: BLE001
        raise _error("NOT_FOUND", "Image not found in storage", 404) from error
    media_type = "image/png" if data.startswith(b"\x89PNG") else "image/webp" if data.startswith(b"RIFF") else "image/jpeg"
    return Response(content=data, media_type=media_type)
