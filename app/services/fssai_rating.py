"""Offline FSSAI September 2022 draft-based INR calculator."""

SOLID_ENERGY = [80,160,240,320,400,480,560,640,720,800,900,1000,1100,1200,1300,1400,1500,1600,1700,1800,1900,2000,2100,2200]
SOLID_SUGAR = [4.2,8.4,12.6,16.8,21,25.2,29.4,33.6,37.8,42,46.2,50.4,54.6,58.8,63,67.2,71.4,75.6,79.8,84]
SOLID_SAT_FAT = list(range(1,31))
SOLID_SODIUM = [90,180,270,360,450,540,630,720,810,900,990,1080,1170,1260,1350,1440,1530,1620,1710,1800,1890,1980,2070,2160,2250]
SOLID_FIBER = [3,6,9,12,15,18,21,24,27,30]
SOLID_PROTEIN = [1.5,2,2.5,3,5,7,10,15,20,25]
LIQUID_ENERGY = [6,12,18,24,30,36,42,48,54,60]
LIQUID_SUGAR = [0.1,1.6,3.1,4.6,6.1,7.6,9.1,10.6,12.1,13.6]
LIQUID_PROTEIN = SOLID_PROTEIN


def _value(data, key):
    value = data.get(key, 0)
    try: return float(value)
    except (TypeError, ValueError): return 0.0


def _points(value, bounds, maximum):
    return min(sum(value > boundary for boundary in bounds), maximum)


def _rating(score, category):
    if category == "liquid":
        return 5.0 if score <= 0 else 4.5 if score <= 2 else 4.0 if score <= 4 else 3.5 if score <= 6 else 3.0 if score <= 9 else 2.5 if score <= 12 else 2.0 if score <= 15 else 1.5 if score <= 18 else 1.0 if score <= 20 else 0.5
    return 5.0 if score <= -11 else 4.5 if score <= -7 else 4.0 if score <= -2 else 3.5 if score <= 2 else 3.0 if score <= 6 else 2.5 if score <= 11 else 2.0 if score <= 15 else 1.5 if score <= 20 else 1.0 if score <= 24 else 0.5


def calculate_inr(per100, *, category="solid", fv_percent=None, nlm_percent=None, exempt=False):
    category = category.lower().strip()
    if exempt:
        return {"status": "exempt", "inr_score": None, "rating_stars": None, "rating_display": "N/A", "basis": "FSSAI 2022 draft INR framework"}
    if category not in {"solid", "liquid"}: raise ValueError("category must be solid or liquid")
    fields = ("energy_kcal", "total_sugars_g", "saturated_fat_g", "sodium_mg", "dietary_fiber_g", "protein_g") if category == "solid" else ("energy_kcal", "total_sugars_g", "protein_g")
    missing = [field for field in fields if field not in per100 or per100[field] is None]
    energy, sugar, protein = _value(per100, "energy_kcal"), _value(per100, "total_sugars_g"), _value(per100, "protein_g")
    if category == "solid":
        negative = {"energy": _points(energy, SOLID_ENERGY, 25), "total_sugar": _points(sugar, SOLID_SUGAR, 20), "saturated_fat": _points(_value(per100, "saturated_fat_g"), SOLID_SAT_FAT, 30), "sodium": _points(_value(per100, "sodium_mg"), SOLID_SODIUM, 25)}
        positive = {"fibre": min(_points(_value(per100, "dietary_fiber_g"), SOLID_FIBER, 10), 10), "protein": min(_points(protein, SOLID_PROTEIN, 10), 15), "fv": 0, "nlm": 0}
    else:
        negative = {"energy": _points(energy, LIQUID_ENERGY, 15), "total_sugar": _points(sugar, LIQUID_SUGAR, 15)}
        positive = {"protein": min(_points(protein, LIQUID_PROTEIN, 10), 15), "fv": 0}
    baseline = sum(negative.values()); positive_total = sum(positive.values()); score = baseline - positive_total; stars = _rating(score, category)
    return {"status": "estimated_missing_as_zero" if missing else "calculated", "inr_score": score, "rating_stars": stars, "rating_display": f"{stars:g}/5", "negative_points": negative, "positive_points": positive, "baseline_points": baseline, "positive_points_total": positive_total, "missing_fields": missing, "missing_fields_treated_as_zero": missing, "basis": f"FSSAI 2022 draft INR framework; Category {category}; per 100g/100ml", "category": category}


calculate_inr_rating = calculate_inr
