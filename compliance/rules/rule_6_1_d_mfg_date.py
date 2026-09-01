"""
Rule 6(1)(d) - Month & Year of Manufacture / Packing
SIH 2026 - Problem Statement SIH26034
Legal Metrology (Packaged Commodities) Rules, 2011

Requirement:
Month + year is sufficient - day is not required.
May be written in words ("March 2026") or numerals ("03/2026") or standard abbreviations.
Exemptions under Rule 6(1)(d): Bidis, incense sticks (agarbatti), and standard LPG cylinders.
"""

import re
from typing import Optional
from ..models import FieldCheckResult, FieldStatus, ViolationCode, PackageCategory
from ..constants import (
    RULE_REF_MFG_DATE,
    MFG_DATE_EXEMPT_CATEGORIES,
    DEFAULT_MIN_OCR_CONFIDENCE_THRESHOLD
)

# Common regex patterns for Month & Year
DATE_PATTERNS = [
    # 03/2026, 03-2026, 03/26, 03-26
    re.compile(r"\b(0[1-9]|1[0-2])[\/\-\.](20\d{2}|\d{2})\b"),
    # March 2026, Mar 2026, MAR/2026, MAR-26
    re.compile(r"\b(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec|january|february|march|april|may|june|july|august|september|october|november|december)\s*[\/\-\.,]?\s*(20\d{2}|\d{2})\b", re.IGNORECASE),
    # 2026/03 (ISO format)
    re.compile(r"\b(20\d{2})[\/\-\.](0[1-9]|1[0-2])\b"),
    # Pkd/Mfg followed by date
    re.compile(r"(?:mfg|pkd|packed|manufactured|mfd|mfg\.?|pkd\.?)\s*[:\-]?\s*([a-zA-Z0-9\/\-\.]+)", re.IGNORECASE)
]


def check_mfg_packing_date(
    mfg_date_raw: Optional[str] = None,
    mfg_month: Optional[int] = None,
    mfg_year: Optional[int] = None,
    commodity_category: Optional[str] = None,
    raw_text: Optional[str] = None,
    confidence: Optional[float] = None,
    min_confidence_threshold: float = DEFAULT_MIN_OCR_CONFIDENCE_THRESHOLD
) -> FieldCheckResult:
    """
    Validates Month & Year of Manufacture / Packing under Rule 6(1)(d).
    """
    # 1. Check Statutory Category Exemptions (Bidis, Incense sticks, LPG cylinders)
    cat_clean = (commodity_category or "").lower().strip().replace("_", " ")
    if cat_clean in MFG_DATE_EXEMPT_CATEGORIES or any(ex in cat_clean for ex in MFG_DATE_EXEMPT_CATEGORIES):
        return FieldCheckResult(
            field="mfg_packing_date",
            status=FieldStatus.EXEMPT,
            rule_reference=RULE_REF_MFG_DATE,
            confidence=confidence,
            message=f"Commodity category '{commodity_category}' is exempt from mandatory manufacture date declaration under Rule 6(1)(d)."
        )

    # 2. Check OCR Confidence Proxy
    if confidence is not None and confidence < min_confidence_threshold:
        return FieldCheckResult(
            field="mfg_packing_date",
            status=FieldStatus.FAIL,
            violation_code=ViolationCode.LOW_CONFIDENCE,
            detected_text=mfg_date_raw or raw_text,
            rule_reference=RULE_REF_MFG_DATE,
            confidence=confidence,
            message=f"Manufacture/packing date detected with low OCR confidence ({confidence:.2f} < {min_confidence_threshold:.2f}). Needs review."
        )

    # 3. Check structured month/year input
    if mfg_month is not None and mfg_year is not None:
        if 1 <= mfg_month <= 12 and 1900 <= mfg_year <= 2100:
            detected_str = mfg_date_raw or f"{mfg_month:02d}/{mfg_year}"
            return FieldCheckResult(
                field="mfg_packing_date",
                status=FieldStatus.PASS,
                detected_text=detected_str,
                rule_reference=RULE_REF_MFG_DATE,
                confidence=confidence,
                message=f"Month and year of manufacture/packing declared as {mfg_month:02d}/{mfg_year}."
            )

    # 4. Check raw string matching regex patterns
    search_str = mfg_date_raw or raw_text or ""
    if search_str:
        for pat in DATE_PATTERNS:
            match = pat.search(search_str)
            if match:
                detected_val = match.group(0)
                return FieldCheckResult(
                    field="mfg_packing_date",
                    status=FieldStatus.PASS,
                    detected_text=detected_val,
                    rule_reference=RULE_REF_MFG_DATE,
                    confidence=confidence,
                    message=f"Month and year of manufacture/packing detected: '{detected_val}'."
                )

    # 5. Missing date declaration
    return FieldCheckResult(
        field="mfg_packing_date",
        status=FieldStatus.FAIL,
        violation_code=ViolationCode.MISSING,
        detected_text=None,
        rule_reference=RULE_REF_MFG_DATE,
        confidence=confidence,
        message="Month and year of manufacture / packing is missing from the package."
    )
