"""
PackCheck OCR Integration & Compliance Demo
SIH 2026 - Problem Statement SIH26034
Legal Metrology (Packaged Commodities) Rules, 2011

Demonstrates how to connect an OCR platform / pipeline to PackCheck backend.
"""

import sys
import json

# Ensure UTF-8 output if supported
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

from ocr import PackageFieldExtractor, GenericOCRJsonAdapter, CloudVisionAdapter
from compliance import ComplianceEngine


def demo_raw_text_scan():
    print("=" * 70)
    print("DEMO 1: Processing Raw OCR Text (from Camera / Tesseract / EasyOCR)")
    print("=" * 70)

    sample_ocr_text = """
    PARLE-G
    Glucose Biscuits
    Net Weight: 100 g
    MRP: Rs. 10.00 (Inclusive of all taxes)
    Date of Mfg: 03/2026
    Manufactured by: Parle Products Pvt. Ltd., North Level Crossing, Vile Parle East, Mumbai, Maharashtra - 400057
    Customer Care Toll-Free: 1800-22-7777 / care@parle.biz
    """

    extractor = PackageFieldExtractor()
    engine = ComplianceEngine()

    # 1. Extract entities from OCR text
    extracted_fields = extractor.extract_from_text(sample_ocr_text, confidence=0.98)
    print(f"[OK] Extracted Commodity: {extracted_fields.generic_name}")
    print(f"[OK] Extracted Net Qty: {extracted_fields.net_quantity_value} {extracted_fields.net_quantity_unit}")
    print(f"[OK] Extracted MRP: Rs. {extracted_fields.mrp_value} (Tax included: {extracted_fields.has_inclusive_of_taxes})")

    # 2. Run Legal Metrology compliance rules engine
    report = engine.evaluate(fields=extracted_fields, commodity_category="biscuits")

    print("\n--- COMPLIANCE AUDIT RESULT ---")
    print(f"Overall Status: {report.overall_status} (Compliant: {report.is_compliant})")
    print(f"Violations Count: {report.violations_count}")
    for res in report.field_results:
        status_symbol = "[PASS]" if res.status == "PASS" else ("[" + res.status + "]")
        v_code = f" [{res.violation_code}]" if res.violation_code else ""
        print(f"  * {res.field:<30}: {status_symbol:<10} {res.rule_reference:<20} {v_code}")


def demo_violation_detection():
    print("\n" + "=" * 70)
    print("DEMO 2: Detecting Violations (Vague Qualifier + Non-Standard Pack + Missing Taxes)")
    print("=" * 70)

    # Violations:
    # 1. Net Qty uses 'Approx' -> VAGUE_LANGUAGE (Rule 6(1)(c))
    # 2. Pack size is 120g tea (not standard size and no disclaimer) -> NONSTANDARD_PACK (Rule 5)
    # 3. MRP has no 'inclusive of all taxes' -> FORMAT_ERROR (Rule 6(1)(e))
    # 4. Marketed by only with no manufacturer -> FORMAT_ERROR (Rule 6(1)(a))
    bad_ocr_text = """
    ROYAL CHAI
    Tea
    Net Wt: Approx 120g
    MRP: Rs 65.00
    Mfg: 03/2026
    Marketed by: Fast Marketing Solutions, Delhi - 110001
    Care Helpline: 1800-999-8888
    """

    extractor = PackageFieldExtractor()
    engine = ComplianceEngine()

    fields = extractor.extract_from_text(bad_ocr_text, confidence=0.92)
    report = engine.evaluate(fields=fields, commodity_category="tea")

    print(f"Overall Status: {report.overall_status} (Compliant: {report.is_compliant})")
    print(f"Total Violations: {report.violations_count}\n")
    for v in report.violation_summary:
        print(f"  [X] {v}")


def demo_ocr_json_payload():
    print("\n" + "=" * 70)
    print("DEMO 3: Ingesting Structured OCR JSON Payload (Bounding Boxes & Confidence)")
    print("=" * 70)

    ocr_platform_response = {
        "text": "PURE SALT\nRefined Iodised Salt\nNet Qty 1 kg\nMRP Rs. 28.00 (Inclusive of all taxes)\nMfg 03/2026\nManufactured by: Salt Works Ltd, Gandhidham, Gujarat - 370201\nCare: 1800-456-7890",
        "tokens": [
            {"text": "PURE", "confidence": 0.99},
            {"text": "SALT", "confidence": 0.98},
            {"text": "1", "confidence": 0.99},
            {"text": "kg", "confidence": 0.99},
            {"text": "28.00", "confidence": 0.95},
        ],
        "confidence": 0.97
    }

    adapter = GenericOCRJsonAdapter()
    ocr_result = adapter.extract_text(ocr_platform_response)

    extractor = PackageFieldExtractor()
    fields = extractor.extract_from_ocr_result(ocr_result)

    engine = ComplianceEngine()
    report = engine.evaluate(fields=fields, commodity_category="salt")

    print(f"Average OCR Confidence: {report.ocr_confidence_score * 100:.1f}%")
    print(f"Overall Compliance: {report.overall_status}")
    print(json.dumps(report.to_dict(), indent=2))


if __name__ == "__main__":
    demo_raw_text_scan()
    demo_violation_detection()
    demo_ocr_json_payload()
