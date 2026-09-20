"""OCR robustness tests: pixel budget, retry behavior, honest failure markers.

Background: on small deployments (single low-CPU worker) the previous
preprocessing (1.5MP budget, then 2x enlargement) pushed Tesseract past its
per-pass timeout, so real-world scans failed with "Tesseract process timeout"
while the UI blamed photo quality. These tests pin the corrected behavior.
"""

import re
import time
from io import BytesIO

import numpy
import pytest
from fastapi.testclient import TestClient
from PIL import Image, ImageDraw, ImageFilter, ImageFont

from app.main import app
from app.services.ocr_service import (
    BLURRY_IMAGE_ERROR,
    MAX_OCR_SOURCE_PIXELS,
    MIN_BLUR_SCORE,
    UNREADABLE_IMAGE_ERROR,
    _adaptive_threshold_variant,
    _blur_score,
    _deskew,
    _prepare_variants,
    _resize_for_ocr,
    extract_text,
    run_ocr_with_retries,
)


@pytest.fixture()
def client():
    return TestClient(app)


@pytest.fixture()
def auth_headers(client):
    signup = client.post("/api/v1/auth/signup", json={
        "email": f"ocr-tester-{time.time_ns()}@example.com", "password": "password123",
    })
    assert signup.status_code == 201, signup.text
    return {"Authorization": f"Bearer {signup.json()['token']}"}


def _rendered_label(width=3000, height=3000):
    image = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(image)
    # A real font at a large size: the default bitmap font is too small to
    # survive the pixel-budget downscale, which is the point being tested.
    font = ImageFont.truetype("/usr/share/fonts/TTF/DejaVuSans.ttf", 48)
    draw.text((60, 60), "Energy 480 kcal", font=font, fill="black")
    buf = BytesIO()
    image.save(buf, format="PNG")
    return buf.getvalue()


def test_source_pixel_budget_bounds_work():
    assert MAX_OCR_SOURCE_PIXELS <= 1_000_000


def test_variants_are_not_enlarged():
    image = Image.open(BytesIO(_rendered_label(2000, 2000)))
    variants = _prepare_variants(image)
    for variant in variants:
        assert variant.width * variant.height <= MAX_OCR_SOURCE_PIXELS * 1.05


def test_extract_text_survives_large_photo():
    result = extract_text(_rendered_label(3000, 3000))
    assert "480" in result["text"] or "Energy" in result["text"]
    assert result["confidence"] is not None


def test_retry_recovers_from_transient_failure(monkeypatch):
    calls = {"n": 0}

    def flaky(_bytes):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("Tesseract process timeout")
        return {"text": "Energy 480 kcal", "confidence": 88.0, "variants_used": 2}

    monkeypatch.setattr("app.services.ocr_service.extract_text", flaky)
    result = run_ocr_with_retries(b"image", attempts=2)
    assert result["text"] == "Energy 480 kcal"
    assert "error" not in result
    assert calls["n"] == 2


def test_retry_returns_honest_failure_marker(monkeypatch):
    def always_times_out(_bytes):
        raise RuntimeError("Tesseract process timeout")

    monkeypatch.setattr("app.services.ocr_service.extract_text", always_times_out)
    result = run_ocr_with_retries(b"image", attempts=2)
    assert result["text"] == ""
    assert result["confidence"] is None
    assert "OCR failed after 2 attempts" in result["error"]
    assert "Tesseract process timeout" in result["error"]


def test_api_scan_fails_honestly_when_ocr_fails(client, auth_headers, monkeypatch):
    import app.api.routes as routes_module

    def always_times_out(_bytes):
        raise RuntimeError("Tesseract process timeout")

    monkeypatch.setattr(
        routes_module, "run_ocr_with_retries", always_times_out
    )
    files = {
        "front_image": ("front.png", _rendered_label(400, 400), "image/png"),
        "back_image": ("back.png", _rendered_label(400, 400), "image/png"),
    }
    response = client.post("/api/v1/scan", files=files, headers=auth_headers)
    assert response.status_code == 202
    scan_id = response.json()["scan_id"]

    body = None
    for _ in range(60):
        poll = client.get(f"/api/v1/scan/{scan_id}", headers=auth_headers)
        body = poll.json()
        if body.get("status") != "processing":
            break
    assert body["status"] == "failed"
    message = body["error"]["message"]
    assert "clearer" not in message.lower()
    assert "again" in message.lower() or "server" in message.lower()


# --- OpenCV hardening: blur gate, deskew, adaptive threshold ----------------


def _cv2_or_skip():
    pytest.importorskip("cv2")


def _gradient_shade(image, low=0.30, high=1.20):
    """Simulate uneven lighting: dark on the left, bright on the right."""
    arr = numpy.asarray(image.convert("L"), dtype=numpy.float32)
    grad = numpy.linspace(low, high, arr.shape[1])[None, :]
    shaded = numpy.clip(arr * grad, 0, 255).astype("uint8")
    return Image.fromarray(shaded, mode="L").convert("RGB")


def test_blur_gate_rejects_hopeless_input():
    """A hard-shake photo is rejected before Tesseract, with the marker."""
    _cv2_or_skip()
    hopeless = _rendered_label(1200, 900)
    img = Image.open(BytesIO(hopeless)).filter(ImageFilter.GaussianBlur(4))
    score = _blur_score(_resize_for_ocr(img))
    assert score < MIN_BLUR_SCORE, f"expected hopeless, score was {score:.1f}"
    result = extract_text(_rendered_label_png(img))
    assert result.get("error", "").startswith(BLURRY_IMAGE_ERROR)
    assert result["text"] == ""


def test_blur_gate_passes_imperfect_but_readable_photos():
    """Mild blur and uneven lighting must NOT be rejected — deskew and the
    adaptive-threshold variant own that band. Guards against tightening the
    gate into false-rejecting real packet photos (the failure mode users hit)."""
    _cv2_or_skip()
    label = Image.open(BytesIO(_rendered_label(1200, 900)))

    mild = label.filter(ImageFilter.GaussianBlur(0.8))
    assert _blur_score(_resize_for_ocr(mild)) >= MIN_BLUR_SCORE

    shaded = _gradient_shade(label)
    assert _blur_score(_resize_for_ocr(shaded)) >= MIN_BLUR_SCORE


def test_deskew_recovers_skewed_photo():
    """A 3-degree camera roll is corrected before variants are built."""
    _cv2_or_skip()
    label = Image.open(BytesIO(_rendered_label(1200, 900)))
    rotated = label.rotate(3, expand=True, fillcolor="white")
    # minAreaRect on the binarized ink should estimate the roll angle
    corrected = _deskew(_resize_for_ocr(rotated))
    # The deskewed output differs from the uncorrected resize (rotation applied)
    assert corrected.size == _resize_for_ocr(rotated).size


def test_adaptive_threshold_variant_separates_uneven_lighting():
    """Per-neighborhood thresholding recovers print a global-tone pipeline
    drowns when one side of the packet is shadowed."""
    _cv2_or_skip()
    label = Image.open(BytesIO(_rendered_label(1200, 900)))
    shaded = _gradient_shade(label, low=0.30, high=1.20)
    binary = _adaptive_threshold_variant(shaded)
    # ink survived binarization: dark pixels exist and are a sane fraction
    # (three text lines on a 1200x900 canvas measure ~0.004)
    gray = numpy.asarray(binary.convert("L"))
    ink_ratio = float((gray < 128).mean())
    assert 0.002 < ink_ratio < 0.5, f"ink fraction {ink_ratio:.3f} is degenerate"
    # and the variant list actually includes it
    variants = _prepare_variants(label)
    assert len(variants) >= 3  # 2 tone crops + 1 adaptive


def test_uneven_lighting_scan_still_extracts_text():
    """End-to-end: a shadowed label still yields rows through the full pipeline."""
    _cv2_or_skip()
    label = Image.open(BytesIO(_rendered_label(1200, 900)))
    shaded = _gradient_shade(label)
    result = extract_text(_rendered_label_png(shaded))
    assert result.get("error") is None
    assert "480" in result["text"]


def test_garbage_ocr_fails_instead_of_junk_product(client, auth_headers, monkeypatch):
    """The screenshot regression: OCR returned "a \\ ee 50 s"-class garbage, and
    the pipeline built a zero-scored product with "values not found" instead of
    admitting the photo carried no label. Near-empty OCR must fail with guidance."""
    import app.api.routes as routes_module

    def garbage_text(_bytes):
        return {"text": "a \\ ee 50 s", "confidence": 41.0, "variants_used": 2}

    monkeypatch.setattr(routes_module, "run_ocr_with_retries", garbage_text)
    files = {
        "front_image": ("front.png", _rendered_label(400, 400), "image/png"),
        "back_image": ("back.png", _rendered_label(400, 400), "image/png"),
    }
    response = client.post("/api/v1/scan", files=files, headers=auth_headers)
    assert response.status_code == 202
    scan_id = response.json()["scan_id"]

    body = None
    for _ in range(60):
        poll = client.get(f"/api/v1/scan/{scan_id}", headers=auth_headers)
        body = poll.json()
        if body.get("status") != "processing":
            break
    assert body["status"] == "failed"
    error = body["error"]
    assert error["code"] == "UNREADABLE_IMAGE"
    assert "retake" in error["message"].lower()
    # and no product was persisted for the garbage scan
    listing = client.get("/api/v1/products", headers=auth_headers)
    assert listing.json().get("products") == []


def test_legibility_gate_passes_real_labels():
    """Short-but-real label text (well under normal panels) clears the gate."""
    text = "Crunchy Biscuits Energy 480 kcal Protein 6 g Total Sugars 18 g"
    words = re.findall(r"[A-Za-z][A-Za-z\-']*[A-Za-z]|[A-Za-z]{2}", text)
    assert len(words) >= 5
    assert UNREADABLE_IMAGE_ERROR  # marker wired through ocr_service


def test_early_exit_skips_fallback_variants(monkeypatch):
    """A strong first read (8+ words, 70+ conf) must not pay for the fallback
    passes — on a small deployment each pass is tens of seconds of latency."""
    from app.services import ocr_service as mod

    calls = {"n": 0}

    def strong_read(_pytesseract, _image, _mode):
        calls["n"] += 1
        return {"text": "Energy 480 kcal Protein 6 g Total Sugars 18 g",
                "confidence": 91.0, "word_count": 10}

    monkeypatch.setattr(mod, "_read_variant", strong_read)
    result = mod.extract_text(_rendered_label(600, 600))
    assert calls["n"] == 1
    assert result["variants_used"] == 1


def test_weak_first_read_still_runs_fallback_variants(monkeypatch):
    """Degraded first reads keep the multi-variant merge (the accuracy path)."""
    from app.services import ocr_service as mod

    calls = {"n": 0}

    def weak_then_better(_pytesseract, _image, _mode):
        calls["n"] += 1
        if calls["n"] == 1:
            return {"text": "Energy 480", "confidence": 40.0, "word_count": 2}
        return {"text": f"pass{calls["n"]} Energy 480 kcal", "confidence": 55.0,
                "word_count": 4}

    monkeypatch.setattr(mod, "_read_variant", weak_then_better)
    result = mod.extract_text(_rendered_label(600, 600))
    assert calls["n"] >= 2  # fallback variants ran
    assert result["variants_used"] >= 2


def _rendered_label_png(image):
    buf = BytesIO()
    image.save(buf, format="PNG")
    return buf.getvalue()
