"""Scan document factory for the LabelLens pipeline."""

from datetime import datetime, timezone


def create_scan_document(scan_id, user_id, image_refs):
    """image_refs: {front: id|None, back: id|None, nutrition: id|None}"""
    return {
        "scan_id": scan_id,
        "user_id": user_id,
        "status": "processing",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "images": {
            "front": image_refs.get("front"),
            "back": image_refs.get("back"),
            "nutrition": image_refs.get("nutrition"),
        },
        "ocr": {
            "text": None,
            "cleaned_text": None,
            "confidence_avg": None,
            "confidence_front": None,
            "confidence_back": None,
            "nutrition_table_detected": None,
        },
        "product": None,
        "product_id": None,
        "needs_review": False,
        "review_reasons": [],
        "error": None,
        "pdf": {"gridfs_id": None, "filename": f"{scan_id}.pdf"},
        "processing": {
            "started_at": datetime.now(timezone.utc).isoformat(),
            "completed_at": None,
            "processing_time_ms": None,
        },
    }
