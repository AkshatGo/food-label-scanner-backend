"""Offline OCR-tolerant extraction of non-nutrition label fields."""

import re


FSSAI_LICENSE_PATTERNS = [
    r"fssai[^0-9]{0,15}(\d{10,14})",
    r"lic(?:en[cs]e)?\s*no?[^0-9]{0,8}(\d{10,14})",
]
BATCH_PATTERNS = [r"(?:batch|lot|code)\s*(?:no\.?|number)?\s*[:#-]?\s*([A-Za-z0-9/-]{2,20})"]
DATE_PATTERNS = [r"(?:mfg|mfd|manufactured|packed|pkd|best before|expiry|exp|use by)[^0-9A-Za-z]{0,12}([0-9]{1,2}[/-][0-9]{1,2}[/-][0-9]{2,4}|[A-Za-z]{3,9}\.?\s*[0-9]{4})"]
NET_QTY_PATTERN = r"net\s*(?:wt|weight|qty|quantity)\s*[:#-]?\s*(\d+(?:\.\d+)?)\s*(kg|g|l|ml)\b"
CONTAINS_PATTERN = r"\bcontains\s*[:#-]?\s*([A-Za-z ,&]{3,100})"
MAY_CONTAIN_PATTERN = r"\bmay\s+contain(?:s)?\s*[:#-]?\s*([A-Za-z ,&]{3,100})"
SCHEDULE_II_KEYWORDS = (
    "pan masala", "supari", "monosodium glutamate", "msg", "aspartame",
    "acesulfame", "saccharin", "sorbitol", "polydextrose", "polyol",
    "isomaltulose", "caffeine", "irradiat", "plant stanol", "plant sterol",
    "trehalose", "dextrin", "multi-source edible oil", "vanaspati", "annatto",
    "gluten free", "gluten-free",
)


def _first(patterns, text):
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return match.group(1).strip()
    return None


def _split(value):
    return [part.strip() for part in re.split(r",|&|\band\b", value or "", flags=re.IGNORECASE) if part.strip()]


def extract_ingredients_block(text):
    match = re.search(r"(?:list of )?ingredients?\s*[:#-]?\s*", text, re.IGNORECASE)
    if not match:
        return {"has_title": False, "raw_block": None, "ingredient_names": []}
    rest = text[match.end():]
    stop = re.search(r"\n\s*(?:nutrition|fssai|batch|lot|mfg|expiry|contains|may contain|manufacturer)", rest, re.IGNORECASE)
    block = rest[:stop.start() if stop else len(rest)].strip(" .:-\n")
    names, current, depth = [], "", 0
    for char in block:
        if char in "([": depth += 1
        if char in ")]": depth = max(0, depth - 1)
        if char in ",;" and depth == 0:
            if current.strip(): names.append(current.strip())
            current = ""
        else:
            current += char
    if current.strip(): names.append(current.strip())
    return {"has_title": True, "raw_block": block, "ingredient_names": names}


def extract_label_fields(text):
    net = re.search(NET_QTY_PATTERN, text, re.IGNORECASE)
    contains = _first([CONTAINS_PATTERN], text)
    may_contain = _first([MAY_CONTAIN_PATTERN], text)
    return {
        "fssai_license_number": _first(FSSAI_LICENSE_PATTERNS, text),
        "batch_lot_code_number": _first(BATCH_PATTERNS, text),
        "date_marking": _first(DATE_PATTERNS, text),
        "net_quantity_value": net.group(1) if net else None,
        "net_quantity_unit": net.group(2).lower() if net else None,
        "manufacturer_statement": bool(re.search(r"\b(?:manufactured|mfg|packed|marketed)\s+by\b", text, re.I)),
        "ingredients": extract_ingredients_block(text),
        "allergens": {"declared_contains": _split(contains), "declared_may_contain": _split(may_contain)},
        "schedule_ii_triggers": [keyword for keyword in SCHEDULE_II_KEYWORDS if keyword in text.lower()],
        "requires_visual_check": ["veg_nonveg_symbol", "fssai_logo", "front_of_pack_name"],
    }
