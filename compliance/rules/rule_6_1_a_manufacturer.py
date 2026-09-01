"""
Rule 6(1)(a) - Manufacturer / Packer / Importer Name & Address
SIH 2026 - Problem Statement SIH26034
Legal Metrology (Packaged Commodities) Rules, 2011

Requirement:
The package must state the name and complete address of whoever made it,
packed it, or imported it.
Edge Case: Flag 'Marketed by only, no Manufactured by' as a distinct FORMAT_ERROR.
"""

import re
from typing import Optional, Dict, Any
from ..models import FieldCheckResult, FieldStatus, ViolationCode
from ..constants import RULE_REF_MANUFACTURER, DEFAULT_MIN_OCR_CONFIDENCE_THRESHOLD


# Regex pattern to match 6-digit Indian PIN code
PINCODE_PATTERN = re.compile(r"\b[1-9][0-9]{2}\s?[0-9]{3}\b")

# Indicators of address (plot, industrial area, road, street, city, state, pin, dist, po)
ADDRESS_INDICATORS = [
    "plot", "ind.", "industrial", "area", "sector", "phase", "road", "rd",
    "street", "st.", "lane", "nagar", "village", "taluka", "dist", "district",
    "pin", "p.o.", "post", "mumbai", "delhi", "bengaluru", "kolkata", "chennai",
    "hyderabad", "pune", "ahmedabad", "maharashtra", "gujarat", "karnataka",
    "tamil nadu", "uttar pradesh", "rajasthan", "haryana", "punjab", "kerala",
    "madhya pradesh", "west bengal", "telangana", "andhra pradesh"
]


def check_manufacturer_details(
    manufacturer_name: Optional[str] = None,
    manufacturer_address: Optional[str] = None,
    packer_name: Optional[str] = None,
    packer_address: Optional[str] = None,
    importer_name: Optional[str] = None,
    importer_address: Optional[str] = None,
    marketed_by_only: bool = False,
    raw_text: Optional[str] = None,
    confidence: Optional[float] = None,
    min_confidence_threshold: float = DEFAULT_MIN_OCR_CONFIDENCE_THRESHOLD
) -> FieldCheckResult:
    """
    Validates Manufacturer / Packer / Importer declaration under Rule 6(1)(a).
    """
    # 1. Check OCR Confidence Proxy
    if confidence is not None and confidence < min_confidence_threshold:
        return FieldCheckResult(
            field="manufacturer_packer_importer",
            status=FieldStatus.FAIL,
            violation_code=ViolationCode.LOW_CONFIDENCE,
            detected_text=manufacturer_name or packer_name or importer_name or raw_text,
            rule_reference=RULE_REF_MANUFACTURER,
            confidence=confidence,
            message=f"Manufacturer/Packer details detected with low OCR confidence ({confidence:.2f} < {min_confidence_threshold:.2f}). Needs human verification."
        )

    # 2. Check "Marketed by only, no Manufactured by" dodge
    if marketed_by_only:
        detected = "Marketed by declared with no manufacturer/packer details"
        if manufacturer_name:
            detected = f"Marketed by: {manufacturer_name}"
        return FieldCheckResult(
            field="manufacturer_packer_importer",
            status=FieldStatus.FAIL,
            violation_code=ViolationCode.FORMAT_ERROR,
            detected_text=detected,
            rule_reference=RULE_REF_MANUFACTURER,
            confidence=confidence,
            message="Package declares 'Marketed by' only without required 'Manufactured by', 'Packed by', or 'Imported by' declaration."
        )

    # Also inspect raw text for "marketed by" without "mfg by" or "manufactured by" if not passed as structured
    if raw_text and not (manufacturer_name or packer_name or importer_name):
        lower_raw = raw_text.lower()
        if "marketed by" in lower_raw and not any(k in lower_raw for k in ["manufactured by", "mfg by", "mfg. by", "packed by", "pkd by", "imported by"]):
            return FieldCheckResult(
                field="manufacturer_packer_importer",
                status=FieldStatus.FAIL,
                violation_code=ViolationCode.FORMAT_ERROR,
                detected_text="Marketed by only found in label text",
                rule_reference=RULE_REF_MANUFACTURER,
                confidence=confidence,
                message="Package mentions 'Marketed by' only with no manufacturer/packer listed anywhere on the label."
            )

    # Determine active entity
    entity_name = manufacturer_name or packer_name or importer_name
    entity_addr = manufacturer_address or packer_address or importer_address
    prefix = "Manufactured by" if manufacturer_name else ("Packed by" if packer_name else "Imported by")

    # 3. Check for complete absence
    if not entity_name and not entity_addr:
        return FieldCheckResult(
            field="manufacturer_packer_importer",
            status=FieldStatus.FAIL,
            violation_code=ViolationCode.MISSING,
            detected_text=None,
            rule_reference=RULE_REF_MANUFACTURER,
            confidence=confidence,
            message="Manufacturer / Packer / Importer name and complete address missing from package."
        )

    # 4. Check for incomplete declaration (name without address or vice versa)
    if entity_name and not entity_addr:
        return FieldCheckResult(
            field="manufacturer_packer_importer",
            status=FieldStatus.FAIL,
            violation_code=ViolationCode.FORMAT_ERROR,
            detected_text=f"{prefix}: {entity_name}",
            rule_reference=RULE_REF_MANUFACTURER,
            confidence=confidence,
            message="Manufacturer/Packer name is present, but complete address is missing."
        )

    if entity_addr and not entity_name:
        return FieldCheckResult(
            field="manufacturer_packer_importer",
            status=FieldStatus.FAIL,
            violation_code=ViolationCode.FORMAT_ERROR,
            detected_text=f"Address: {entity_addr}",
            rule_reference=RULE_REF_MANUFACTURER,
            confidence=confidence,
            message="Address is present, but legal entity/manufacturer name is missing."
        )

    # 5. Check address quality (presence of PIN code or locality/city indicators)
    addr_str = str(entity_addr).lower()
    has_pincode = bool(PINCODE_PATTERN.search(addr_str))
    has_locality = any(ind in addr_str for ind in ADDRESS_INDICATORS)

    detected_full = f"{prefix}: {entity_name}, {entity_addr}"

    if not (has_pincode or has_locality or len(addr_str.split()) >= 3):
        return FieldCheckResult(
            field="manufacturer_packer_importer",
            status=FieldStatus.FAIL,
            violation_code=ViolationCode.FORMAT_ERROR,
            detected_text=detected_full,
            rule_reference=RULE_REF_MANUFACTURER,
            confidence=confidence,
            message="Manufacturer address appears incomplete (lacks postal code or clear locality/city details)."
        )

    return FieldCheckResult(
        field="manufacturer_packer_importer",
        status=FieldStatus.PASS,
        detected_text=detected_full,
        rule_reference=RULE_REF_MANUFACTURER,
        confidence=confidence,
        message="Manufacturer / Packer / Importer name and address are fully compliant."
    )
