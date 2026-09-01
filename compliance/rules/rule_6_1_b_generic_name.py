"""
Rule 6(1)(b) - Common / Generic Name of the Commodity
SIH 2026 - Problem Statement SIH26034
Legal Metrology (Packaged Commodities) Rules, 2011

Requirement:
The label must state what the product actually IS in plain everyday language,
distinct from the brand name.
"""

from typing import Optional
from ..models import FieldCheckResult, FieldStatus, ViolationCode
from ..constants import RULE_REF_GENERIC_NAME, DEFAULT_MIN_OCR_CONFIDENCE_THRESHOLD


def check_generic_name(
    generic_name: Optional[str] = None,
    brand_name: Optional[str] = None,
    raw_text: Optional[str] = None,
    confidence: Optional[float] = None,
    min_confidence_threshold: float = DEFAULT_MIN_OCR_CONFIDENCE_THRESHOLD
) -> FieldCheckResult:
    """
    Validates Generic / Common Name declaration under Rule 6(1)(b).
    """
    if confidence is not None and confidence < min_confidence_threshold:
        return FieldCheckResult(
            field="generic_name",
            status=FieldStatus.FAIL,
            violation_code=ViolationCode.LOW_CONFIDENCE,
            detected_text=generic_name or brand_name or raw_text,
            rule_reference=RULE_REF_GENERIC_NAME,
            confidence=confidence,
            message=f"Generic commodity name detected with low OCR confidence ({confidence:.2f} < {min_confidence_threshold:.2f}). Needs review."
        )

    # 1. Complete absence
    if not generic_name or not generic_name.strip():
        if brand_name:
            return FieldCheckResult(
                field="generic_name",
                status=FieldStatus.FAIL,
                violation_code=ViolationCode.MISSING,
                detected_text=f"Brand only: '{brand_name}'",
                rule_reference=RULE_REF_GENERIC_NAME,
                confidence=confidence,
                message=f"Only brand name '{brand_name}' is declared; common/generic commodity name is missing."
            )
        return FieldCheckResult(
            field="generic_name",
            status=FieldStatus.FAIL,
            violation_code=ViolationCode.MISSING,
            detected_text=None,
            rule_reference=RULE_REF_GENERIC_NAME,
            confidence=confidence,
            message="Common or generic name of the commodity is missing from package."
        )

    gen_clean = generic_name.strip()
    brand_clean = brand_name.strip() if brand_name else ""

    # 2. Check if generic name is identical to brand name (e.g. brand is used as the only name)
    if brand_clean and gen_clean.lower() == brand_clean.lower():
        return FieldCheckResult(
            field="generic_name",
            status=FieldStatus.FAIL,
            violation_code=ViolationCode.FORMAT_ERROR,
            detected_text=gen_clean,
            rule_reference=RULE_REF_GENERIC_NAME,
            confidence=confidence,
            message=f"Commodity name '{gen_clean}' is identical to brand name; missing distinct generic descriptor."
        )

    # 3. Valid generic name present
    return FieldCheckResult(
        field="generic_name",
        status=FieldStatus.PASS,
        detected_text=gen_clean,
        rule_reference=RULE_REF_GENERIC_NAME,
        confidence=confidence,
        message=f"Generic commodity descriptor '{gen_clean}' is declared."
    )
