"""Ingredient curation: dedupe, INS-number resolution, allergen flags.

Ingredient reference data is sourced from FSSAI regulations only (per ADR-6:
never from unverified blogs or AI guesses). Every entry carries a source tag.
"""

import re

# INS number -> (name, functional class, note). Source: FSSAI Food Product
# Standards & Food Additives Regulations, 2011 (common label additives).
INS_ADDITIVES = {
    "170": ("Calcium carbonate", "Colour / Anticaking agent", "May contain milk traces"),
    "200": ("Sorbic acid", "Preservative", ""),
    "202": ("Potassium sorbate", "Preservative", ""),
    "211": ("Sodium benzoate", "Preservative", ""),
    "260": ("Acetic acid", "Acidity regulator", ""),
    "270": ("Lactic acid", "Acidity regulator", "Milk-derived (dairy allergen)"),
    "296": ("Malic acid", "Acidity regulator", ""),
    "300": ("Ascorbic acid", "Antioxidant", ""),
    "301": ("Sodium ascorbate", "Antioxidant", ""),
    "306": ("Tocopherol-rich extract (Vitamin E)", "Antioxidant", ""),
    "322": ("Lecithin (soya)", "Emulsifier", "Soya allergen"),
    "330": ("Citric acid", "Acidity regulator", ""),
    "331": ("Sodium citrate", "Acidity regulator", ""),
    "332": ("Potassium citrate", "Acidity regulator", ""),
    "333": ("Calcium citrate", "Acidity regulator", ""),
    "334": ("Tartaric acid", "Acidity regulator", ""),
    "406": ("Agar", "Thickener", ""),
    "407": ("Carrageenan", "Thickener / Gelling agent", ""),
    "412": ("Guar gum", "Thickener", ""),
    "413": ("Tragacanth gum", "Thickener", ""),
    "414": ("Gum arabic", "Thickener", ""),
    "415": ("Xanthan gum", "Thickener", ""),
    "418": ("Gellan gum", "Thickener / Gelling agent", ""),
    "422": ("Glycerol (glycerine)", "Humectant", ""),
    "440": ("Pectin", "Gelling agent", ""),
    "441": ("Gelatine", "Gelling agent", "Animal-derived"),
    "450": ("Sodium/potassium phosphates", "Emulsifying salt", ""),
    "451": ("Sodium/potassium triphosphates", "Emulsifying salt", ""),
    "452": ("Sodium/potassium polyphosphates", "Emulsifying salt", ""),
    "471": ("Mono- and diglycerides of fatty acids", "Emulsifier", ""),
    "472e": ("Diacetyl tartaric acid esters", "Emulsifier", ""),
    "476": ("Polyglycerol esters of interesterified ricinoleic acid", "Emulsifier", ""),
    "500": ("Sodium carbonate / bicarbonate", "Acidity regulator / Raising agent", ""),
    "501": ("Potassium carbonate / bicarbonate", "Acidity regulator / Raising agent", ""),
    "503": ("Ammonium carbonate / bicarbonate", "Raising agent", ""),
    "504": ("Magnesium carbonate", "Acidity regulator", ""),
    "551": ("Silicon dioxide", "Anticaking agent", ""),
    "552": ("Calcium silicate", "Anticaking agent", ""),
    "554": ("Sodium aluminosilicate", "Anticaking agent", ""),
    "621": ("Monosodium glutamate (MSG)", "Flavour enhancer", "Migraine trigger flag"),
    "627": ("Disodium guanylate", "Flavour enhancer", ""),
    "631": ("Disodium inosinate", "Flavour enhancer", ""),
    "900": ("Dimethylpolysiloxane", "Antifoaming agent", ""),
    "901": ("Beeswax", "Glazing agent", ""),
    "903": ("Carnauba wax", "Glazing agent", ""),
    "950": ("Acesulfame potassium", "Sweetener", "Migraine caution flag"),
    "951": ("Aspartame", "Sweetener", "Phenylketonurics: contains phenylalanine; migraine trigger flag"),
    "952": ("Cyclamate", "Sweetener", ""),
    "954": ("Saccharin", "Sweetener", ""),
    "955": ("Sucralose", "Sweetener", ""),
    "960": ("Steviol glycosides", "Sweetener", ""),
    "961": ("Neotame", "Sweetener", ""),
    "1103": ("Invertase", "Enzyme", ""),
    "150a": ("Plain caramel colour", "Colour", ""),
    "150d": ("Caramel colour Class IV", "Colour", ""),
    "160a": ("Beta-carotene", "Colour", ""),
    "160b": ("Annatto", "Colour", ""),
    "163": ("Anthocyanin", "Colour", ""),
    "171": ("Titanium dioxide", "Colour", ""),
    "249": ("Potassium nitrite", "Preservative", "Cured-meat nitrite; migraine trigger flag"),
    "250": ("Sodium nitrite", "Preservative", "Cured-meat nitrite; migraine trigger flag"),
    "251": ("Sodium nitrate", "Preservative", "Cured-meat nitrate; migraine trigger flag"),
    "252": ("Potassium nitrate", "Preservative", "Cured-meat nitrate; migraine trigger flag"),
    "282": ("Calcium propionate", "Preservative", ""),
    "320": ("Butylated hydroxyanisole (BHA)", "Antioxidant", ""),
    "321": ("Butylated hydroxytoluene (BHT)", "Antioxidant", ""),
    "386": ("EDTA (disodium calcium ethylenediaminetetraacetate)", "Antioxidant / Sequestrant", ""),
    "407a": ("Processed eucheuma seaweed", "Thickener", ""),
    "460": ("Cellulose", "Anticaking agent", ""),
    "466": ("Carboxymethylcellulose (CMC)", "Thickener", ""),
    "900a": ("Dimethyl polysiloxane", "Antifoaming agent", ""),
}

INS_PATTERN = re.compile(r"\b(?:ins|e)?\s*[-–]?\s*(\d{3,4}[a-z]?)\b", re.IGNORECASE)

# Source: Reg. 5(14) — mandatory allergen list (FSSAI Labelling & Display, 2020)
ALLERGEN_GROUPS = {
    "Cereals containing gluten": ["wheat", "maida", "barley", "rye", "oats", "gluten", "semolina", "suji", "atta"],
    "Crustacean": ["prawn", "shrimp", "crab", "lobster", "crustacean"],
    "Milk": ["milk", "casein", "whey", "lactose", "butter", "cream", "ghee", "cheese", "khoya", "curd", "yogurt"],
    "Egg": ["egg", "albumin", "ovalbumin"],
    "Fish": ["fish", "anchovy", "tuna", "sardine", "salmon"],
    "Peanuts": ["peanut", "groundnut", "moongfali"],
    "Tree nuts": ["almond", "cashew", "walnut", "pistachio", "hazelnut", "pecan", "nut"],
    "Soybeans": ["soy", "soya", "soybean", "edamame", "tofu", "miso"],
    "Sulphites": ["sulphite", "sulfite", "sulphur dioxide", "sulfur dioxide", "metabisulphite", "metabisulfite"],
}


def resolve_ins_number(token):
    """Return (name, function, note, source) for an INS code, or None."""
    key = token.strip().lower().lstrip("e")
    # direct lookup, then fallback without letter suffix stripping
    if key in INS_ADDITIVES:
        name, function, note = INS_ADDITIVES[key]
        return {"name": name, "function": function, "note": note,
                "source": "FSSAI Food Product Standards & Food Additives Regulations, 2011"}
    if token.strip().lower() in INS_ADDITIVES:
        name, function, note = INS_ADDITIVES[token.strip().lower()]
        return {"name": name, "function": function, "note": note,
                "source": "FSSAI Food Product Standards & Food Additives Regulations, 2011"}
    return None


def detect_allergens(ingredients):
    """Return list of allergen group names detected from ingredient text."""
    joined = " ".join(str(i) for i in ingredients).lower()
    detected = []
    for group, keywords in ALLERGEN_GROUPS.items():
        if any(re.search(rf"\b{re.escape(kw)}\b", joined) for kw in keywords):
            detected.append(group)
    return detected


def curate_ingredients(raw_ingredients):
    """Dedupe, resolve INS codes, position-index and flag allergens.

    Returns list of dicts: {name, position, ins_number?, function?, note?,
    resolved_from_ins: bool}
    """
    curated = []
    seen = set()
    position = 0
    for raw in raw_ingredients or []:
        item = str(raw).strip(" .;-")
        if not item or len(item) < 2:
            continue
        position += 1

        ins_number = None
        resolved = None
        match = INS_PATTERN.search(item)
        if match:
            candidate = match.group(1)
            resolved = resolve_ins_number(candidate)
            if resolved:
                ins_number = candidate

        name = resolved["name"] if resolved else item
        key = name.lower()
        if key in seen:
            position -= 1
            continue
        seen.add(key)

        entry = {
            "name": name,
            "position": position,
            "resolved_from_ins": bool(resolved),
        }
        if ins_number:
            entry["ins_number"] = ins_number
        if resolved:
            entry["function"] = resolved["function"]
            if resolved["note"]:
                entry["note"] = resolved["note"]
        curated.append(entry)

    allergens = detect_allergens([entry["name"] for entry in curated])
    for entry in curated:
        entry["allergen_information"] = [
            group for group in ALLERGEN_GROUPS
            if any(re.search(rf"\b{re.escape(kw)}\b", entry["name"].lower())
                   for kw in ALLERGEN_GROUPS[group])
        ]
    return curated, allergens
