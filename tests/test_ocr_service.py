"""Mobile-photo regressions, including real Tesseract when installed."""

import shutil
from io import BytesIO
from pathlib import Path

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
        # A genuinely strong read of a NON-panel image (no nutrition heading,
        # no core fields) — a strong read like this exits the pass loop.
        return {"text": "Front of pack Brand X Net weight 100g", "confidence": 95,
                "word_count": 10}

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


# --- Real packaging regressions (white print on saturated background) -----------
# Real photos captured from a Dabur Glucoplus-C carton: the nutrition table is
# condensed white lettering on orange with a ruled grid. Full-frame OCR reads
# the heading and loses every row; table reflow must recover them.

REAL_BACK = Path(__file__).parent / "fixtures" / "glucoplus_back_real.png"
REAL_FRONT = Path(__file__).parent / "fixtures" / "glucoplus_front_real.png"

_EXPECTED_VALUES = {
    "energy_kcal": 365.0,
    "carbohydrate_g": 90.0,
    "total_sugar_g": 90.0,
    "protein_g": 0.0,
    "total_fat_g": 0.0,
    "sodium_mg": 300.0,
}


def _read_label(path):
    from app.services.ocr_service import extract_text as _extract

    raw = _extract(Path(path).read_bytes())
    cleaned = nlp_reconstruct(raw["text"])["human_readable_text"]
    return raw, extract_nutrition(cleaned)


@pytest.mark.skipif(not REAL_BACK.exists(), reason="real-photo fixture missing")
def test_real_colored_table_reads_all_core_values():
    if not shutil.which("tesseract"):
        pytest.skip("Tesseract is not installed")
    _raw, nutrition = _read_label(REAL_BACK)
    assert nutrition["basis"] == "per_100"
    for field, expected in _EXPECTED_VALUES.items():
        entry = nutrition["values"].get(field)
        assert entry is not None, f"{field} missing from {sorted(nutrition['values'])}"
        assert entry["value"] == expected, f"{field}: {entry['value']} != {expected}"


@pytest.mark.skipif(not REAL_FRONT.exists(), reason="real-photo fixture missing")
def test_real_front_photo_yields_usable_text():
    if not shutil.which("tesseract"):
        pytest.skip("Tesseract is not installed")
    raw, _nutrition = _read_label(REAL_FRONT)
    assert (raw["confidence"] or 0) > 40
    assert "glucoplus" in raw["text"].lower()


def test_table_reflow_detects_ruled_grid():
    """The mosaic canvas is produced for a synthetic ruled table."""
    import numpy as np

    from app.services.table_image import table_variants

    width, height = 900, 1200
    image = Image.new("RGB", (width, height), "#e05a2b")
    draw = ImageDraw.Draw(image)
    line = 14
    for row in range(9):
        y = 100 + row * 100
        draw.rectangle([140, y, 760, y + line], fill="white")
        for x in (140, 400, 760 - line):
            draw.rectangle([x, y, x + line, y + 100], fill="white")
    variants = list(table_variants(image, __import__("cv2")))
    assert variants, "ruled table not detected"
    mosaic = np.asarray(variants[0].convert("L"))
    # Canvas is assembled (bounded size) with both ink and paper present.
    # Empty synthetic cells binarize arbitrarily, so only bound the extremes:
    assert mosaic.shape[0] < 2000 and mosaic.shape[1] < 2600
    assert (mosaic < 100).mean() > 0.001
    assert (mosaic > 200).mean() > 0.001


def test_panel_gate_requires_core_fields_not_derivatives():
    """added_sugar must not complete the panel while a core row (sodium,
    energy) is missing — that premature exit is how rows got dropped."""
    six_core = ("Per 100g Energy 365 kcal Carbohydrate 90 g Total Sugars 90 g "
                "Protein 0 g Total Fat 0 g Sodium 300 mg")
    five_core_plus_added = ("Per 100g Energy 365 kcal Carbohydrate 90 g Total Sugars 90 g "
                            "Added Sugars 90 g Protein 0 g Total Fat 0 g")
    strong = {"text": six_core, "confidence": 80.0, "word_count": 24}
    assert ocr_service._has_readable_panel(strong) is True
    weak = {"text": five_core_plus_added, "confidence": 80.0, "word_count": 24}
    assert ocr_service._has_readable_panel(weak) is False


def test_gradient_shaded_panel_keeps_rescue_variants(monkeypatch):
    """A strong read that lost bottom rows to shading (heading present, core
    incomplete) must not early-exit — the adaptive/flat-field variants exist
    to recover exactly those rows (dark-premium-pack sweep regression)."""
    from app.services import ocr_service as mod

    calls = {"n": 0}

    def shaded_read(_pytesseract, _image, _mode, **kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            return {"text": "Nutritional Information per 100g Energy 480 kcal "
                            "Protein 6 g Total Carbohydrate 62 g Total Sugars 18 g",
                    "confidence": 92.8, "word_count": 18}
        return {"text": "Nutritional Information per 100g Energy 480 kcal Protein 6 g "
                        "Total Carbohydrate 62 g Total Sugars 18 g Total Fat 20 g "
                        "Sodium 420 mg",
                "confidence": 91.4, "word_count": 30}

    monkeypatch.setattr(mod, "_read_variant", shaded_read)
    # Real-print stand-in (the blur gate rejects blank canvases outright).
    image = Image.new("RGB", (600, 800), "white")
    ImageDraw.Draw(image).text((30, 30), "Nutritional Information per 100g",
                               fill="black")
    result = mod.extract_text(_bytes(image))
    assert calls["n"] >= 2, "rescue variants never ran"
    assert "Sodium" in result["text"] and "Total Fat" in result["text"]


def test_merge_prefers_complete_panel_over_higher_confidence(monkeypatch):
    """Raw confidence must not elect a truncated panel: core rows dominate."""
    truncated = {"text": "Energy 480 kcal Protein 6 g Total Carbohydrate 62 g "
                         "Total Sugars 18 g",
                 "confidence": 92.67, "word_count": 18}
    complete = {"text": "Nutritional Information per 100g Energy 480 kcal Protein 6 g "
                        "Total Carbohydrate 62 g Total Sugars 18 g Total Fat 20 g "
                        "Sodium 420 mg",
                "confidence": 91.40, "word_count": 30}
    result = ocr_service._merge_candidates([truncated, complete])
    assert "Sodium 420 mg" in result["text"]


# --- WhatsApp-compressed JPEG fixtures (degraded real photos) --------------------
# Same Dabur Glucoplus-C carton, re-photographed and passed through WhatsApp
# compression: genuinely different captures, not re-encodes of the PNGs.

_TRUTH = {
    "energy_kcal": 365.0, "carbohydrate_g": 90.0, "total_sugar_g": 90.0,
    "protein_g": 0.0, "total_fat_g": 0.0, "sodium_mg": 300.0,
}


def _fixture(name):
    return Path(__file__).parent / "fixtures" / name


def test_whatsapp_back_photo_reads_all_core_values():
    if not shutil.which("tesseract"):
        pytest.skip("Tesseract is not installed")
    _raw, nutrition = _read_label(_fixture("glucoplus_back_whatsapp.jpeg"))
    for field, expected in _TRUTH.items():
        entry = nutrition["values"].get(field)
        assert entry is not None, f"{field} missing"
        assert entry["value"] == expected, f"{field}: {entry['value']} != {expected}"


def test_whatsapp_degraded_digits_never_score_silently():
    """The harsher capture misreads digits confidently (365->385, 90->80).
    Whatever the pipeline does with it, it must NOT present unflagged values:
    either the invariant check fires or review is demanded."""
    if not shutil.which("tesseract"):
        pytest.skip("Tesseract is not installed")
    _raw, nutrition = _read_label(_fixture("glucoplus_back_whatsapp_alt.jpeg"))
    assert nutrition["needs_review"] is True, (
        "confidently-corrupted digits reached the score unflagged"
    )


def test_front_photo_extracts_product_identity():
    if not shutil.which("tesseract"):
        pytest.skip("Tesseract is not installed")
    raw, _nutrition = _read_label(_fixture("glucoplus_front_whatsapp.jpeg"))
    assert "glucoplus" in raw["text"].lower()


def test_white_on_color_without_grid_is_rescued():
    """White print on saturated orange with NO ruled grid: table reflow
    cannot detect it (no lines), and grayscale tone passes lose the print.
    The min-channel variant must recover the rows (real-phone failure class)."""
    import pytesseract

    from app.services.ocr_service import _min_channel_variant

    image = Image.new("RGB", (1000, 700), "#c2480f")
    draw = ImageDraw.Draw(image)
    font = ImageFont.truetype("/usr/share/fonts/TTF/DejaVuSans.ttf", 30)
    lines = ("Nutritional Information per 100g", "Energy 457 kcal",
             "Protein 8 g", "Total Sugars 22 g", "Total Fat 18 g",
             "Sodium 310 mg")
    for index, line in enumerate(lines):
        draw.text((50, 40 + index * 90), line, font=font, fill="white")
    variant = _min_channel_variant(image)
    text = pytesseract.image_to_string(variant, config="--psm 6")
    found = sum(1 for probe in ("457", "Protein", "22", "18", "310") if probe in text)
    assert found >= 4, f"min-channel rescue too weak: {found}/5 probes in {text!r}"


def test_min_channel_variant_added_to_rescue_passes():
    from app.services import ocr_service as mod

    source = Path(mod.__file__).read_text()
    # Wired into the variant list (def call site plus _prepare_variants).
    assert source.count("_min_channel_variant(image)") >= 1
    assert "variants.append(_min_channel_variant(image))" in source
