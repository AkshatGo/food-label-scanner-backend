"""Scan pipeline integration tests — synthetic OCR text through the full path."""

from app.services.scan_pipeline import build_structured_product, run_scan_pipeline


BISCUIT_LABEL = """Crunchy Biscuits
Brand: ACME
Ingredients: Wheat Flour (Maida), Sugar, Palm Oil, Invert Sugar Syrup,
Raising Agent (INS 500 (ii)), Emulsifier (Soya Lecithin, INS 322),
Salt, Milk Solids, Artificial Flavouring Substances
Contains Wheat, Milk, Soya
Nutritional Information per 100g
Energy 480 kcal
Protein 6 g
Total Carbohydrate 62 g
Total Sugars 18 g
Added Sugars 15 g
Total Fat 20 g
Saturated Fat 6 g
Trans Fat 0 g
Sodium 420 mg
Net weight 100g
MRP Rs 40 (Inclusive of all taxes)
Manufactured by ACME Foods Pvt Ltd, Mumbai
FSSAI Lic. No. 10012345678901
Batch No. B123
Best Before 6 months from packaging
Consumer Care: 1800-123-456
Store in a cool and dry place
"""


def test_pipeline_structures_a_biscuit_label():
    product, compliance = run_scan_pipeline(BISCUIT_LABEL, ocr_confidence=88.0)

    assert product["product_id"] is None  # assigned by persistence layer
    assert product["category"] in ("I", "II", "III")

    per100 = product["nutrition_per_100g"]
    assert per100["energy_kcal"] == 480
    assert per100["total_sugar_g"] == 18
    assert per100["sodium_mg"] == 420

    # INR runs and is eligible-or-exempt with a version stamp
    inr = product["inr"]
    assert inr["formula_version"] == "FSSAI-INR-2022-draft-v1"
    assert inr["eligible"] is True
    assert 0.5 <= inr["rating_stars"] <= 5.0


def test_pipeline_resolves_ins_and_detects_allergens():
    product, _compliance = run_scan_pipeline(BISCUIT_LABEL, ocr_confidence=88.0)
    names = [entry["name"] for entry in product["ingredients"]]
    assert any("Sodium carbonate" in name or "500" in str(entry.get("ins_number", ""))
               for entry, name in zip(product["ingredients"], names))
    detected = product["allergens"]["detected"]
    assert "Cereals containing gluten" in detected
    assert "Milk" in detected
    assert "Soybeans" in detected


def test_pipeline_identity_fields():
    product, _ = run_scan_pipeline(BISCUIT_LABEL, ocr_confidence=88.0)
    assert product["fssai_license_no"] == "10012345678901"
    assert product["net_quantity"] == "100g"
    assert product["mrp"] == "40"
    assert "ACME Foods" in product["manufacturer"]
    assert product["best_before"]


def test_pipeline_compliance_has_20_rows_with_citations():
    product, compliance = run_scan_pipeline(BISCUIT_LABEL, ocr_confidence=88.0)
    rows = compliance["section_b"]["rows"]
    assert len(rows) == 20
    assert all(row["citation"] for row in rows)
    assert compliance["regulation_version"].startswith("FSSAI Compendium")


def test_pipeline_milk_is_exempt_not_scored():
    milk_label = """Toned Milk
Plain milk, homogenized, pasteurized
Nutritional Information per 100ml
Energy 58 kcal
Protein 3.1 g
Total Sugars 4.8 g
Sodium 44 mg
"""
    product, _ = run_scan_pipeline(milk_label, ocr_confidence=90.0)
    assert product["category"] == "III"
    assert product["inr"]["eligible"] is False
    assert product["inr"]["inr_score"] is None
    assert "Schedule-IV" in product["inr"]["exemption_reason"]


def test_pipeline_diet_beverage_gets_no_stars():
    diet_label = """Zero Sugar Cola
Carbonated water, acidity regulator (INS 330), sweetener (INS 951),
preservative (INS 211), caffeine
Nutritional Information per 100ml
Energy 0 kcal
Protein 0 g
Total Sugars 0 g
Sodium 8 mg
"""
    product, _ = run_scan_pipeline(diet_label, ocr_confidence=90.0)
    assert product["category"] == "II"
    assert product["inr"]["eligible"] is False
    assert product["inr"]["status"] == "not_eligible_zero_energy_zero_sugar"


def test_pipeline_sugary_drink_scores_liquid_path():
    juice_label = """Mango Drink
Ingredients: Water, Mango Pulp, Sugar, Acidity Regulator (INS 330)
Nutritional Information per 100ml
Energy 60 kcal
Protein 0.5 g
Total Sugars 14 g
Sodium 10 mg
"""
    product, _ = run_scan_pipeline(juice_label, ocr_confidence=90.0)
    assert product["category"] == "II"
    inr = product["inr"]
    assert inr["eligible"] is True
    # liquid baseline uses energy + sugar only
    assert "sodium" not in inr["negative_points"]
    assert inr["rating_stars"] <= 1.0  # 14g/100ml sugar is well above the liquid AVOID band
