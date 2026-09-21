"""Personalization rule engine — doc 04 §4 (4 launch conditions).

Each condition is an explicit, versioned rule table, NOT a model (ADR-4).
Verdicts: AVOID requires at least one hard trigger; CAUTION is a softer
threshold; otherwise GOOD_FIT. When a rule's decisive input was not read
from the label, the verdict is COULD_NOT_VERIFY — never GOOD_FIT, since
"no value read" is not evidence of compliance. Hard triggers (AVOID/CAUTION)
still fire from whatever evidence WAS read (e.g. an ingredient trigger).
Every verdict carries the specific rules that fired plus the mandatory
non-medical-advice disclaimer.
Thresholds are per-100g/100ml, matching the INR normalization.
"""

import re

PERSONALIZATION_VERSION = "labellens-personalization-v1"

DISCLAIMER = (
    "LabelLens is not a medical device and does not diagnose or treat any "
    "condition. These are general dietary flags based on your selected "
    "conditions and the product's declared ingredients/nutrition. Always "
    "consult your doctor or a registered dietitian."
)

SUPPORTED_CONDITIONS = ("sugar", "diabetes", "migraine", "fever")

# Doc 04 §4.1 — INR baseline sugar thresholds double as the AVOID line
SUGAR_AVOID_SOLID_G = 21.0
SUGAR_AVOID_LIQUID_G = 6.0
SODIUM_AVOID_MG = 450.0  # Diabetes comorbidity / Fever risk threshold
SATFAT_AVOID_SOLID_G = 5.0  # Fever risk threshold (INR baseline)

# Diabetes: high-glycemic sweeteners among first 3 ingredients
_HIGH_GLYCEMIC = ["glucose syrup", "dextrose", "maltodextrin", "honey",
                  "glucose", "liquid glucose", "corn syrup", "invert syrup"]
# Migraine triggers (well-documented dietary triggers; ingredient-flag driven)
_MIGRAINE_AVOID = ["msg", "monosodium glutamate", "ins 621", "621",
                   "aspartame", "ins 951", "951", "nitrite", "nitrate",
                   "ins 249", "ins 250", "ins 251", "ins 252",
                   "aged cheese", "yeast extract"]
_MIGRAINE_CAUTION = ["caffeine", "cocoa", "chocolate", "acesulfame", "coffee extract"]

_TRIGGER_DISPLAY = {
    "msg": "MSG (Monosodium glutamate, INS 621)",
    "monosodium glutamate": "MSG (Monosodium glutamate, INS 621)",
    "ins 621": "MSG (INS 621)",
    "621": "MSG (INS 621)",
    "aspartame": "Aspartame (INS 951)",
    "ins 951": "Aspartame (INS 951)",
    "951": "Aspartame (INS 951)",
    "nitrite": "Nitrites (INS 249-252)",
    "nitrate": "Nitrates (INS 249-252)",
    "ins 249": "Nitrite/potassium nitrite (INS 249)",
    "ins 250": "Sodium nitrite (INS 250)",
    "ins 251": "Sodium nitrate (INS 251)",
    "ins 252": "Potassium nitrate (INS 252)",
    "aged cheese": "Aged cheese (tyramine source)",
    "yeast extract": "Yeast extract (tyramine source)",
}
# Fever: heavy-spice / chilli as primary declared ingredient
_FEVER_SPICE = ["chilli", "chili", "red pepper", "cayenne", "hot spice mix"]


def _num(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _per100_of(product):
    return product.get("nutrition_per_100g") or product.get("nutrition_per_100ml") or {}


def _first3_names(product):
    ingredients = product.get("ingredients") or []
    names = []
    for entry in ingredients[:3]:
        if isinstance(entry, dict):
            names.append(str(entry.get("name", "")).lower())
        else:
            names.append(str(entry).lower())
    return names


def _all_ingredient_text(product):
    ingredients = product.get("ingredients") or []
    parts = []
    for entry in ingredients:
        parts.append(str(entry.get("name", "")).lower() if isinstance(entry, dict) else str(entry).lower())
    return " ".join(parts)


def _additive_class_count(product):
    """Count INS-numbered additive entries (highly-processed indicator)."""
    ingredients = product.get("ingredients") or []

    def _is_additive(entry):
        if isinstance(entry, dict):
            return bool(entry.get("ins_number") or entry.get("resolved_from_ins"))
        if isinstance(entry, str):
            return bool(re.search(r"\bins?\s*\d{3,4}", entry, re.IGNORECASE))
        return False

    return sum(1 for entry in ingredients if _is_additive(entry))


def _verdict(avoids, cautions, good_reason, unverified_reasons=None):
    if avoids:
        return {"verdict": "AVOID", "reasons": avoids}
    if cautions:
        return {"verdict": "CAUTION", "reasons": cautions}
    if unverified_reasons:
        return {"verdict": "COULD_NOT_VERIFY", "reasons": unverified_reasons}
    return {"verdict": "GOOD_FIT", "reasons": [good_reason]}


def _rule_sugar(product):
    per100 = _per100_of(product)
    sugar = _num(per100.get("total_sugar_g"))
    liquid = product.get("category", "I") == "II"
    threshold = SUGAR_AVOID_LIQUID_G if liquid else SUGAR_AVOID_SOLID_G
    unit = "100ml" if liquid else "100g"
    added_in_first3 = any(
        kw in name for name in _first3_names(product)
        for kw in ("sugar", "sucrose", "glucose", "fructose", "syrup", "dextrose", "jaggery")
    )

    avoids, cautions = [], []
    unverified = []
    if sugar is None:
        unverified.append(
            "The total-sugar value was not read from the label, so the sugar "
            "thresholds could not be checked."
        )
    if sugar is not None and sugar > threshold:
        avoids.append(
            f"Total sugar ({sugar:g}g/{unit}) exceeds the {threshold:g}g/{unit} "
            f"sugar-sensitivity threshold (INR baseline)."
        )
    elif (sugar is not None and sugar > 4.2 if not liquid else sugar is not None and sugar > 0.1) or added_in_first3:
        if added_in_first3 and (sugar is None or sugar <= threshold):
            cautions.append(
                "Added sugar (or a sugary ingredient) appears among the first "
                "3 ingredients by weight."
            )
        elif sugar is not None:
            cautions.append(
                f"Total sugar ({sugar:g}g/{unit}) is above the INR 0-point band "
                f"though below the {threshold:g}g/{unit} AVOID threshold."
            )
    return _verdict(avoids, cautions,
                    "Total sugar is within the INR 0-point band and no sugary ingredient ranks in the top 3.",
                    unverified)


def _rule_diabetes(product):
    per100 = _per100_of(product)
    sugar = _num(per100.get("total_sugar_g"))
    sodium = _num(per100.get("sodium_mg"))
    carbs = _num(per100.get("carbohydrate_g"))
    fibre = _num(per100.get("dietary_fiber_g")) or 0.0
    liquid = product.get("category", "I") == "II"
    sugar_threshold = SUGAR_AVOID_LIQUID_G if liquid else SUGAR_AVOID_SOLID_G
    unit = "100ml" if liquid else "100g"
    high_glycemic_first3 = any(
        kw in name for name in _first3_names(product) for kw in _HIGH_GLYCEMIC
    )

    avoids, cautions = [], []
    unverified = []
    if sugar is None:
        unverified.append(
            "The total-sugar value was not read from the label, so the "
            "diabetes sugar threshold could not be checked."
        )
    if (sugar is not None and sugar > sugar_threshold) or high_glycemic_first3:
        if sugar is not None and sugar > sugar_threshold:
            avoids.append(
                f"Total sugar ({sugar:g}g/{unit}) exceeds the Diabetes "
                f"threshold ({sugar_threshold:g}g/{unit})."
            )
        if high_glycemic_first3:
            avoids.append(
                "A high-glycemic sweetener (glucose syrup, dextrose, "
                "maltodextrin, or honey) is among the first 3 ingredients."
            )
    if sodium is not None and sodium > SODIUM_AVOID_MG:
        avoids.append(
            f"Sodium ({sodium:g}mg/100g) exceeds 450mg/100g — a hypertension "
            f"comorbidity risk factor for Diabetes."
        )

    if sugar is not None and (10 if not liquid else 3) < sugar <= sugar_threshold:
        cautions.append(
            f"Total sugar ({sugar:g}g/{unit}) is in the Diabetes caution band."
        )
    if carbs is not None and carbs > 30 and fibre < 3:
        cautions.append(
            f"Carbohydrate ({carbs:g}g/100g) is high with low fibre "
            f"({fibre:g}g/100g) — expect a faster glucose response."
        )
    unverified_partial = []
    if carbs is None:
        unverified_partial.append(
            "The carbohydrate value was not read, so the high-carb/low-fibre "
            "check could not be completed."
        )
    if sodium is None:
        unverified_partial.append(
            "The sodium value was not read, so the blood-pressure check "
            "could not be completed."
        )
    return _verdict(avoids, cautions,
                    "Sugar, sodium and carbohydrate load are within Diabetes caution thresholds.",
                    unverified + unverified_partial)


def _rule_migraine(product):
    text = _all_ingredient_text(product)
    avoids, cautions = [], []
    unverified = []
    if not text:
        unverified.append(
            "The ingredient list was not read from the label, so trigger "
            "ingredients (MSG, aspartame, nitrites, tyramine sources) could "
            "not be checked."
        )
    for trigger in _MIGRAINE_AVOID:
        if trigger in text:
            display = _TRIGGER_DISPLAY.get(trigger, trigger.title())
            avoids.append(
                f"Contains a documented migraine trigger ingredient: {display}."
            )
            break
    for trigger in _MIGRAINE_CAUTION:
        if trigger in text:
            cautions.append(
                f"Contains '{trigger.title()}', a moderate migraine caution "
                f"ingredient (common dietary trigger)."
            )
            break
    return _verdict(avoids, cautions,
                    "No known migraine-trigger ingredients (MSG, aspartame, "
                    "nitrites, tyramine sources) detected.",
                    unverified)


def _rule_fever(product):
    per100 = _per100_of(product)
    sodium = _num(per100.get("sodium_mg"))
    satfat = _num(per100.get("saturated_fat_g"))
    total_fat = _num(per100.get("total_fat_g"))
    first3 = _first3_names(product)
    additive_count = _additive_class_count(product)

    avoids, cautions = [], []
    unverified = []
    if sodium is None and satfat is None:
        unverified.append(
            "Sodium and saturated-fat values were not read from the label, "
            "so the fever-diet thresholds could not be checked."
        )
    if sodium is not None and sodium > SODIUM_AVOID_MG:
        avoids.append(
            f"Sodium ({sodium:g}mg/100g) exceeds 450mg/100g — heavy sodium is "
            f"discouraged during fever."
        )
    if satfat is not None and satfat > SATFAT_AVOID_SOLID_G:
        avoids.append(
            f"Saturated fat ({satfat:g}g/100g) exceeds 5g/100g — heavy fat load "
            f"is discouraged during fever."
        )
    if any(spice in name for name in first3 for spice in _FEVER_SPICE):
        avoids.append(
            "Chilli / heavy-spice seasoning appears among the first 3 "
            "declared ingredients."
        )
    if total_fat is not None and total_fat > 10:
        cautions.append(
            f"Total fat ({total_fat:g}g/100g) is above 10g/100g — rich foods "
            f"can feel heavy during fever."
        )
    if additive_count >= 5:
        cautions.append(
            f"Contains {additive_count} additive-class (INS-numbered) "
            f"ingredients — a highly-processed indicator."
        )
    unverified_partial = []
    if satfat is None:
        unverified_partial.append(
            "The saturated-fat value was not read, so the fat-load check "
            "could not be completed."
        )
    if total_fat is None:
        unverified_partial.append(
            "The total-fat value was not read, so the richness check could "
            "not be completed."
        )
    return _verdict(avoids, cautions,
                    "Sodium, fat and spice load are within fever-diet guidance thresholds.",
                    unverified + unverified_partial)


_RULES = {
    "sugar": _rule_sugar,
    "diabetes": _rule_diabetes,
    "migraine": _rule_migraine,
    "fever": _rule_fever,
}

CONDITION_LABELS = {
    "sugar": "Sugar-sensitivity / high sugar intake",
    "diabetes": "Diabetes",
    "migraine": "Migraine",
    "fever": "Fever",
}


def personalize(product, conditions):
    """Evaluate the selected conditions' rule tables against one product.

    Returns {product_id, conditions_version, disclaimer, verdicts: [...]}.
    Unknown conditions raise ValueError (INVALID_CONDITION).
    """
    conditions = list(conditions or [])
    if not conditions:
        return {"verdicts": [], "disclaimer": DISCLAIMER,
                "conditions_version": PERSONALIZATION_VERSION,
                "note": "No conditions selected — no personalization shown."}

    invalid = [c for c in conditions if c not in SUPPORTED_CONDITIONS]
    if invalid:
        raise ValueError(
            f"Unsupported condition(s): {', '.join(invalid)}. "
            f"Supported: {', '.join(SUPPORTED_CONDITIONS)}."
        )

    verdicts = []
    for condition in conditions:
        result = _RULES[condition](product)
        verdicts.append({
            "condition": condition,
            "condition_label": CONDITION_LABELS[condition],
            "verdict": result["verdict"],
            "reasons": result["reasons"],
            "rule_version": PERSONALIZATION_VERSION,
        })
    return {
        "verdicts": verdicts,
        "disclaimer": DISCLAIMER,
        "conditions_version": PERSONALIZATION_VERSION,
    }
