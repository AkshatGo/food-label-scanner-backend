"""Personalization rule engine tests — doc 05 §5.

For each of the 4 conditions: one clear AVOID, one CAUTION, one GOOD_FIT,
asserting the specific rule that fired (not a generic message).
"""

import pytest

from app.services.personalization import (
    DISCLAIMER,
    SUPPORTED_CONDITIONS,
    personalize,
)


def _product(overrides=None, ingredients=None, category="I"):
    base = {
        "product_id": "p_test",
        "category": category,
        "nutrition_per_100g": {
            "energy_kcal": 400, "protein_g": 6, "carbohydrate_g": 50,
            "total_sugar_g": 2, "total_fat_g": 10, "saturated_fat_g": 2,
            "sodium_mg": 100, "dietary_fiber_g": 5,
        },
        "ingredients": ingredients or [{"name": "Wheat flour", "position": 1}],
    }
    if overrides:
        base["nutrition_per_100g"].update(overrides)
    return base


# --- Sugar ---------------------------------------------------------------------

def test_sugar_avoid():
    product = _product({"total_sugar_g": 25})
    result = personalize(product, ["sugar"])
    verdict = result["verdicts"][0]
    assert verdict["verdict"] == "AVOID"
    assert "exceeds" in verdict["reasons"][0]


def test_sugar_caution_added_sugar_in_first_3():
    product = _product(ingredients=[
        {"name": "Sugar", "position": 1}, {"name": "Wheat flour", "position": 2},
    ])
    result = personalize(product, ["sugar"])
    assert result["verdicts"][0]["verdict"] == "CAUTION"
    assert "first" in result["verdicts"][0]["reasons"][0]


def test_sugar_good_fit():
    result = personalize(_product(), ["sugar"])
    assert result["verdicts"][0]["verdict"] == "GOOD_FIT"


def test_sugar_liquid_threshold():
    product = _product({"total_sugar_g": 7}, category="II")
    result = personalize(product, ["sugar"])
    assert result["verdicts"][0]["verdict"] == "AVOID"


# --- Diabetes ------------------------------------------------------------------

def test_diabetes_avoid_high_sugar():
    product = _product({"total_sugar_g": 25})
    result = personalize(product, ["diabetes"])
    assert result["verdicts"][0]["verdict"] == "AVOID"
    assert any("sugar" in reason.lower() for reason in result["verdicts"][0]["reasons"])


def test_diabetes_avoid_sodium_comorbidity():
    product = _product({"sodium_mg": 600})
    result = personalize(product, ["diabetes"])
    assert result["verdicts"][0]["verdict"] == "AVOID"
    assert any("Sodium" in reason for reason in result["verdicts"][0]["reasons"])


def test_diabetes_avoid_high_glycemic_first3():
    product = _product(ingredients=[
        {"name": "Maltodextrin", "position": 1},
        {"name": "Wheat flour", "position": 2},
    ])
    result = personalize(product, ["diabetes"])
    assert result["verdicts"][0]["verdict"] == "AVOID"


def test_diabetes_caution_carbs_low_fibre():
    product = _product({"carbohydrate_g": 70, "dietary_fiber_g": 1})
    result = personalize(product, ["diabetes"])
    assert result["verdicts"][0]["verdict"] == "CAUTION"
    assert any("fibre" in reason.lower() for reason in result["verdicts"][0]["reasons"])


def test_diabetes_good_fit():
    result = personalize(_product(), ["diabetes"])
    assert result["verdicts"][0]["verdict"] == "GOOD_FIT"


# --- Migraine ------------------------------------------------------------------

def test_migraine_avoid_msg():
    product = _product(ingredients=[
        {"name": "Monosodium glutamate (MSG)", "position": 2},
    ])
    result = personalize(product, ["migraine"])
    assert result["verdicts"][0]["verdict"] == "AVOID"
    assert any("MSG" in reason for reason in result["verdicts"][0]["reasons"])


def test_migraine_avoid_aspartame_ins():
    product = _product(ingredients=[{"name": "Aspartame (INS 951)", "position": 3}])
    result = personalize(product, ["migraine"])
    assert result["verdicts"][0]["verdict"] == "AVOID"


def test_migraine_caution_caffeine():
    product = _product(ingredients=[{"name": "Caffeine", "position": 4}])
    result = personalize(product, ["migraine"])
    assert result["verdicts"][0]["verdict"] == "CAUTION"


def test_migraine_good_fit():
    result = personalize(_product(), ["migraine"])
    assert result["verdicts"][0]["verdict"] == "GOOD_FIT"
    assert "No known migraine-trigger" in result["verdicts"][0]["reasons"][0]


# --- Fever ---------------------------------------------------------------------

def test_fever_avoid_sodium():
    product = _product({"sodium_mg": 800})
    result = personalize(product, ["fever"])
    assert result["verdicts"][0]["verdict"] == "AVOID"


def test_fever_avoid_satfat():
    product = _product({"saturated_fat_g": 8})
    result = personalize(product, ["fever"])
    assert result["verdicts"][0]["verdict"] == "AVOID"


def test_fever_avoid_chilli_first3():
    product = _product(ingredients=[
        {"name": "Chilli powder", "position": 2}, {"name": "Wheat flour", "position": 1},
    ])
    result = personalize(product, ["fever"])
    assert result["verdicts"][0]["verdict"] == "AVOID"


def test_fever_caution_highly_processed():
    product = _product(ingredients=[
        {"name": f"Additive INS {200 + i}", "position": i + 1} for i in range(6)
    ])
    # resolve via ins numbers
    product["ingredients"] = [
        {"name": "Sodium benzoate", "ins_number": "211", "resolved_from_ins": True, "position": 1},
        {"name": "Sorbic acid", "ins_number": "200", "resolved_from_ins": True, "position": 2},
        {"name": "Citric acid", "ins_number": "330", "resolved_from_ins": True, "position": 3},
        {"name": "Xanthan gum", "ins_number": "415", "resolved_from_ins": True, "position": 4},
        {"name": "Lecithin", "ins_number": "322", "resolved_from_ins": True, "position": 5},
        {"name": "Calcium carbonate", "ins_number": "170", "resolved_from_ins": True, "position": 6},
    ]
    result = personalize(product, ["fever"])
    assert result["verdicts"][0]["verdict"] == "CAUTION"
    assert any("additive" in reason.lower() for reason in result["verdicts"][0]["reasons"])


def test_fever_good_fit():
    result = personalize(_product(), ["fever"])
    assert result["verdicts"][0]["verdict"] == "GOOD_FIT"


# --- Engine-level contracts ------------------------------------------------------

def test_disclaimer_always_present():
    result = personalize(_product(), ["diabetes", "migraine"])
    assert result["disclaimer"] == DISCLAIMER
    assert "not a medical device" in result["disclaimer"]


def test_no_conditions_no_verdicts():
    result = personalize(_product(), [])
    assert result["verdicts"] == []
    assert "No conditions selected" in result["note"]


def test_multiple_conditions_stay_distinct():
    product = _product({"total_sugar_g": 30})
    result = personalize(product, ["diabetes", "migraine"])
    conditions = [v["condition"] for v in result["verdicts"]]
    assert conditions == ["diabetes", "migraine"]
    verdicts = {v["condition"]: v["verdict"] for v in result["verdicts"]}
    assert verdicts["diabetes"] == "AVOID"
    assert verdicts["migraine"] == "GOOD_FIT"


def test_invalid_condition_raises():
    with pytest.raises(ValueError):
        personalize(_product(), ["common cold"])


def test_supported_conditions_fixed():
    assert SUPPORTED_CONDITIONS == ("sugar", "diabetes", "migraine", "fever")


def test_unread_values_yield_could_not_verify_never_good_fit():
    """\"Value not read\" is not evidence of compliance: with nothing readable,
    every rule must return COULD_NOT_VERIFY instead of GOOD_FIT."""
    empty = {"product_id": "p", "category": "I",
             "nutrition_per_100g": {}, "ingredients": []}
    result = personalize(empty, list(SUPPORTED_CONDITIONS))
    assert {v["verdict"] for v in result["verdicts"]} == {"COULD_NOT_VERIFY"}


def test_hard_triggers_still_fire_from_partial_reads():
    """A review-flagged scan with a partial panel still AVOIDs when the read
    values/ingredients cross a hard threshold — personalization is shown on
    review scans instead of being blanket-withheld."""
    product = {"product_id": "p", "category": "I",
               "nutrition_per_100g": {"total_sugar_g": 90.0, "sodium_mg": 300.0,
                                      "carbohydrate_g": 90.0, "dietary_fiber_g": 0.0},
               "ingredients": [{"name": "Glucose"}, {"name": "Water"},
                               {"name": "Vitamin C"}]}
    result = personalize(product, ["diabetes", "fever"])
    verdicts = {v["condition"]: v for v in result["verdicts"]}
    assert verdicts["diabetes"]["verdict"] == "AVOID"
    assert verdicts["fever"]["verdict"] == "GOOD_FIT"  # sodium/satfat were read
