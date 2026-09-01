"""
PackCheck Compliance Service Layer
SIH 2026 - Problem Statement SIH26034
Legal Metrology (Packaged Commodities) Rules, 2011

Bridges OCR Ingestion, Entity Extraction, and the Statutory Compliance Engine.
"""

from typing import Dict, Any, Optional

try:
    from compliance.models import ExtractedFields, ComplianceReport
    from compliance.engine import ComplianceEngine
    from compliance.constants import (
        STANDARD_PACK_SIZES,
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
        DEFAULT_MIN_OCR_CONFIDENCE_THRESHOLD,
    )
    from ocr.extractor import PackageFieldExtractor
    from ocr.adapters import GenericOCRJsonAdapter, TesseractAdapter, CloudVisionAdapter
except ImportError:
    from ..compliance.models import ExtractedFields, ComplianceReport
    from ..compliance.engine import ComplianceEngine
    from ..compliance.constants import (
        STANDARD_PACK_SIZES,
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
        DEFAULT_MIN_OCR_CONFIDENCE_THRESHOLD,
    )
    from ..ocr.extractor import PackageFieldExtractor
    from ..ocr.adapters import GenericOCRJsonAdapter, TesseractAdapter, CloudVisionAdapter


class ComplianceService:
    """
    Main business logic service managing compliance evaluations across input modalities.
    """

    def __init__(self, min_confidence_threshold: float = DEFAULT_MIN_OCR_CONFIDENCE_THRESHOLD):
        self.engine = ComplianceEngine(min_confidence_threshold=min_confidence_threshold)
        self.extractor = PackageFieldExtractor()
        self.generic_adapter = GenericOCRJsonAdapter()
        self.tesseract_adapter = TesseractAdapter()
        self.cloud_vision_adapter = CloudVisionAdapter()

    def check_raw_text(
        self,
        text: str,
        commodity_category: Optional[str] = None,
        brand_name: Optional[str] = None,
        is_fast_food: bool = False,
        is_scheduled_drug: bool = False,
        is_agricultural_produce: bool = False,
        confidence: float = 1.0,
    ) -> Dict[str, Any]:
        """
        Extracts fields from raw OCR text string and runs compliance verification.
        """
        extracted = self.extractor.extract_from_text(text, confidence=confidence)
        if brand_name:
            extracted.brand_name = brand_name
        if commodity_category and not extracted.generic_name:
            extracted.generic_name = commodity_category

        report = self.engine.evaluate(
            fields=extracted,
            commodity_category=commodity_category or extracted.generic_name,
            is_fast_food=is_fast_food,
            is_scheduled_drug=is_scheduled_drug,
            is_agricultural_produce=is_agricultural_produce,
        )

        response = report.to_dict()
        response["extracted_fields"] = extracted.to_dict()
        return response

    def check_structured_fields(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Runs compliance verification on pre-extracted field dictionary.
        """
        extracted = ExtractedFields(
            manufacturer_name=data.get("manufacturer_name"),
            manufacturer_address=data.get("manufacturer_address"),
            packer_name=data.get("packer_name"),
            packer_address=data.get("packer_address"),
            importer_name=data.get("importer_name"),
            importer_address=data.get("importer_address"),
            marketed_by_only=bool(data.get("marketed_by_only", False)),
            generic_name=data.get("generic_name"),
            brand_name=data.get("brand_name"),
            net_quantity_raw=data.get("net_quantity_raw"),
            net_quantity_value=float(data["net_quantity_value"]) if data.get("net_quantity_value") is not None else None,
            net_quantity_unit=data.get("net_quantity_unit"),
            has_banned_qualifier=bool(data.get("has_banned_qualifier", False)),
            banned_qualifier_word=data.get("banned_qualifier_word"),
            mfg_date_raw=data.get("mfg_date_raw"),
            mfg_month=int(data["mfg_month"]) if data.get("mfg_month") is not None else None,
            mfg_year=int(data["mfg_year"]) if data.get("mfg_year") is not None else None,
            mrp_raw=data.get("mrp_raw"),
            mrp_value=float(data["mrp_value"]) if data.get("mrp_value") is not None else None,
            has_inclusive_of_taxes=bool(data.get("has_inclusive_of_taxes", False)),
            dimensions_raw=data.get("dimensions_raw"),
            consumer_care_raw=data.get("consumer_care_raw"),
            consumer_care_phone=data.get("consumer_care_phone"),
            consumer_care_email=data.get("consumer_care_email"),
            consumer_care_address=data.get("consumer_care_address"),
            has_non_standard_size_disclaimer=bool(data.get("has_non_standard_size_disclaimer", False)),
            detected_languages=data.get("detected_languages", ["English (Latin)"]),
            has_hindi_or_english=bool(data.get("has_hindi_or_english", True)),
            average_ocr_confidence=float(data.get("confidence", 1.0)),
            field_confidences=data.get("field_confidences", {}),
            raw_text=data.get("raw_text", ""),
        )

        category = data.get("commodity_category") or extracted.generic_name
        report = self.engine.evaluate(
            fields=extracted,
            commodity_category=category,
            is_fast_food=bool(data.get("is_fast_food", False)),
            is_scheduled_drug=bool(data.get("is_scheduled_drug", False)),
            is_agricultural_produce=bool(data.get("is_agricultural_produce", False)),
        )

        response = report.to_dict()
        response["extracted_fields"] = extracted.to_dict()
        return response

    def check_ocr_payload(
        self,
        payload: Dict[str, Any],
        adapter_type: str = "generic",
        commodity_category: Optional[str] = None,
        brand_name: Optional[str] = None,
        is_fast_food: bool = False,
        is_scheduled_drug: bool = False,
        is_agricultural_produce: bool = False,
    ) -> Dict[str, Any]:
        """
        Accepts full OCR platform JSON response, normalizes via adapter, and audits compliance.
        """
        if adapter_type == "tesseract":
            ocr_res = self.tesseract_adapter.extract_text(payload)
        elif adapter_type in ["cloud_vision", "google_vision", "textract"]:
            ocr_res = self.cloud_vision_adapter.extract_text(payload)
        else:
            ocr_res = self.generic_adapter.extract_text(payload)

        extracted = self.extractor.extract_from_ocr_result(ocr_res)
        if brand_name:
            extracted.brand_name = brand_name
        if commodity_category and not extracted.generic_name:
            extracted.generic_name = commodity_category

        report = self.engine.evaluate(
            fields=extracted,
            commodity_category=commodity_category or extracted.generic_name,
            is_fast_food=is_fast_food,
            is_scheduled_drug=is_scheduled_drug,
            is_agricultural_produce=is_agricultural_produce,
        )

        response = report.to_dict()
        response["ocr_metadata"] = ocr_res.to_dict()
        response["extracted_fields"] = extracted.to_dict()
        return response

    def get_standard_sizes_info(self) -> Dict[str, Any]:
        """
        Returns reference standard pack sizes table under Rule 5 and Second Schedule.
        """
        return {
            "legal_basis": "Rule 5 & Second Schedule, Legal Metrology (Packaged Commodities) Rules, 2011",
            "statutory_reference": RULE_REF_STANDARD_SIZES,
            "regulated_commodities": STANDARD_PACK_SIZES,
        }

    def get_rules_reference_info(self) -> Dict[str, Any]:
        """
        Returns full legal rulebook definitions for auditor inspection and API documentation.
        """
        return {
            "rulebook": "Legal Metrology (Packaged Commodities) Rules, 2011 (GSR 202(E))",
            "problem_statement": "SIH 2026 - SIH26034 (PackCheck)",
            "rules": {
                "Rule 6(1)(a)": {
                    "field": "manufacturer_packer_importer",
                    "title": "Manufacturer / Packer / Importer Name & Complete Address",
                    "requirement": "State complete name and address of maker, packer, or importer.",
                    "violation_types": ["MISSING", "FORMAT_ERROR", "LOW_CONFIDENCE"]
                },
                "Rule 6(1)(b)": {
                    "field": "generic_name",
                    "title": "Common / Generic Name of Commodity",
                    "requirement": "Plain everyday category name separate from brand name.",
                    "violation_types": ["MISSING", "FORMAT_ERROR", "LOW_CONFIDENCE"]
                },
                "Rule 6(1)(c)": {
                    "field": "net_quantity",
                    "title": "Net Quantity Declaration",
                    "requirement": "Stated in standard metric units (g, kg, ml, l, count) with definite measure. Vague qualifiers like 'approx' or units like 'dozen' are prohibited.",
                    "violation_types": ["MISSING", "VAGUE_LANGUAGE", "UNIT_ERROR", "LOW_CONFIDENCE"]
                },
                "Rule 6(1)(d)": {
                    "field": "mfg_packing_date",
                    "title": "Month & Year of Manufacture / Packing",
                    "requirement": "Month and Year of manufacture or packing. Bidis, incense sticks, and LPG cylinders exempt.",
                    "violation_types": ["MISSING", "LOW_CONFIDENCE"]
                },
                "Rule 6(1)(e)": {
                    "field": "retail_sale_price_mrp",
                    "title": "Retail Sale Price (MRP)",
                    "requirement": "Maximum retail price explicitly declaring 'inclusive of all taxes'.",
                    "violation_types": ["MISSING", "FORMAT_ERROR", "LOW_CONFIDENCE"]
                },
                "Rule 6(1)(f)": {
                    "field": "dimensions",
                    "title": "Dimensions of Commodity",
                    "requirement": "Mandatory only for size-relevant goods (bedsheets, towels, tiles). Not applicable for food/FMCG.",
                    "violation_types": ["MISSING", "LOW_CONFIDENCE"]
                },
                "Rule 6(2)": {
                    "field": "consumer_care_details",
                    "title": "Consumer Care Details",
                    "requirement": "Helpline phone number, email address, or dedicated redressal address.",
                    "violation_types": ["MISSING", "FORMAT_ERROR", "LOW_CONFIDENCE"]
                },
                "Rule 5 / Second Schedule": {
                    "field": "standard_pack_size",
                    "title": "Standard Pack Sizes",
                    "requirement": "Regulated commodities must be sold in listed sizes or carry 'Non-standard size' disclaimer.",
                    "violation_types": ["NONSTANDARD_PACK"]
                },
                "Rule 7 / Rule 8": {
                    "field": "numeral_height",
                    "title": "Font Size & Numeral Height",
                    "status": "SKIPPED_PER_TEAM_DECISION",
                    "reason": "Real-world mm dimension cannot be reliably computed without a physical reference coin in general consumer photos."
                },
                "Rule 9": {
                    "field": "language_and_legibility",
                    "title": "Language & Legibility",
                    "requirement": "Mandatory declarations in Hindi (Devanagari) or English. Low OCR confidence flags legibility issues.",
                    "violation_types": ["LANGUAGE_ERROR", "LOW_CONFIDENCE"]
                },
                "Rule 26": {
                    "field": "exemptions",
                    "title": "Statutory Exemptions",
                    "requirement": "Packages <= 10g/ml fully exempt; packages 10g-20g/ml partial exemption (MRP + Net Qty required); fast food, DPCO drugs, > 50kg agricultural produce exempt."
                }
            }
        }
