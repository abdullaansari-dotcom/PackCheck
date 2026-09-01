"""
Unit Tests for PackCheck Backend REST API Endpoints
SIH 2026 - Problem Statement SIH26034
"""

import unittest
import json
from backend.app import create_app


class TestPackCheckAPI(unittest.TestCase):

    def setUp(self):
        self.app = create_app()
        self.client = self.app.test_client()

    def test_health_endpoint(self):
        response = self.client.get("/api/health")
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(data["status"], "healthy")
        self.assertEqual(data["service"], "PackCheck Compliance Engine")

    def test_rules_endpoint(self):
        response = self.client.get("/api/compliance/rules")
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertIn("Rule 6(1)(a)", data["rules"])
        self.assertIn("Rule 6(1)(e)", data["rules"])

    def test_standard_sizes_endpoint(self):
        response = self.client.get("/api/compliance/standard-sizes")
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertIn("tea", data["regulated_commodities"])
        self.assertIn("biscuits", data["regulated_commodities"])

    def test_exemptions_endpoint(self):
        response = self.client.get("/api/compliance/exemptions")
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertTrue(len(data["exemption_categories"]) >= 4)

    def test_check_text_endpoint_pass(self):
        payload = {
            "text": """
            BRAND: ZOOMO
            Generic: Carbonated Soft Drink
            Net Vol: 250ml
            MRP: Rs 20.00 (Inclusive of all taxes)
            Mfg: 03/2026
            Manufactured by: Cool Drinks Pvt Ltd, Plot 5, Pune, Maharashtra - 411001
            Care: care@cooldrinks.com
            """,
            "commodity_category": "aerated_drinks",
            "confidence": 0.95
        }
        response = self.client.post(
            "/api/compliance/check-text",
            data=json.dumps(payload),
            content_type="application/json"
        )
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertTrue(data["is_compliant"])
        self.assertEqual(data["overall_status"], "COMPLIANT")

    def test_check_text_endpoint_mrp_format_error(self):
        payload = {
            "text": """
            BRAND: ZOOMO
            Generic: Carbonated Soft Drink
            Net Vol: 250ml
            MRP: Rs 20.00
            Mfg: 03/2026
            Manufactured by: Cool Drinks Pvt Ltd, Plot 5, Pune, Maharashtra - 411001
            Care: care@cooldrinks.com
            """,
            "commodity_category": "aerated_drinks",
            "confidence": 0.95
        }
        response = self.client.post(
            "/api/compliance/check-text",
            data=json.dumps(payload),
            content_type="application/json"
        )
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertFalse(data["is_compliant"])
        self.assertIn("Rule 6(1)(e)", data["rule_references_flagged"])

    def test_check_fields_endpoint(self):
        payload = {
            "manufacturer_name": "ABC Foods Pvt Ltd",
            "manufacturer_address": "Ind. Estate, Delhi - 110001",
            "generic_name": "Tea",
            "net_quantity_value": 120.0,
            "net_quantity_unit": "g",
            "has_non_standard_size_disclaimer": False,
            "mfg_date_raw": "03/2026",
            "mrp_value": 45.0,
            "has_inclusive_of_taxes": True,
            "consumer_care_phone": "1800-111-2222",
            "commodity_category": "tea"
        }
        response = self.client.post(
            "/api/compliance/check-fields",
            data=json.dumps(payload),
            content_type="application/json"
        )
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        # 120g tea without disclaimer must fail
        self.assertFalse(data["is_compliant"])
        self.assertIn("Rule 5 / Second Schedule", data["rule_references_flagged"])


if __name__ == "__main__":
    unittest.main()
