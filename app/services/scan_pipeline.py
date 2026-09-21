"""Scan pipeline: OCR -> cleanup -> extraction -> classification -> scoring.

Orchestrates the whole analysis per doc 03 §3 (data flow steps 2-9). The
heavy OCR step runs in a worker thread (asyncio.to_thread) so the event loop
stays responsive (doc 03 §6).
"""

import re

from .category_classifier import classify_category
from .compliance import evaluate_compliance
from .fssai_rating import calculate_inr
from .ingredient_service import curate_ingredients
from .nutrition_extractor import extract_nutrition, to_inr_input


def _first(patterns, text, flags=re.IGNORECASE):
    for pattern in patterns:
        match = re.search(pattern, text, flags)
        if match:
            return match.group(1).strip() if match.lastindex else match.group(0).strip()
    return None


def _extract_product_name(text):
    """Heuristic front-of-pack product-name detection from OCR lines."""
    skip_re = re.compile(
        r"total fat|saturated fat|trans fat|cholesterol|sodium|carbohydrate|"
        r"dietary fib|total sugars|protein|vitamin|calcium|iron|potassium|"
        r"energy|calories|ingredients|nutrition|per\s|serving|net\s*(wt|weight|qty)|"
        r"mrp|fssai|batch|lot|best\s*before|use\s*by|mfg|expiry|exp\b|"
        r"manufactured|marketed|consumer\s+care|store\s+in|contains\b|"
        r"brand\s*[:%]|\d+(?:\.\d+)?\s*(?:g|mg|kcal|kj)\b|%",
        re.IGNORECASE,
    )
    for line in (text or "").splitlines():
        line = line.strip()
        if len(line) < 4:
            continue
        letters = re.findall(r"[A-Za-z]", line)
        if len(letters) < 4:
            continue
        if any(char in line for char in ('"', "'|", "|", "_")):
            continue
        if re.search(r"\d", line) and not re.match(r"^[A-Za-z]", line):
            continue
        if skip_re.search(line):
            continue
        return line
    return None


def _product_identity(text):
    """Extract product name / brand / net quantity / dates / license."""

    product_name = _extract_product_name(text) or "Scanned Product"

    brand = _first([r"\b(?:brand|marketed\s+by)\s*[:\-]?\s*([A-Za-z][A-Za-z0-9 &.]{2,40})"], text)

    net = re.search(
        r"net\s*(?:wt|weight|qty|quantity)\s*[:#\-]?\s*(\d+(?:\.\d+)?)\s*(kg|g|l|ml)\b",
        text, re.IGNORECASE,
    )
    net_quantity = f"{net.group(1)}{net.group(2)}" if net else None

    fssai_license = _first([
        r"fssai[^0-9]{0,15}(\d{10,14})",
        r"lic(?:en[cs]e)?\s*no?[^0-9]{0,8}(\d{10,14})",
    ], text)

    mrp = _first([r"(?:mrp|maximum\s+retail)\s*(?:price)?\s*[:\-]?\s*(?:rs\.?|₹)?\s*(\d+(?:\.\d+)?)"], text)

    dates = re.search(
        r"(?:mfg|mfd|manufactured|packed|pkd)[^\n0-9]{0,15}"
        r"(\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|[A-Za-z]{3,9}\.?\s*\d{4})",
        text, re.IGNORECASE,
    )
    best_before = re.search(
        r"(?:best\s*before|expiry|exp|use\s*by)[^\n0-9A-Za-z]{0,15}"
        r"(\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|[A-Za-z]{3,9}\.?\s*\d{4}|\d+\s*(?:months?|years?|days?))",
        text, re.IGNORECASE,
    )

    batch = _first(
        [r"(?:batch|lot|code)\s*(?:no\.?|number)?\s*[:#\-]?\s*([A-Za-z0-9/-]{2,20})"],
        text,
    )

    manufacturer = _first(
        [r"\bmanufactured\s+by\s*[:\-]?\s*([^\n]{4,80})"],
        text,
    )

    consumer_care = _first(
        [r"(?:consumer\s+care|customer\s+care|contact)[^\n:]{0,20}[:\-]?\s*([^\n]{4,60})"],
        text,
    )

    return {
        "product_name": product_name,
        "brand": brand,
        "net_quantity": net_quantity,
        "fssai_license_no": fssai_license,
        "mrp": mrp,
        "manufacturing_date": dates.group(1) if dates else None,
        "best_before": best_before.group(1) if best_before else None,
        "batch_number": batch,
        "manufacturer": manufacturer,
        "consumer_care": consumer_care,
    }


def _has_ingredients_title(text):
    return bool(re.search(r"\b(?:list\s+of\s+)?ingredients?\b\s*[:\-]?", text, re.IGNORECASE))


def _detect_veg_symbol(text):
    return bool(re.search(
        r"\b(?:veg(?:etarian)?\s*(?:logo|symbol|mark)?|non[-\s]?veg(?:etarian)?|green\s*dot|brown\s*dot)\b",
        text, re.IGNORECASE,
    ))


def _english_or_hindi(text):
    return bool(re.search(r"[A-Za-z]{3,}", text))  # Latin-script detection


def build_structured_product(ocr_text, ocr_confidence=None):
    """Turn cleaned OCR text into the structured product dict (doc 03 §3.4)."""
    text = ocr_text or ""
    identity = _product_identity(text)

    nutrition = extract_nutrition(text)
    inr_input = to_inr_input(nutrition)

    classification = classify_category(text, identity["product_name"] or "")
    category = classification["category"]
    if (category == "II" and nutrition["basis_unit"] == "g"
            and re.search(r"\b(?:beverage\s+mix|drink\s+mix|powder)\b", text, re.I)):
        nutrition["needs_review"] = True
        nutrition["note"] = (
            "Nutrition is declared per 100 g of dry mix. A prepared-drink rating "
            "requires its dilution and nutrition basis to be verified."
        )

    # A per-100g beverage-mix panel describes the dry powder, not the prepared
    # drink; the rating is honest but the basis must be surfaced to the user.
    if (category == "II" and nutrition["basis_unit"] == "g"
            and re.search(r"\b(?:beverage\s+mix|drink\s+mix|powder)\b", text, re.I)):
        nutrition["needs_review"] = True
        nutrition["note"] = (
            "Nutrition is declared per 100 g of dry mix. A prepared-drink rating "
            "requires its dilution and nutrition basis to be verified."
        )

    # Ingredient curation
    ingredients_match = re.search(
        r"(?:list\s+of\s+)?ingredients?\s*[:\-]?\s*(.*?)(?:\n\s*\n|$)",
        text, re.IGNORECASE | re.DOTALL,
    )
    raw_ingredients = []
    if ingredients_match:
        block = ingredients_match.group(1)
        block = re.split(r"\n\s*(?:nutrition|fssai|batch|lot|mfg|expiry|contains|may contain|mrp|net)",
                         block, flags=re.IGNORECASE)[0]
        raw_ingredients = [
            part.strip(" .;:-")
            for part in re.split(r",|;", block)
            if part.strip(" .;:-")
        ]
    curated_ingredients, detected_allergens = curate_ingredients(raw_ingredients)

    declared_contains = _first([r"\bcontains\s*[:\-]?\s*([A-Za-z ,&]{3,100})"], text)
    declared_allergens = (
        [part.strip() for part in re.split(r",|&|\band\b", declared_contains, flags=re.IGNORECASE) if part.strip()]
        if declared_contains else []
    )

    # INR scoring (Category-III short-circuits inside the engine)
    inr = calculate_inr(
        inr_input,
        category="liquid" if category == "II" else "solid",
        exempt=(category == "III"),
        is_beverage=classification["is_beverage"],
    )

    per100 = {
        "energy_kcal": inr_input["energy_kcal"],
        "protein_g": inr_input["protein_g"],
        "carbohydrate_g": inr_input["carbohydrate_g"],
        "total_sugar_g": inr_input["total_sugars_g"],
        "added_sugar_g": inr_input["added_sugar_g"],
        "total_fat_g": inr_input["total_fat_g"],
        "saturated_fat_g": inr_input["saturated_fat_g"],
        "trans_fat_g": inr_input["trans_fat_g"],
        "sodium_mg": inr_input["sodium_mg"],
        "fibre_g": inr_input["dietary_fiber_g"],
        "fv_percent": 0,
        "nlm_percent": 0,
    }

    product = {
        "product_id": None,  # assigned by the caller/persistence layer
        "product_name": identity["product_name"],
        "brand": identity["brand"],
        "category": category,
        "category_basis": classification["basis"],
        "category_confidence": classification["confidence"],
        "mrp": identity["mrp"],
        "net_quantity": identity["net_quantity"],
        "manufacturer": identity["manufacturer"],
        "manufacturing_date": identity["manufacturing_date"],
        "best_before": identity["best_before"],
        "batch_number": identity["batch_number"],
        "fssai_license_no": identity["fssai_license_no"],
        "consumer_care": identity["consumer_care"],
        "ingredients": curated_ingredients,
        "allergens": {
            "detected": detected_allergens,
            "declared": declared_allergens,
        },
        "nutrition_per_100g": per100,
        "nutrition_extraction": {
            "basis": nutrition["basis"],
            "basis_unit": nutrition["basis_unit"],
            "panel_found": nutrition.get("panel_found", bool(nutrition.get("values"))),
            "normalized_to_per_100": nutrition["normalized_to_per_100"],
            "needs_review": nutrition["needs_review"],
            "ocr_ambiguous_fields": nutrition["ocr_ambiguous_fields"],
            "note": nutrition["note"],
        },
        "inr": inr,
    }
    return product


def build_compliance_input(product, ocr_text, ocr_confidence=None):
    """Assemble the structured dict the compliance engine evaluates."""
    per100 = product.get("nutrition_per_100g", {})
    # The per-100 dict always carries keys (None when not extracted), so its
    # bare truthiness is always True. B9 must FAIL when nothing was actually
    # extracted, so presence means at least one core value is a real number.
    nutrition_present = any(
        per100.get(k) is not None
        for k in ("energy_kcal", "protein_g", "carbohydrate_g", "total_sugar_g",
                  "total_fat_g", "saturated_fat_g", "sodium_mg")
    )
    text_lower = (ocr_text or "").lower()

    return {
        "label_text": ocr_text or "",
        "name_of_food": bool(product.get("product_name")),
        "ingredients_list": _has_ingredients_title(ocr_text or ""),
        "ingredient_order_verifiable": False,  # not automatable in v1 (doc 06)
        "has_compound_ingredients": bool(re.search(r"\([^)]{6,}\)", ocr_text or "")),
        "compound_declared": bool(re.search(r"\([^)]*(?:contains|ingredients)[^)]*\)", ocr_text or "", re.IGNORECASE)),
        "water_relevant_category": bool(re.search(r"\b(instant|powder|concentrate|mix)\b", text_lower)),
        "additive_entries": [
            entry for entry in product.get("ingredients", [])
            if isinstance(entry, dict) and entry.get("ins_number")
        ],
        "additives_with_functional_class": sum(
            1 for entry in product.get("ingredients", [])
            if isinstance(entry, dict) and entry.get("ins_number") and entry.get("function")
        ),
        "detected_allergens": product.get("allergens", {}).get("detected", []),
        "declared_allergens": product.get("allergens", {}).get("declared", []),
        "veg_nonveg_detected": _detect_veg_symbol(ocr_text or ""),
        "veg_symbol_detected": _detect_veg_symbol(ocr_text or ""),
        "inr_rating": bool(product.get("inr", {}).get("eligible")),
        "nutrition_per_100_present": nutrition_present,
        "nutrition_per_serving_present": bool(re.search(
            r"per\s+(?:serving|pack|packet|sachet|cup|container)", text_lower)),
        "net_quantity": bool(product.get("net_quantity")),
        "mrp": bool(product.get("mrp")),
        "manufacturer_address": bool(product.get("manufacturer")),
        "fssai_license": bool(product.get("fssai_license_no")),
        "batch_number": bool(product.get("batch_number")),
        "date_marking": bool(product.get("manufacturing_date") or product.get("best_before")),
        "consumer_care": bool(product.get("consumer_care")),
        "instructions_for_use": bool(re.search(
            r"\b(?:instructions?|directions?\s+for\s+use|refrigerate after opening|store in)\b",
            text_lower)),
        "english_or_hindi_present": _english_or_hindi(ocr_text or ""),
        "legibility_status": "good" if (ocr_confidence or 0) >= 70 else "poor",
    }


def run_scan_pipeline(ocr_text, ocr_confidence=None):
    """Full analysis pass: structured product + compliance evaluation.

    Returns {product, compliance} — persistence assigns IDs.
    """
    product = build_structured_product(ocr_text, ocr_confidence)
    compliance_input = build_compliance_input(product, ocr_text, ocr_confidence)
    compliance = evaluate_compliance(
        compliance_input,
        category=product["category"],
        calibration=None,  # no scale calibration from a photo (doc 05 §4)
    )
    return product, compliance
