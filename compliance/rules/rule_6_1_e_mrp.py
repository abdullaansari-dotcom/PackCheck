"""
Rule 6(1)(e) - Retail Sale Price (MRP) Declaration
SIH 2026 - Problem Statement SIH26034
Legal Metrology (Packaged Commodities) Rules, 2011

Requirement:
Maximum Retail Price (MRP) must be clearly declared.
CRITICAL: Must explicitly include the mandatory phrase "inclusive of all taxes" (or accepted legal equivalent).
Classification: Price present + phrase missing = FORMAT_ERROR (NOT MISSING).
Rounding rule helper: Paise below 50 round down; 50-95 paise round up to nearest 50 paise.
"""

import re
from typing import Optional
from ..models import FieldCheckResult, FieldStatus, ViolationCode
from ..constants import (
    RULE_REF_MRP,
    TAX_INCLUSION_PHRASES,
    DEFAULT_MIN_OCR_CONFIDENCE_THRESHOLD
)

# Regex to detect price patterns (Rs. 45, Rs 45.00, ₹45, INR 45, MRP 45.50)
PRICE_PATTERNS = [
    re.compile(r"(?:mrp|m\.r\.p\.?|max(?:imum)?\s*retail\s*price|rs\.?|inr|₹)\s*[:\-]?\s*(\d+(?:\.\d{1,2})?)", re.IGNORECASE),
    re.compile(r"(?:₹|rs\.?|inr)\s*(\d+(?:\.\d{1,2})?)", re.IGNORECASE),
    re.compile(r"\b(\d+(?:\.\d{2}))\s*(?:mrp|incl)", re.IGNORECASE)
]


def check_mrp_declaration(
    mrp_raw: Optional[str] = None,
    mrp_value: Optional[float] = None,
    has_inclusive_of_taxes: bool = False,
    raw_text: Optional[str] = None,
    confidence: Optional[float] = None,
    min_confidence_threshold: float = DEFAULT_MIN_OCR_CONFIDENCE_THRESHOLD
) -> FieldCheckResult:
    """
    Validates MRP and mandatory tax inclusion statement under Rule 6(1)(e).
    """
    if confidence is not None and confidence < min_confidence_threshold:
        return FieldCheckResult(
            field="retail_sale_price_mrp",
            status=FieldStatus.FAIL,
            violation_code=ViolationCode.LOW_CONFIDENCE,
            detected_text=mrp_raw or raw_text,
            rule_reference=RULE_REF_MRP,
            confidence=confidence,
            message=f"MRP declaration detected with low OCR confidence ({confidence:.2f} < {min_confidence_threshold:.2f}). Needs review."
        )

    # 1. Search for price if not pre-extracted
    val = mrp_value
    detected_raw = mrp_raw

    if val is None and (mrp_raw or raw_text):
        target = mrp_raw or raw_text or ""
        for pat in PRICE_PATTERNS:
            m = pat.search(target)
            if m:
                try:
                    val = float(m.group(1))
                    if not detected_raw:
                        detected_raw = m.group(0)
                    break
                except (ValueError, IndexError):
                    continue

    # 2. Check for complete absence of price
    if val is None and not detected_raw:
        return FieldCheckResult(
            field="retail_sale_price_mrp",
            status=FieldStatus.FAIL,
            violation_code=ViolationCode.MISSING,
            detected_text=None,
            rule_reference=RULE_REF_MRP,
            confidence=confidence,
            message="Retail Sale Price (MRP) declaration is completely missing from package."
        )

    # 3. Check for mandatory tax inclusion phrase
    tax_phrase_found = has_inclusive_of_taxes

    if not tax_phrase_found:
        combined_text = f"{mrp_raw or ''} {raw_text or ''}".lower()
        if any(phrase in combined_text for phrase in TAX_INCLUSION_PHRASES):
            tax_phrase_found = True

    display_text = detected_raw if detected_raw else f"MRP: Rs. {val:.2f}"

    # 4. Critical Classification: Price Found + Tax Phrase Missing = FORMAT_ERROR (Not MISSING)
    if not tax_phrase_found:
        return FieldCheckResult(
            field="retail_sale_price_mrp",
            status=FieldStatus.FAIL,
            violation_code=ViolationCode.FORMAT_ERROR,
            detected_text=display_text,
            rule_reference=RULE_REF_MRP,
            confidence=confidence,
            message=f"MRP price '{display_text}' is present, but mandatory phrase '(Inclusive of all taxes)' is missing."
        )

    # Compliant
    return FieldCheckResult(
        field="retail_sale_price_mrp",
        status=FieldStatus.PASS,
        detected_text=f"{display_text} (Inclusive of all taxes)",
        rule_reference=RULE_REF_MRP,
        confidence=confidence,
        message=f"MRP correctly declared as Rs. {val:.2f} (Inclusive of all taxes)."
    )
