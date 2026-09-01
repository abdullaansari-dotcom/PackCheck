"""
PackCheck Compliance Data Models and Taxonomy Definitions
SIH 2026 - Problem Statement SIH26034
Legal Metrology (Packaged Commodities) Rules, 2011
"""

from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Optional, List, Dict, Any


class FieldStatus(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    EXEMPT = "EXEMPT"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class ViolationCode(str, Enum):
    """
    Part D - Violation Type Classification Taxonomy
    Explains WHAT KIND of failure occurred for auditable compliance reporting.
    """
    MISSING = "MISSING"                    # Field absent entirely (e.g., No MRP found)
    FORMAT_ERROR = "FORMAT_ERROR"          # Field present, wrong format (e.g., MRP without "inclusive of all taxes")
    UNIT_ERROR = "UNIT_ERROR"              # Wrong / non-standard unit used (e.g., "dozen")
    SIZE_ERROR = "SIZE_ERROR"              # OUT OF SCOPE - Rule 7 checking skipped by team decision
    NONSTANDARD_PACK = "NONSTANDARD_PACK"  # Standard-pack commodity in wrong size, no disclaimer
    VAGUE_LANGUAGE = "VAGUE_LANGUAGE"      # Quantity uses banned qualifiers ("approx 500g", "minimum 1kg")
    LANGUAGE_ERROR = "LANGUAGE_ERROR"      # Not in Hindi or English (only a regional language present)
    LOW_CONFIDENCE = "LOW_CONFIDENCE"      # OCR uncertain - needs human review


class PackageCategory(str, Enum):
    FOOD_FMCG = "food_fmcg"
    TEA = "tea"
    BISCUITS = "biscuits"
    SALT = "salt"
    CEMENT = "cement"
    TOILET_SOAP = "toilet_soap"
    AERATED_DRINK = "aerated_drink"
    DIMENSION_RELEVANT = "dimension_relevant"  # Bedsheets, towels, fabrics, tiles, etc.
    BIDI_INCENSE = "bidi_incense"              # Agarbatti, bidis (exempt from mfg date)
    LPG_CYLINDER = "lpg_cylinder"              # Standard LPG cylinders (exempt from mfg date)
    FAST_FOOD = "fast_food"                    # Packed by hotels/restaurants for immediate sale
    SCHEDULED_DRUG = "scheduled_drug"          # DPCO governed
    LARGE_AGRICULTURAL = "large_agricultural"  # > 50kg agricultural produce
    GENERAL = "general"


@dataclass
class FieldCheckResult:
    """
    Standard output schema per field (Part D & Rule 6 / Rule 9)
    """
    field: str
    status: FieldStatus
    violation_code: Optional[ViolationCode] = None
    detected_text: Optional[str] = None
    rule_reference: str = ""
    message: str = ""
    confidence: Optional[float] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        res = {
            "field": self.field,
            "status": self.status.value if isinstance(self.status, FieldStatus) else self.status,
            "violation_code": self.violation_code.value if self.violation_code else None,
            "detected_text": self.detected_text,
            "rule_reference": self.rule_reference,
            "message": self.message,
        }
        if self.confidence is not None:
            res["confidence"] = round(self.confidence, 4)
        if self.metadata:
            res["metadata"] = self.metadata
        return res


@dataclass
class ExemptionResult:
    """
    Part E (Rule 26) Exemption Assessment Result
    """
    is_exempt: bool
    is_partial_exemption: bool = False  # True for 10g-20g / 10ml-20ml (requires MRP + Net Qty only)
    exemption_type: Optional[str] = None
    reason: str = ""
    rule_reference: str = "Rule 26"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ExtractedFields:
    """
    Normalized package declaration fields extracted from OCR / raw input
    """
    manufacturer_name: Optional[str] = None
    manufacturer_address: Optional[str] = None
    packer_name: Optional[str] = None
    packer_address: Optional[str] = None
    importer_name: Optional[str] = None
    importer_address: Optional[str] = None
    marketed_by_only: bool = False

    generic_name: Optional[str] = None
    brand_name: Optional[str] = None

    net_quantity_raw: Optional[str] = None
    net_quantity_value: Optional[float] = None
    net_quantity_unit: Optional[str] = None
    has_banned_qualifier: bool = False
    banned_qualifier_word: Optional[str] = None

    mfg_date_raw: Optional[str] = None
    mfg_month: Optional[int] = None
    mfg_year: Optional[int] = None

    mrp_raw: Optional[str] = None
    mrp_value: Optional[float] = None
    has_inclusive_of_taxes: bool = False

    dimensions_raw: Optional[str] = None
    dimensions_length: Optional[float] = None
    dimensions_width: Optional[float] = None
    dimensions_unit: Optional[str] = None

    consumer_care_raw: Optional[str] = None
    consumer_care_phone: Optional[str] = None
    consumer_care_email: Optional[str] = None
    consumer_care_address: Optional[str] = None

    has_non_standard_size_disclaimer: bool = False
    detected_languages: List[str] = field(default_factory=list)
    has_hindi_or_english: bool = True
    average_ocr_confidence: float = 1.0
    field_confidences: Dict[str, float] = field(default_factory=dict)
    raw_text: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ComplianceReport:
    """
    Complete audit report for a package label scan
    """
    is_compliant: bool
    overall_status: str  # COMPLIANT, NON_COMPLIANT, EXEMPT, NEEDS_REVIEW
    exemption: ExemptionResult
    field_results: List[FieldCheckResult]
    violations_count: int
    violation_summary: List[str]
    rule_references_flagged: List[str]
    commodity_category: str
    ocr_confidence_score: float
    audit_notes: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "is_compliant": self.is_compliant,
            "overall_status": self.overall_status,
            "exemption": self.exemption.to_dict(),
            "field_results": [f.to_dict() for f in self.field_results],
            "violations_count": self.violations_count,
            "violation_summary": self.violation_summary,
            "rule_references_flagged": self.rule_references_flagged,
            "commodity_category": self.commodity_category,
            "ocr_confidence_score": round(self.ocr_confidence_score, 4),
            "audit_notes": self.audit_notes,
        }
