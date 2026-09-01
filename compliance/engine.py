"""
PackCheck Master Compliance Engine
SIH 2026 - Problem Statement SIH26034
Legal Metrology (Packaged Commodities) Rules, 2011 (GSR 202(E))

Coordinates:
- Part E: Exemptions (Rule 26) - Evaluated FIRST
- Part A: The 7 Mandatory Declaration Fields (Rule 6(1)(a)-(f), Rule 6(2))
- Part C: Standard Pack Sizes (Rule 5 + Second Schedule)
- Part F: Language & Legibility (Rule 9)
- Part D: Violation Taxonomy classification and audit trail generation
"""

from typing import Optional, List, Dict, Any
from .models import (
    FieldStatus,
    ViolationCode,
    FieldCheckResult,
    ExemptionResult,
    ExtractedFields,
    ComplianceReport,
    PackageCategory,
)
from .constants import (
    RULE_REF_EXEMPTIONS,
    DEFAULT_MIN_OCR_CONFIDENCE_THRESHOLD,
    RULE_REF_MANUFACTURER,
    RULE_REF_GENERIC_NAME,
    RULE_REF_NET_QUANTITY,
    RULE_REF_MFG_DATE,
    RULE_REF_MRP,
    RULE_REF_DIMENSIONS,
    RULE_REF_CONSUMER_CARE,
)
from .exemptions import evaluate_exemption
from .standard_sizes import validate_standard_pack_size
from .rules import (
    check_manufacturer_details,
    check_generic_name,
    check_net_quantity,
    check_mfg_packing_date,
    check_mrp_declaration,
    check_dimensions_declaration,
    check_consumer_care_details,
    check_language_compliance,
)


class ComplianceEngine:
    """
    Core Compliance Verification Engine for Legal Metrology Packaged Commodities.
    """

    def __init__(self, min_confidence_threshold: float = DEFAULT_MIN_OCR_CONFIDENCE_THRESHOLD):
        self.min_confidence_threshold = min_confidence_threshold

    def evaluate(
        self,
        fields: ExtractedFields,
        commodity_category: Optional[str] = None,
        is_fast_food: bool = False,
        is_scheduled_drug: bool = False,
        is_agricultural_produce: bool = False,
    ) -> ComplianceReport:
        """
        Executes complete compliance verification workflow on extracted label fields.
        """
        resolved_category = commodity_category or fields.generic_name or PackageCategory.GENERAL.value
        audit_notes: List[str] = []

        # =========================================================================
        # STEP 1: Rule 26 Exemption Assessment (Evaluated FIRST)
        # =========================================================================
        exemption = evaluate_exemption(
            category=resolved_category,
            net_quantity_value=fields.net_quantity_value,
            net_quantity_unit=fields.net_quantity_unit,
            is_fast_food=is_fast_food,
            is_scheduled_drug=is_scheduled_drug,
            is_agricultural_produce=is_agricultural_produce,
        )

        field_results: List[FieldCheckResult] = []

        # Fully Exempt Package Handler
        if exemption.is_exempt and not exemption.is_partial_exemption:
            audit_notes.append(f"Package qualifies for full exemption under {exemption.rule_reference}: {exemption.reason}")
            
            # Return all fields marked as EXEMPT
            all_fields_exempt = [
                FieldCheckResult(field="manufacturer_packer_importer", status=FieldStatus.EXEMPT, rule_reference=RULE_REF_MANUFACTURER, message=exemption.reason),
                FieldCheckResult(field="generic_name", status=FieldStatus.EXEMPT, rule_reference=RULE_REF_GENERIC_NAME, message=exemption.reason),
                FieldCheckResult(field="net_quantity", status=FieldStatus.EXEMPT, rule_reference=RULE_REF_NET_QUANTITY, message=exemption.reason),
                FieldCheckResult(field="mfg_packing_date", status=FieldStatus.EXEMPT, rule_reference=RULE_REF_MFG_DATE, message=exemption.reason),
                FieldCheckResult(field="retail_sale_price_mrp", status=FieldStatus.EXEMPT, rule_reference=RULE_REF_MRP, message=exemption.reason),
                FieldCheckResult(field="dimensions", status=FieldStatus.EXEMPT, rule_reference=RULE_REF_DIMENSIONS, message=exemption.reason),
                FieldCheckResult(field="consumer_care_details", status=FieldStatus.EXEMPT, rule_reference=RULE_REF_CONSUMER_CARE, message=exemption.reason),
            ]
            
            return ComplianceReport(
                is_compliant=True,
                overall_status="EXEMPT",
                exemption=exemption,
                field_results=all_fields_exempt,
                violations_count=0,
                violation_summary=[],
                rule_references_flagged=[],
                commodity_category=resolved_category,
                ocr_confidence_score=fields.average_ocr_confidence,
                audit_notes=audit_notes,
            )

        # =========================================================================
        # STEP 2: Field-by-Field Compliance Verification (Rule 6)
        # =========================================================================
        field_confs = fields.field_confidences or {}

        # 1. Rule 6(1)(a) Manufacturer / Packer / Importer
        if exemption.is_partial_exemption:
            field_results.append(FieldCheckResult(
                field="manufacturer_packer_importer",
                status=FieldStatus.EXEMPT,
                rule_reference=RULE_REF_MANUFACTURER,
                message="Exempt on small package (<=20g/ml) under Rule 26."
            ))
        else:
            res_mfg = check_manufacturer_details(
                manufacturer_name=fields.manufacturer_name,
                manufacturer_address=fields.manufacturer_address,
                packer_name=fields.packer_name,
                packer_address=fields.packer_address,
                importer_name=fields.importer_name,
                importer_address=fields.importer_address,
                marketed_by_only=fields.marketed_by_only,
                raw_text=fields.raw_text,
                confidence=field_confs.get("manufacturer"),
                min_confidence_threshold=self.min_confidence_threshold,
            )
            field_results.append(res_mfg)

        # 2. Rule 6(1)(b) Generic Name
        if exemption.is_partial_exemption:
            field_results.append(FieldCheckResult(
                field="generic_name",
                status=FieldStatus.EXEMPT,
                rule_reference=RULE_REF_GENERIC_NAME,
                message="Exempt on small package (<=20g/ml) under Rule 26."
            ))
        else:
            res_gen = check_generic_name(
                generic_name=fields.generic_name,
                brand_name=fields.brand_name,
                raw_text=fields.raw_text,
                confidence=field_confs.get("generic_name"),
                min_confidence_threshold=self.min_confidence_threshold,
            )
            field_results.append(res_gen)

        # 3. Rule 6(1)(c) Net Quantity (Mandatory even for partial small package exemption)
        res_qty = check_net_quantity(
            net_quantity_raw=fields.net_quantity_raw,
            net_quantity_value=fields.net_quantity_value,
            net_quantity_unit=fields.net_quantity_unit,
            has_banned_qualifier=fields.has_banned_qualifier,
            banned_qualifier_word=fields.banned_qualifier_word,
            raw_text=fields.raw_text,
            confidence=field_confs.get("net_quantity"),
            min_confidence_threshold=self.min_confidence_threshold,
        )
        field_results.append(res_qty)

        # 4. Rule 6(1)(d) Month & Year of Manufacture
        if exemption.is_partial_exemption:
            field_results.append(FieldCheckResult(
                field="mfg_packing_date",
                status=FieldStatus.EXEMPT,
                rule_reference=RULE_REF_MFG_DATE,
                message="Exempt on small package (<=20g/ml) under Rule 26."
            ))
        else:
            res_date = check_mfg_packing_date(
                mfg_date_raw=fields.mfg_date_raw,
                mfg_month=fields.mfg_month,
                mfg_year=fields.mfg_year,
                commodity_category=resolved_category,
                raw_text=fields.raw_text,
                confidence=field_confs.get("mfg_date"),
                min_confidence_threshold=self.min_confidence_threshold,
            )
            field_results.append(res_date)

        # 5. Rule 6(1)(e) MRP (Mandatory even for partial small package exemption)
        res_mrp = check_mrp_declaration(
            mrp_raw=fields.mrp_raw,
            mrp_value=fields.mrp_value,
            has_inclusive_of_taxes=fields.has_inclusive_of_taxes,
            raw_text=fields.raw_text,
            confidence=field_confs.get("mrp"),
            min_confidence_threshold=self.min_confidence_threshold,
        )
        field_results.append(res_mrp)

        # 6. Rule 6(1)(f) Dimensions (Conditional)
        if exemption.is_partial_exemption:
            field_results.append(FieldCheckResult(
                field="dimensions",
                status=FieldStatus.EXEMPT,
                rule_reference=RULE_REF_DIMENSIONS,
                message="Exempt on small package (<=20g/ml) under Rule 26."
            ))
        else:
            res_dim = check_dimensions_declaration(
                commodity_category=resolved_category,
                generic_name=fields.generic_name,
                dimensions_raw=fields.dimensions_raw,
                raw_text=fields.raw_text,
                confidence=field_confs.get("dimensions"),
                min_confidence_threshold=self.min_confidence_threshold,
            )
            field_results.append(res_dim)

        # 7. Rule 6(2) Consumer Care Details
        if exemption.is_partial_exemption:
            field_results.append(FieldCheckResult(
                field="consumer_care_details",
                status=FieldStatus.EXEMPT,
                rule_reference=RULE_REF_CONSUMER_CARE,
                message="Exempt on small package (<=20g/ml) under Rule 26."
            ))
        else:
            res_care = check_consumer_care_details(
                consumer_care_raw=fields.consumer_care_raw,
                consumer_care_phone=fields.consumer_care_phone,
                consumer_care_email=fields.consumer_care_email,
                consumer_care_address=fields.consumer_care_address,
                raw_text=fields.raw_text,
                confidence=field_confs.get("consumer_care"),
                min_confidence_threshold=self.min_confidence_threshold,
            )
            field_results.append(res_care)

        # =========================================================================
        # STEP 3: Part C Standard Pack Sizes (Rule 5 + Second Schedule)
        # =========================================================================
        res_pack_size = validate_standard_pack_size(
            commodity=resolved_category,
            quantity_value=fields.net_quantity_value,
            quantity_unit=fields.net_quantity_unit,
            has_disclaimer=fields.has_non_standard_size_disclaimer,
            raw_text=fields.raw_text,
        )
        if res_pack_size.status != FieldStatus.NOT_APPLICABLE:
            field_results.append(res_pack_size)

        # =========================================================================
        # STEP 4: Part F Language & Legibility (Rule 9)
        # =========================================================================
        res_lang = check_language_compliance(
            raw_text=fields.raw_text,
            detected_languages=fields.detected_languages,
            has_hindi_or_english=fields.has_hindi_or_english,
            ocr_confidence=fields.average_ocr_confidence,
            min_confidence_threshold=self.min_confidence_threshold,
        )
        field_results.append(res_lang)

        # =========================================================================
        # STEP 5: Aggregate Audit Results
        # =========================================================================
        violations = [f for f in field_results if f.status == FieldStatus.FAIL]
        violations_count = len(violations)
        violation_summary = [f"{v.field}: [{v.violation_code.value if v.violation_code else 'FAIL'}] {v.message}" for v in violations]
        flagged_rules = list(dict.fromkeys([v.rule_reference for v in violations if v.rule_reference]))

        has_low_conf = any(v.violation_code == ViolationCode.LOW_CONFIDENCE for v in violations)
        has_critical_fail = any(v.violation_code != ViolationCode.LOW_CONFIDENCE for v in violations)

        if violations_count == 0:
            overall_status = "COMPLIANT"
            is_compliant = True
        elif has_low_conf and not has_critical_fail:
            overall_status = "NEEDS_REVIEW"
            is_compliant = False
            audit_notes.append("One or more fields have low OCR confidence; manual operator inspection recommended.")
        else:
            overall_status = "NON_COMPLIANT"
            is_compliant = False

        if exemption.is_partial_exemption:
            audit_notes.append("Evaluated under Rule 26 Partial Exemption (10g-20g/ml): only MRP and Net Quantity enforced.")

        return ComplianceReport(
            is_compliant=is_compliant,
            overall_status=overall_status,
            exemption=exemption,
            field_results=field_results,
            violations_count=violations_count,
            violation_summary=violation_summary,
            rule_references_flagged=flagged_rules,
            commodity_category=resolved_category,
            ocr_confidence_score=fields.average_ocr_confidence,
            audit_notes=audit_notes,
        )
