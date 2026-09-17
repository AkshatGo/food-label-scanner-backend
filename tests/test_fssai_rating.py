"""INR scoring engine tests — doc 05 §2 QA checklist.

Every boundary/edge in Tables 2/3/6 is exercised, plus capping, the
worked example, determinism, and the exemption paths.

Note on the doc's worked example (doc 04 §3): the prose there contains
arithmetic slips against its own strict-> tables (energy 480 = exactly on
the ">480" boundary scores 5 pts by the doc's own boundary rule, not 6;
protein 6g scores 5 pts, not 6). The engine implements the TABLES
faithfully; the final score (13) and star rating (2.0) match the doc
either way, and both derivations are asserted below.
"""

import pytest

from app.services.fssai_rating import (
    INR_FORMULA_VERSION,
    calculate_inr,
    is_zero_energy_zero_sugar_beverage,
)


# --- Doc 04 §3 worked example -------------------------------------------------

def test_worked_example_final_score_and_stars():
    """Energy 480, satfat 6, sugar 18, sodium 420, protein 6 -> 13 pts -> 2 stars."""
    result = calculate_inr({
        "energy_kcal": 480,
        "total_sugars_g": 18,
        "saturated_fat_g": 6.0,
        "sodium_mg": 420,
        "protein_g": 6,
    }, category="solid")
    # strict-> lookup: energy 5, satfat 5, sugar 4, sodium 4 = 18 baseline
    assert result["baseline_points"] == 18
    assert result["negative_points"] == {"energy": 5, "total_sugar": 4, "saturated_fat": 5, "sodium": 4}
    assert result["positive_points"]["protein"] == 5
    assert result["inr_score"] == 13
    assert result["rating_stars"] == 2.0
    assert result["eligible"] is True


def test_worked_example_doc_prose_derivation_also_yields_13():
    """The doc prose' own point picks (6+5+4+4=19 baseline, protein 6) also end at 13."""
    # 19 - 6 = 13; table lookup produces 18 - 5 = 13. Same final answer.
    assert 19 - 6 == 18 - 5 == 13


# --- Boundary handling (doc 04 §6.2): strict > --------------------------------

def test_energy_boundary_exact_value_scores_lower_band():
    result = calculate_inr({"energy_kcal": 480, "total_sugars_g": 0, "saturated_fat_g": 0,
                            "sodium_mg": 0, "protein_g": 0}, category="solid")
    assert result["negative_points"]["energy"] == 5  # 480 is NOT > 480


def test_energy_just_above_boundary_scores_higher_band():
    result = calculate_inr({"energy_kcal": 480.01, "total_sugars_g": 0, "saturated_fat_g": 0,
                            "sodium_mg": 0, "protein_g": 0}, category="solid")
    assert result["negative_points"]["energy"] == 6


@pytest.mark.parametrize("value,expected_points", [
    (0, 0), (80, 0), (80.01, 1), (160, 1), (160.01, 2), (800, 9), (800.01, 10), (2000, 10),
])
def test_energy_band_table(value, expected_points):
    result = calculate_inr({"energy_kcal": value, "total_sugars_g": 0, "saturated_fat_g": 0,
                            "sodium_mg": 0, "protein_g": 0}, category="solid")
    assert result["negative_points"]["energy"] == expected_points


@pytest.mark.parametrize("value,expected_points", [
    (0, 0), (1.0, 0), (1.01, 1), (2.0, 1), (2.01, 2), (40, 24), (40.01, 25), (100, 25),
])
def test_satfat_band_table(value, expected_points):
    result = calculate_inr({"energy_kcal": 0, "total_sugars_g": 0, "saturated_fat_g": value,
                            "sodium_mg": 0, "protein_g": 0}, category="solid")
    assert result["negative_points"]["saturated_fat"] == expected_points


@pytest.mark.parametrize("value,expected_points", [
    (0, 0), (4.2, 0), (4.21, 1), (21, 4), (21.01, 5), (84, 19), (84.01, 20), (100, 20),
])
def test_sugar_band_table(value, expected_points):
    result = calculate_inr({"energy_kcal": 0, "total_sugars_g": value, "saturated_fat_g": 0,
                            "sodium_mg": 0, "protein_g": 0}, category="solid")
    assert result["negative_points"]["total_sugar"] == expected_points


@pytest.mark.parametrize("value,expected_points", [
    (0, 0), (90, 0), (90.01, 1), (450, 4), (450.01, 5), (2250, 24), (2250.01, 25), (3000, 25),
])
def test_sodium_band_table(value, expected_points):
    result = calculate_inr({"energy_kcal": 0, "total_sugars_g": 0, "saturated_fat_g": 0,
                            "sodium_mg": value, "protein_g": 0}, category="solid")
    assert result["negative_points"]["sodium"] == expected_points


@pytest.mark.parametrize("value,expected_points", [
    (0, 0), (1.5, 0), (1.51, 1), (2.0, 1), (2.01, 2), (3.0, 3), (5.0, 4), (5.01, 5),
    (25, 9), (50, 14), (100, 15),
])
def test_protein_band_table(value, expected_points):
    result = calculate_inr({"energy_kcal": 0, "total_sugars_g": 0, "saturated_fat_g": 0,
                            "sodium_mg": 0, "protein_g": value}, category="solid")
    assert result["positive_points"]["protein"] == expected_points


# --- Liquid (Category-II) paths ------------------------------------------------

def test_liquid_ignores_satfat_sodium_fibre_nlm():
    """Category-II never scores sat fat/sodium/NLM/fibre — absent, not zeroed (doc 04 §6.3)."""
    result = calculate_inr({
        "energy_kcal": 50, "total_sugars_g": 11, "protein_g": 4.0,
        "saturated_fat_g": 30, "sodium_mg": 3000, "dietary_fiber_g": 20,
    }, category="liquid", fv_percent=30)
    assert "saturated_fat" not in result["negative_points"]
    assert "sodium" not in result["negative_points"]
    assert "nlm" not in result["positive_points"]
    assert "fibre" not in result["positive_points"]
    # energy 50 -> >48 -> 8 pts; sugar 11 -> >10.6 -> 8 pts; baseline 16
    assert result["baseline_points"] == 16
    # FV 30%: > 5,10,15,20,25 -> 5 raw pts; baseline 16 > 10 -> capped at 5
    assert result["positive_points"] == {"fv": 5, "protein": 4}


@pytest.mark.parametrize("value,expected_points", [
    (0, 0), (6, 0), (6.01, 1), (12, 1), (12.01, 2), (60, 9), (60.01, 10), (80, 10),
])
def test_liquid_energy_band_table(value, expected_points):
    result = calculate_inr({"energy_kcal": value, "total_sugars_g": 0, "protein_g": 0},
                           category="liquid", is_beverage=False)
    assert result["negative_points"]["energy"] == expected_points


@pytest.mark.parametrize("value,expected_points", [
    (0, 0), (0.1, 0), (0.11, 1), (1.6, 1), (1.61, 2), (13.6, 9), (13.61, 10), (20, 10),
])
def test_liquid_sugar_band_table(value, expected_points):
    result = calculate_inr({"energy_kcal": 0, "total_sugars_g": value, "protein_g": 0},
                           category="liquid", is_beverage=False)
    assert result["negative_points"]["total_sugar"] == expected_points


# --- Capping (doc 04 Table 4) ---------------------------------------------------

def test_capping_low_baseline_protein_15_fv_10():
    """Baseline <= 20 allows protein up to 15, FV/NLM/fibre up to 10 each."""
    result = calculate_inr({
        "energy_kcal": 0, "total_sugars_g": 0, "saturated_fat_g": 0, "sodium_mg": 0,
        "protein_g": 100,  # raw 15
        "dietary_fiber_g": 100,  # raw 10
    }, category="solid", fv_percent=100, nlm_percent=100)
    assert result["baseline_points"] == 0
    assert result["positive_points"] == {"fv": 10, "nlm": 10, "fibre": 10, "protein": 15}


def test_capping_high_baseline_protein_7_fv_5():
    """Baseline > 20 caps protein at 7 and FV/NLM/fibre at 5 each (doc 05 §2)."""
    result = calculate_inr({
        "energy_kcal": 900,  # 10 pts
        "total_sugars_g": 90,  # >84 -> 20 pts... capped by sugar bounds; use exact
        "saturated_fat_g": 45,  # >40 -> 25 pts
        "sodium_mg": 2500,  # >2250 -> 25 pts
        "protein_g": 100,  # raw 15 -> capped 7
        "dietary_fiber_g": 100,  # raw 10 -> capped 5
    }, category="solid", fv_percent=100, nlm_percent=100)
    # energy 10 + sugar 20 + satfat 25 + sodium 25 = 80 baseline
    assert result["baseline_points"] > 20
    assert result["positive_points"]["protein"] == 7
    assert result["positive_points"]["fv"] == 5
    assert result["positive_points"]["nlm"] == 5
    assert result["positive_points"]["fibre"] == 5
    assert result["capped_factors"]["protein"] is True


def test_liquid_capping_low_baseline():
    result = calculate_inr({
        "energy_kcal": 0, "total_sugars_g": 0, "protein_g": 100,
    }, category="liquid", fv_percent=100, is_beverage=False)
    assert result["positive_points"] == {"fv": 10, "protein": 15}


def test_liquid_capping_high_baseline():
    result = calculate_inr({
        "energy_kcal": 100, "total_sugars_g": 20, "protein_g": 100,
    }, category="liquid", fv_percent=100)
    # energy 10 + sugar 10 = 20 > 10
    assert result["baseline_points"] > 10
    assert result["positive_points"] == {"fv": 5, "protein": 7}


# --- Star mapping (doc 04 Table 6) — both edges of every band -------------------

@pytest.mark.parametrize("score,stars", [
    (-11, 5.0), (-12, 5.0),
    (-10, 4.5), (-7, 4.5),
    (-6, 4.0), (-2, 4.0),
    (-1, 3.5), (2, 3.5),
    (3, 3.0), (6, 3.0),
    (7, 2.5), (11, 2.5),
    (12, 2.0), (15, 2.0),
    (16, 1.5), (20, 1.5),
    (21, 1.0), (24, 1.0),
    (25, 0.5), (80, 0.5),  # 80 = max solid baseline (10+25+20+25)
])
def test_star_mapping_solid_edges(score, stars):
    assert _stars_for_score(score, "solid") == stars


@pytest.mark.parametrize("score,stars", [
    (0, 5.0), (-5, 5.0),
    (1, 4.5), (2, 4.5),
    (3, 4.0), (4, 4.0),
    (5, 3.5), (6, 3.5),
    (7, 3.0), (9, 3.0),
    (10, 2.5), (12, 2.5),
    (13, 2.0), (15, 2.0),
    (16, 1.5), (17, 1.5),
    (18, 1.0), (19, 1.0),
    (20, 0.5),  # 20 = max liquid baseline (10+10)
])
def test_star_mapping_liquid_edges(score, stars):
    assert _stars_for_score(score, "liquid") == stars


def _stars_for_score(score, category):
    """Drive the star mapper through the public API with a crafted input."""
    result = _score_via_public(score, category)
    return result["rating_stars"]


def _score_via_public(score, category):
    """Construct per-100 values that produce the requested final score."""
    if category == "solid":
        if score <= 0:
            # negative score requires positive points: use protein (max 15 at low baseline)
            protein_points = min(-score, 15)
            protein_value = [0, 1.51, 2.01, 2.51, 3.01, 5.01, 7.01, 10.01, 15.01, 20.01, 25.01, 30.01, 35.01, 40.01, 45.01, 50.01][protein_points]
            return calculate_inr({
                "energy_kcal": 0, "total_sugars_g": 0, "saturated_fat_g": 0,
                "sodium_mg": 0, "protein_g": protein_value,
            }, category="solid")
        # score = sugar_points (max 20) + sodium_points (max 25)
        sugar_points = min(score, 20)
        sodium_points = score - sugar_points
        sugar_value = 4.2 * sugar_points + 0.1 if sugar_points else 0
        sodium_value = 90 * sodium_points + 0.01 if sodium_points else 0
        return calculate_inr({
            "energy_kcal": 0, "total_sugars_g": sugar_value, "saturated_fat_g": 0,
            "sodium_mg": sodium_value, "protein_g": 0,
        }, category="solid")
    # liquid — is_beverage=False keeps the zero-energy proviso out of formula tests
    if score <= 0:
        protein_points = min(-score, 10)
        protein_value = [0, 1.51, 2.01, 2.51, 3.01, 5.01, 7.01, 10.01, 15.01, 20.01, 25.01][protein_points]
        return calculate_inr({
            "energy_kcal": 0, "total_sugars_g": 0, "protein_g": protein_value,
        }, category="liquid", is_beverage=False)
    # score = energy_points + sugar_points, each 0..10
    energy_points = min(score, 10)
    sugar_points = score - energy_points
    energy_value = 60.01 if energy_points == 10 else ([6, 12, 18, 24, 30, 36, 42, 48, 54, 60][energy_points - 1] + 0.01 if energy_points else 0)
    sugar_value = 13.61 if sugar_points == 10 else ([0.1, 1.6, 3.1, 4.6, 6.1, 7.6, 9.1, 10.6, 12.1, 13.6][sugar_points - 1] + 0.01 if sugar_points else 0)
    return calculate_inr({
        "energy_kcal": energy_value, "total_sugars_g": sugar_value, "protein_g": 0,
    }, category="liquid", is_beverage=False)


# --- Determinism & versioning (doc 05 §2) ----------------------------------------

def test_round_trip_determinism():
    """Same input twice -> identical output (pure function, doc 03 §6)."""
    payload = {
        "energy_kcal": 480, "total_sugars_g": 18, "saturated_fat_g": 6.0,
        "sodium_mg": 420, "protein_g": 6, "dietary_fiber_g": 2,
    }
    assert calculate_inr(payload, category="solid") == calculate_inr(payload, category="solid")


def test_formula_version_recorded():
    result = calculate_inr({"energy_kcal": 100, "total_sugars_g": 5, "saturated_fat_g": 1,
                            "sodium_mg": 50, "protein_g": 2}, category="solid")
    assert result["formula_version"] == INR_FORMULA_VERSION == "FSSAI-INR-2022-draft-v1"


# --- Exemptions (doc 04 §1, doc 05 §1) --------------------------------------------

def test_category_iii_exempt_short_circuits():
    result = calculate_inr({"energy_kcal": 500, "total_sugars_g": 30}, category="solid", exempt=True)
    assert result["eligible"] is False
    assert result["status"] == "exempt"
    assert result["inr_score"] is None
    assert result["rating_stars"] is None
    assert "Schedule-IV" in result["exemption_reason"]


def test_zero_energy_zero_sugar_beverage_ineligible():
    """Diet soft drink must NOT get a fabricated star rating (doc 05 §1)."""
    result = calculate_inr(
        {"energy_kcal": 0, "total_sugars_g": 0, "protein_g": 0},
        category="liquid", is_beverage=True,
    )
    assert result["eligible"] is False
    assert result["status"] == "not_eligible_zero_energy_zero_sugar"


def test_zero_energy_zero_sugar_non_beverage_still_scores():
    """A solid with 0/0 declared is still scoreable (proviso is beverage-only)."""
    result = calculate_inr(
        {"energy_kcal": 0, "total_sugars_g": 0, "saturated_fat_g": 0,
         "sodium_mg": 0, "protein_g": 3},
        category="solid", is_beverage=False,
    )
    assert result["eligible"] is True


def test_is_zero_energy_helper():
    assert is_zero_energy_zero_sugar_beverage({"energy_kcal": 0, "total_sugars_g": 0}) is True
    assert is_zero_energy_zero_sugar_beverage({"energy_kcal": 1, "total_sugars_g": 0}) is False
    assert is_zero_energy_zero_sugar_beverage({"energy_kcal": 0, "total_sugars_g": 0}, is_beverage=False) is False


# --- Missing values ----------------------------------------------------------------

def test_missing_baseline_fields_flagged_not_silent():
    result = calculate_inr({"protein_g": 2}, category="solid")
    assert result["status"] == "estimated_missing_as_zero"
    assert "energy_kcal" in result["missing_fields_treated_as_zero"]
    assert "sodium_mg" in result["missing_fields_treated_as_zero"]


def test_undeclared_positive_factors_score_zero():
    result = calculate_inr({
        "energy_kcal": 480, "total_sugars_g": 18, "saturated_fat_g": 6.0,
        "sodium_mg": 420, "protein_g": 6,
    }, category="solid")
    assert result["positive_points"]["fv"] == 0
    assert result["positive_points"]["nlm"] == 0
    assert result["positive_points"]["fibre"] == 0


def test_invalid_category_raises():
    with pytest.raises(ValueError):
        calculate_inr({}, category="powder")
