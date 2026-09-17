"""Category classification per doc 04 §1 and Schedule-IV (FOPNL-exempt list).

- Category-I  : solid foods (all FSS 2011 categories except 6.8.1 and 14.0)
- Category-II : liquid foods, non-dairy (FSS categories 6.8.1 and 14.0)
- Category-III: FOPNL-exempt per Schedule-IV -> never receives a star score

Classification uses declared FSS food-category codes when available,
otherwise keyword heuristics over the OCR'd label text. Heuristic hits
carry a confidence so the caller can decide whether to surface them.
"""

import re

# FSS 2011 category codes that define Category-II (liquid, non-dairy)
CATEGORY_II_CODES = {"6.8.1", "14.0"}

# Schedule-IV Category-III (FOPNL-exempt) reference list — doc 04 §5.
# Keyword groups are matched on normalized (lowercased) label text.
CATEGORY_III_KEYWORDS = [
    # Milk & milk products (plain only — Schedule-IV qualifies these as "plain")
    r"\bplain\s+(milk|dahi|curd|yogurt|yoghurt|fermented\s+milk|cream)\b",
    r"\b(whole|toned|skimmed|skim)\s+milk\b(?!\s*(powder|drink|shake|masala))",
    r"\bghee\b", r"\bbutter\s+oil\b", r"\bvanaspati\b",
    # Fats & oils
    r"\b(vegetable\s+)?oil(s)?\b(?!.*spray)", r"\b(vegetable\s+)?fat(s)?\b",
    r"\brefined\s+oil\b", r"\bmustard\s+oil\b", r"\bcoconut\s+oil\b", r"\bolive\s+oil\b",
    r"\bfat\s+spread\b",
    # Grains, flours & cocoa (whole/broken/flaked grain, flours, starches, batters)
    r"\bwhole\s+(?:wheat|grain)\s+(?:grain|atta)\b", r"\bmaida\b", r"\batta\b(?!.*noodle)",
    r"\bstarch(es)?\b", r"\bbatter\b", r"\bbroken\s+wheat\b", r"\bflaked\s+(?:rice|grain)\b",
    r"\bcocoa\s+(mass|cake|mix)\b",
    # Fresh produce
    r"\bfresh\s+fruit\b", r"\bfresh\s+vegetable\b", r"\bfrozen\s+(peas|vegetables|fruit)\b",
    r"\bmushroom\b", r"\btuber\b", r"\bpulses\b", r"\blegumes\b", r"\baloe\s+vera\b",
    r"\bseaweed\b", r"\bnuts?\b(?!.*butter)", r"\bseeds\b",
    # Meat & fish
    r"\bfresh\s+(meat|poultry|fish|mutton|chicken)\b", r"\braw\s+meat\b",
    r"\bedible\s+casing\b", r"\bfresh\s+(mollusc|crustacean)s?\b", r"\bfresh\s+prawn\b",
    r"\bfresh\s+egg(s)?\b", r"\begg\s+product\b", r"\btable\s+eggs\b",
    # Sweeteners
    r"\brefined\s+sugar\b", r"\bbrown\s+sugar\b", r"\braw\s+sugar\b", r"\btable\s+sugar\b",
    r"\bcollectively\s+sugars?\b", r"\bsugar\s+syrup\b", r"\bhoney\b(?!.*oats.*cereal)",
    r"\btable[- ]top\s+sweetener\b", r"\bstevia\b(?!.*drink)", r"\bsaccharin\b(?!.*biscuit)",
    # Salt, spices, condiments
    r"\biodized\s+salt\b", r"\btable\s+salt\b", r"\brock\s+salt\b", r"\bblack\s+salt\b",
    r"\bsalt\s+substitute\b", r"\bherbs\b", r"\bspices\b", r"\bmasala\b(?!.*noodle.*snack)",
    r"\bseasoning\b", r"\bcondiments?\b", r"\bvinegar\b", r"\bmustard\b(?!.*sauce.*mayo)",
    r"\b( salad|sandwich)\s+spread\b", r"\byeast\b",
    # Particular nutritional uses
    r"\binfant\s+formula\b", r"\bfollow[- ]on\s+formula\b", r"\bmedical[- ]purpose\b",
    r"\bdietetic\b", r"\bslimming\s+formula\b", r"\bfood\s+supplement\b",
    r"\bcomplementary\s+food\b",
    # Waters & alcohol
    r"\bmineral\s+water\b", r"\bpackaged\s+drinking\s+water\b", r"\btable\s+water\b",
    r"\bsoda\s+water\b(?!.*lime)", r"\bclub\s+soda\b", r"\bcarbonated\s+water\b",
    r"\bbeer\b", r"\bcider\b", r"\bwine\b", r"\bmead\b", r"\bwhisk(e)?y\b", r"\brum\b",
    r"\bvodka\b", r"\bgin\b", r"\bbrandy\b", r"\barrack\b", r"\bliquor\b", r"\balcoholic\s+beverage\b",
]

# Compile once
_EXEMPT_RE = re.compile("|".join(CATEGORY_III_KEYWORDS), re.IGNORECASE)

# Category-II heuristics: beverages (FSS 14.0) excluding dairy-based drinks
_LIQUID_BEVERAGE_RE = re.compile(
    r"\b(juice|drink|beverage|soft\s+drink|cola|soda|nectar|sherbet|"
    r"iced\s+tea|cold\s+drink|energy\s+drink|carbonated)\b",
    re.IGNORECASE,
)
# Dairy-based liquids stay Category-I (solid-food tables apply, per Reg. 14)
_DAIRY_LIQUID_RE = re.compile(
    r"\b(milk|dahi|curd|lassi|buttermilk|mattha|chaas|paneer|yogurt|yoghurt)\b",
    re.IGNORECASE,
)

# Zero-energy beverage eligibility proviso handled in fssai_rating


def classify_category(label_text, product_name="", declared_category_code=None):
    """Classify a product into INR Category-I / II / III.

    Returns dict: {category: "I"|"II"|"III", basis: str, confidence: float,
    is_beverage: bool, exempt: bool}
    """
    text = f"{product_name or ''} {label_text or ''}".strip()

    # 1. Declared FSS category code wins outright
    if declared_category_code:
        code = str(declared_category_code).strip()
        if code in CATEGORY_II_CODES:
            return _result("II", f"declared FSS category {code}", 1.0, True, False)
        if code not in CATEGORY_II_CODES:
            return _result("I", f"declared FSS category {code}", 1.0, False, False)

    # 2. Schedule-IV exempt check.
    # The exempt list describes what the PRODUCT IS, not what it contains —
    # "palm oil" in a biscuit's ingredient list does not make the biscuit
    # exempt. Front-of-pack region = text before the ingredients declaration.
    # Without an ingredients marker we cannot tell ingredient text from
    # front-of-pack text, so only the first line (product identity) is used.
    name_hit = _EXEMPT_RE.search(product_name or "")
    first_line = (label_text or "").splitlines()[0] if label_text else ""
    marker = re.search(r"\bingredients?\b", text, re.IGNORECASE)
    if marker:
        front_region = text[: marker.start()]
    else:
        front_region = f"{product_name or ''} {first_line}".strip()
    exempt_hit = name_hit or _EXEMPT_RE.search(front_region)

    # 3. Beverage vs dairy-liquid heuristics
    is_liquid_form = bool(
        re.search(r"\b(ml|millilitre|milliliter|litre|liter)\b", text, re.IGNORECASE)
    )
    beverage_hit = _LIQUID_BEVERAGE_RE.search(text)
    dairy_hit = _DAIRY_LIQUID_RE.search(text)

    if beverage_hit and not dairy_hit:
        # A beverage that is also on the exempt list (e.g. plain water,
        # soda water, alcohol) stays Category-III.
        if exempt_hit:
            return _result(
                "III",
                f"Schedule-IV exempt: '{exempt_hit.group(0).strip()}'",
                0.75,
                True,
                True,
            )
        return _result("II", f"beverage keyword '{beverage_hit.group(0).strip()}'", 0.7, True, False)

    if exempt_hit:
        return _result(
            "III",
            f"Schedule-IV exempt: '{exempt_hit.group(0).strip()}'",
            0.75,
            False,
            True,
        )

    if is_liquid_form and dairy_hit:
        return _result("I", "dairy-based product (Reg. 14 treats dairy as solid tables)", 0.6, False, False)

    return _result("I", "default: not on exempt list, not a non-dairy beverage", 0.5, False, False)


def _result(category, basis, confidence, is_beverage, exempt):
    return {
        "category": category,
        "basis": basis,
        "confidence": confidence,
        "is_beverage": is_beverage,
        "exempt": exempt,
    }
