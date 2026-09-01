"""
Entity Extractor for Legal Metrology Packaged Commodities
SIH 2026 - Problem Statement SIH26034
PackCheck AI/OCR Pipeline Interop Layer

Extracts normalized ExtractedFields from raw text or structured OCR tokens.
"""

import re
from typing import Optional, List, Dict, Any, Tuple

try:
    from compliance.models import ExtractedFields
    from compliance.constants import (
        BANNED_QUALIFIERS,
        TAX_INCLUSION_PHRASES,
        NON_STANDARD_SIZE_DISCLAIMERS,
        ALL_STANDARD_UNITS,
        BANNED_UNITS,
    )
    from ocr.interface import OCRResult, OCRToken
    from ocr.preprocessor import normalize_ocr_text, analyze_ocr_scripts
except ImportError:
    from ..compliance.models import ExtractedFields
    from ..compliance.constants import (
        BANNED_QUALIFIERS,
        TAX_INCLUSION_PHRASES,
        NON_STANDARD_SIZE_DISCLAIMERS,
        ALL_STANDARD_UNITS,
        BANNED_UNITS,
    )
    from .interface import OCRResult, OCRToken
    from .preprocessor import normalize_ocr_text, analyze_ocr_scripts


class PackageFieldExtractor:
    """
    Heuristic and regex-based entity extractor tailored for Indian packaged commodities.
    """

    GENERIC_PREFIX_REGEX = re.compile(
        r"\b(?:generic(?:\s*name)?|common(?:\s*name)?|commodity|product(?:\s*name)?|item(?:\s*name)?|category)\s*[:\-]\s*([^\n\r]+)",
        re.IGNORECASE
    )

    KNOWN_GENERIC_DESCRIPTORS = [
        "glucose biscuits", "cream biscuits", "carbonated fruit drink", "carbonated soft drink",
        "carbonated beverage", "ready to serve fruit drink", "fruit drink", "fruit juice",
        "soft drink", "instant noodles", "instant coffee", "pure green tea",
        "tea powder", "black tea", "green tea", "tea", "biscuits", "cookies",
        "refined iodised salt", "iodised salt", "table salt", "salt", "toilet soap", "bathing bar",
        "soap bar", "washing powder", "detergent powder", "cotton bedsheet", "bedsheet", "bath towel",
        "towel", "edible vegetable oil", "mustard oil", "sunflower oil", "refined oil", "wheat flour",
        "atta", "besan", "rice", "basmati rice", "portland cement", "cement", "toothpaste", "shampoo"
    ]

    NET_QTY_REGEX = re.compile(
        r"(?:net\s*(?:wt\.?|weight|vol\.?|volume|quantity|qty\.?|contents?)|contains)\s*[:\-]?\s*([a-zA-Z\+\-\.\s]*?)(\d+(?:\.\d+)?)\s*([a-zA-Z\.]+)",
        re.IGNORECASE
    )
    STANDALONE_QTY_REGEX = re.compile(
        r"\b(\d+(?:\.\d+)?)\s*(kg|g|gm|gms|gram|grams|mg|ml|m\.l\.|millilitre|millilitres|l|ltr|litre|litres|pcs|pieces|tablets|capsules|units|count|dozen|dz)\b",
        re.IGNORECASE
    )

    MRP_REGEX = re.compile(
        r"(?:mrp|m\.r\.p\.?|max(?:imum)?\s*retail\s*price|maximum\s*price)\s*[:\-]?\s*(?:rs\.?|inr|₹)?\s*(\d+(?:\.\d{1,2})?)",
        re.IGNORECASE
    )
    STANDALONE_PRICE_REGEX = re.compile(
        r"(?:rs\.?|inr|₹)\s*(\d+(?:\.\d{1,2})?)",
        re.IGNORECASE
    )

    MFG_DATE_PREFIX_REGEX = re.compile(
        r"(?:mfg|pkd|packed|manufactured|mfd|date\s*of\s*mfg|date\s*of\s*pkd|month\s*(?:&|and)\s*year)\s*[:\-]?\s*([a-zA-Z0-9\/\-\., ]+)",
        re.IGNORECASE
    )

    DIMENSION_REGEX = re.compile(
        r"(?:size|dimensions?|dim\.?)\s*[:\-]?\s*(\d+(?:\.\d+)?\s*(?:cm|m|mm|inches|in|ft)\s*[xX\*by\s]+\s*\d+(?:\.\d+)?\s*(?:cm|m|mm|inches|in|ft)?)",
        re.IGNORECASE
    )
    STANDALONE_DIM_REGEX = re.compile(
        r"\b(\d+(?:\.\d+)?)\s*(cm|m|mm)\s*[xX\*]\s*(\d+(?:\.\d+)?)\s*(cm|m|mm)\b",
        re.IGNORECASE
    )

    PHONE_REGEX = re.compile(
        r"\b(?:1800[\s\-]?\d{3}[\s\-]?\d{3,4}|\+?91[\s\-]?[6-9]\d{9}|[0][1-9]\d{1,3}[\s\-]?\d{6,8}|[6-9]\d{9})\b"
    )
    EMAIL_REGEX = re.compile(
        r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b"
    )

    MFG_NAME_REGEX = re.compile(
        r"(?:manufactured|mfg\.?|mfd\.?)\s*(?:by|at)\s*[:\-]?\s*([^\n,]+)(?:,\s*([^\n]+))?",
        re.IGNORECASE
    )
    PKD_NAME_REGEX = re.compile(
        r"(?:packed|pkd\.?)\s*(?:by|at)\s*[:\-]?\s*([^\n,]+)(?:,\s*([^\n]+))?",
        re.IGNORECASE
    )
    IMP_NAME_REGEX = re.compile(
        r"(?:imported)\s*(?:by)\s*[:\-]?\s*([^\n,]+)(?:,\s*([^\n]+))?",
        re.IGNORECASE
    )
    MKT_NAME_REGEX = re.compile(
        r"(?:marketed)\s*(?:by)\s*[:\-]?\s*([^\n,]+)(?:,\s*([^\n]+))?",
        re.IGNORECASE
    )

    def extract_from_text(self, raw_text: str, confidence: float = 1.0) -> ExtractedFields:
        """
        Parses raw text string and returns structured ExtractedFields.
        """
        text = normalize_ocr_text(raw_text)
        fields = ExtractedFields()
        fields.raw_text = text
        fields.average_ocr_confidence = confidence

        # 1. Script and Language Detection (Rule 9)
        scripts, has_hindi_or_english = analyze_ocr_scripts(text)
        fields.detected_languages = scripts
        fields.has_hindi_or_english = has_hindi_or_english

        lower_text = text.lower()
        lines = [line.strip() for line in text.splitlines() if line.strip()]

        # 2. Extract Common / Generic Name (Rule 6(1)(b))
        gen_prefix_match = self.GENERIC_PREFIX_REGEX.search(text)
        if gen_prefix_match:
            fields.generic_name = gen_prefix_match.group(1).strip()
        else:
            for desc in self.KNOWN_GENERIC_DESCRIPTORS:
                if re.search(rf"\b{re.escape(desc)}\b", lower_text, re.IGNORECASE):
                    fields.generic_name = desc.title()
                    break

            if not fields.generic_name and len(lines) >= 2:
                for cand in lines[0:3]:
                    c_lower = cand.lower()
                    if not any(k in c_lower for k in ["mrp", "mfg", "net", "pkd", "manufactured", "care", "phone"]):
                        if len(cand.split()) >= 1 and len(cand) < 40:
                            if not fields.brand_name:
                                fields.brand_name = cand
                            elif not fields.generic_name and cand != fields.brand_name:
                                fields.generic_name = cand
                                break

        # 3. Extract Manufacturer / Packer / Importer / Marketed By (Rule 6(1)(a))
        mfg_match = self.MFG_NAME_REGEX.search(text)
        pkd_match = self.PKD_NAME_REGEX.search(text)
        imp_match = self.IMP_NAME_REGEX.search(text)
        mkt_match = self.MKT_NAME_REGEX.search(text)

        if mfg_match:
            fields.manufacturer_name = mfg_match.group(1).strip()
            if mfg_match.group(2):
                fields.manufacturer_address = mfg_match.group(2).strip()
        elif pkd_match:
            fields.packer_name = pkd_match.group(1).strip()
            if pkd_match.group(2):
                fields.packer_address = pkd_match.group(2).strip()
        elif imp_match:
            fields.importer_name = imp_match.group(1).strip()
            if imp_match.group(2):
                fields.importer_address = imp_match.group(2).strip()

        if mkt_match and not (mfg_match or pkd_match or imp_match):
            fields.marketed_by_only = True
            fields.manufacturer_name = mkt_match.group(1).strip()
            if mkt_match.group(2):
                fields.manufacturer_address = mkt_match.group(2).strip()

        if (fields.manufacturer_name or fields.packer_name or fields.importer_name) and not (fields.manufacturer_address or fields.packer_address):
            for line in lines:
                if re.search(r"\b[1-9][0-9]{2}\s?[0-9]{3}\b", line):
                    if fields.manufacturer_name:
                        fields.manufacturer_address = line.strip()
                    elif fields.packer_name:
                        fields.packer_address = line.strip()
                    break

        # 4. Extract Net Quantity (Rule 6(1)(c))
        qty_match = self.NET_QTY_REGEX.search(text)
        if qty_match:
            qualifier_part = qty_match.group(1).strip().lower()
            val_str = qty_match.group(2)
            unit_str = qty_match.group(3).strip().lower()

            fields.net_quantity_raw = f"{qty_match.group(0).strip()}"
            try:
                fields.net_quantity_value = float(val_str)
                fields.net_quantity_unit = unit_str
            except ValueError:
                pass

            for b in BANNED_QUALIFIERS:
                if b in qualifier_part:
                    fields.has_banned_qualifier = True
                    fields.banned_qualifier_word = b
                    break
        else:
            standalone_match = self.STANDALONE_QTY_REGEX.search(text)
            if standalone_match:
                fields.net_quantity_raw = standalone_match.group(0)
                try:
                    fields.net_quantity_value = float(standalone_match.group(1))
                    fields.net_quantity_unit = standalone_match.group(2).lower()
                except ValueError:
                    pass

        if fields.net_quantity_raw and not fields.has_banned_qualifier:
            for line in lines:
                if fields.net_quantity_raw in line or (fields.net_quantity_unit and fields.net_quantity_unit in line.lower()):
                    line_lower = line.lower()
                    for b in BANNED_QUALIFIERS:
                        if re.search(rf"\b{re.escape(b)}\b", line_lower):
                            fields.has_banned_qualifier = True
                            fields.banned_qualifier_word = b
                            break

        # 5. Extract Retail Sale Price (MRP) & Tax Phrase (Rule 6(1)(e))
        mrp_match = self.MRP_REGEX.search(text)
        if mrp_match:
            fields.mrp_raw = mrp_match.group(0).strip()
            try:
                fields.mrp_value = float(mrp_match.group(1))
            except ValueError:
                pass
        else:
            price_match = self.STANDALONE_PRICE_REGEX.search(text)
            if price_match:
                fields.mrp_raw = price_match.group(0).strip()
                try:
                    fields.mrp_value = float(price_match.group(1))
                except ValueError:
                    pass

        if any(phrase in lower_text for phrase in TAX_INCLUSION_PHRASES):
            fields.has_inclusive_of_taxes = True

        # 6. Extract Month & Year of Manufacture / Packing (Rule 6(1)(d))
        date_cand_match = re.search(r"\b(0[1-9]|1[0-2])[\/\-\.](20\d{2}|\d{2})\b", text)
        month_word_cand = re.search(r"\b(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec|january|february|march|april|may|june|july|august|september|october|november|december)\s*[\/\-\.,]?\s*(20\d{2}|\d{2})\b", text, re.IGNORECASE)
        
        if date_cand_match:
            fields.mfg_date_raw = date_cand_match.group(0)
        elif month_word_cand:
            fields.mfg_date_raw = month_word_cand.group(0)
        else:
            mfg_date_prefix = self.MFG_DATE_PREFIX_REGEX.search(text)
            if mfg_date_prefix:
                fields.mfg_date_raw = mfg_date_prefix.group(1).strip().splitlines()[0]

        # 7. Extract Dimensions (Rule 6(1)(f))
        dim_match = self.DIMENSION_REGEX.search(text)
        if dim_match:
            fields.dimensions_raw = dim_match.group(1).strip()
        else:
            std_dim_match = self.STANDALONE_DIM_REGEX.search(text)
            if std_dim_match:
                fields.dimensions_raw = std_dim_match.group(0)

        # 8. Extract Consumer Care Details (Rule 6(2))
        phone_match = self.PHONE_REGEX.search(text)
        if phone_match:
            fields.consumer_care_phone = phone_match.group(0)

        email_match = self.EMAIL_REGEX.search(text)
        if email_match:
            fields.consumer_care_email = email_match.group(0)

        # 9. Check Non-standard Size Disclaimer (Rule 5 + Second Schedule)
        if any(d in lower_text for d in NON_STANDARD_SIZE_DISCLAIMERS):
            fields.has_non_standard_size_disclaimer = True

        return fields

    def extract_from_ocr_result(self, ocr_result: OCRResult) -> ExtractedFields:
        """
        Parses standardized OCRResult with token-level bounding boxes and confidences.
        """
        fields = self.extract_from_text(ocr_result.raw_text, confidence=ocr_result.average_confidence)
        
        if ocr_result.tokens:
            field_confs: Dict[str, float] = {}
            for token in ocr_result.tokens:
                if fields.net_quantity_raw and token.text in fields.net_quantity_raw:
                    field_confs["net_quantity"] = min(field_confs.get("net_quantity", 1.0), token.confidence)
                if fields.mrp_raw and token.text in fields.mrp_raw:
                    field_confs["mrp"] = min(field_confs.get("mrp", 1.0), token.confidence)
                if fields.mfg_date_raw and token.text in fields.mfg_date_raw:
                    field_confs["mfg_date"] = min(field_confs.get("mfg_date", 1.0), token.confidence)
            fields.field_confidences = field_confs

        return fields
