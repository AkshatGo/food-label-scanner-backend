"""Indian Nutrition Rating (INR) engine — FSSAI Gazette, 13 Sept 2022 draft.

Implements Schedule III Tables 1-6 of the draft amendment to the Food Safety
and Standards (Labelling & Display) Regulations, 2020, inserting Chapter 6
(Regulation 14) exactly as specified in doc 04 of the LabelLens documentation
set.

Implementation guarantees (doc 04 §6, doc 05 §2):
- All values are per 100 g (solid) / per 100 ml (liquid), "as sold".
- Every band is a strict ``>`` (open lower bound): a value exactly equal to a
  band's lower bound scores the LOWER band. An explicit comparator is used,
  not an eyeballed ``if``.
- Category-II (liquid, non-dairy) never scores saturated fat, sodium, NLM or
  fibre - those terms are absent from the calculation, not zeroed.
- Missing positive-nutrient declarations (FV%, NLM%, fibre) score 0 points.
- Missing baseline values are treated as 0 and flagged (never silently).
- The function is pure: identical input -> identical output.
- Zero-energy AND zero-sugar beverages are ineligible for a star rating.

Known table artifact: Table 6's liquid column prints "1.5 stars: 16 to 18"
and "1 star: 18 to 20", overlapping at 18. We resolve this deterministically
as contiguous bands (1.5 stars = 16-17, 1 star = 18-19, 0.5 stars >= 20),
which preserves every non-overlapping edge of the printed table.

Formula version string is recorded on every result so historic scans can show
what was true when they were scanned (doc 03 §6).
"""

INR_FORMULA_VERSION = "FSSAI-INR-2022-draft-v1"

# --- Table 2 / Table 3 band lower-bounds (strict >) -------------------------
# A point value N is scored when value > bounds[N-1] (bounds ascending).

_SOLID_ENERGY_BOUNDS = [80, 160, 240, 320, 400, 480, 560, 640, 720, 800]  # max 10
# Sat fat: step 1 up to >10 (10 pts), then step 2 (12,14,...,40) up to >40 (25 pts) — per Table 2
_SOLID_SATFAT_BOUNDS = [float(g) for g in range(1, 11)] + [float(g) for g in range(12, 41, 2)]  # max 25
_SOLID_SUGAR_BOUNDS = [round(4.2 * i, 1) for i in range(1, 21)]  # max 20
_SOLID_SODIUM_BOUNDS = [90 * i for i in range(1, 26)]  # max 25
_SOLID_FV_BOUNDS = [10, 15, 20, 25, 30, 35, 40, 45, 50, 55]  # max 10
_SOLID_NLM_BOUNDS = [10, 15, 20, 25, 30, 35, 40, 45, 50, 55]  # max 10
_SOLID_FIBRE_BOUNDS = [3, 6, 9, 12, 15, 18, 21, 24, 27, 30]  # max 10
_SOLID_PROTEIN_BOUNDS = [1.5, 2.0, 2.5, 3.0, 5, 7, 10, 15, 20, 25, 30, 35, 40, 45, 50]  # max 15

_LIQUID_ENERGY_BOUNDS = [6, 12, 18, 24, 30, 36, 42, 48, 54, 60]  # max 10
_LIQUID_SUGAR_BOUNDS = [0.1, 1.6, 3.1, 4.6, 6.1, 7.6, 9.1, 10.6, 12.1, 13.6]  # max 10
_LIQUID_FV_BOUNDS = [5, 10, 15, 20, 25, 30, 35, 40, 45, 55]  # max 10 (as printed)
# Table 3 protein column runs to 15 pts (>50) — same shape as solid protein
_LIQUID_PROTEIN_BOUNDS = [1.5, 2.0, 2.5, 3.0, 5, 7, 10, 15, 20, 25, 30, 35, 40, 45, 50]  # max 15

# Table 4 capping: {category: {baseline_le_threshold: {factor: cap}}}
_CAPS = {
    "solid": {
        "low_baseline_max": 20,
        "low": {"protein": 15, "fv": 10, "nlm": 10, "fibre": 10},
        "high": {"protein": 7, "fv": 5, "nlm": 5, "fibre": 5},
    },
    "liquid": {
        "low_baseline_max": 10,
        "low": {"protein": 15, "fv": 10},
        "high": {"protein": 7, "fv": 5},
    },
}

# Raw point maxima per factor before capping (Table 2/3 column lengths)
_RAW_MAX = {
    "solid": {"fv": 10, "nlm": 10, "fibre": 10, "protein": 15},
    "liquid": {"fv": 10, "protein": 15},
}


def _as_float(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _points(value, bounds):
    """Strict-> comparator: value exactly on a boundary scores the lower band."""
    if value is None:
        return 0
    return sum(1 for bound in bounds if value > bound)


def _cap(value, cap):
    return min(value, cap)


def _stars_solid(score):
    if score <= -11:
        return 5.0
    if score <= -7:
        return 4.5
    if score <= -2:
        return 4.0
    if score <= 2:
        return 3.5
    if score <= 6:
        return 3.0
    if score <= 11:
        return 2.5
    if score <= 15:
        return 2.0
    if score <= 20:
        return 1.5
    if score <= 24:
        return 1.0
    return 0.5


def _stars_liquid(score):
    # See module docstring re the printed 18-point overlap artifact.
    if score <= 0:
        return 5.0
    if score <= 2:
        return 4.5
    if score <= 4:
        return 4.0
    if score <= 6:
        return 3.5
    if score <= 9:
        return 3.0
    if score <= 12:
        return 2.5
    if score <= 15:
        return 2.0
    if score <= 17:
        return 1.5
    if score <= 19:
        return 1.0
    return 0.5


def is_zero_energy_zero_sugar_beverage(per100, is_beverage=True):
    """Regulation proviso: any beverage with zero energy AND zero sugar is
    not eligible for an INR star rating, regardless of category."""
    if not is_beverage:
        return False
    energy = _as_float(per100.get("energy_kcal"))
    sugar = _as_float(per100.get("total_sugars_g"))
    if energy is None or sugar is None:
        return False
    return energy == 0 and sugar == 0


def calculate_inr(per100, *, category="solid", fv_percent=None, nlm_percent=None,
                  exempt=False, is_beverage=None):
    """Compute the INR star rating for one product.

    per100 keys (per 100 g / 100 ml, as sold):
        energy_kcal, total_sugars_g, saturated_fat_g, sodium_mg,
        dietary_fiber_g, protein_g  (fv_percent / nlm_percent via kwargs)
    """
    category = str(category).lower().strip()

    if exempt:
        return {
            "status": "exempt",
            "eligible": False,
            "exemption_reason": (
                "This product category is exempt from FOPNL star rating "
                "under FSSAI Schedule-IV."
            ),
            "inr_score": None,
            "rating_stars": None,
            "rating_display": "N/A",
            "formula_version": INR_FORMULA_VERSION,
            "basis": "FSSAI 2022 draft INR framework; Category-III exempt",
        }

    if category not in {"solid", "liquid"}:
        raise ValueError("category must be solid or liquid")

    if is_beverage is None:
        is_beverage = category == "liquid"

    if is_zero_energy_zero_sugar_beverage(per100, is_beverage=is_beverage):
        return {
            "status": "not_eligible_zero_energy_zero_sugar",
            "eligible": False,
            "exemption_reason": (
                "Beverages with zero energy and zero sugar are not eligible "
                "for an INR star rating (Regulation 14 proviso)."
            ),
            "inr_score": None,
            "rating_stars": None,
            "rating_display": "N/A",
            "formula_version": INR_FORMULA_VERSION,
            "basis": "FSSAI 2022 draft INR framework; zero-energy/zero-sugar proviso",
        }

    energy = _as_float(per100.get("energy_kcal"))
    sugar = _as_float(per100.get("total_sugars_g"))
    protein = _as_float(per100.get("protein_g"))
    fv = _as_float(fv_percent if fv_percent is not None else per100.get("fv_percent")) or 0.0
    nlm = _as_float(nlm_percent if nlm_percent is not None else per100.get("nlm_percent")) or 0.0

    missing = []
    for field in ("energy_kcal", "total_sugars_g", "protein_g"):
        if _as_float(per100.get(field)) is None:
            missing.append(field)
    if fv_percent is None and per100.get("fv_percent") is None:
        pass  # undeclared positive factors score 0, not "missing" (doc 04 §6.5)

    if category == "solid":
        satfat = _as_float(per100.get("saturated_fat_g"))
        sodium = _as_float(per100.get("sodium_mg"))
        fibre = _as_float(per100.get("dietary_fiber_g")) or 0.0
        if satfat is None:
            missing.append("saturated_fat_g")
        if sodium is None:
            missing.append("sodium_mg")

        negative = {
            "energy": _points(energy, _SOLID_ENERGY_BOUNDS),
            "total_sugar": _points(sugar, _SOLID_SUGAR_BOUNDS),
            "saturated_fat": _points(satfat, _SOLID_SATFAT_BOUNDS),
            "sodium": _points(sodium, _SOLID_SODIUM_BOUNDS),
        }
        raw_positive = {
            "fv": _points(fv, _SOLID_FV_BOUNDS),
            "nlm": _points(nlm, _SOLID_NLM_BOUNDS),
            "fibre": _points(fibre, _SOLID_FIBRE_BOUNDS),
            "protein": _points(protein, _SOLID_PROTEIN_BOUNDS),
        }
    else:
        negative = {
            "energy": _points(energy, _LIQUID_ENERGY_BOUNDS),
            "total_sugar": _points(sugar, _LIQUID_SUGAR_BOUNDS),
        }
        raw_positive = {
            "fv": _points(fv, _LIQUID_FV_BOUNDS),
            "protein": _points(protein, _LIQUID_PROTEIN_BOUNDS),
        }

    baseline = sum(negative.values())

    caps = _CAPS[category]
    cap_table = caps["low"] if baseline <= caps["low_baseline_max"] else caps["high"]
    positive = {
        factor: _cap(min(raw, _RAW_MAX[category][factor]), cap_table[factor])
        for factor, raw in raw_positive.items()
    }
    capped = {
        factor: raw_positive[factor] > positive[factor]
        for factor in raw_positive
        if raw_positive[factor] > positive[factor]
    }

    positive_total = sum(positive.values())
    score = baseline - positive_total
    stars = _stars_solid(score) if category == "solid" else _stars_liquid(score)

    return {
        "status": "estimated_missing_as_zero" if missing else "calculated",
        "eligible": True,
        "category": category,
        "basis": (
            f"FSSAI 2022 draft INR framework; Category-"
            f"{'I (solid)' if category == 'solid' else 'II (liquid, non-dairy)'}; "
            f"per {'100g' if category == 'solid' else '100ml'}, as sold"
        ),
        "formula_version": INR_FORMULA_VERSION,
        "inr_score": score,
        "rating_stars": stars,
        "rating_display": f"{stars:g}/5",
        "baseline_points": baseline,
        "negative_points": negative,
        "positive_points": positive,
        "positive_points_total": positive_total,
        "capped_factors": capped,
        "missing_fields_treated_as_zero": missing,
    }


calculate_inr_rating = calculate_inr  # backwards-compatible alias
