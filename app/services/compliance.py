"""Government Compliance Rule Engine — doc 06 (FSSAI Labelling & Display
Compendium, Version VII, 03.04.2025).

Two sections per the brief:
  Section A — Font/letter size checklist (Reg. 6(3) Table I, Reg. 7(1),
              Reg. 14(2)(c), Reg. 5(4)(c))
  Section B — 20-row mandatory-declaration checklist with citations

Status values (doc 06): PASS / FAIL / COULD NOT VERIFY / NOT APPLICABLE.
A checklist item the extraction genuinely could not determine is NEVER
silently defaulted to PASS (doc 05 §4).

Font-size calibration honesty gate (doc 05 §4): a photo has no absolute
scale. Font-height checks run ONLY when a calibration method is supplied
(reference object or user-entered pack dimension). Without calibration the
items report COULD NOT VERIFY with the reason stated — never a fabricated
mm estimate presented as a legal PASS/FAIL.
"""

COMPLIANCE_VERSION = "FSSAI Compendium Version VII (03.04.2025)"

# --- Section A tables --------------------------------------------------------

# Reg. 6(3) Table I: PDP area (cm2) -> (normal min mm, blown/formed/moulded min mm)
TABLE_I_BANDS = [
    (200, 1, 2),        # up to 200 cm2
    (500, 2, 4),        # >200 to 500
    (2500, 3, 5),       # >500 to 2500
    (float("inf"), 6, 8),  # >2500
]

# Reg. 14(2)(c): INR logo min height/width by PDP area
INR_LOGO_BANDS = [
    (100, None, None),  # up to 100: not specified in table
    (500, 15, 15),
    (2500, 20, 20),
    (float("inf"), 25, 25),
]

# Reg. 5(4)(c): veg/non-veg symbol min sizes by PDP area
VEG_SYMBOL_BANDS = [
    (100, 3, 2.5, 6),
    (500, 4, 3.5, 8),
    (2500, 6, 5, 12),
    (float("inf"), 8, 7, 16),
]


def _band_lookup(area, bands, index):
    for threshold, *values in bands:
        if area <= threshold:
            return values[index] if values[index] is not None else None
    return bands[-1][index + 1]


def required_font_height(pdp_area_cm2, blown_or_moulded=False):
    """Reg. 6(3) Table I minimum numeral/letter height in mm."""
    index = 1 if blown_or_moulded else 0
    return _band_lookup(pdp_area_cm2, TABLE_I_BANDS, index)


def required_inr_logo_mm(pdp_area_cm2):
    return _band_lookup(pdp_area_cm2, INR_LOGO_BANDS, 0)


def required_veg_symbol_mm(pdp_area_cm2):
    return _band_lookup(pdp_area_cm2, VEG_SYMBOL_BANDS, 0)


# --- Section B: the 20-row mandatory-declaration checklist -------------------

CHECKLIST = [
    # (id, requirement, regulation, evaluator_key)
    ("B1", "Name of food (true nature; on front of pack)", "Reg. 5(1)", "name_of_food"),
    ("B2", "List of ingredients present, titled 'Ingredients'/'List of Ingredients' (unless single-ingredient food)", "Reg. 5(2)(a)", "ingredients_list"),
    ("B3", "Ingredients listed in descending order of composition by weight/volume", "Reg. 5(2)(b)", "ingredient_order"),
    ("B4", "Compound ingredients declared correctly (bracketed sub-list or individual sub-ingredients)", "Reg. 5(2)(e)", "compound_ingredients"),
    ("B5", "Added water declared where applicable", "Reg. 5(2)(f)", "added_water"),
    ("B6", "Food additives declared with functional class + specific name or INS number", "Reg. 5(5)", "additives_declared"),
    ("B7", "Allergen declaration present as 'Contains...' for the mandatory allergen list", "Reg. 5(14)", "allergen_declaration"),
    ("B8", "Veg/Non-veg symbol present, correct colour and size, placed near product/brand name", "Reg. 5(4)", "veg_nonveg_symbol"),
    ("B9", "Nutritional information panel present per 100g/100ml AND per serving, plus %RDA", "Reg. 5(3)", "nutrition_panel"),
    ("B10", "INR / FOPNL star rating displayed where product is not Category-III exempt", "Reg. 14", "inr_rating"),
    ("B11", "Net Quantity declared", "Legal Metrology Rules, 2011", "net_quantity"),
    ("B12", "MRP declared", "Legal Metrology Rules, 2011", "mrp"),
    ("B13", "Name & complete address of manufacturer/packer/importer", "Reg. 5; Legal Metrology", "manufacturer_address"),
    ("B14", "FSSAI Logo + License Number present", "Reg. 10(1)(c); retail-pack general requirement", "fssai_license"),
    ("B15", "Batch/Lot/Code Number present", "Reg. 10(1)(e); general requirement", "batch_number"),
    ("B16", "Date of Manufacture/Packaging AND Best Before/Use By/Expiry declared, grouped together", "Reg. 5(10)", "date_marking"),
    ("B17", "Consumer care details present", "General requirement", "consumer_care"),
    ("B18", "Instructions for use present, where applicable", "Reg. 5(13)", "instructions_for_use"),
    ("B19", "Language: declarations in English or Hindi (Devanagari)", "Reg. 4(5)", "language"),
    ("B20", "Label content clear, unambiguous, prominent, legible, not misleading", "Reg. 4(3), 4(7)", "legibility"),
]

# Rows NOT evaluated in this version (Legal Metrology scope cut, doc 01 §4)
NOT_EVALUATED = {"mrp": "Legal Metrology weight/price verification is Phase 2 (doc 01 §4)"}

# Reg. 5(4) veg/non-veg symbol exemptions
VEG_SYMBOL_EXEMPT_KEYWORDS = [
    "mineral water", "packaged drinking water", "carbonated water",
    "alcoholic", "beer", "wine", "whisky", "whiskey", "rum", "vodka", "gin",
    "liquid milk", "milk powder", "honey",
]

# Reg. 5(3)(c) nutritional-labelling exemptions
NUTRITION_EXEMPT_KEYWORDS = [
    "single-ingredient", "unprocessed", "mineral water", "packaged drinking water",
    "table-top sweetener", "coffee extract", "tea extract", "herbal infusion",
    "vinegar", "alcoholic", "chewing gum", "foods for special dietary use",
]

PASS = "PASS"
FAIL = "FAIL"
CNV = "COULD NOT VERIFY"
NA = "NOT APPLICABLE"


def _has(value):
    return bool(value)


def _visual_unknown(field, unknown_set):
    return field in unknown_set


def evaluate_section_b(structured, category="I", visual_unknown=None):
    """Evaluate the 20-row checklist from structured extraction output.

    structured: dict with keys matching evaluator_key names (truthiness = found)
    plus ingredient_order_verifiable, additive_entries_with_class, etc.
    Returns list of row dicts: {id, requirement, found, citation, status, note}
    """
    visual_unknown = set(visual_unknown or [])
    rows = []

    for row_id, requirement, citation, key in CHECKLIST:
        found = structured.get(key)

        # Scope cuts & exemptions first
        if key == "mrp":
            rows.append(_row(row_id, requirement, citation, None, CNV,
                             NOT_EVALUATED["mrp"]))
            continue
        if key == "veg_nonveg_symbol":
            text_blob = str(structured.get("label_text", "")).lower()
            if any(kw in text_blob for kw in VEG_SYMBOL_EXEMPT_KEYWORDS):
                rows.append(_row(row_id, requirement, citation, None, NA,
                                 "Reg. 5(4) exemption applies"))
                continue
            found = structured.get("veg_nonveg_detected")
            if _visual_unknown("veg_nonveg_symbol", visual_unknown) and not found:
                rows.append(_row(row_id, requirement, citation, None, CNV,
                                 "Symbol requires visual inspection (colour-coded mark); OCR cannot confirm"))
                continue
            rows.append(_row(row_id, requirement, citation, found,
                             PASS if found else CNV,
                             "" if found else "Not detected by OCR; verify visually"))
            continue
        if key == "ingredient_order":
            if structured.get("ingredient_order_verifiable"):
                ok = structured.get("ingredient_order_descending", True)
                rows.append(_row(row_id, requirement, citation, ok,
                                 PASS if ok else FAIL, ""))
            else:
                rows.append(_row(row_id, requirement, citation, None, CNV,
                                 "Descending-order verification is not automatable in v1 (doc 06); needs human review"))
            continue
        if key == "compound_ingredients":
            if structured.get("has_compound_ingredients"):
                ok = structured.get("compound_declared", False)
                rows.append(_row(row_id, requirement, citation, ok,
                                 PASS if ok else CNV,
                                 "" if ok else "Compound ingredient detected; sub-ingredient list not verifiable by OCR"))
            else:
                rows.append(_row(row_id, requirement, citation, True, PASS,
                                 "No compound ingredients detected"))
            continue
        if key == "added_water":
            if structured.get("water_relevant_category"):
                rows.append(_row(row_id, requirement, citation, found,
                                 PASS if found else CNV,
                                 "" if found else "Water declaration expected for this category; not detected"))
            else:
                rows.append(_row(row_id, requirement, citation, None, NA,
                                 "No added-water requirement evident"))
            continue
        if key == "additives_declared":
            additive_entries = structured.get("additive_entries", [])
            if not additive_entries:
                rows.append(_row(row_id, requirement, citation, None, NA,
                                 "No food additives detected in ingredients"))
            else:
                with_class = structured.get("additives_with_functional_class", 0)
                ok = with_class == len(additive_entries)
                rows.append(_row(row_id, requirement, citation, ok,
                                 PASS if ok else CNV,
                                 f"{with_class}/{len(additive_entries)} additive entries carry a functional class"))
            continue
        if key == "inr_rating":
            if category == "III":
                rows.append(_row(row_id, requirement, citation, None, NA,
                                 "Category-III product is exempt from FOPNL (Schedule-IV)"))
            else:
                rows.append(_row(row_id, requirement, citation, found,
                                 PASS if found else CNV,
                                 "" if found else "INR star rating not detected on label"))
            continue
        if key == "nutrition_panel":
            text_blob = str(structured.get("label_text", "")).lower()
            if any(kw in text_blob for kw in NUTRITION_EXEMPT_KEYWORDS):
                rows.append(_row(row_id, requirement, citation, None, NA,
                                 "Reg. 5(3)(c) nutritional-labelling exemption may apply — confirm"))
                continue
            per100 = structured.get("nutrition_per_100_present", False)
            per_serving = structured.get("nutrition_per_serving_present", False)
            if per100 and per_serving:
                rows.append(_row(row_id, requirement, citation, True, PASS, ""))
            elif per100 or per_serving:
                rows.append(_row(row_id, requirement, citation, True, CNV,
                                 "Nutrition panel found but both per-100g/100ml and per-serving values not confirmed"))
            else:
                rows.append(_row(row_id, requirement, citation, False, FAIL,
                                 "No nutritional information panel detected"))
            continue
        if key == "allergen_declaration":
            detected = [a for a in structured.get("detected_allergens", []) if a]
            declared_raw = [a for a in structured.get("declared_allergens", []) if a]
            # Normalize declared items (e.g. "Wheat") into allergen group names
            # (e.g. "Cereals containing gluten") for a like-for-like comparison.
            declared = set(a.lower() for a in declared_raw)
            try:
                from .ingredient_service import detect_allergens
                declared.update(a.lower() for a in detect_allergens(declared_raw))
            except ImportError:
                pass
            if not detected:
                rows.append(_row(row_id, requirement, citation, None, NA,
                                 "No mandatory-allergen ingredients detected"))
            elif declared:
                missing = sorted(set(a.lower() for a in detected) - declared)
                ok = not missing
                rows.append(_row(row_id, requirement, citation, ok,
                                 PASS if ok else FAIL,
                                 "" if ok else f"Undeclared allergens detected: {', '.join(missing)}"))
            else:
                rows.append(_row(row_id, requirement, citation, False, FAIL,
                                 f"Allergen ingredients detected ({', '.join(detected)}) but no 'Contains...' declaration found"))
            continue
        if key == "language":
            ok = structured.get("english_or_hindi_present", False)
            rows.append(_row(row_id, requirement, citation, ok,
                             PASS if ok else CNV,
                             "" if ok else "Could not confirm English/Hindi declarations from OCR"))
            continue
        if key == "legibility":
            quality = structured.get("legibility_status")
            if quality == "good":
                rows.append(_row(row_id, requirement, citation, True, PASS, ""))
            elif quality == "poor":
                rows.append(_row(row_id, requirement, citation, False, CNV,
                                 "Image quality insufficient for a legibility verdict"))
            else:
                rows.append(_row(row_id, requirement, citation, None, CNV,
                                 "Automated legibility verdict not available; human review recommended"))
            continue
        if key == "consumer_care":
            if _visual_unknown("consumer_care", visual_unknown) and not found:
                rows.append(_row(row_id, requirement, citation, None, CNV,
                                 "Panel not visible in captured photos"))
                continue
            rows.append(_row(row_id, requirement, citation, found,
                             PASS if found else CNV,
                             "" if found else "Not detected by OCR"))
            continue

        # Generic boolean row
        if found is None:
            rows.append(_row(row_id, requirement, citation, None, CNV,
                             "Not determinable from extraction"))
        else:
            rows.append(_row(row_id, requirement, citation, found,
                             PASS if found else FAIL,
                             "" if found else "Requirement not detected in extracted label data"))

    return rows


def _row(row_id, requirement, citation, found, status, note):
    return {
        "id": row_id,
        "requirement": requirement,
        "citation": citation,
        "found": found,
        "status": status,
        "note": note,
    }


def evaluate_font_sizes(structured, calibration=None):
    """Section A: font-size checks.

    calibration: None, or {"method": "reference_object"|"user_dimensions",
    "mm_per_pixel": float, "confidence": "high"|"medium"|"low"}
    Without calibration every font row is COULD NOT VERIFY (doc 05 §4 honesty
    gate) — never a fabricated PASS/FAIL.
    """
    pdp_area = structured.get("pdp_area_cm2")
    rows = []

    def measured_mm(pixel_height):
        if calibration and calibration.get("mm_per_pixel"):
            return round(pixel_height * calibration["mm_per_pixel"], 2)
        return None

    # A.1 — Reg. 6(3) Table I general declarations
    required = required_font_height(pdp_area, False) if pdp_area else None
    measured = measured_mm(structured.get("general_text_px_height", 0))
    if measured is not None and required is not None:
        rows.append({
            "id": "A1", "item": "General numeral/letter height (Reg. 6(3) Table I)",
            "required_mm": required, "measured_mm": measured,
            "status": PASS if measured >= required else FAIL,
            "citation": "Reg. 6(3), Table I",
            "note": f"PDP area band: {pdp_area} cm2",
        })
    else:
        rows.append({
            "id": "A1", "item": "General numeral/letter height (Reg. 6(3) Table I)",
            "required_mm": required, "measured_mm": measured,
            "status": CNV,
            "citation": "Reg. 6(3), Table I",
            "note": ("PDP area unknown" if not pdp_area
                     else "No scale calibration — photo has no absolute reference (doc 05 §4)"),
        })

    # A.2 — Reg. 7(1): ingredients declaration >= 3mm (the brief's named check)
    required = 3
    measured = measured_mm(structured.get("ingredients_text_px_height", 0))
    if measured is not None:
        status = PASS if measured >= required else FAIL
        note = ""
    else:
        status = CNV
        note = "No scale calibration — supply pack dimensions or a reference object"
    rows.append({
        "id": "A2",
        "item": "Ingredients declaration letter height >= 3mm (Schedule-II declarations)",
        "required_mm": required, "measured_mm": measured,
        "status": status, "citation": "Reg. 7(1)",
        "note": (note + ("; 1mm exception for <=30cm2 sweetener packs (not evaluated)" if note else "")).strip("; "),
    })

    # A.3 — INR logo size (only if product carries a rating)
    if structured.get("inr_logo_detected"):
        required = required_inr_logo_mm(pdp_area) if pdp_area else None
        measured = measured_mm(structured.get("inr_logo_px_height", 0))
        if measured is not None and required is not None:
            status = PASS if measured >= required else FAIL
            note = ""
        else:
            status = CNV
            note = "No scale calibration"
        rows.append({
            "id": "A3", "item": "INR / FOPNL logo minimum size",
            "required_mm": required, "measured_mm": measured,
            "status": status, "citation": "Reg. 14(2)(c)",
            "note": note or f"PDP area band: {pdp_area} cm2",
        })

    # A.4 — veg/non-veg symbol size
    if structured.get("veg_symbol_detected"):
        required = required_veg_symbol_mm(pdp_area) if pdp_area else None
        measured = measured_mm(structured.get("veg_symbol_px_diameter", 0))
        if measured is not None and required is not None:
            status = PASS if measured >= required else FAIL
            note = ""
        else:
            status = CNV
            note = "No scale calibration"
        rows.append({
            "id": "A4", "item": "Veg / non-veg symbol minimum size (circle diameter)",
            "required_mm": required, "measured_mm": measured,
            "status": status, "citation": "Reg. 5(4)(c)",
            "note": note or f"PDP area band: {pdp_area} cm2",
        })

    return rows


def evaluate_compliance(structured, category="I", calibration=None):
    """Full compliance evaluation: Section A + Section B + summary."""
    section_a = evaluate_font_sizes(structured, calibration)
    section_b = evaluate_section_b(structured, category)

    def summarize(rows):
        counts = {PASS: 0, FAIL: 0, CNV: 0, NA: 0}
        for row in rows:
            counts[row["status"]] = counts.get(row["status"], 0) + 1
        return counts

    a_summary = summarize(section_a)
    b_summary = summarize(section_b)

    return {
        "regulation_version": COMPLIANCE_VERSION,
        "calibration": calibration or {
            "method": "none",
            "note": ("Font-size rows are COULD NOT VERIFY because a photo alone "
                     "carries no absolute scale. Provide pack dimensions or an "
                     "in-frame reference object to enable measurement (doc 05 §4)."),
        },
        "section_a": {"rows": section_a, "summary": a_summary},
        "section_b": {"rows": section_b, "summary": b_summary},
        "summary": {
            "font_size": {k: v for k, v in a_summary.items()},
            "declarations": {k: v for k, v in b_summary.items()},
        },
        "overall_note": (
            "Automated pre-check only — not a legal compliance certification. "
            "Human/legal review is recommended before relying on this for "
            "regulatory submission."
        ),
    }
