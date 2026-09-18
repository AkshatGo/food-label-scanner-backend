"""OCR service: off-the-shelf Tesseract behind an internal interface (ADR-2).

Preprocessing (grayscale -> enlarge -> autocontrast -> sharpen -> contrast)
happens here so downstream code only sees text + confidence. The engine is
swappable without touching the pipeline.
"""

from io import BytesIO

from PIL import Image, ImageEnhance, ImageFilter, ImageOps

MAX_OCR_SOURCE_PIXELS = 1_500_000


def _resize_for_ocr(image):
    """Bound OCR work for high-resolution mobile photos."""
    pixel_count = image.width * image.height
    if pixel_count <= MAX_OCR_SOURCE_PIXELS:
        return image
    scale = (MAX_OCR_SOURCE_PIXELS / pixel_count) ** 0.5
    return image.resize(
        (max(1, int(image.width * scale)), max(1, int(image.height * scale))),
        Image.Resampling.LANCZOS,
    )


def _prepare_variants(image):
    """Create readable label crops without changing the source image."""
    image = _resize_for_ocr(image)
    width, height = image.size
    crops = [
        image,
        image.crop((0, int(height * 0.15), width, height)),
    ]
    variants = []
    for crop in crops:
        gray = ImageOps.grayscale(crop)
        enlarged = gray.resize(
            (gray.width * 2, gray.height * 2),
            Image.Resampling.LANCZOS,
        )
        contrasted = ImageOps.autocontrast(enlarged)
        sharpened = contrasted.filter(ImageFilter.SHARPEN)
        variants.append(ImageEnhance.Contrast(sharpened).enhance(1.8))
    return variants


def _read_variant(pytesseract, image, mode):
    data = pytesseract.image_to_data(
        image,
        config=f"--oem 3 --psm {mode}",
        output_type=pytesseract.Output.DICT,
        timeout=30,
    )
    lines = {}
    confidences = []
    for index, raw_text in enumerate(data["text"]):
        text = raw_text.strip()
        if not text:
            continue
        try:
            confidence = float(data["conf"][index])
        except (TypeError, ValueError):
            confidence = -1
        if confidence >= 0:
            confidences.append(confidence)
        key = (data["block_num"][index], data["par_num"][index], data["line_num"][index])
        lines.setdefault(key, []).append(text)

    return {
        "text": "\n".join(" ".join(words) for words in lines.values()),
        "confidence": round(sum(confidences) / len(confidences), 2) if confidences else None,
        "word_count": sum(len(words) for words in lines.values()),
    }


def _merge_candidates(candidates):
    unique_lines = []
    seen = set()
    for candidate in sorted(candidates, key=lambda item: item["confidence"] or 0, reverse=True):
        for line in candidate["text"].splitlines():
            normalized = " ".join(line.lower().split())
            if normalized and normalized not in seen:
                seen.add(normalized)
                unique_lines.append(line.strip())
    confidence_values = [item["confidence"] for item in candidates if item["confidence"] is not None]
    return {
        "text": "\n".join(unique_lines),
        "confidence": round(sum(confidence_values) / len(confidence_values), 2) if confidence_values else None,
        "variants_used": len(candidates),
    }


def extract_text(image_bytes: bytes) -> dict:
    """Extract reconstructed label text from full-frame and focused crops."""
    try:
        import pytesseract
    except ImportError as error:
        raise RuntimeError("OCR is unavailable; install the backend requirements") from error

    image = ImageOps.exif_transpose(Image.open(BytesIO(image_bytes))).convert("RGB")
    candidates = []
    for variant in _prepare_variants(image):
        result = _read_variant(pytesseract, variant, 6)
        if result["word_count"] >= 2:
            candidates.append(result)

    if not candidates:
        return {"text": "", "confidence": None, "variants_used": 0}
    return _merge_candidates(candidates)
