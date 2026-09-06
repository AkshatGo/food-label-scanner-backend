"""Orchestrates OCR-cleaned nutrition, label-field, INR and compliance analysis."""

from .fssai_label_rules import full_label_audit
from .fssai_rating import calculate_inr
from .label_field_extractor import extract_label_fields
from .analysis_service import analyze_label
import re


NUTRIENT_ALIASES = {
    "energy_kcal": ("energy", "calories", "calorie"),
    "protein_g": ("protein",),
    "carbohydrate_g": ("total carbohydrate", "carbohydrate", "carbs"),
    "sugar_g": ("total sugars", "total sugar", "sugars", "sugar"),
    "fat_g": ("total fat", "fat"),
    "saturated_fat_g": ("saturated fat",),
    "trans_fat_g": ("trans fat",),
    "sodium_mg": ("sodium",),
    "fiber_g": ("dietary fiber", "dietary fibre", "fiber", "fibre"),
    "cholesterol_mg": ("cholesterol",),
}


def _extract_all_nutrients(text):
    """Keep readable nutrition, vitamin, and mineral rows."""
    labels = [alias for aliases in NUTRIENT_ALIASES.values() for alias in aliases]
    labels.extend(["vitamin", "calcium", "iron", "potassium", "magnesium", "zinc", "iodine", "folate", "biotin", "phosphorus"])
    label_pattern = "|".join(re.escape(label) for label in sorted(labels, key=len, reverse=True))
    row_pattern = re.compile(
        rf"^\s*({label_pattern}(?:\s+[A-Za-z0-9]+){{0,3}})\s*[:\-]?\s*(?:less than\s+)?(\d+(?:\.\d+)?)\s*(kcal|mcg|µg|mg|g|ml)?",
        re.IGNORECASE,
    )
    nutrients = {}
    for line in text.splitlines():
        match = row_pattern.search(line)
        if not match:
            continue
        label = " ".join(match.group(1).split()).lower()
        canonical = next((field for field, aliases in NUTRIENT_ALIASES.items() if label in aliases), re.sub(r"[^a-z0-9]+", "_", label).strip("_"))
        nutrients[canonical] = {
            "value": float(match.group(2)),
            "unit": (match.group(3) or "label-unit-not-detected").replace("µ", "u").lower(),
            "source_label": label,
        }
    return nutrients


def analyze_enhanced(text: str) -> dict:
    base = analyze_label(text)
    fields = extract_label_fields(text)
    category = base["product"]["category"]
    nutrition = _extract_all_nutrients(text)
    # The established parser has bounded OCR corrections for core INR fields
    # such as `g` being read as `9`; keep those canonical values authoritative.
    nutrition.update(base["nutrition"])
    per100 = {
        "energy_kcal": nutrition.get("energy_kcal", {}).get("value"),
        "total_sugars_g": nutrition.get("sugar_g", {}).get("value"),
        "saturated_fat_g": nutrition.get("saturated_fat_g", {}).get("value"),
        "sodium_mg": nutrition.get("sodium_mg", {}).get("value"),
        "dietary_fiber_g": nutrition.get("fiber_g", {}).get("value"),
        "protein_g": nutrition.get("protein_g", {}).get("value"),
    }
    inr = calculate_inr(per100, category=category)
    ingredient_names = fields["ingredients"]["ingredient_names"]
    declared = {
        "name_of_food": base["product"]["name"] is not None,
        "ingredients_list": fields["ingredients"]["has_title"],
        "nutritional_info": bool(nutrition),
        "manufacturer_or_brand_owner_address": fields["manufacturer_statement"],
        "fssai_logo_and_license_no": bool(fields["fssai_license_number"]),
        "net_quantity": bool(fields["net_quantity_value"]),
        "batch_lot_or_code_number": bool(fields["batch_lot_code_number"]),
        "date_of_manufacture_or_packaging": bool(fields["date_marking"]),
        "expiry_or_use_by_date": bool(fields["date_marking"]),
    }
    audit = full_label_audit({
        "category": category,
        "label_text": text,
        "declared": declared,
        "ingredient_names": ingredient_names,
        "declared_allergens": fields["allergens"]["declared_contains"],
    })
    statuses = base["fssai"]["statuses"]
    for item in audit["mandatory_declarations"]["missing"]:
        statuses.append({"field": item["field"], "status": "NOT_DETECTED", "value": None})
    potential = list(base["fssai"]["potential_issues"])
    potential.extend(audit["allergen_declarations"]["missing_declarations"])
    base["fssai"].update({
        "detected": {**base["fssai"]["detected"], **{key: value for key, value in fields.items() if key in {"fssai_license_number", "batch_lot_code_number", "date_marking", "net_quantity_value"} and value}},
        "potential_issues": potential,
        "statuses": statuses,
        "label_fields": fields,
        "compliance_audit": audit,
        "overall_status": "REVIEW_REQUIRED" if audit["overall_compliant"] is not True else "NO_OCR_GAPS_DETECTED",
    })
    base["inr"] = inr
    base["nutrition_details"] = {
        "all_detected_rows": nutrition,
        "note": "Values are OCR-derived and should be checked against the original package.",
    }
    return base
