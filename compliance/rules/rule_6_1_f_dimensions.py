"""
Rule 6(1)(f) - Dimensions of the Commodity
SIH 2026 - Problem Statement SIH26034
Legal Metrology (Packaged Commodities) Rules, 2011

Requirement:
CONDITIONAL FIELD - Only applies to products where physical size matters
to consumer purchase decisions (bedsheets, towels, fabrics, tiles, rugs).
Most food/FMCG products DO NOT need this field and must be marked NOT_APPLICABLE.
"""

import re
from typing import Optional
from ..models import FieldCheckResult, FieldStatus, ViolationCode
from ..constants import (
    RULE_REF_DIMENSIONS,
    DIMENSIONS_REQUIRED_CATEGORIES,
    DEFAULT_MIN_OCR_CONFIDENCE_THRESHOLD
)

DIMENSION_PATTERN = re.compile(
    r"(\d+(?:\.\d+)?)\s*(?:cm|m|mm|inches|in|ft|meters?|metres?)\s*[xX\*by\s]+\s*(\d+(?:\.\d+)?)\s*(?:cm|m|mm|inches|in|ft|meters?|metres?)?",
    re.IGNORECASE
)


def check_dimensions_declaration(
    commodity_category: Optional[str] = None,
    generic_name: Optional[str] = None,
    dimensions_raw: Optional[str] = None,
    raw_text: Optional[str] = None,
    confidence: Optional[float] = None,
    min_confidence_threshold: float = DEFAULT_MIN_OCR_CONFIDENCE_THRESHOLD
) -> FieldCheckResult:
    """
    Validates conditional dimensions declaration under Rule 6(1)(f).
    """
    cat_clean = (commodity_category or "").lower().strip()
    gen_clean = (generic_name or "").lower().strip()

    # Determine if commodity category is on the whitelist where dimensions are mandatory
    is_dimension_relevant = any(
        dim_cat in cat_clean or dim_cat in gen_clean
        for dim_cat in DIMENSIONS_REQUIRED_CATEGORIES
    )

    # 1. If not dimension-relevant (e.g. biscuits, tea, shampoo, juice), mark NOT_APPLICABLE
    if not is_dimension_relevant:
        return FieldCheckResult(
            field="dimensions",
            status=FieldStatus.NOT_APPLICABLE,
            detected_text=dimensions_raw,
            rule_reference=RULE_REF_DIMENSIONS,
            confidence=confidence,
            message="Dimensions declaration is not applicable for this commodity category."
        )

    # 2. Check OCR Confidence Proxy
    if confidence is not None and confidence < min_confidence_threshold:
        return FieldCheckResult(
            field="dimensions",
            status=FieldStatus.FAIL,
            violation_code=ViolationCode.LOW_CONFIDENCE,
            detected_text=dimensions_raw or raw_text,
            rule_reference=RULE_REF_DIMENSIONS,
            confidence=confidence,
            message=f"Dimensions detected with low OCR confidence ({confidence:.2f} < {min_confidence_threshold:.2f}). Needs review."
        )

    # 3. For dimension-relevant goods, check if dimensions are present
    target_text = dimensions_raw or raw_text or ""
    match = DIMENSION_PATTERN.search(target_text)

    if match:
        detected_val = match.group(0)
        return FieldCheckResult(
            field="dimensions",
            status=FieldStatus.PASS,
            detected_text=dimensions_raw or detected_val,
            rule_reference=RULE_REF_DIMENSIONS,
            confidence=confidence,
            message=f"Physical dimensions declared: '{detected_val}'."
        )

    if dimensions_raw and len(dimensions_raw.strip()) > 0:
        return FieldCheckResult(
            field="dimensions",
            status=FieldStatus.PASS,
            detected_text=dimensions_raw,
            rule_reference=RULE_REF_DIMENSIONS,
            confidence=confidence,
            message=f"Physical dimensions declared: '{dimensions_raw}'."
        )

    # 4. Mandatory dimensions missing for size-relevant goods
    return FieldCheckResult(
        field="dimensions",
        status=FieldStatus.FAIL,
        violation_code=ViolationCode.MISSING,
        detected_text=None,
        rule_reference=RULE_REF_DIMENSIONS,
        confidence=confidence,
        message=f"Dimensions declaration is mandatory for size-relevant commodity '{commodity_category or generic_name}', but is missing."
    )
