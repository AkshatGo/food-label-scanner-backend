"""Category classifier tests — doc 05 §1 (category assignment correctness)."""

from app.services.category_classifier import classify_category


def test_declared_category_code_wins():
    result = classify_category("some drink", "Cola", declared_category_code="14.0")
    assert result["category"] == "II"
    assert result["confidence"] == 1.0


def test_non_beverage_code_is_category_i():
    result = classify_category("biscuit", "Choco Biscuit", declared_category_code="7.1.2")
    assert result["category"] == "I"


def test_beverage_keyword_is_category_ii():
    result = classify_category("Mango juice drink, 200ml", "Mango Punch")
    assert result["category"] == "II"
    assert result["is_beverage"] is True


def test_plain_toned_milk_is_exempt_schedule_iv():
    """Plain (incl. toned) milk is on the Schedule-IV exempt list -> Category-III."""
    result = classify_category("Toned milk, 500 ml", "Golden Milk")
    assert result["category"] == "III"
    assert result["exempt"] is True


def test_flavored_milk_drink_is_category_i():
    """A flavoured milk drink is dairy (never Category-II) and not plain -> Category-I."""
    result = classify_category(
        "Chocolate Milk Drink. Ingredients: milk, sugar, cocoa solids",
        "Choco Milk",
    )
    assert result["category"] == "I"
    assert result["exempt"] is False


def test_plain_milk_is_schedule_iv_exempt():
    result = classify_category("Plain toned milk", "Dairy Milk")
    assert result["category"] == "III"
    assert result["exempt"] is True


def test_salt_honey_water_exempt():
    for text in ("Iodized table salt", "Pure honey", "Packaged drinking water"):
        result = classify_category(text, "Staple")
        assert result["category"] == "III", text


def test_vegetable_oil_exempt():
    result = classify_category("Refined vegetable oil", "Sunflower Oil")
    assert result["category"] == "III"


def test_regular_snack_is_category_i():
    result = classify_category(
        "Ingredients: wheat flour, sugar, palm oil. Net weight 100g",
        "Crunchy Biscuits",
    )
    assert result["category"] == "I"
    assert result["exempt"] is False


def test_ocr_panel_before_ingredients_does_not_exempt_fat():
    result = classify_category(
        "Test Oat Biscuits\nNutritional Information per 100g\nTotal Fat 20g\n"
        "Ingredients: wheat flour, palm oil, sugar", "Test Oat Biscuits")
    assert result["category"] == "I"


def test_alcoholic_beverage_exempt():
    result = classify_category("Whisky, 42.8% v/v", "Malty Spirit")
    assert result["category"] == "III"


def test_beverage_that_is_water_stays_exempt():
    result = classify_category("Soda water", "Sparkling")
    assert result["category"] == "III"
