"""Regression tests for the real-world Lay's scan failure cluster.

A real upload (294x727 web-saved image) produced: no ingredients, an OCR
ambiguity flag on "Total Carbohydrate 159 5%" (true value 15g, the printed
unit lost to JPEG degradation), and an unparsed "'Sugars less than 1g" row —
together withholding the star rating. These tests pin each layer of the fix.
"""

from app.services.nlp_cleanup import nlp_reconstruct
from app.services.nutrition_extractor import extract_nutrition
from app.services.ocr_service import (
    MAX_OCR_SOURCE_PIXELS,
    _prepare_variants,
    _resize_for_ocr,
)
from app.services.scan_pipeline import build_structured_product

from PIL import Image

# --- OCR sizing: small sources are upscaled toward the budget --------------------


def test_small_image_is_upscaled_to_budget():
    image = Image.new("RGB", (294, 727), "white")
    resized = _resize_for_ocr(image)
    pixels = resized.width * resized.height
    assert pixels * 1.05 >= MAX_OCR_SOURCE_PIXELS  # reached the budget
    assert resized.width > image.width  # and grew, not shrank


def test_huge_image_is_still_downscaled_to_budget():
    image = Image.new("RGB", (4000, 3000), "white")
    resized = _resize_for_ocr(image)
    assert resized.width * resized.height <= MAX_OCR_SOURCE_PIXELS * 1.05


def test_extreme_thumbnail_is_capped():
    image = Image.new("RGB", (50, 50), "white")
    resized = _resize_for_ocr(image)
    assert resized.width <= 50 * 4  # linear cap holds


def test_variants_stay_within_budget():
    image = Image.new("RGB", (294, 727), "white")
    for variant in _prepare_variants(image):
        assert variant.width * variant.height <= MAX_OCR_SOURCE_PIXELS * 1.05


# --- Row regex: OCR junk prefixes must not kill real rows -----------------------


def test_stray_quote_prefix_still_parses_sugars_row():
    extracted = extract_nutrition("'\u00adsugars less than 1g")
    assert extracted["values"]["total_sugar_g"]["value"] == 1.0


def test_normal_rows_unaffected_by_junk_prefix_rule():
    extracted = extract_nutrition("Energy 480 kcal\nProtein 9 g")
    assert extracted["values"]["energy_kcal"]["value"] == 480.0
    assert "energy_kcal" not in extracted["ocr_ambiguous_fields"]


# --- Unit-bearing readings win across OCR variants ------------------------------


def test_unit_bearing_reading_beats_earlier_unitless_one():
    text = "Sugars less than 19\nSugars less than 1g"
    extracted = extract_nutrition(text)
    assert extracted["values"]["total_sugar_g"]["value"] == 1.0
    assert "total_sugar_g" not in extracted["ocr_ambiguous_fields"]


# --- % Daily Value corroboration / repair ---------------------------------------


def test_dv_column_corroborates_unitless_value():
    # 18g of total fat = 28% of the 65g FDA reference: consistent, not corrupt.
    extracted = extract_nutrition("Total Fat 18g 28%")
    assert "total_fat_g" not in extracted["ocr_ambiguous_fields"]
    assert extracted["values"]["total_fat_g"]["value"] == 18.0


def test_dv_column_repairs_g_to_9_substitution():
    # "15g" read as "159"; 159g would be 53% DV, the panel says 5%.
    extracted = extract_nutrition("Total Carbohydrate 159 5%")
    assert extracted["values"]["carbohydrate_g"]["value"] == 15.0
    assert "carbohydrate_g" not in extracted["ocr_ambiguous_fields"]
    assert "carbohydrate_g" in extracted["dv_resolved_fields"]
    # Basis stays "unknown" on a one-line panel (honest), so review remains on;
    # the ambiguity flag itself is what the %DV repair clears.
    assert extracted["needs_review"] is True  # basis unknown, values present


def test_g_to_9_repair_requires_strip_hypothesis_to_agree_with_dv():
    # "459" at 10% DV: stripping the trailing 9 gives 45g, but the panel's own
    # math implies 6.5g — the two disagree, so the contradiction may sit in the
    # percentage. Must stay flagged, never silently rewritten.
    extracted = extract_nutrition("Total Fat 459 10%")
    assert "total_fat_g" in extracted["ocr_ambiguous_fields"]
    assert extracted["needs_review"]


def test_unitless_value_without_pct_stays_ambiguous():
    extracted = extract_nutrition("Sodium 249")
    assert "sodium_mg" in extracted["ocr_ambiguous_fields"]
    assert extracted["needs_review"]


# --- US Serving Size basis -------------------------------------------------------


def test_us_serving_size_line_is_detected_as_per_serving():
    extracted = extract_nutrition(
        "Serving Size 1 oz (28g/About 15 chips)\nCalories 160"
    )
    assert extracted["basis"] == "per_serving"
    assert extracted["serving_size"] == 28.0
    assert extracted["normalized_to_per_100"] is True


# --- End-to-end on a reconstruction of the real OCR text ------------------------


LAYLS_BACK_TEXT = """lays'
Classic
Nutrition Facts
Serving Size 1 oz (28g/About 15 chips)
Calories 160
Calories from Fat 90
'% Daily Value*
Total Fat 10g 16%
Saturated Fat 1.5g 8%
Trans Fat 0g
Cholesterol 0 mg 0%
Sodium 170mg 7%
Potassium 350mg 10%
Total Carbohydrate 159 5%
Dietary Fiber 1g 5%
'Sugars less than 1g
Protein 2g
Vitamin A 0% s Vitamin C 10%
Calcium 0% ° Iron 2%
* Percent Daily Values are based on a 2,000 calorie
diet. Your daily values may be higher or lower
Fat 9 * Carbohydrate 4 * Protein 4
"""


def test_real_lays_text_yields_rating_without_review():
    cleaned = nlp_reconstruct(LAYLS_BACK_TEXT)["human_readable_text"]
    product = build_structured_product(cleaned, 82.0)
    ext = product["nutrition_extraction"]
    assert ext["needs_review"] is False
    assert product["nutrition_per_100g"]["carbohydrate_g"] == 53.57
    assert product["nutrition_per_100g"]["total_sugar_g"] == 3.57
    assert product["inr"]["status"] == "calculated"
    assert product["inr"]["rating_stars"] > 0


def test_ingredient_header_misspelling_is_reconstructed():
    for misspelled in ("Lngredients: Potato, Salt", "Ingredierits: Potato, Salt"):
        cleaned = nlp_reconstruct(misspelled)["human_readable_text"]
        assert "Ingredients" in cleaned
        product = build_structured_product(cleaned)
        names = [i if isinstance(i, str) else i["name"] for i in product["ingredients"]]
        assert any("potato" in str(n).lower() for n in names), misspelled
