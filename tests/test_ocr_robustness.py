"""OCR robustness tests: pixel budget, retry behavior, honest failure markers.

Background: on small deployments (single low-CPU worker) the previous
preprocessing (1.5MP budget, then 2x enlargement) pushed Tesseract past its
per-pass timeout, so real-world scans failed with "Tesseract process timeout"
while the UI blamed photo quality. These tests pin the corrected behavior.
"""

import time
from io import BytesIO

import pytest
from fastapi.testclient import TestClient
from PIL import Image, ImageDraw, ImageFont

from app.main import app
from app.services.ocr_service import (
    MAX_OCR_SOURCE_PIXELS,
    _prepare_variants,
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
