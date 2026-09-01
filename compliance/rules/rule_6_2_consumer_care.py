"""
Rule 6(2) - Consumer Care Details
SIH 2026 - Problem Statement SIH26034
Legal Metrology (Packaged Commodities) Rules, 2011

Requirement:
Name, address, and (phone / email) of whoever handles consumer complaints.
Can be the manufacturer contact or dedicated customer care line.
Implementation: Check for phone number pattern OR email pattern OR dedicated care address anywhere on label.
"""

import re
from typing import Optional
from ..models import FieldCheckResult, FieldStatus, ViolationCode
from ..constants import RULE_REF_CONSUMER_CARE, DEFAULT_MIN_OCR_CONFIDENCE_THRESHOLD

# Regex patterns for Toll-free numbers, Indian 10-digit mobile/landline numbers, and email addresses
PHONE_PATTERN = re.compile(r"\b(?:1800[\s\-]?\d{3}[\s\-]?\d{3,4}|\+?91[\s\-]?[6-9]\d{9}|[0][1-9]\d{1,3}[\s\-]?\d{6,8}|[6-9]\d{9})\b")
EMAIL_PATTERN = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b")
CARE_KEYWORDS = ["customer care", "consumer care", "feedback", "queries", "complaints", "helpline", "toll free", "care@"]


def check_consumer_care_details(
    consumer_care_raw: Optional[str] = None,
    consumer_care_phone: Optional[str] = None,
    consumer_care_email: Optional[str] = None,
    consumer_care_address: Optional[str] = None,
    raw_text: Optional[str] = None,
    confidence: Optional[float] = None,
    min_confidence_threshold: float = DEFAULT_MIN_OCR_CONFIDENCE_THRESHOLD
) -> FieldCheckResult:
    """
    Validates Consumer Care declaration under Rule 6(2).
    """
    if confidence is not None and confidence < min_confidence_threshold:
        return FieldCheckResult(
            field="consumer_care_details",
            status=FieldStatus.FAIL,
            violation_code=ViolationCode.LOW_CONFIDENCE,
            detected_text=consumer_care_raw or raw_text,
            rule_reference=RULE_REF_CONSUMER_CARE,
            confidence=confidence,
            message=f"Consumer care details detected with low OCR confidence ({confidence:.2f} < {min_confidence_threshold:.2f}). Needs review."
        )

    # 1. Check structured inputs
    found_items = []
    if consumer_care_phone:
        found_items.append(f"Tel: {consumer_care_phone}")
    if consumer_care_email:
        found_items.append(f"Email: {consumer_care_email}")
    if consumer_care_address:
        found_items.append(f"Addr: {consumer_care_address}")

    if found_items:
        return FieldCheckResult(
            field="consumer_care_details",
            status=FieldStatus.PASS,
            detected_text=" | ".join(found_items),
            rule_reference=RULE_REF_CONSUMER_CARE,
            confidence=confidence,
            message="Consumer care contact details (phone/email/address) are provided."
        )

    # 2. Check raw text / context
    target_str = f"{consumer_care_raw or ''} {raw_text or ''}"

    phone_match = PHONE_PATTERN.search(target_str)
    email_match = EMAIL_PATTERN.search(target_str)

    detected = []
    if phone_match:
        detected.append(f"Phone: {phone_match.group(0)}")
    if email_match:
        detected.append(f"Email: {email_match.group(0)}")

    if detected:
        return FieldCheckResult(
            field="consumer_care_details",
            status=FieldStatus.PASS,
            detected_text=" | ".join(detected),
            rule_reference=RULE_REF_CONSUMER_CARE,
            confidence=confidence,
            message="Consumer care contact channel detected on label."
        )

    # 3. Check for care keywords without contact channel
    lower_str = target_str.lower()
    if any(kw in lower_str for kw in CARE_KEYWORDS):
        return FieldCheckResult(
            field="consumer_care_details",
            status=FieldStatus.FAIL,
            violation_code=ViolationCode.FORMAT_ERROR,
            detected_text=consumer_care_raw or "Consumer care keyword found but contact details invalid",
            rule_reference=RULE_REF_CONSUMER_CARE,
            confidence=confidence,
            message="Consumer care section mentioned, but valid phone number, email address, or contact details are missing."
        )

    # 4. Completely missing
    return FieldCheckResult(
        field="consumer_care_details",
        status=FieldStatus.FAIL,
        violation_code=ViolationCode.MISSING,
        detected_text=None,
        rule_reference=RULE_REF_CONSUMER_CARE,
        confidence=confidence,
        message="Consumer care helpline/email/contact details are missing under Rule 6(2)."
    )
