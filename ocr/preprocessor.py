"""
OCR Text Preprocessing and Script Detection
SIH 2026 - Problem Statement SIH26034
"""

import re
import unicodedata
from typing import List, Tuple

try:
    from compliance.rules.rule_9_language_legibility import detect_scripts
except ImportError:
    from ..compliance.rules.rule_9_language_legibility import detect_scripts


def normalize_ocr_text(text: str) -> str:
    """
    Cleans and standardizes raw OCR text for robust field extraction.
    """
    if not text:
        return ""

    # Normalize unicode characters (NFKC)
    normalized = unicodedata.normalize("NFKC", text)

    # Standardize currency symbols and variants
    normalized = normalized.replace("`", "'").replace("’", "'").replace("‘", "'")
    normalized = normalized.replace("₹", " Rs. ").replace("Rs.", " Rs. ").replace("INR", " INR ")

    # Standardize common OCR misreads in dates and metrics
    normalized = re.sub(r"([0-9]{2})\s*[\/|\\]\s*([0-9]{2,4})", r"\1/\2", normalized)

    # Standardize whitespace
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in normalized.splitlines()]
    cleaned = "\n".join([line for line in lines if line])

    return cleaned


def analyze_ocr_scripts(text: str) -> Tuple[List[str], bool]:
    """
    Analyzes scripts in text and determines if Hindi/English are present.
    Returns:
        (detected_scripts, has_hindi_or_english)
    """
    scripts = detect_scripts(text)
    has_hindi_or_english = any(s in ["English (Latin)", "Hindi (Devanagari)"] for s in scripts)
    return scripts, has_hindi_or_english
