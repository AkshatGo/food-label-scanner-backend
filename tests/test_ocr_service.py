"""Mobile-photo regressions, including real Tesseract when installed."""

from io import BytesIO
import shutil

import pytest
from PIL import Image, ImageDraw, ImageFont

from app.services import ocr_service
from app.services.nlp_cleanup import nlp_reconstruct
from app.services.nutrition_extractor import extract_nutrition


def _bytes(image, exif=None):
    stream = BytesIO()
    image.save(stream, format="JPEG", **({"exif": exif} if exif else {}))
    return stream.getvalue()


def test_preserves_phone_fine_print_with_bounded_work():
    variants = list(ocr_service._prepare_variants(Image.new("RGB", (4000, 3000))))
    assert len(variants) >= 2
    assert all(im.width * im.height <= ocr_service.MAX_OCR_SOURCE_PIXELS for im in variants)
    assert variants[0].width * variants[0].height > ocr_service.MAX_OCR_SOURCE_PIXELS * 0.99


def test_conflicting_passes_are_not_concatenated():
    result = ocr_service._merge_candidates([
        {"text": "Per 100g\nProtein 6 g", "confidence": 95, "word_count": 5},
        {"text": "Per 100g\nProtein 60 g", "confidence": 40, "word_count": 5},
    ])
    assert result["text"] == "Per 100g\nProtein 6 g"
    assert result["confidence"] == 95


def test_timeout_retries_without_losing_successful_read(monkeypatch):
    monkeypatch.setattr(ocr_service, "cv2", None)
    calls = []

    def read(*args, **kwargs):
        calls.append(kwargs["timeout"])
        if len(calls) == 1:
            raise RuntimeError("Tesseract process timeout")
        return {"text": "Nutrition per 100g Protein 6 g Energy 400 kcal", "confidence": 95, "word_count": 10}

    monkeypatch.setattr(ocr_service, "_read_variant", read)
    result = ocr_service.extract_text(_bytes(Image.new("RGB", (100, 100))))
    assert result["confidence"] == 95
    assert len(calls) == 2
    assert all(0 < timeout <= ocr_service.OCR_PASS_TIMEOUT for timeout in calls)


@pytest.mark.parametrize("rotation,exif_orientation", [(0, None), (90, None), (90, 6)])
def test_real_ocr_reads_rotated_mobile_label(rotation, exif_orientation):
    if not shutil.which("tesseract"):
        pytest.skip("Tesseract is not installed")
    try:
        font = ImageFont.truetype("DejaVuSans.ttf", 32)
    except OSError:
        pytest.skip("DejaVuSans fixture font is not installed")
    image = Image.new("RGB", (1000, 750), "#dddddd")
    draw = ImageDraw.Draw(image)
    lines = ["TEST LABEL", "Nutritional Information per 100g", "Energy 480 kcal",
             "Protein 6 g", "Total Sugars 18 g", "Sodium 420 mg"]
    for index, line in enumerate(lines):
        draw.text((40, 50 + index * 80), line, font=font, fill="#333333")
    image = image.rotate(rotation, expand=True)
    exif = Image.Exif()
    if exif_orientation:
        exif[274] = exif_orientation
    result = ocr_service.extract_text(_bytes(image, exif))
    nutrition = extract_nutrition(nlp_reconstruct(result["text"])["human_readable_text"])
    assert nutrition["values"]["energy_kcal"]["value"] == 480
    assert nutrition["values"]["protein_g"]["value"] == 6
    assert nutrition["values"]["sodium_mg"]["value"] == 420


def test_all_timeouts_preserve_server_failure(monkeypatch):
    monkeypatch.setattr(ocr_service, "cv2", None)

    def timeout(*args, **kwargs):
        raise RuntimeError("Tesseract process timeout")

    monkeypatch.setattr(ocr_service, "_read_variant", timeout)
    result = ocr_service.run_ocr_with_retries(_bytes(Image.new("RGB", (100, 100))))
    assert "timeout" in result["error"]


def test_unit_separated_rows_are_reconstructed():
    text = "Per 100g Energy 480 kcal Protein 6 g Total Sugars 18 g Sodium 420 mg"
    cleaned = nlp_reconstruct(text)["human_readable_text"]
    assert extract_nutrition(cleaned)["values"]["protein_g"]["value"] == 6
