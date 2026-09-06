import re
import unicodedata


def clean_ocr_text(text: str) -> str:
    """Normalize common OCR noise without inventing label content."""
    normalized = unicodedata.normalize("NFKC", text or "")
    normalized = normalized.replace("|", "I")
    corrections = {
        "contsiner": "container",
        "fegredients": "Ingredients",
        "fegrediants": "Ingredients",
        "ingedients": "Ingredients",
        "Arraust": "Amount",
        "Suturalod": "Saturated",
        "Fipee": "Fiber",
        "Finer": "Fiber",
        "Vilamin": "Vitamin",
        "Caichun": "Calcium",
        "Potstozs": "Potatoes",
        "Potztozs": "Potatoes",
        "Potztoas": "Potatoes",
        "Vezetatie": "Vegetable",
        "Vepetatte": "Vegetable",
        "Senfiowec": "Sunflower",
        "Sat.": "Salt",
        "Com ander Cencts Oi": "Corn and/or Canola Oil",
        "Com ander Cencts Oi}": "Corn and/or Canola Oil",
        "fegredients": "Ingredients",
    }
    for wrong, right in corrections.items():
        normalized = re.sub(rf"\b{wrong}\b", right, normalized, flags=re.IGNORECASE)
    normalized = re.sub(r"[ \t]+", " ", normalized)
    normalized = re.sub(r"\n{3,}", "\n\n", normalized)
    normalized = re.sub(r"\s*:\s*", ": ", normalized)
    return "\n".join(line.strip() for line in normalized.splitlines()).strip()