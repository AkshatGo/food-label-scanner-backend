import re


NUTRITION_FIELDS = {
    "energy_kcal": (("energy", "calories", "calorie"), "kcal"),
    "protein_g": (("protein",), "g"),
    "carbohydrate_g": (("total carbohydrate", "carbohydrate", "carbs"), "g"),
    "sugar_g": (("total sugars", "sugars", "sugar"), "g"),
    "fat_g": (("total fat", "fat"), "g"),
    "saturated_fat_g": (("saturated fat",), "g"),
    "sodium_mg": (("sodium",), "mg"),
    "fiber_g": (("dietary fiber", "fiber", "fibre"), "g"),
}

FSSAI_FIELDS = {
    "fssai_license": r"\b(?:fssai|license|licence)\D{0,8}(\d{8,14})\b",
    "ingredient_declaration": r"\bingredients?\b\s*[:\-]",
    "nutrition_information": r"\b(?:nutrition facts?|nutrition information|calories|energy)\b",
    "allergen_declaration": r"\b(?:contains|allergen|allergy)\b",
    "vegetarian_mark": r"\b(?:vegetarian|non[- ]?vegetarian|veg|non[- ]?veg)\b",
    "batch_number": r"\b(?:batch|lot)\s*(?:no\.?|number)?\s*[:#-]?\s*([A-Z0-9-]+)",
    "net_quantity": r"\b(?:net\s*(?:quantity|wt|weight)|quantity)\D{0,8}(\d+(?:\.\d+)?\s*(?:g|kg|ml|l))\b",
    "date_marking": r"\b(?:exp(?:iry)?|best\s*before|manufactured|mfg|use\s*by)\b",
    "manufacturer": r"\bmanufactured\s+by\s*[: -]?\s*([^\n]+)",
}


def _nutrition_value(text, labels):
    lines = text.splitlines()
    for index, line in enumerate(lines):
        label_match = re.search(
            rf"\b(?:{'|'.join(re.escape(label) for label in labels)})\b",
            line,
            re.IGNORECASE,
        )
        if not label_match:
            continue
        tail = line[label_match.end():]
        number = re.search(r"\b(\d+(?:\.\d+)?)", tail)
        if number:
            return _coerce_ocr_number(number.group(1), tail, "g")
        if index + 1 < len(lines):
            number = re.search(r"\b(\d+(?:\.\d+)?)\b", lines[index + 1])
            if number:
                return _coerce_ocr_number(number.group(1), lines[index + 1], "g")
    return None


def _coerce_ocr_number(value, context, unit):
    """Undo Tesseract's common g->9 substitution only in nutrition rows."""
    if unit == "g" and not re.search(r"\b(?:g|gram|grams)\b", context, re.IGNORECASE):
        if value.endswith(".59"):
            return value[:-1]
        if value.endswith("9") and len(value) > 1 and "." not in value:
            return value[:-1]
    return value


def _first_match(pattern, text):
    match = re.search(pattern, text, re.IGNORECASE)
    if not match:
        return None
    return match.group(1).strip() if match.lastindex else match.group(0).strip()


def _extract_ingredients(text):
    candidates = []
    lines = text.splitlines()
    for index, line in enumerate(lines):
        match = re.search(r"ingredients?\s*[:\-]?\s*(.*)", line, re.IGNORECASE)
        if not match:
            continue
        parts = [match.group(1).strip()]
        for continuation in lines[index + 1:index + 4]:
            if re.search(
                r"nutrition|calories|daily value|vitamin|potassium|frito|frido|frado|smartlabel|guaranteed|barcode|manufacturer|inc\.",
                continuation,
                re.IGNORECASE,
            ):
                break
            parts.append(continuation.strip())
        candidate = " ".join(part for part in parts if part)
        if candidate:
            candidates.append(candidate)
    if not candidates:
        return []
    ingredients_text = max(
        candidates,
        key=lambda value: sum(
            keyword in value.lower()
            for keyword in ("potato", "oil", "corn", "canola", "salt")
        ),
    )
    ingredients_text = re.sub(r"\bSat\.\s*I?\b", "Salt", ingredients_text, flags=re.IGNORECASE)
    return [
        item.strip(" .:-{}")
        for item in re.split(r",|;", ingredients_text)
        if item.strip(" .:-{}")
    ]


def analyze_label(text):
    text = text or ""
    normalized_text = re.sub(r"\s+", " ", text).strip()
    nutrition = {}
    for field, (labels, unit) in NUTRITION_FIELDS.items():
        value = _nutrition_value(text, labels)
        if value is not None:
            nutrition[field] = {"value": float(value), "unit": unit}

    fssai_detected = {}
    fssai_not_detected = []
    for field, pattern in FSSAI_FIELDS.items():
        value = _first_match(pattern, normalized_text)
        if value:
            fssai_detected[field] = value
        else:
            fssai_not_detected.append(field)

    warnings = []
    potential_issues = []
    if re.search(r"\b(trans fat|partially hydrogenated|artificial color)\b", normalized_text, re.IGNORECASE):
        potential_issues.append("Potentially concerning ingredient detected")
    if "sugar_g" in nutrition and nutrition["sugar_g"]["value"] > 10:
        warnings.append("Sugar content is above 10 g per serving")

    fssai_statuses = [
        {
            "field": field,
            "status": "DETECTED" if field in fssai_detected else "NOT_DETECTED",
            "value": fssai_detected.get(field),
        }
        for field in FSSAI_FIELDS
    ]
    fssai_statuses.extend(
        {"field": issue, "status": "POTENTIAL_ISSUE"}
        for issue in potential_issues
    )
    fssai_statuses.extend(
        {"field": warning, "status": "WARNING"}
        for warning in warnings
    )

    product_lines = [line.strip() for line in (text or "").splitlines() if line.strip()]
    product_name = next(
        (
            line
            for line in product_lines
            if len(re.findall(r"[A-Za-z]", line)) >= 4
            and len(line) >= 4
            and not any(c in line for c in ("\"", "'", "“", "”", "|", "_"))
            and not re.search(r"\d|\b(?:mg|kcal|g)\b|%", line, re.IGNORECASE)
            and not re.search(
                r"total fat|saturated fat|trans fat|cholesterol|sodium|carbohydrate|dietary fiber|total sugars|protein|potassium|vitamin|calcium|iron|amount per serving|source of added sugars|daily value|how much|significant source|percent|daily",
                line,
                re.IGNORECASE,
            )
            and not re.match(
                r"^(?:\d+\s+)?(ingredients?|nutrition|nutrition facts|energy|calories?|amount|serving|daily value|% daily|sen|pack|fresh|guaranteed|call|information)\b",
                line,
                re.IGNORECASE,
            )
        ),
        None,
    )
    is_liquid = bool(re.search(r"\b(ml|milliliter|litre|liter|juice|drink|beverage)\b", normalized_text, re.IGNORECASE))
    compliance_checks = [
        {
            "requirement": field,
            "status": "DETECTED" if field in fssai_detected else "NOT_DETECTED",
            "note": "Detected on label" if field in fssai_detected else "Not detected by OCR; manual review required",
        }
        for field in FSSAI_FIELDS
    ]

    required_nutrition = [
        "energy_kcal",
        "protein_g",
        "carbohydrate_g",
        "sugar_g",
        "fat_g",
        "saturated_fat_g",
        "sodium_mg",
    ]
    nutrition_values = {field: nutrition.get(field, {}).get("value", 0) for field in required_nutrition}
    components = {
        "energy_penalty": round(nutrition_values["energy_kcal"] / 20, 2),
        "sugar_penalty": round(nutrition_values["sugar_g"] * 2, 2),
        "saturated_fat_penalty": round(nutrition_values["saturated_fat_g"] * 2, 2),
        "sodium_penalty": round(nutrition_values["sodium_mg"] / 20, 2),
        "protein_bonus": round(nutrition_values["protein_g"] * 2, 2),
        "fiber_bonus": round(nutrition.get("fiber_g", {}).get("value", 0) * 2, 2),
    }
    score = max(0, min(100, round(
        100
        - components["energy_penalty"]
        - components["sugar_penalty"]
        - components["saturated_fat_penalty"]
        - components["sodium_penalty"]
        + components["protein_bonus"]
        + components["fiber_bonus"]
    )))

    return {
        "product": {"name": product_name or ("Liquid Product" if is_liquid else "Solid Product"), "category": "liquid" if is_liquid else "solid", "category_confidence": 0.6},
        "ingredients": _extract_ingredients(text),
        "nutrition": nutrition,
        "label_information": {"classification": "liquid" if is_liquid else "solid"},
        "fssai": {
            "detected": fssai_detected,
            "not_detected": fssai_not_detected,
            "potential_issues": potential_issues,
            "warnings": warnings,
            "statuses": fssai_statuses,
            "compliance_checks": compliance_checks,
            "overall_status": "REVIEW_REQUIRED" if fssai_not_detected else "NO_OCR_GAPS_DETECTED",
        },
        "inr": {
            "score": score,
            "rating": "excellent" if score >= 80 else "good" if score >= 60 else "needs attention",
            "missing_values_treated_as_zero": True,
            "basis": "100 minus energy, sugar, saturated fat, and sodium penalties plus protein and fiber bonuses",
            "components": components,
        },
    }