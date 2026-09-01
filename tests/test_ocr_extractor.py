"""
Unit Tests for OCR Extraction and Ingestion Layer
SIH 2026 - Problem Statement SIH26034
"""

import unittest
from ocr.extractor import PackageFieldExtractor
from ocr.adapters import GenericOCRJsonAdapter, TesseractAdapter, CloudVisionAdapter


class TestOCRExtractor(unittest.TestCase):

    def setUp(self):
        self.extractor = PackageFieldExtractor()

    def test_extract_from_realistic_label_text(self):
        sample_label = """
        ZOOMO BLAST
        Carbonated Fruit Drink
        Net Quantity: 250 ml
        MRP: Rs. 35.00 (Inclusive of all taxes)
        Date of Mfg: 03/2026
        Manufactured by: Zoomo Beverages Pvt. Ltd., Plot 102, GIDC Industrial Estate, Surat, Gujarat - 395001
        For customer queries contact: 1800-200-9999 or care@zoomoblast.com
        """
        fields = self.extractor.extract_from_text(sample_label, confidence=0.98)

        self.assertEqual(fields.generic_name, "Carbonated Fruit Drink")
        self.assertEqual(fields.net_quantity_value, 250.0)
        self.assertEqual(fields.net_quantity_unit, "ml")
        self.assertEqual(fields.mrp_value, 35.0)
        self.assertTrue(fields.has_inclusive_of_taxes)
        self.assertEqual(fields.mfg_date_raw, "03/2026")
        self.assertEqual(fields.manufacturer_name, "Zoomo Beverages Pvt. Ltd.")
        self.assertIn("Surat, Gujarat - 395001", fields.manufacturer_address or "")
        self.assertEqual(fields.consumer_care_phone, "1800-200-9999")
        self.assertEqual(fields.consumer_care_email, "care@zoomoblast.com")
        self.assertTrue(fields.has_hindi_or_english)

    def test_extract_vague_qualifier(self):
        sample_vague = """
        Instant Coffee
        Net Wt: Approx 500g
        MRP: Rs 200.00 (Inclusive of all taxes)
        Mfg: Mar 2026
        Manufactured by: ABC Coffee, Chikmagalur, Karnataka - 577101
        Customer care: 9876543210
        """
        fields = self.extractor.extract_from_text(sample_vague)
        self.assertEqual(fields.net_quantity_value, 500.0)
        self.assertEqual(fields.net_quantity_unit, "g")
        self.assertTrue(fields.has_banned_qualifier)
        self.assertEqual(fields.banned_qualifier_word, "approx")

    def test_generic_json_adapter(self):
        adapter = GenericOCRJsonAdapter()
        payload = {
            "text": "Manufactured by ABC Ltd\nMRP Rs. 100\nNet Wt 200g",
            "tokens": [
                {"text": "Manufactured", "confidence": 0.98},
                {"text": "by", "confidence": 0.99},
                {"text": "ABC", "confidence": 0.95},
                {"text": "Ltd", "confidence": 0.96},
            ],
            "confidence": 0.97
        }
        res = adapter.extract_text(payload)
        self.assertEqual(len(res.tokens), 4)
        self.assertAlmostEqual(res.average_confidence, 0.97, places=2)

    def test_cloud_vision_adapter(self):
        adapter = CloudVisionAdapter()
        payload = {
            "textAnnotations": [
                {"description": "Net Wt 100g\nMRP Rs 50.00 (Inclusive of all taxes)", "confidence": 0.95}
            ]
        }
        res = adapter.extract_text(payload)
        self.assertIn("Net Wt 100g", res.raw_text)


if __name__ == "__main__":
    unittest.main()
