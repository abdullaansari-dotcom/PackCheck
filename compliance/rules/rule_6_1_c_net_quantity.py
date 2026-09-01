"""
Rule 6(1)(c) - Net Quantity Declaration
SIH 2026 - Problem Statement SIH26034
Legal Metrology (Packaged Commodities) Rules, 2011

Requirement:
Stated using STANDARD metric units (g, kg, ml, l, or plain count).
Must be a definite number - not a range or approximation.
Prohibits vague qualifiers ('approx', 'minimum') and banned non-metric units ('dozen').
"""

import re
from typing import Optional
from ..models import FieldCheckResult, FieldStatus, ViolationCode
from ..constants import (
    RULE_REF_NET_QUANTITY,
    BANNED_QUALIFIERS,
    ALL_STANDARD_UNITS,
    BANNED_UNITS,
    DEFAULT_MIN_OCR_CONFIDENCE_THRESHOLD
)


def check_net_quantity(
    net_quantity_raw: Optional[str] = None,
    net_quantity_value: Optional[float] = None,
    net_quantity_unit: Optional[str] = None,
    has_banned_qualifier: bool = False,
    banned_qualifier_word: Optional[str] = None,
    raw_text: Optional[str] = None,
    confidence: Optional[float] = None,
    min_confidence_threshold: float = DEFAULT_MIN_OCR_CONFIDENCE_THRESHOLD
) -> FieldCheckResult:
    """
    Validates Net Quantity declaration under Rule 6(1)(c).
    """
    if confidence is not None and confidence < min_confidence_threshold:
        return FieldCheckResult(
            field="net_quantity",
            status=FieldStatus.FAIL,
            violation_code=ViolationCode.LOW_CONFIDENCE,
            detected_text=net_quantity_raw or raw_text,
            rule_reference=RULE_REF_NET_QUANTITY,
            confidence=confidence,
            message=f"Net quantity detected with low OCR confidence ({confidence:.2f} < {min_confidence_threshold:.2f}). Needs review."
        )

    # 1. Inspect raw string or context for banned qualifiers if not pre-flagged
    raw_str = (net_quantity_raw or "").lower()
    detected_banned: Optional[str] = banned_qualifier_word

    if not detected_banned and raw_str:
        for b in BANNED_QUALIFIERS:
            # Match whole word
            if re.search(rf"\b{re.escape(b)}\b", raw_str, re.IGNORECASE):
                detected_banned = b
                break

    if detected_banned or has_banned_qualifier:
        b_word = detected_banned or "approx / minimum"
        return FieldCheckResult(
            field="net_quantity",
            status=FieldStatus.FAIL,
            violation_code=ViolationCode.VAGUE_LANGUAGE,
            detected_text=net_quantity_raw or f"{b_word} {net_quantity_value or ''}{net_quantity_unit or ''}".strip(),
            rule_reference=RULE_REF_NET_QUANTITY,
            confidence=confidence,
            message=f"Net quantity uses prohibited vague qualifier '{b_word}'. Quantity must be a definite, unequivocal number."
        )

    # 2. Check for complete absence
    if not net_quantity_raw and (net_quantity_value is None or not net_quantity_unit):
        return FieldCheckResult(
            field="net_quantity",
            status=FieldStatus.FAIL,
            violation_code=ViolationCode.MISSING,
            detected_text=None,
            rule_reference=RULE_REF_NET_QUANTITY,
            confidence=confidence,
            message="Net quantity declaration is missing from the package."
        )

    # 3. Parse value and unit if only raw string was provided
    val = net_quantity_value
    unit = (net_quantity_unit or "").lower().strip()

    if (val is None or not unit) and net_quantity_raw:
        # Regex to extract number and unit
        match = re.search(r"(\d+(?:\.\d+)?)\s*([a-zA-Z\.]+)", net_quantity_raw)
        if match:
            val = float(match.group(1))
            unit = match.group(2).lower().rstrip(".")

    if val is None or val <= 0:
        return FieldCheckResult(
            field="net_quantity",
            status=FieldStatus.FAIL,
            violation_code=ViolationCode.FORMAT_ERROR,
            detected_text=net_quantity_raw,
            rule_reference=RULE_REF_NET_QUANTITY,
            confidence=confidence,
            message="Net quantity value is invalid or missing numerical measure."
        )

    # 4. Check for banned units (e.g., 'dozen', 'lbs', 'oz')
    clean_unit = unit.rstrip(".")
    if clean_unit in BANNED_UNITS:
        return FieldCheckResult(
            field="net_quantity",
            status=FieldStatus.FAIL,
            violation_code=ViolationCode.UNIT_ERROR,
            detected_text=net_quantity_raw or f"{val} {unit}",
            rule_reference=RULE_REF_NET_QUANTITY,
            confidence=confidence,
            message=f"Net quantity uses prohibited / non-standard unit '{unit}'. Metric units (g, kg, ml, l, count) are mandatory under Rule 13(4)."
        )

    # 5. Check if unit is in standard allowed units
    if clean_unit not in ALL_STANDARD_UNITS and unit not in ALL_STANDARD_UNITS:
        return FieldCheckResult(
            field="net_quantity",
            status=FieldStatus.FAIL,
            violation_code=ViolationCode.UNIT_ERROR,
            detected_text=net_quantity_raw or f"{val} {unit}",
            rule_reference=RULE_REF_NET_QUANTITY,
            confidence=confidence,
            message=f"Unrecognized or non-standard measurement unit '{unit}'."
        )

    # Compliant
    detected_display = net_quantity_raw if net_quantity_raw else f"Net Qty: {val} {unit}"
    return FieldCheckResult(
        field="net_quantity",
        status=FieldStatus.PASS,
        detected_text=detected_display,
        rule_reference=RULE_REF_NET_QUANTITY,
        confidence=confidence,
        message=f"Net quantity correctly declared as {val} {unit}."
    )
