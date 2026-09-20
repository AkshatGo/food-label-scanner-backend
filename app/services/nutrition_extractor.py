"""Nutrition extraction from OCR text with per-100g/100ml normalization.

Implements doc 04 §6.1 — the #1 flagged pitfall: nutrition declared per
serving (e.g. "per 30g pack") MUST be normalized to per-100g/100ml before
scoring. Also surfaces low-confidence values for user review rather than
silently feeding a health formula (doc 01 §8.2, doc 05 §3).
"""

import re

# Explicit alias lists per canonical field (longest match wins).
FIELD_ALIASES = [
    ("added_sugar_g", ["added sugars", "added sugar", "added sucrose"]),
    ("total_sugar_g", ["total sugars", "total sugar", "of which sugars", "sugars", "sugar"]),
    ("carbohydrate_g", ["total carbohydrate", "total carbohydrates", "carbohydrate", "carbohydrates", "carbs"]),
    ("saturated_fat_g", ["saturated fat", "sat fat"]),
    ("trans_fat_g", ["trans fat"]),
    ("total_fat_g", ["total fat", "fat"]),
    ("energy_kcal", ["energy (kcal)", "energy kcal", "energy", "calories", "calorie", "cal"]),
    ("protein_g", ["protein"]),
    ("sodium_mg", ["sodium", "na"]),
    ("fibre_g", ["dietary fibre", "dietary fiber", "fibre", "fiber"]),
    ("cholesterol_mg", ["cholesterol"]),
]

_ALTERNATION = "|".join(
    re.escape(alias) for alias, _field in sorted(
        ((alias, field) for field, aliases in FIELD_ALIASES for alias in aliases),
        key=lambda pair: -len(pair[0]),
    )
)

_ROW_RE = re.compile(
    r"^[\W_]{0,4}(" + _ALTERNATION + r")\s*"
    r"(?:\(\s*(?P<header_unit>kcal|kj|mcg|ug|mg|g)\s*\)|\([^)]{0,40}\))?\s*[:=\-|]?\s*"
    r"(?:(?P<prefix_unit>kcal|kj|mcg|ug|mg|g)\s+)?"
    r"(?:approx\.?\s*)?(?P<bound>less\s+than\s+|<\s*)?"
    r"(?P<number>\d+(?:[.,]\d+)?)(?![\d.,])\s*"
    r"(?P<unit>kcal|kj|mcg|ug|mg|g|iu)?(?![A-Za-z])",
    re.IGNORECASE,
)

_FIELD_LOOKUP = {
    alias: field
    for field, aliases in FIELD_ALIASES
    for alias in aliases
}

_SERVING_RE = re.compile(
    r"per\s+(?:serving|pack|packet|sachet|cup|portion|container)\s*"
    r"(?:of\s*)?[\(\[]?\s*(\d+(?:\.\d+)?)\s*(g|kg|ml|l)\s*[\)\]]?",
    re.IGNORECASE,
)
# US-style panels declare "Serving Size 1 oz (28g/About 15 chips)": the gram
# equivalent inside the parentheses is the per-serving basis.
_US_SERVING_RE = re.compile(
    r"serving\s*size\s*:?\s*(?:[\d.]+\s*(?:oz|cup|piece\s*\(\s*[\d.]+\s*g\s*\))?\s*)?"
    r"[\(\[]?\s*(\d+(?:\.\d+)?)\s*(g|ml)\b",
    re.IGNORECASE,
)

# FDA 2,000-kcal Daily Value references used on US-style panels. Only used to
# corroborate or repair an OCR-ambiguous reading against the panel's own
# "% Daily Value" arithmetic — never to invent a value for a row without one.
_DAILY_VALUE = {
    "energy_kcal": 2000,
    "total_fat_g": 65,
    "saturated_fat_g": 20,
    "cholesterol_mg": 300,
    "sodium_mg": 2400,
    "carbohydrate_g": 300,
    "fibre_g": 25,
    "total_sugar_g": 50,
    "added_sugar_g": 50,
    "protein_g": 50,
}
_PER100_RE = re.compile(r"per\s*100\s*(g|ml)", re.IGNORECASE)

_DEFAULT_UNITS = {
    "energy_kcal": "kcal", "protein_g": "g", "carbohydrate_g": "g",
    "total_sugar_g": "g", "added_sugar_g": "g", "total_fat_g": "g",
    "saturated_fat_g": "g", "trans_fat_g": "g", "sodium_mg": "mg",
    "fibre_g": "g", "cholesterol_mg": "mg",
}
_GRAM_FIELDS = {field for field, unit in _DEFAULT_UNITS.items() if unit == "g"}


def _coerce_ocr_number(value_str, context):
    """Detect (but never silently mutate) Tesseract's common g->9 substitution.

    A value read on a line with no unit token may be an OCR substitution
    ("54g" read as "549"). Rewriting it here would corrupt perfectly valid
    numbers that merely end in 9 (e.g. "Energy 549 kcal" printed without the
    unit), so the caller only flags the row for review instead (doc 01 §8.2:
    never silently guess a number that feeds a health formula).
    """
    ambiguous = (
        not re.search(r"\b(?:g|gram|grams|mg)\b", context, re.IGNORECASE)
        and (value_str.endswith(".59")
             or (value_str.endswith("9") and len(value_str) > 1 and "." not in value_str))
    )
    return value_str, ambiguous


def _extract_rows(text):
    """Pull (canonical_field, value, unit) tuples from nutrition rows.

    The same panel row is often OCR'd more than once (full-frame and crop
    variants); a reading that carries an explicit unit is strictly more
    trustworthy than a unit-less one (the unit is exactly what the g->9
    confusion eats), so unit-bearing readings win regardless of order.

    Second/third return values:
      ambiguous_fields: fields whose chosen reading is unit-less and ends in
        an OCR-ambiguous digit, minus any the panel's own % Daily Value
        arithmetic corroborates or repairs.
      dv_resolved_fields: fields whose value was corroborated or repaired
        using the stated % Daily Value (recorded for the extraction note).
    A subset-consistency pass may also repair total_sugar_g against the
    carbohydrate row; those fields are reported via subset_resolved_fields
    on the extraction result, not here.
    """
    best = {}
    for line in (text or "").splitlines():
        match = _ROW_RE.search(line)
        if not match:
            continue
        label = re.sub(r"\s+", " ", match.group(1).lower().strip())
        canonical = _FIELD_LOOKUP.get(label)
        if canonical is None:
            continue
        value_str, ambiguous = _coerce_ocr_number(match.group("number"), line)
        uncertain = bool(
            (match.group("bound") or "").strip() == "<"
            or line[match.end():].lstrip().startswith("%")
        )
        if "," in value_str:
            uncertain |= len(value_str.split(",")[1]) == 3
            value_str = value_str.replace(",", ".")
        value = float(value_str)
        unit = (match.group("unit") or match.group("header_unit")
                or match.group("prefix_unit") or "").lower()
        has_unit = bool(unit)

        pct = None
        pct_match = re.search(r"(\d+(?:\.\d+)?)\s*%", line[match.end():])
        if pct_match:
            pct = float(pct_match.group(1))

        current = best.get(canonical)
        if current is not None and (current["has_unit"] or not has_unit):
            continue  # keep the first unit-bearing reading
        best[canonical] = {
            "value": value,
            "value_str": value_str,
            "unit": unit,
            "has_unit": has_unit,
            "ambiguous": ambiguous,
            "pct": pct,
            "uncertain": uncertain,
        }

    ambiguous_fields = []
    dv_resolved_fields = []
    for canonical, entry in best.items():
        if not (entry["ambiguous"] and entry["pct"] is not None):
            if entry["ambiguous"]:
                ambiguous_fields.append(canonical)
            continue
        rda = _DAILY_VALUE.get(canonical)
        implied = rda * entry["pct"] / 100.0 if rda else None
        if not implied or implied <= 0:
            ambiguous_fields.append(canonical)
            continue
        # "459" could be "45" + a substituted trailing 'g': the digit-strip
        # hypothesis must ALSO agree with the %DV-implied value, otherwise the
        # contradiction may sit in a misread percentage, not the value.
        strip_hypothesis = float(entry["value_str"].rstrip("9"))
        strip_agrees = abs(strip_hypothesis - implied) / implied <= 0.25
        if abs(entry["value"] - implied) / implied <= 0.25:
            # The reading agrees with the panel's own %DV math: not corrupt.
            entry["ambiguous"] = False
            dv_resolved_fields.append(canonical)
        elif strip_agrees and entry["value"] / implied >= 5:
            # e.g. "Total Carbohydrate 159 5%": 159g would be 53% DV, not 5%.
            # The trailing '9' is a substituted 'g' and the panel's stated %DV
            # pins the true value (300g * 5% = 15g). Repair transparently.
            entry["value"] = implied
            entry["ambiguous"] = False
            dv_resolved_fields.append(canonical)
        else:
            ambiguous_fields.append(canonical)

    # Subset consistency: sugars are a subset of carbohydrates, so a
    # unit-less sugars reading that is physically impossible against the
    # (already reconciled) carbohydrate row — e.g. "Sugars less than 19" on a
    # panel whose total carbohydrate is 15g — is repaired to the digit-strip
    # hypothesis ("1g") when that restores coherence. A reading that fits
    # within carbohydrates as-read stays flagged: it is possible, just
    # unverified, and must not be silently chosen over the strip hypothesis.
    subset_resolved_fields = []
    carbs_entry = best.get("carbohydrate_g")
    sugar = best.get("total_sugar_g")
    if (
        carbs_entry is not None
        and not carbs_entry["ambiguous"]
        and sugar is not None
        and sugar["ambiguous"]
        and sugar["pct"] is None
    ):
        stripped = sugar["value_str"].rstrip("9")
        if stripped:
            stripped_value = float(stripped)
            if sugar["value"] > carbs_entry["value"] and stripped_value <= carbs_entry["value"]:
                sugar["value"] = stripped_value
                sugar["ambiguous"] = False
                # The %DV pass already queued it as ambiguous (no pct column);
                # the repair clears that flag and must clear the list too.
                if "total_sugar_g" in ambiguous_fields:
                    ambiguous_fields.remove("total_sugar_g")
                subset_resolved_fields.append("total_sugar_g")

    rows = []
    for canonical, entry in best.items():
        value = entry["value"]
        unit = entry["unit"]
        if entry["uncertain"] and canonical not in ambiguous_fields:
            ambiguous_fields.append(canonical)
        # Unit normalization
        if canonical == "energy_kcal" and unit == "kj":
            value /= 4.184
            unit = "kcal"
        elif (canonical == "energy_kcal" and unit not in ("", "kcal")) or (
            canonical != "energy_kcal" and unit in ("kj", "kcal", "iu")
        ):
            ambiguous_fields.append(canonical)
            continue
        elif unit in ("mcg", "ug"):
            value /= 1_000_000 if canonical in _GRAM_FIELDS else 1000
            unit = _DEFAULT_UNITS[canonical]
        elif unit == "mg" and canonical in _GRAM_FIELDS:
            value /= 1000.0
            unit = "g"
        elif unit == "g" and canonical not in _GRAM_FIELDS:
            value *= 1000.0
            unit = "mg"
        elif not unit:
            unit = _DEFAULT_UNITS[canonical]
        rows.append((canonical, round(value, 2), unit))
    return rows, ambiguous_fields, dv_resolved_fields, subset_resolved_fields


def _detect_basis(text):
    """Detect whether values are per-100g/ml or per-serving."""
    per100 = _PER100_RE.search(text)
    if per100:
        return {"basis": "per_100", "unit": per100.group(1).lower(), "serving_size": None}
    us_serving = _US_SERVING_RE.search(text)
    if us_serving:
        return {
            "basis": "per_serving",
            "unit": us_serving.group(2).lower(),
            "serving_size": float(us_serving.group(1)),
        }
    serving = _SERVING_RE.search(text)
    if serving:
        size = float(serving.group(1))
        unit = serving.group(2).lower()
        if unit == "kg":
            size *= 1000
            unit = "g"
        elif unit == "l":
            size *= 1000
            unit = "ml"
        return {"basis": "per_serving", "unit": unit, "serving_size": size}
    return {"basis": "unknown", "unit": None, "serving_size": None}


def extract_nutrition(text):
    """Extract nutrition from OCR text, normalized to per-100g/100ml.

    Returns dict:
        values: {field: {value, unit}} — normalized per-100
        basis: per_100 | per_serving | unknown
        normalized_to_per_100: bool (True if a per-serving -> per-100 conversion ran)
        needs_review: bool (basis unknown, or an OCR-ambiguous digit was read)
        ocr_ambiguous_fields: fields whose unit-less value may hide a g->9 OCR error
        serving_size: grams/ml when per-serving detected
    """
    rows, ambiguous_fields, dv_resolved_fields, subset_resolved = _extract_rows(text)
    basis_info = _detect_basis(text)

    # Panel-visibility signal for the honesty gates: did the OCR text contain
    # a nutrition-table heading at all? Ingredients-readable-but-panel-absent
    # means the photo framed the wrong side of the packet — that must fail
    # with targeted retake advice instead of scoring a zero-nutrition product.
    panel_found = bool(
        re.search(
            r"nutritional\s+information|nutrition\s+(?:facts|information|panel)"
            r"|nutrition\s+per|per\s+100\s*(?:g|ml)|\bper\s+serving\b",
            text,
            re.IGNORECASE,
        )
    )

    values = {
        field: {"value": value, "unit": unit}
        for field, value, unit in rows
    }

    normalized = False
    factor = 1.0
    if basis_info["basis"] == "per_serving" and basis_info["serving_size"]:
        size = basis_info["serving_size"]
        if size > 0:
            factor = 100.0 / size
            if abs(factor - 1.0) > 1e-9:
                normalized = True
                for entry in values.values():
                    entry["value"] = round(entry["value"] * factor, 2)

    # FSSAI-semantic invariants: a printed panel cannot violate these.
    # total sugars are a subset of total carbohydrates, and saturated fat is
    # a subset of total fat. A confident-looking violation is OCR digit
    # corruption (WhatsApp-compressed JPEGs confidently read "385/365" and
    # "80/90") and must demand verification, never feed a health formula.
    inconsistent_fields = []
    if ("total_sugar_g" in values and "carbohydrate_g" in values
            and values["total_sugar_g"]["value"] > values["carbohydrate_g"]["value"]):
        inconsistent_fields += ["total_sugar_g", "carbohydrate_g"]
    if ("saturated_fat_g" in values and "total_fat_g" in values
            and values["saturated_fat_g"]["value"] > values["total_fat_g"]["value"]):
        inconsistent_fields += ["saturated_fat_g", "total_fat_g"]
    for canonical in inconsistent_fields:
        if canonical not in ambiguous_fields:
            ambiguous_fields.append(canonical)

    # A digit that may be a substituted "g" must never silently reach the
    # scoring engine, even when the basis itself was confidently detected.
    multiple_bases = bool(_PER100_RE.search(text) and re.search(r"per\s+serving\b", text, re.I))
    needs_review = (not values
                    or (basis_info["basis"] == "unknown" and bool(values))
                    or bool(ambiguous_fields) or multiple_bases)

    note = "Values read on a per-100g/100ml basis."
    if inconsistent_fields:
        note = (
            "Read values violate a nutrition invariant (sugars within "
            "carbohydrates, saturated fat within total fat) — a sign of OCR "
            "digit corruption. Verify these values against the pack."
        )
    elif not values:
        note = "No nutrition values could be read. Retake a close-up of the nutrition table."
    if not values:
        note = "No nutrition values could be read. Retake a close-up of the nutrition table."
    if ambiguous_fields:
        note = (
            "Some nutrition values contain ambiguous OCR numbers, units, "
            "percentages or bounds; verify them against the label before scoring."
        )
    elif multiple_bases:
        note = "Both per-serving and per-100 values appear; verify the nutrition column before scoring."
    elif dv_resolved_fields:
        note = (
            "Value(s) " + ", ".join(sorted(dv_resolved_fields)) + " were read "
            "against the panel's own % Daily Value column (the printed unit was "
            "lost to OCR) and reconciled with it before scoring."
        )
    elif subset_resolved:
        note = (
            "The sugars value was read without its unit (OCR); it was "
            "reconciled with the carbohydrate row it must fit within "
            "(sugars are a subset of carbohydrates) before scoring."
        )
    elif normalized:
        note = (
            "Nutrition values normalized from per-serving to per-100g/100ml "
            "before scoring (doc 04 §6.1)."
        )
    elif needs_review:
        note = (
            "Nutrition basis could not be confirmed as per-100g/100ml; "
            "values flagged for user review before trusting a health formula."
        )

    return {
        "values": values,
        "panel_found": panel_found,
        "basis": basis_info["basis"],
        "basis_unit": basis_info["unit"],
        "serving_size": basis_info["serving_size"],
        "normalized_to_per_100": normalized,
        "normalization_factor": round(factor, 4),
        "needs_review": needs_review,
        "ocr_ambiguous_fields": ambiguous_fields,
        "inconsistent_fields": inconsistent_fields,
        "dv_resolved_fields": dv_resolved_fields,
        "subset_resolved_fields": subset_resolved,
        "note": note,
    }


def to_inr_input(nutrition):
    """Map extracted nutrition to the INR engine's input shape."""
    values = nutrition.get("values", {})

    def get(field):
        entry = values.get(field)
        return entry["value"] if entry else None

    return {
        "energy_kcal": get("energy_kcal"),
        "protein_g": get("protein_g"),
        "carbohydrate_g": get("carbohydrate_g"),
        "total_sugars_g": get("total_sugar_g"),
        "added_sugar_g": get("added_sugar_g"),
        "total_fat_g": get("total_fat_g"),
        "saturated_fat_g": get("saturated_fat_g"),
        "trans_fat_g": get("trans_fat_g"),
        "sodium_mg": get("sodium_mg"),
        "dietary_fiber_g": get("fibre_g"),
        "cholesterol_mg": get("cholesterol_mg"),
    }
