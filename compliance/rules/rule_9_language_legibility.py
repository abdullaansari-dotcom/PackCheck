"""
Rule 9 - Language, Legibility & Contrast Verification
SIH 2026 - Problem Statement SIH26034
Legal Metrology (Packaged Commodities) Rules, 2011

Requirement:
1. Language: All mandatory declarations MUST be in Hindi (Devanagari script) OR English (Latin characters).
   Regional languages may be added alongside, but cannot replace Hindi or English.
2. Legibility / Contrast Proxy: If OCR confidence score is below threshold, routes to LOW_CONFIDENCE.
"""

import re
from typing import Optional, List, Dict, Any
from ..models import FieldCheckResult, FieldStatus, ViolationCode
from ..constants import RULE_REF_LEGIBILITY_LANGUAGE, DEFAULT_MIN_OCR_CONFIDENCE_THRESHOLD

# Devanagari Unicode Block: \u0900 - \u097F
DEVANAGARI_REGEX = re.compile(r"[\u0900-\u097F]")
# Latin Alphabetic Characters: [A-Za-z]
LATIN_REGEX = re.compile(r"[A-Za-z]")

# Non-Hindi Indic scripts (e.g., Tamil, Telugu, Kannada, Malayalam, Bengali, Gujarati, Odia, Gurmukhi)
OTHER_INDIC_SCRIPTS = {
    "Bengali": re.compile(r"[\u0980-\u09FF]"),
    "Gurmukhi": re.compile(r"[\u0A00-\u0A7F]"),
    "Gujarati": re.compile(r"[\u0A80-\u0AFF]"),
    "Odia": re.compile(r"[\u0B00-\u0B7F]"),
    "Tamil": re.compile(r"[\u0B80-\u0BFF]"),
    "Telugu": re.compile(r"[\u0C00-\u0C7F]"),
    "Kannada": re.compile(r"[\u0C80-\u0CFF]"),
    "Malayalam": re.compile(r"[\u0D00-\u0D7F]"),
}


def detect_scripts(text: str) -> List[str]:
    """
    Identifies scripts present in the text string.
    """
    if not text:
        return ["English (Latin)"]

    detected = []
    if LATIN_REGEX.search(text):
        detected.append("English (Latin)")
    if DEVANAGARI_REGEX.search(text):
        detected.append("Hindi (Devanagari)")
    for script_name, reg in OTHER_INDIC_SCRIPTS.items():
        if reg.search(text):
            detected.append(script_name)
    return detected


def check_language_compliance(
    raw_text: str = "",
    detected_languages: Optional[List[str]] = None,
    has_hindi_or_english: Optional[bool] = None,
    ocr_confidence: Optional[float] = None,
    min_confidence_threshold: float = DEFAULT_MIN_OCR_CONFIDENCE_THRESHOLD
) -> FieldCheckResult:
    """
    Validates mandatory declarations language and legibility compliance under Rule 9.
    """
    # 1. OCR Confidence check for legibility proxy
    if ocr_confidence is not None and ocr_confidence < min_confidence_threshold:
        return FieldCheckResult(
            field="language_and_legibility",
            status=FieldStatus.FAIL,
            violation_code=ViolationCode.LOW_CONFIDENCE,
            detected_text=raw_text[:100] if raw_text else None,
            rule_reference=RULE_REF_LEGIBILITY_LANGUAGE,
            confidence=ocr_confidence,
            message=f"Label legibility/contrast uncertainty: Average OCR confidence score ({ocr_confidence:.2f}) is below acceptable threshold ({min_confidence_threshold:.2f})."
        )

    # 2. If has_hindi_or_english flag was explicitly provided (e.g. from structured input or pre-check)
    if has_hindi_or_english is False:
        scripts = detected_languages or (detect_scripts(raw_text) if raw_text else [])
        regional_present = [s for s in scripts if s not in ["English (Latin)", "Hindi (Devanagari)"]]
        reg_desc = ", ".join(regional_present) if regional_present else "Regional language"
        return FieldCheckResult(
            field="language_and_legibility",
            status=FieldStatus.FAIL,
            violation_code=ViolationCode.LANGUAGE_ERROR,
            detected_text=raw_text[:120] if raw_text else reg_desc,
            rule_reference=RULE_REF_LEGIBILITY_LANGUAGE,
            confidence=ocr_confidence,
            message=f"Mandatory declarations printed in {reg_desc} without required Hindi (Devanagari) or English translation under Rule 9."
        )

    if not raw_text or not raw_text.strip():
        # If no raw text was passed but structured fields are present with default English/Hindi
        return FieldCheckResult(
            field="language_and_legibility",
            status=FieldStatus.PASS,
            detected_text="Standard English/Hindi structured declarations",
            rule_reference=RULE_REF_LEGIBILITY_LANGUAGE,
            confidence=ocr_confidence,
            message="Declarations satisfy Rule 9 statutory language requirement."
        )

    # 3. Script detection from text
    scripts = detected_languages if detected_languages else detect_scripts(raw_text)
    has_english = bool(LATIN_REGEX.search(raw_text))
    has_hindi = bool(DEVANAGARI_REGEX.search(raw_text))

    if not (has_english or has_hindi):
        regional_present = [s for s in scripts if s not in ["English (Latin)", "Hindi (Devanagari)"]]
        reg_desc = ", ".join(regional_present) if regional_present else "Non-statutory script"
        return FieldCheckResult(
            field="language_and_legibility",
            status=FieldStatus.FAIL,
            violation_code=ViolationCode.LANGUAGE_ERROR,
            detected_text=raw_text[:120],
            rule_reference=RULE_REF_LEGIBILITY_LANGUAGE,
            confidence=ocr_confidence,
            message=f"Mandatory declarations printed in {reg_desc} without required Hindi (Devanagari) or English translation under Rule 9."
        )

    # Compliant
    lang_desc = ", ".join(scripts) if scripts else "English/Hindi"
    return FieldCheckResult(
        field="language_and_legibility",
        status=FieldStatus.PASS,
        detected_text=f"Detected scripts: {lang_desc}",
        rule_reference=RULE_REF_LEGIBILITY_LANGUAGE,
        confidence=ocr_confidence,
        message=f"Declarations satisfy Rule 9 language requirement (contains Hindi/English: {lang_desc})."
    )
