"""OCR service: off-the-shelf Tesseract behind an internal interface (ADR-2).

Preprocessing happens here so downstream code only sees text + confidence.
Two toolkits, two jobs (they are not competitors):

- **PIL** owns decode, EXIF orientation, pixel-budget resize, tone
  (autocontrast/sharpen/contrast) — the simple, deterministic operations.
- **OpenCV** owns the geometric/adaptive operations phone photos need and
  PIL was never built for: variance-of-Laplacian blur scoring, skew
  correction (deskew), and adaptive thresholding for uneven lighting
  (glare/shadow across a curved packet).

The engine is swappable without touching the pipeline.
"""

from io import BytesIO

import numpy
from PIL import Image, ImageEnhance, ImageFilter, ImageOps

try:  # optional hardening: headless build keeps Docker slim
    import cv2
except ImportError:  # pragma: no cover - cv2 ships in requirements
    cv2 = None

# A photo below this variance-of-Laplacian blur score is rejected before
# OCR: hopeless input burns 30-60s of small-deployment CPU and returns
# hallucinated rows that the honesty gate then has to catch. Calibration
# sweep (synthetic label, 44px glyphs at OCR budget): crisp ~400, sigma=1.0
# ~71 (still fully readable), sigma=2.0 ~9, hard shake/box-blur <6. Real
# packet photos carry smaller effective glyphs, so the readable band sits
# *lower* than the synthetic sweep — the gate is therefore set deep in the
# hopeless zone (15) to only reject input no preprocessing could rescue,
# never merely imperfect photos. Deskew + the adaptive-threshold variant
# handle the degraded-but-readable middle band instead of a rejection.
MIN_BLUR_SCORE = 15.0
BLURRY_IMAGE_ERROR = "BLURRY_IMAGE"
# Marker for the downstream legibility gate (routes): OCR completed but the
# text carries too few real words to be a label at all (e.g. "a \\ ee 50 s"
# off a photo of a hand/blurry background). Such input must fail with
# guidance, never become a stored zero-scored product.
UNREADABLE_IMAGE_ERROR = "UNREADABLE_IMAGE"

# OCR budget tuning: the pipeline downscales sources to this pixel budget and
# no longer enlarges them. The previous budget (1.5MP, then enlarged 2x on
# each side) quadrupled per-pass work; on a small deployment (0.1 CPU) that
# pushed Tesseract past its per-pass timeout and scans failed with "Tesseract
# process timeout" even for crisp photos. Accuracy on 900k-pixel grayscale
# input remains sufficient for printed labels; see tests/test_scan_pipeline.py.
MAX_OCR_SOURCE_PIXELS = 900_000
ENLARGE_LINEAR_CAP = 4  # safety bound for absurd thumbnails (e.g. 50x50)
ENLARGE_FACTOR = 1


def _resize_for_ocr(image):
    """Normalize any source toward the OCR pixel budget, up or down.

    Large photos are downscaled to the budget (the old 2x-enlarge path once
    blew the per-pass timeout on small deployments). Sources *smaller* than
    the budget are upscaled toward it: sub-budget uploads (web-saved images,
    messaging-app forwards) carry print too small for Tesseract's
    un-upscaled expectations — a real 294px-wide upload was read as
    "Total Carbohydrate 159" instead of "15g", tripping the ambiguity
    review gate and withholding the rating. Upscaled work never exceeds the
    budget a normal photo already costs, so this is timeout-safe.
    """
    pixel_count = image.width * image.height
    if pixel_count == MAX_OCR_SOURCE_PIXELS:
        return image
    scale = (MAX_OCR_SOURCE_PIXELS / pixel_count) ** 0.5
    if pixel_count > MAX_OCR_SOURCE_PIXELS:
        pass  # plain downscale to the budget
    else:
        scale = min(scale, ENLARGE_LINEAR_CAP)
    return image.resize(
        (max(1, int(image.width * scale)), max(1, int(image.height * scale))),
        Image.Resampling.LANCZOS,
    )


def _to_cv(pil_image):
    """PIL (mode L or RGB) -> BGR/gray numpy array for OpenCV."""
    array = numpy.asarray(pil_image.convert("RGB"))
    return cv2.cvtColor(array, cv2.COLOR_RGB2BGR)


def _to_pil(cv_image):
    """OpenCV BGR/gray numpy array -> PIL (mode RGB or L)."""
    if cv_image.ndim == 2:
        return Image.fromarray(cv_image, mode="L")
    return Image.fromarray(cv2.cvtColor(cv_image, cv2.COLOR_BGR2RGB), mode="RGB")


def _blur_score(pil_image):
    """Variance of the Laplacian: the standard single-number focus metric.

    Sharp printed text carries many high-frequency edges -> high variance.
    Motion/defocus blur smooths edges -> variance collapses. Cheap (one
    convolution at OCR budget) and robust to scene content.
    """
    gray = cv2.cvtColor(_to_cv(pil_image), cv2.COLOR_BGR2GRAY)
    return float(cv2.Laplacian(gray, cv2.CV_64F).var())


def _deskew(pil_image, max_angle=10.0):
    """Rotate mild skew (level horizon estimate) back to 0deg.

    Tesseract accuracy degrades sharply past ~2deg. The angle comes from
    the minimum-area rectangle around binarized ink: real packets fill the
    frame edge-to-edge, so the rectangle angle tracks the camera roll.
    Angles beyond +/-max_angle are treated as unreliable estimates and left
    alone (a wrong guess would rotate a fine photo into garbage).
    """
    gray = cv2.cvtColor(_to_cv(pil_image), cv2.COLOR_BGR2GRAY)
    binary = cv2.adaptiveThreshold(
        gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, 35, 15
    )
    coords = cv2.findNonZero(binary)
    if coords is None:
        return pil_image
    angle = cv2.minAreaRect(coords)[-1]
    if angle > 45:
        angle -= 90
    if abs(angle) < 0.3 or abs(angle) > max_angle:
        return pil_image
    height, width = gray.shape
    matrix = cv2.getRotationMatrix2D((width / 2, height / 2), angle, 1.0)
    rotated = cv2.warpAffine(
        gray,
        matrix,
        (width, height),
        flags=cv2.INTER_CUBIC,
        borderMode=cv2.BORDER_REPLICATE,
    )
    return _to_pil(rotated)


def _adaptive_threshold_variant(pil_image):
    """Adaptive-threshold read for glare/shadow across a curved packet.

    Global tone (PIL autocontrast/contrast) cannot separate print from
    background when one side of the label is lit and the other shadowed;
    a per-neighborhood threshold can. Returned in normal (dark-ink-on-
    paper) polarity for Tesseract.
    """
    gray = cv2.cvtColor(_to_cv(pil_image), cv2.COLOR_BGR2GRAY)
    binary = cv2.adaptiveThreshold(
        gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 51, 12
    )
    return _to_pil(binary)


def _prepare_variants(image):
    """Create readable label crops without changing the source image."""
    image = _resize_for_ocr(image)
    if cv2 is not None:
        image = _deskew(image)
    width, height = image.size
    crops = [
        image,
        image.crop((0, int(height * 0.15), width, height)),
    ]
    variants = []
    for crop in crops:
        gray = ImageOps.grayscale(crop)
        if ENLARGE_FACTOR > 1:
            enlarged = gray.resize(
                (gray.width * ENLARGE_FACTOR, gray.height * ENLARGE_FACTOR),
                Image.Resampling.LANCZOS,
            )
        else:
            enlarged = gray
        contrasted = ImageOps.autocontrast(enlarged)
        sharpened = contrasted.filter(ImageFilter.SHARPEN)
        variants.append(ImageEnhance.Contrast(sharpened).enhance(1.8))
    if cv2 is not None:
        variants.append(_adaptive_threshold_variant(image))
    return variants


def _read_variant(pytesseract, image, mode):
    data = pytesseract.image_to_data(
        image,
        config=f"--oem 3 --psm {mode}",
        output_type=pytesseract.Output.DICT,
        timeout=60,
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
    if cv2 is not None:
        score = _blur_score(_resize_for_ocr(image))
        if score < MIN_BLUR_SCORE:
            return {
                "text": "",
                "confidence": None,
                "variants_used": 0,
                "error": f"{BLURRY_IMAGE_ERROR}: variance-of-Laplacian {score:.1f} is below {MIN_BLUR_SCORE:g}",
            }
    candidates = []
    for variant in _prepare_variants(image):
        result = _read_variant(pytesseract, variant, 6)
        if result["word_count"] >= 2:
            candidates.append(result)

    if not candidates:
        return {"text": "", "confidence": None, "variants_used": 0}
    return _merge_candidates(candidates)


def run_ocr_with_retries(image_bytes: bytes, attempts: int = 2) -> dict:
    """Extract text, tolerating transient Tesseract failures (timeouts).

    Small deployments periodically hit the per-pass timeout under load. One
    retry usually succeeds. When every attempt fails, the returned marker
    carries the reason so the scan can fail honestly instead of being
    silently scored from missing data.
    """
    last_error = None
    for _ in range(max(1, attempts)):
        try:
            return extract_text(image_bytes)
        except (RuntimeError, OSError) as error:  # pytesseract timeouts raise RuntimeError
            last_error = error
    return {
        "text": "",
        "confidence": None,
        "variants_used": 0,
        "error": f"OCR failed after {attempts} attempts: {last_error}",
    }
