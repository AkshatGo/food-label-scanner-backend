from datetime import datetime, timezone


def create_scan_document(
    scan_id,
    filename,
    image_id,
    content_type=None,
    file_size=None,
):
    return {
        "scan_id": scan_id,

        "uploaded_at": datetime.now(timezone.utc),

        "image": {
            "filename": filename,
            "gridfs_id": image_id,
            "content_type": content_type,
            "size": file_size,
        },

        "product": {
            "name": None,
            "category": None,
            "category_confidence": None
        },

        "ingredients": [],

        "nutrition": {},

        "label_information": {},

        "fssai": {
            "detected": [],
            "not_detected": [],
            "potential_issues": [],
            "warnings": []
        },

        "inr": {},

        "ocr": {
            "confidence": None,
            "text": None
        },

        "pdf": {
            "gridfs_id": None,
            "filename": f"{scan_id}.pdf"
        },

        "processing": {
            "status": "uploaded",
            "started_at": None,
            "completed_at": None,
            "processing_time_ms": None,
        }
    }