"""Offline OCR cleanup and nutrition-table reconstruction."""

import re

OCR_FIXES = (
    (r"\bProtesn\b|\bProtien\b", "Protein"),
    (r"\bCarboydrate\b|\bCarbohydrat\b", "Carbohydrate"),
    (r"\bTrane\s+Fat\b", "Trans Fat"),
    (r"\bSaturat(?:ed|e)d?\s+Fat\b", "Saturated Fat"),
    (r"\bNutritional\s+Informati[o0]n\b", "Nutritional Information"),
    (r"\bServings?\s+Per\s+Container\b", "Servings Per Container"),
    (r"\bOmg\b", "0 mg"),
    (r"\bmeg\b", "mcg"),
    (r"\bFipee\b|\bFiner\b", "Fiber"),
    (r"\bVilamin\b", "Vitamin"),
    (r"\bCaichum\b", "Calcium"),
    (r"\bVepetatte\b|\bVezetatie\b", "Vegetable"),
    (r"\bSenfiowec\b", "Sunflower"),
    (r"\bFegrediants?\b|\bIngedients\b", "Ingredients"),
    (r"\bSat\.\s*I\b", "Salt"),
    (r"\bSat\.\s*\|", "Salt"),
)

NUTRIENT_LABELS = (
    "energy", "calories", "protein", "total carbohydrate", "carbohydrate",
    "total sugars", "total sugar", "sugars", "sugar", "total fat", "fat",
    "saturated fat", "trans fat", "dietary fiber", "dietary fibre", "fiber",
    "fibre", "sodium", "cholesterol", "calcium", "iron", "potassium",
    "vitamin", "added sugar",
)


def clean_text(raw_text: str) -> str:
    text = str(raw_text or "").replace("\u00a0", " ")
    text = re.sub(r"(\w+)-\s*\n\s*(\w+)", r"\1\2", text)
    for pattern, replacement in OCR_FIXES:
        text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)
    text = text.replace("–", "-").replace("—", "-")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"\s+([,.;:!?])", r"\1", text)
    return "\n".join(line.strip() for line in text.splitlines() if line.strip()).strip()


def _nutrition_table(text: str) -> bool:
    lower = text.lower()
    return sum(label in lower for label in NUTRIENT_LABELS) >= 3


def _insert_row_breaks(text: str) -> str:
    labels = "|".join(sorted((re.escape(label) for label in NUTRIENT_LABELS), key=len, reverse=True))
    text = re.sub(rf"(?i)(?<=\d)\s+(?=({labels})\b)", "\n", text)
    text = re.sub(rf"(?i)(%\s*)(?=({labels})\b)", r"\1\n", text)
    return text


def nlp_reconstruct(text: str, do_spellcheck: bool = False) -> dict:
    cleaned = clean_text(text)
    human_readable = _insert_row_breaks(cleaned) if _nutrition_table(cleaned) else cleaned
    return {
        "raw_text": text,
        "cleaned_text": cleaned,
        "human_readable_text": human_readable,
        "nutrition_table_detected": _nutrition_table(cleaned),
    }


clean_ocr_text = clean_text
reconstruct_text = nlp_reconstruct
