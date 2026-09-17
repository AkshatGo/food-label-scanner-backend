"""Ingredient curation tests — doc 05 §3 (INS resolution, allergen flags)."""

from app.services.ingredient_service import (
    curate_ingredients,
    detect_allergens,
    resolve_ins_number,
)


def test_ins_211_resolves_to_sodium_benzoate():
    resolved = resolve_ins_number("211")
    assert resolved is not None
    assert "Sodium benzoate" in resolved["name"]
    assert resolved["function"] == "Preservative"


def test_ins_330_and_322_resolve():
    assert "Citric acid" in resolve_ins_number("330")["name"]
    assert "Lecithin" in resolve_ins_number("322")["name"]
    assert "Soya" in resolve_ins_number("322")["note"]


def test_unknown_ins_returns_none():
    assert resolve_ins_number("9999") is None


def test_curate_assigns_positions_and_resolves_ins():
    curated, allergens = curate_ingredients([
        "Wheat Flour", "Sugar", "Palm Oil", "INS 211, Preservative",
    ])
    assert [entry["position"] for entry in curated] == [1, 2, 3, 4]
    resolved_entry = curated[3]
    assert resolved_entry["resolved_from_ins"] is True
    assert resolved_entry["ins_number"] == "211"
    assert "Sodium benzoate" in resolved_entry["name"]


def test_curate_dedupes():
    curated, _allergens = curate_ingredients(["Sugar", "sugar", "SUGAR "])
    assert len(curated) == 1


def test_detect_allergens_gluten_milk_soya():
    detected = detect_allergens(["Wheat flour", "Milk solids", "Soya lecithin"])
    assert "Cereals containing gluten" in detected
    assert "Milk" in detected
    assert "Soybeans" in detected


def test_gluten_wheat_detected():
    detected = detect_allergens(["Maida", "Sugar"])
    assert "Cereals containing gluten" in detected


def test_no_allergens_empty():
    assert detect_allergens(["Salt", "Water"]) == []
