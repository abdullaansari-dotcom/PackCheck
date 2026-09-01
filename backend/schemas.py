"""
API Request & Response Schemas
SIH 2026 - Problem Statement SIH26034
Legal Metrology (Packaged Commodities) Rules, 2011
"""

from typing import Optional, List, Dict, Any
from dataclasses import dataclass, field


@dataclass
class CheckTextRequest:
    """
    Request payload for raw OCR text compliance check
    """
    text: str
    commodity_category: Optional[str] = None
    brand_name: Optional[str] = None
    is_fast_food: bool = False
    is_scheduled_drug: bool = False
    is_agricultural_produce: bool = False
    confidence: float = 1.0


@dataclass
class CheckFieldsRequest:
    """
    Request payload for structured / pre-extracted fields compliance check
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
    consumer_care_raw: Optional[str] = None
    consumer_care_phone: Optional[str] = None
    consumer_care_email: Optional[str] = None
    consumer_care_address: Optional[str] = None

    commodity_category: Optional[str] = None
    has_non_standard_size_disclaimer: bool = False
    is_fast_food: bool = False
    is_scheduled_drug: bool = False
    is_agricultural_produce: bool = False

    detected_languages: List[str] = field(default_factory=list)
    has_hindi_or_english: bool = True
    confidence: float = 1.0
    field_confidences: Dict[str, float] = field(default_factory=dict)
    raw_text: str = ""


@dataclass
class CheckOCRPayloadRequest:
    """
    Request payload for full OCR platform JSON output (tokens, bounding boxes, confidences)
    """
    ocr_payload: Dict[str, Any]
    commodity_category: Optional[str] = None
    brand_name: Optional[str] = None
    adapter_type: str = "generic"  # "generic", "tesseract", "cloud_vision"
    is_fast_food: bool = False
    is_scheduled_drug: bool = False
    is_agricultural_produce: bool = False
