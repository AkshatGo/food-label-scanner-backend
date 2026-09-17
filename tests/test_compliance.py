"""Compliance engine tests — doc 05 §4.

Covers: font-size honesty gate (no calibration -> COULD NOT VERIFY, never a
fabricated PASS/FAIL), intentionally-flawed labels flagged with the correct
citation, and no false PASS for undeterminable items.
"""

from app.services.compliance import (
    COMPLIANCE_VERSION,
    evaluate_compliance,
    required_font_height,
    required_inr_logo_mm,
    required_veg_symbol_mm,
)


# --- Section A reference tables (doc 06 A.1/A.3/A.4) -----------------------------

def test_table_i_bands():
    assert required_font_height(150) == 1
    assert required_font_height(200) == 1
    assert required_font_height(201) == 2
    assert required_font_height(500) == 2
    assert required_font_height(501) == 3
    assert required_font_height(2500) == 3
    assert required_font_height(2501) == 6


def test_table_i_blown_moulded():
    assert required_font_height(150, blown_or_moulded=True) == 2
    assert required_font_height(300, blown_or_moulded=True) == 4
    assert required_font_height(1000, blown_or_moulded=True) == 5
    assert required_font_height(3000, blown_or_moulded=True) == 8


def test_inr_logo_bands():
    assert required_inr_logo_mm(400) == 15
    assert required_inr_logo_mm(1000) == 20
    assert required_inr_logo_mm(3000) == 25


def test_veg_symbol_bands():
    assert required_veg_symbol_mm(80) == 3
    assert required_veg_symbol_mm(300) == 4
    assert required_veg_symbol_mm(1000) == 6
    assert required_veg_symbol_mm(3000) == 8


# --- Section A honesty gate --------------------------------------------------------

def test_no_calibration_means_could_not_verify():
    """A photo alone carries no absolute scale (doc 05 §4) — never a fabricated PASS."""
    structured = {
        "pdp_area_cm2": 400,
        "general_text_px_height": 40,
        "ingredients_text_px_height": 35,
    }
    result = evaluate_font_sizes_safe(structured)
    assert all(row["status"] == "COULD NOT VERIFY" for row in result)


def evaluate_font_sizes_safe(structured):
    from app.services.compliance import evaluate_font_sizes
    return evaluate_font_sizes(structured, calibration=None)


def test_with_calibration_passes_or_fails():
    from app.services.compliance import evaluate_font_sizes
    calibration = {"method": "user_dimensions", "mm_per_pixel": 0.1}
    structured = {
        "pdp_area_cm2": 400,  # band requires 2mm
        "general_text_px_height": 25,  # 2.5mm measured -> PASS
        "ingredients_text_px_height": 20,  # 2.0mm measured -> FAIL (needs 3mm)
    }
    rows = evaluate_font_sizes(structured, calibration=calibration)
    a1 = next(row for row in rows if row["id"] == "A1")
    a2 = next(row for row in rows if row["id"] == "A2")
    assert a1["status"] == "PASS"
    assert a1["measured_mm"] == 2.5
    assert a2["status"] == "FAIL"
    assert a2["measured_mm"] == 2.0


def test_undersized_ingredient_font_flagged_fail_with_citation():
    """The brief's named check: undersized ingredients font -> FAIL, cited Reg. 7(1)."""
    from app.services.compliance import evaluate_font_sizes
    calibration = {"method": "reference_object", "mm_per_pixel": 0.05}
    rows = evaluate_font_sizes({
        "pdp_area_cm2": 600,
        "general_text_px_height": 80,  # 4.0mm >= 3mm -> PASS
        "ingredients_text_px_height": 40,  # 2.0mm < 3mm -> FAIL
    }, calibration=calibration)
    a2 = next(row for row in rows if row["id"] == "A2")
    assert a2["status"] == "FAIL"
    assert a2["citation"] == "Reg. 7(1)"


# --- Section B ----------------------------------------------------------------------

def _base_structured(**overrides):
    structured = {
        "label_text": "Tasty Biscuits. Ingredients: wheat flour, sugar. Best before 6 months. "
                      "Manufactured by ACME Foods Pvt Ltd. FSSAI Lic. No. 12345678901234. "
                      "Net weight 100g. MRP Rs 40. Batch No. B12. Consumer care: 1800-000-000. "
                      "Store in a cool dry place.",
        "name_of_food": True,
        "ingredients_list": True,
        "detected_allergens": ["Cereals containing gluten"],
        "declared_allergens": ["Wheat"],
        "veg_nonveg_detected": True,
        "inr_rating": True,
        "nutrition_per_100_present": True,
        "nutrition_per_serving_present": True,
        "net_quantity": True,
        "mrp": True,
        "manufacturer_address": True,
        "fssai_license": True,
        "batch_number": True,
        "date_marking": True,
        "consumer_care": True,
        "english_or_hindi_present": True,
        "legibility_status": "good",
    }
    structured.update(overrides)
    return structured


def test_all_good_label_gives_no_fails():
    result = evaluate_compliance(_base_structured(), category="I")
    statuses = [row["status"] for row in result["section_b"]["rows"]]
    assert "FAIL" not in statuses
    assert len(result["section_b"]["rows"]) == 20
    # every row carries a citation (doc 05 §4)
    assert all(row["citation"] for row in result["section_b"]["rows"])


def test_missing_allergen_declaration_fails_with_citation():
    """The classic flawed label: allergen ingredients but no Contains line."""
    structured = _base_structured(declared_allergens=[])
    result = evaluate_compliance(structured, category="I")
    b7 = next(row for row in result["section_b"]["rows"] if row["id"] == "B7")
    assert b7["status"] == "FAIL"
    assert b7["citation"].startswith("Reg. 5(14)")
    assert any("gluten" in note.lower() for note in [b7["note"]])


def test_no_allergens_is_not_applicable():
    structured = _base_structured(detected_allergens=[], declared_allergens=[])
    result = evaluate_compliance(structured, category="I")
    b7 = next(row for row in result["section_b"]["rows"] if row["id"] == "B7")
    assert b7["status"] == "NOT APPLICABLE"


def test_mrp_row_not_evaluated_in_v1():
    result = evaluate_compliance(_base_structured(), category="I")
    b12 = next(row for row in result["section_b"]["rows"] if row["id"] == "B12")
    assert "Legal Metrology" in b12["citation"]
    assert "Phase 2" in b12["note"]


def test_category_iii_inr_row_not_applicable():
    result = evaluate_compliance(_base_structured(inr_rating=False), category="III")
    b10 = next(row for row in result["section_b"]["rows"] if row["id"] == "B10")
    assert b10["status"] == "NOT APPLICABLE"
    assert "Schedule-IV" in b10["note"]


def test_veg_symbol_exempt_for_water():
    structured = _base_structured(
        label_text="Packaged drinking water",
        veg_nonveg_detected=False,
    )
    result = evaluate_compliance(structured, category="I")
    b8 = next(row for row in result["section_b"]["rows"] if row["id"] == "B8")
    assert b8["status"] == "NOT APPLICABLE"


def test_ingredient_order_not_automatable_is_could_not_verify():
    """doc 06: descending-order verification is not automatable in v1 — be explicit."""
    result = evaluate_compliance(_base_structured(), category="I")
    b3 = next(row for row in result["section_b"]["rows"] if row["id"] == "B3")
    assert b3["status"] == "COULD NOT VERIFY"
    assert "human review" in b3["note"].lower() or "not automatable" in b3["note"].lower()


def test_missing_nutrition_panel_fails():
    structured = _base_structured(
        nutrition_per_100_present=False, nutrition_per_serving_present=False,
        label_text="no nutrition here",
    )
    result = evaluate_compliance(structured, category="I")
    b9 = next(row for row in result["section_b"]["rows"] if row["id"] == "B9")
    assert b9["status"] == "FAIL"


def test_missing_fssai_license_fails():
    structured = _base_structured(fssai_license=False)
    result = evaluate_compliance(structured, category="I")
    b14 = next(row for row in result["section_b"]["rows"] if row["id"] == "B14")
    assert b14["status"] == "FAIL"


def test_regulation_version_recorded():
    result = evaluate_compliance(_base_structured(), category="I")
    assert result["regulation_version"] == COMPLIANCE_VERSION
    assert "Version VII" in result["regulation_version"]


def test_overall_note_is_not_a_legal_certification():
    result = evaluate_compliance(_base_structured(), category="I")
    assert "not a legal compliance certification" in result["overall_note"]


def test_additives_with_class_pass():
    structured = _base_structured(
        additive_entries=[{"ins_number": "211"}],
        additives_with_functional_class=1,
    )
    result = evaluate_compliance(structured, category="I")
    b6 = next(row for row in result["section_b"]["rows"] if row["id"] == "B6")
    assert b6["status"] == "PASS"
