import re
import unicodedata

def clean_title(text: str) -> str:
    if not text:
        return ""
    dash_variants = ["-", "–", "—", "−", "‑", "‐"]
    for d in dash_variants:
        text = text.replace(d, " ")
    text = unicodedata.normalize('NFKC', text)
    cleaned = []
    for ch in text:
        if unicodedata.category(ch)[0] in ("L", "N", "Z"):
            cleaned.append(ch.lower())
    return re.sub(r'\s+', ' ', ''.join(cleaned)).strip()

def clean_title_for_remedial(text: str) -> str:
    if not text:
        return ""
    text = unicodedata.normalize('NFKC', text)
    dash_variants = ["-", "–", "—", "−", "‑", "‐"]
    for d in dash_variants:
        text = text.replace(d, " ")
    text = re.sub(r'\b\d+\b', '', text)
    cleaned = []
    for ch in text:
        if unicodedata.category(ch)[0] in ("L", "N", "Z"):
            cleaned.append(ch.lower())
    return re.sub(r'\s+', ' ', ''.join(cleaned)).strip()
