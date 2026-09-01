"""
PackCheck Compliance Engine Package
SIH 2026 - Problem Statement SIH26034
Legal Metrology (Packaged Commodities) Rules, 2011
"""

from .models import (
    FieldStatus,
    ViolationCode,
    PackageCategory,
    FieldCheckResult,
    ExemptionResult,
    ExtractedFields,
    ComplianceReport,
)
from .constants import (
    RULE_REF_MANUFACTURER,
    RULE_REF_GENERIC_NAME,
    RULE_REF_NET_QUANTITY,
    RULE_REF_MFG_DATE,
    RULE_REF_MRP,
    RULE_REF_DIMENSIONS,
    RULE_REF_CONSUMER_CARE,
    RULE_REF_STANDARD_SIZES,
    RULE_REF_NUMERAL_HEIGHT,
    RULE_REF_LEGIBILITY_LANGUAGE,
    RULE_REF_EXEMPTIONS,
    STANDARD_PACK_SIZES,
    TAX_INCLUSION_PHRASES,
    BANNED_QUALIFIERS,
    ALL_STANDARD_UNITS,
    BANNED_UNITS,
)
from .exemptions import evaluate_exemption
from .standard_sizes import is_allowed_standard_size, validate_standard_pack_size
from .engine import ComplianceEngine

__all__ = [
    "FieldStatus",
    "ViolationCode",
    "PackageCategory",
    "FieldCheckResult",
    "ExemptionResult",
    "ExtractedFields",
    "ComplianceReport",
    "ComplianceEngine",
    "evaluate_exemption",
    "is_allowed_standard_size",
    "validate_standard_pack_size",
    "RULE_REF_MANUFACTURER",
    "RULE_REF_GENERIC_NAME",
    "RULE_REF_NET_QUANTITY",
    "RULE_REF_MFG_DATE",
    "RULE_REF_MRP",
    "RULE_REF_DIMENSIONS",
    "RULE_REF_CONSUMER_CARE",
    "RULE_REF_STANDARD_SIZES",
    "RULE_REF_NUMERAL_HEIGHT",
    "RULE_REF_LEGIBILITY_LANGUAGE",
    "RULE_REF_EXEMPTIONS",
    "STANDARD_PACK_SIZES",
    "TAX_INCLUSION_PHRASES",
    "BANNED_QUALIFIERS",
    "ALL_STANDARD_UNITS",
    "BANNED_UNITS",
]
