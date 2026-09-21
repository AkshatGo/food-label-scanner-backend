"""Nutrition extraction tests — doc 05 §3 (per-100g normalization is the #1
flagged pitfall and is tested explicitly)."""

from app.services.nutrition_extractor import extract_nutrition, to_inr_input
from app.services.scan_pipeline import run_scan_pipeline
import pytest


@pytest.mark.parametrize("row,expected", [("Protein (g) 6,5", 6.5), ("Protein g 6.5", 6.5), ("Protein 6500 mg", 6.5)])
def test_mobile_table_units_and_decimal_marks(row, expected):
    result = extract_nutrition("Per 100g\n" + row)
    assert result["values"]["protein_g"]["value"] == expected


@pytest.mark.parametrize("row", ["Protein < 1 g", "Protein 1,000 g", "Protein 10%", "Protein 20 kcal"])
def test_uncertain_numeric_readings_require_review(row):
    assert extract_nutrition("Per 100g\n" + row)["needs_review"] is True


def test_mixed_serving_columns_require_review():
    result = extract_nutrition("Per serving (30g) | Per 100g\nProtein 1.8 g 6 g")
    assert result["needs_review"] is True


def test_micrograms_are_converted_to_milligrams():
    result = extract_nutrition("Per 100g\nSodium 1000 mcg")
    assert result["values"]["sodium_mg"] == {"value": 1, "unit": "mg"}


def test_per100_values_extracted_directly():
    text = (
        "Nutritional Information\n"
        "Per 100g:\n"
        "Energy 480 kcal\n"
        "Protein 6 g\n"
        "Total Sugar 18 g\n"
        "Saturated Fat 6 g\n"
        "Sodium 420 mg\n"
        "Dietary Fibre 2 g\n"
    )
    result = extract_nutrition(text)
    assert result["basis"] == "per_100"
    assert result["values"]["energy_kcal"]["value"] == 480
    assert result["values"]["sodium_mg"]["value"] == 420
    assert result["values"]["total_sugar_g"]["value"] == 18
    assert result["needs_review"] is False


def test_per_serving_normalized_to_per_100g():
    """A 'per 30g serving' panel must be multiplied to per-100g before scoring."""
    text = (
        "Nutritional Information per serving (30g)\n"
        "Energy 144 kcal\n"
        "Protein 1.8 g\n"
        "Total Sugar 5.4 g\n"
        "Sodium 126 mg\n"
    )
    result = extract_nutrition(text)
    assert result["basis"] == "per_serving"
    assert result["serving_size"] == 30
    assert result["normalized_to_per_100"] is True
    values = result["values"]
    assert values["energy_kcal"]["value"] == 480  # 144 * 100/30
    assert values["protein_g"]["value"] == 6
    assert values["total_sugar_g"]["value"] == 18
    assert values["sodium_mg"]["value"] == 420


def test_unknown_basis_flags_needs_review():
    text = "Energy 100 kcal\nProtein 2 g"
    result = extract_nutrition(text)
    assert result["basis"] == "unknown"
    assert result["needs_review"] is True


def test_kj_converted_to_kcal():
    text = "Per 100g\nEnergy 837 kJ\nProtein 5 g"
    result = extract_nutrition(text)
    assert abs(result["values"]["energy_kcal"]["value"] - 200) < 1
    assert result["values"]["energy_kcal"]["unit"] == "kcal"


def test_mg_to_g_conversion_for_gram_fields():
    text = "Per 100g\nSodium 900 mg\nProtein 5 g"
    result = extract_nutrition(text)
    # sodium stays mg
    assert result["values"]["sodium_mg"]["value"] == 900
    assert result["values"]["sodium_mg"]["unit"] == "mg"


def test_to_inr_input_mapping():
    text = (
        "Per 100g\nEnergy 480 kcal\nProtein 6 g\nTotal Carbohydrate 60 g\n"
        "Total Sugar 18 g\nAdded Sugar 15 g\nTotal Fat 20 g\nSaturated Fat 6 g\n"
        "Sodium 420 mg\nDietary Fibre 2 g\n"
    )
    result = extract_nutrition(text)
    inr_input = to_inr_input(result)
    assert inr_input["energy_kcal"] == 480
    assert inr_input["total_sugars_g"] == 18
    assert inr_input["added_sugar_g"] == 15
    assert inr_input["sodium_mg"] == 420
    assert inr_input["dietary_fiber_g"] == 2


def test_added_sugar_not_confused_with_total_sugar():
    text = "Per 100g\nTotal Sugars 12 g\nAdded Sugars 8 g"
    result = extract_nutrition(text)
    assert result["values"]["total_sugar_g"]["value"] == 12
    assert result["values"]["added_sugar_g"]["value"] == 8


# --- OCR-ambiguous trailing digit (former g->9 silent rewrite) ---------------

def test_trailing_nine_without_unit_is_not_rewritten():
    """"Energy 549" without a unit is a valid number: it must be kept intact.

    The old code stripped the trailing 9 here, silently scoring 54 kcal.
    """
    text = "Nutritional Information per 100g\nEnergy 549\nProtein 6 g"
    result = extract_nutrition(text)
    assert result["values"]["energy_kcal"]["value"] == 549


def test_ambiguous_digit_flags_needs_review():
    """A unit-less trailing 9 is flagged for review, never silently scored."""
    text = "Nutritional Information per 100g\nEnergy 549\nProtein 6 g"
    result = extract_nutrition(text)
    assert result["needs_review"] is True
    assert result["ocr_ambiguous_fields"] == ["energy_kcal"]
    assert "OCR" in result["note"] or "OCR" in result["note"].upper()


def test_trailing_nine_with_unit_is_unambiguous():
    """"Protein 9 g" carries its unit; no review flag may fire."""
    text = "Per 100g\nProtein 9 g\nEnergy 100 kcal"
    result = extract_nutrition(text)
    assert result["values"]["protein_g"]["value"] == 9
    assert result["ocr_ambiguous_fields"] == []
    assert result["needs_review"] is False


def test_pipeline_review_reason_for_ambiguous_digit():
    """The pipeline surfaces the ambiguous field and flags the extraction."""
    text = "Test Biscuits\nNutritional Information per 100g\nEnergy 549\nProtein 6 g\nTotal Sugars 2 g\nSodium 50 mg"
    product, _compliance = run_scan_pipeline(text, ocr_confidence=90.0)
    assert product["nutrition_extraction"]["ocr_ambiguous_fields"] == ["energy_kcal"]
    assert product["nutrition_extraction"]["needs_review"] is True


def test_implausible_magnitudes_flag_review():
    """OCR digit-inflation (0->000) must never silently reach the scorer."""
    result = extract_nutrition("Per 100g\nEnergy 480000 kcal\nSodium 999999 mg\nProtein 6 g")
    assert "energy_kcal" in result["implausible_fields"]
    assert "sodium_mg" in result["implausible_fields"]
    assert result["needs_review"] is True


def test_extreme_but_real_foods_pass_plausibility_bounds():
    """Pure oil (900 kcal) and salt-heavy sauces (sodium >5000) are real."""
    oil = extract_nutrition("Per 100g\nEnergy 900 kcal\nTotal Fat 100 g")
    assert oil["implausible_fields"] == []
    sauce = extract_nutrition("Per 100g\nSodium 6000 mg")
    assert sauce["implausible_fields"] == []
