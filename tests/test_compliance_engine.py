"""
Comprehensive Unit Tests for Legal Metrology Compliance Engine
SIH 2026 - Problem Statement SIH26034
Legal Metrology (Packaged Commodities) Rules, 2011 (GSR 202(E))
"""

import unittest
from compliance.models import (
    FieldStatus,
    ViolationCode,
    ExtractedFields,
    PackageCategory,
)
from compliance.engine import ComplianceEngine
from compliance.standard_sizes import is_allowed_standard_size, validate_standard_pack_size
from compliance.exemptions import evaluate_exemption
from compliance.constants import (
    RULE_REF_MANUFACTURER,
    RULE_REF_GENERIC_NAME,
    RULE_REF_NET_QUANTITY,
    RULE_REF_MFG_DATE,
    RULE_REF_MRP,
    RULE_REF_DIMENSIONS,
    RULE_REF_CONSUMER_CARE,
    RULE_REF_STANDARD_SIZES,
    RULE_REF_LEGIBILITY_LANGUAGE,
    RULE_REF_EXEMPTIONS,
)


class TestLegalMetrologyComplianceEngine(unittest.TestCase):

    def setUp(self):
        self.engine = ComplianceEngine()

    def test_full_compliant_package(self):
        """Test a fully compliant consumer goods package."""
        fields = ExtractedFields(
            manufacturer_name="XYZ Foods Pvt. Ltd.",
            manufacturer_address="Plot 14, Industrial Area, Nashik, Maharashtra – 422010",
            generic_name="Carbonated Fruit Drink",
            brand_name="Zoomo Blast",
            net_quantity_raw="Net Vol. 500ml",
            net_quantity_value=500.0,
            net_quantity_unit="ml",
            mfg_date_raw="Mfg: March 2026",
            mfg_month=3,
            mfg_year=2026,
            mrp_raw="MRP: Rs 45.00",
            mrp_value=45.00,
            has_inclusive_of_taxes=True,
            consumer_care_phone="1800-123-4567",
            consumer_care_email="care@xyzfoods.com",
            detected_languages=["English (Latin)"],
            has_hindi_or_english=True,
            average_ocr_confidence=0.95,
            raw_text="Zoomo Blast Carbonated Fruit Drink Net Vol. 500ml MRP: Rs 45.00 (Inclusive of all taxes) Mfg: March 2026 Manufactured by: XYZ Foods Pvt. Ltd., Plot 14, Industrial Area, Nashik, Maharashtra - 422010. Care: 1800-123-4567"
        )

        report = self.engine.evaluate(fields=fields, commodity_category="aerated_drinks")
        self.assertTrue(report.is_compliant)
        self.assertEqual(report.overall_status, "COMPLIANT")
        self.assertEqual(report.violations_count, 0)
        self.assertEqual(len(report.rule_references_flagged), 0)

    # ----------------------------------------------------
    # Rule 6(1)(a) Manufacturer / Packer / Importer
    # ----------------------------------------------------
    def test_rule_6_1_a_marketed_by_only(self):
        """FAIL (common dodge): Label says only 'Marketed by' with no manufacturer."""
        fields = ExtractedFields(
            manufacturer_name="XYZ Marketing Ltd.",
            marketed_by_only=True,
            generic_name="Instant Noodles",
            net_quantity_value=70.0,
            net_quantity_unit="g",
            mfg_date_raw="03/2026",
            mrp_value=15.0,
            has_inclusive_of_taxes=True,
            consumer_care_phone="1800-000-0000",
            raw_text="Marketed by XYZ Marketing Ltd."
        )
        report = self.engine.evaluate(fields=fields)
        self.assertFalse(report.is_compliant)
        
        mfg_result = next(f for f in report.field_results if f.field == "manufacturer_packer_importer")
        self.assertEqual(mfg_result.status, FieldStatus.FAIL)
        self.assertEqual(mfg_result.violation_code, ViolationCode.FORMAT_ERROR)
        self.assertEqual(mfg_result.rule_reference, RULE_REF_MANUFACTURER)

    def test_rule_6_1_a_missing_manufacturer(self):
        """Missing manufacturer/packer entirely."""
        fields = ExtractedFields(
            generic_name="Biscuits",
            net_quantity_value=100.0,
            net_quantity_unit="g",
            mfg_date_raw="03/2026",
            mrp_value=20.0,
            has_inclusive_of_taxes=True,
            consumer_care_phone="1800-000-0000"
        )
        report = self.engine.evaluate(fields=fields)
        mfg_result = next(f for f in report.field_results if f.field == "manufacturer_packer_importer")
        self.assertEqual(mfg_result.status, FieldStatus.FAIL)
        self.assertEqual(mfg_result.violation_code, ViolationCode.MISSING)

    # ----------------------------------------------------
    # Rule 6(1)(b) Generic Name
    # ----------------------------------------------------
    def test_rule_6_1_b_missing_generic_name(self):
        """FAIL: Only brand name appears anywhere, no generic descriptor at all."""
        fields = ExtractedFields(
            manufacturer_name="XYZ Ltd",
            manufacturer_address="Mumbai - 400001",
            brand_name="Zoomo Blast",
            generic_name=None,
            net_quantity_value=250.0,
            net_quantity_unit="ml",
            mfg_date_raw="03/2026",
            mrp_value=30.0,
            has_inclusive_of_taxes=True,
            consumer_care_phone="1800-000-0000"
        )
        report = self.engine.evaluate(fields=fields)
        gen_result = next(f for f in report.field_results if f.field == "generic_name")
        self.assertEqual(gen_result.status, FieldStatus.FAIL)
        self.assertEqual(gen_result.violation_code, ViolationCode.MISSING)
        self.assertEqual(gen_result.rule_reference, RULE_REF_GENERIC_NAME)

    # ----------------------------------------------------
    # Rule 6(1)(c) Net Quantity & Banned Qualifiers
    # ----------------------------------------------------
    def test_rule_6_1_c_vague_qualifier_approx(self):
        """FAIL: 'Net Wt: Approx 100g' uses banned qualifiers."""
        fields = ExtractedFields(
            manufacturer_name="XYZ Ltd",
            manufacturer_address="Mumbai - 400001",
            generic_name="Tea",
            net_quantity_raw="Net Wt: Approx 100g",
            net_quantity_value=100.0,
            net_quantity_unit="g",
            has_banned_qualifier=True,
            banned_qualifier_word="approx",
            mfg_date_raw="03/2026",
            mrp_value=50.0,
            has_inclusive_of_taxes=True,
            consumer_care_phone="1800-000-0000"
        )
        report = self.engine.evaluate(fields=fields)
        qty_result = next(f for f in report.field_results if f.field == "net_quantity")
        self.assertEqual(qty_result.status, FieldStatus.FAIL)
        self.assertEqual(qty_result.violation_code, ViolationCode.VAGUE_LANGUAGE)
        self.assertEqual(qty_result.rule_reference, RULE_REF_NET_QUANTITY)

    def test_rule_6_1_c_banned_unit_dozen(self):
        """FAIL: Declared in 'dozen' when not permitted."""
        fields = ExtractedFields(
            manufacturer_name="XYZ Ltd",
            manufacturer_address="Mumbai - 400001",
            generic_name="Biscuits",
            net_quantity_raw="1 dozen",
            net_quantity_value=1.0,
            net_quantity_unit="dozen",
            mfg_date_raw="03/2026",
            mrp_value=60.0,
            has_inclusive_of_taxes=True,
            consumer_care_phone="1800-000-0000"
        )
        report = self.engine.evaluate(fields=fields)
        qty_result = next(f for f in report.field_results if f.field == "net_quantity")
        self.assertEqual(qty_result.status, FieldStatus.FAIL)
        self.assertEqual(qty_result.violation_code, ViolationCode.UNIT_ERROR)

    # ----------------------------------------------------
    # Rule 6(1)(d) Month & Year of Manufacture
    # ----------------------------------------------------
    def test_rule_6_1_d_mfg_date_exempt_incense_sticks(self):
        """EXEMPT: Agarbatti / Incense sticks / LPG cylinders do not require mfg date."""
        fields = ExtractedFields(
            manufacturer_name="XYZ Agarbatti Works",
            manufacturer_address="Mysuru, Karnataka - 570001",
            generic_name="Incense Sticks",
            net_quantity_value=50.0,
            net_quantity_unit="g",
            mfg_date_raw=None,  # missing date
            mrp_value=25.0,
            has_inclusive_of_taxes=True,
            consumer_care_phone="1800-000-0000"
        )
        report = self.engine.evaluate(fields=fields, commodity_category="incense sticks")
        date_result = next(f for f in report.field_results if f.field == "mfg_packing_date")
        self.assertEqual(date_result.status, FieldStatus.EXEMPT)
        self.assertEqual(date_result.rule_reference, RULE_REF_MFG_DATE)

    # ----------------------------------------------------
    # Rule 6(1)(e) Retail Sale Price (MRP) & Tax Phrase
    # ----------------------------------------------------
    def test_rule_6_1_e_mrp_without_inclusive_of_taxes(self):
        """
        FAIL - FORMAT_ERROR (not MISSING):
        'MRP: Rs 45.00' - price is present but mandatory tax phrase is absent.
        """
        fields = ExtractedFields(
            manufacturer_name="XYZ Ltd",
            manufacturer_address="Mumbai - 400001",
            generic_name="Fruit Drink",
            net_quantity_value=200.0,
            net_quantity_unit="ml",
            mfg_date_raw="03/2026",
            mrp_raw="MRP: Rs 45.00",
            mrp_value=45.0,
            has_inclusive_of_taxes=False,  # MISSING TAX PHRASE
            consumer_care_phone="1800-000-0000",
            raw_text="MRP: Rs 45.00"
        )
        report = self.engine.evaluate(fields=fields)
        mrp_result = next(f for f in report.field_results if f.field == "retail_sale_price_mrp")
        self.assertEqual(mrp_result.status, FieldStatus.FAIL)
        self.assertEqual(mrp_result.violation_code, ViolationCode.FORMAT_ERROR)
        self.assertEqual(mrp_result.rule_reference, RULE_REF_MRP)

    # ----------------------------------------------------
    # Rule 6(1)(f) Dimensions of the Commodity
    # ----------------------------------------------------
    def test_rule_6_1_f_dimensions_conditional(self):
        """Food/FMCG is NOT_APPLICABLE; Bedsheet requires dimensions."""
        # Food product
        fields_food = ExtractedFields(
            manufacturer_name="XYZ Ltd",
            manufacturer_address="Mumbai - 400001",
            generic_name="Biscuits",
            net_quantity_value=100.0,
            net_quantity_unit="g",
            mfg_date_raw="03/2026",
            mrp_value=10.0,
            has_inclusive_of_taxes=True,
            consumer_care_phone="1800-000-0000"
        )
        report_food = self.engine.evaluate(fields=fields_food, commodity_category="biscuits")
        dim_food = next(f for f in report_food.field_results if f.field == "dimensions")
        self.assertEqual(dim_food.status, FieldStatus.NOT_APPLICABLE)

        # Bedsheet without dimensions
        fields_sheet = ExtractedFields(
            manufacturer_name="XYZ Textiles",
            manufacturer_address="Surat, Gujarat - 395002",
            generic_name="Cotton Bedsheet",
            net_quantity_value=1.0,
            net_quantity_unit="piece",
            mfg_date_raw="03/2026",
            mrp_value=599.0,
            has_inclusive_of_taxes=True,
            consumer_care_phone="1800-000-0000",
            dimensions_raw=None
        )
        report_sheet = self.engine.evaluate(fields=fields_sheet, commodity_category="bedsheet")
        dim_sheet = next(f for f in report_sheet.field_results if f.field == "dimensions")
        self.assertEqual(dim_sheet.status, FieldStatus.FAIL)
        self.assertEqual(dim_sheet.violation_code, ViolationCode.MISSING)

    # ----------------------------------------------------
    # Part C - Rule 5 + Second Schedule Standard Pack Sizes
    # ----------------------------------------------------
    def test_standard_pack_size_tea_120g_without_disclaimer(self):
        """A 120g tea packet without 'Non-standard size' disclaimer must FAIL with NONSTANDARD_PACK."""
        fields = ExtractedFields(
            manufacturer_name="XYZ Tea Ltd",
            manufacturer_address="Kolkata - 700001",
            generic_name="Tea",
            net_quantity_value=120.0,
            net_quantity_unit="g",
            mfg_date_raw="03/2026",
            mrp_value=60.0,
            has_inclusive_of_taxes=True,
            consumer_care_phone="1800-000-0000",
            has_non_standard_size_disclaimer=False,
            raw_text="Tea 120g"
        )
        report = self.engine.evaluate(fields=fields, commodity_category="tea")
        pack_res = next(f for f in report.field_results if f.field == "standard_pack_size")
        self.assertEqual(pack_res.status, FieldStatus.FAIL)
        self.assertEqual(pack_res.violation_code, ViolationCode.NONSTANDARD_PACK)
        self.assertEqual(pack_res.rule_reference, RULE_REF_STANDARD_SIZES)

    def test_standard_pack_size_tea_120g_with_disclaimer(self):
        """A 120g tea packet WITH 'Non-standard size' disclaimer must PASS."""
        fields = ExtractedFields(
            manufacturer_name="XYZ Tea Ltd",
            manufacturer_address="Kolkata - 700001",
            generic_name="Tea",
            net_quantity_value=120.0,
            net_quantity_unit="g",
            mfg_date_raw="03/2026",
            mrp_value=60.0,
            has_inclusive_of_taxes=True,
            consumer_care_phone="1800-000-0000",
            has_non_standard_size_disclaimer=True,
            raw_text="Tea 120g Non-standard size promotional pack"
        )
        report = self.engine.evaluate(fields=fields, commodity_category="tea")
        pack_res = next(f for f in report.field_results if f.field == "standard_pack_size")
        self.assertEqual(pack_res.status, FieldStatus.PASS)

    def test_standard_pack_size_aerated_drinks(self):
        """Allowed aerated drink sizes (250ml, 330ml can, 750ml, 1L, etc.)."""
        self.assertTrue(is_allowed_standard_size("aerated_drinks", 250, "ml"))
        self.assertTrue(is_allowed_standard_size("aerated_drinks", 330, "ml"))
        self.assertTrue(is_allowed_standard_size("aerated_drinks", 1, "l"))
        self.assertFalse(is_allowed_standard_size("aerated_drinks", 420, "ml"))

    # ----------------------------------------------------
    # Part E - Rule 26 Statutory Exemptions
    # ----------------------------------------------------
    def test_rule_26_very_small_package_exemption(self):
        """Package <= 10g or <= 10ml is fully exempt from Chapter II."""
        fields = ExtractedFields(
            generic_name="Chewing Gum",
            net_quantity_value=5.0,
            net_quantity_unit="g",
        )
        report = self.engine.evaluate(fields=fields)
        self.assertTrue(report.is_compliant)
        self.assertEqual(report.overall_status, "EXEMPT")
        self.assertTrue(report.exemption.is_exempt)
        self.assertEqual(report.exemption.exemption_type, "VERY_SMALL_PACKAGE")

    def test_rule_26_small_package_partial_exemption(self):
        """Package 10g-20g: exempt from maker/date/care, but Net Qty + MRP mandatory."""
        fields = ExtractedFields(
            net_quantity_value=15.0,
            net_quantity_unit="g",
            mrp_value=5.0,
            has_inclusive_of_taxes=True
            # No manufacturer, date, or consumer care provided
        )
        report = self.engine.evaluate(fields=fields)
        self.assertTrue(report.is_compliant)
        self.assertTrue(report.exemption.is_partial_exemption)

    def test_rule_26_fast_food_exemption(self):
        """Fast food packed directly by restaurant is fully exempt."""
        ex = evaluate_exemption(is_fast_food=True)
        self.assertTrue(ex.is_exempt)
        self.assertEqual(ex.exemption_type, "FAST_FOOD")

    def test_rule_26_large_agricultural_produce_exemption(self):
        """Agricultural produce > 50kg is exempt."""
        ex = evaluate_exemption(is_agricultural_produce=True, net_quantity_value=55.0, net_quantity_unit="kg")
        self.assertTrue(ex.is_exempt)
        self.assertEqual(ex.exemption_type, "LARGE_AGRICULTURAL_PRODUCE")

    # ----------------------------------------------------
    # Part F - Rule 9 Language & Legibility
    # ----------------------------------------------------
    def test_rule_9_language_error_regional_only(self):
        """FAIL: Only a regional language present, no Hindi or English."""
        fields = ExtractedFields(
            manufacturer_name="XYZ",
            manufacturer_address="Chennai",
            generic_name="Coffee",
            net_quantity_value=100.0,
            net_quantity_unit="g",
            mfg_date_raw="03/2026",
            mrp_value=40.0,
            has_inclusive_of_taxes=True,
            consumer_care_phone="1800-000-0000",
            detected_languages=["Tamil"],
            has_hindi_or_english=False,
            raw_text="தமிழ் மட்டுமே"  # Tamil only
        )
        report = self.engine.evaluate(fields=fields)
        lang_res = next(f for f in report.field_results if f.field == "language_and_legibility")
        self.assertEqual(lang_res.status, FieldStatus.FAIL)
        self.assertEqual(lang_res.violation_code, ViolationCode.LANGUAGE_ERROR)
        self.assertEqual(lang_res.rule_reference, RULE_REF_LEGIBILITY_LANGUAGE)

    def test_rule_9_low_ocr_confidence(self):
        """LOW_CONFIDENCE proxy when OCR score is below 0.60."""
        fields = ExtractedFields(
            manufacturer_name="XYZ Ltd",
            manufacturer_address="Mumbai - 400001",
            generic_name="Snacks",
            net_quantity_value=50.0,
            net_quantity_unit="g",
            mfg_date_raw="03/2026",
            mrp_value=10.0,
            has_inclusive_of_taxes=True,
            consumer_care_phone="1800-000-0000",
            average_ocr_confidence=0.45,  # LOW CONFIDENCE
            raw_text="Blurry text"
        )
        report = self.engine.evaluate(fields=fields)
        self.assertEqual(report.overall_status, "NEEDS_REVIEW")
        lang_res = next(f for f in report.field_results if f.field == "language_and_legibility")
        self.assertEqual(lang_res.violation_code, ViolationCode.LOW_CONFIDENCE)


if __name__ == "__main__":
    unittest.main()
