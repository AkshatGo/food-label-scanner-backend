"""Offline conservative label-compliance checks based on supplied FSSAI rules."""

import re

MANDATORY_FIELDS = {
    "name_of_food": "Reg. 5(1)", "ingredients_list": "Reg. 5(2)", "nutritional_info": "Reg. 5(3)",
    "veg_nonveg_symbol": "Reg. 5(4)", "manufacturer_or_brand_owner_address": "Reg. 5(6)",
    "fssai_logo_and_license_no": "Reg. 5(7)", "net_quantity": "Reg. 5(8)",
    "batch_lot_or_code_number": "Reg. 5(9)", "date_of_manufacture_or_packaging": "Reg. 5(10)(a)",
    "expiry_or_use_by_date": "Reg. 5(10)(a)", "instructions_for_use": "Reg. 5(13)",
}
ALLERGENS = {"gluten": ("wheat", "rye", "barley", "oats", "maida"), "milk": ("milk", "casein", "whey", "butter", "cream"), "egg": ("egg",), "fish": ("fish",), "nut": ("peanut", "almond", "walnut", "cashew"), "soy": ("soy", "soya"), "sulphite": ("sulphite", "sulfite", "sulphur dioxide")}


def check_allergen_declarations(ingredients, declared_allergens):
    lower = [item.lower() for item in ingredients]; declared = {item.lower() for item in declared_allergens}; detected = sorted(group for group, words in ALLERGENS.items() if any(word in ingredient for ingredient in lower for word in words)); missing = sorted(set(detected) - declared)
    return {"detected_allergens": detected, "declared_allergens": sorted(declared), "missing_declarations": [f"Contains {item.capitalize()}" for item in missing], "is_compliant": not missing}


def check_mandatory_declarations(declared, visual_unknown=None):
    visual_unknown = set(visual_unknown or [])
    present, missing, visual = [], [], []
    for field, reference in MANDATORY_FIELDS.items():
        if field in visual_unknown:
            visual.append({"field": field, "status": "REQUIRES_VISUAL_CHECK", "regulation": reference})
        elif declared.get(field):
            present.append(field)
        else:
            missing.append({"field": field, "status": "NOT_DETECTED", "regulation": reference, "note": "OCR gap; not a legal violation"})
    return {"present": present, "missing": missing, "requires_visual_check": visual, "is_compliant_on_mandatory_fields": not missing}


def full_label_audit(label_data):
    text = label_data.get("label_text", "")
    ingredients = label_data.get("ingredient_names", [])
    declared = label_data.get("declared", {})
    mandatory = check_mandatory_declarations(declared, ["veg_nonveg_symbol", "fssai_logo_and_license_no"])
    allergens = check_allergen_declarations(ingredients, label_data.get("declared_allergens", []))
    misleading = [f"Review potentially misleading claim: {term}" for term in ("super-refined", "100% natural", "cures", "prevents disease") if term in text.lower()]
    return {"mandatory_declarations": mandatory, "allergen_declarations": allergens, "misleading_terms": misleading, "overall_compliant": not mandatory["missing"] and allergens["is_compliant"], "basis": "Food Safety and Standards (Labelling and Display) Regulations, 2020 and supplied draft rule references; OCR review only"}
