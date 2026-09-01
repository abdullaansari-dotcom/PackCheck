"""
API Route Handlers for PackCheck Compliance System
SIH 2026 - Problem Statement SIH26034
Legal Metrology (Packaged Commodities) Rules, 2011
"""

from flask import Blueprint, request, jsonify
from .service import ComplianceService

compliance_bp = Blueprint("compliance", __name__, url_prefix="/api")
service = ComplianceService()


@compliance_bp.route("/health", methods=["GET"])
def health_check():
    """Health check status endpoint."""
    return jsonify({
        "status": "healthy",
        "service": "PackCheck Compliance Engine",
        "version": "1.0.0",
        "standard": "Legal Metrology (Packaged Commodities) Rules, 2011"
    }), 200


@compliance_bp.route("/compliance/check-text", methods=["POST"])
def check_text():
    """
    Evaluates raw OCR text string for Legal Metrology compliance.
    Request JSON:
    {
        "text": "Manufactured by XYZ Foods Pvt Ltd, Mumbai - 400001...",
        "commodity_category": "biscuits",
        "brand_name": "Crunchy Bites",
        "is_fast_food": false,
        "confidence": 0.95
    }
    """
    data = request.get_json(silent=True) or {}
    text = data.get("text")
    if not text or not str(text).strip():
        return jsonify({
            "error": "BAD_REQUEST",
            "message": "Field 'text' is required and must not be empty."
        }), 400

    report = service.check_raw_text(
        text=str(text),
        commodity_category=data.get("commodity_category"),
        brand_name=data.get("brand_name"),
        is_fast_food=bool(data.get("is_fast_food", False)),
        is_scheduled_drug=bool(data.get("is_scheduled_drug", False)),
        is_agricultural_produce=bool(data.get("is_agricultural_produce", False)),
        confidence=float(data.get("confidence", 1.0)),
    )
    return jsonify(report), 200


@compliance_bp.route("/compliance/check-fields", methods=["POST"])
def check_fields():
    """
    Evaluates pre-extracted / structured fields dictionary for Legal Metrology compliance.
    """
    data = request.get_json(silent=True) or {}
    if not data:
        return jsonify({
            "error": "BAD_REQUEST",
            "message": "Request body cannot be empty JSON."
        }), 400

    report = service.check_structured_fields(data)
    return jsonify(report), 200


@compliance_bp.route("/compliance/check-ocr", methods=["POST"])
def check_ocr_payload():
    """
    Evaluates full OCR engine JSON payload (tokens, bounding boxes, confidences).
    Request JSON:
    {
        "ocr_payload": { ... },
        "adapter_type": "generic" | "tesseract" | "cloud_vision",
        "commodity_category": "tea"
    }
    """
    data = request.get_json(silent=True) or {}
    payload = data.get("ocr_payload")
    if not payload:
        return jsonify({
            "error": "BAD_REQUEST",
            "message": "Field 'ocr_payload' is required."
        }), 400

    report = service.check_ocr_payload(
        payload=payload,
        adapter_type=data.get("adapter_type", "generic"),
        commodity_category=data.get("commodity_category"),
        brand_name=data.get("brand_name"),
        is_fast_food=bool(data.get("is_fast_food", False)),
        is_scheduled_drug=bool(data.get("is_scheduled_drug", False)),
        is_agricultural_produce=bool(data.get("is_agricultural_produce", False)),
    )
    return jsonify(report), 200


@compliance_bp.route("/compliance/standard-sizes", methods=["GET"])
def get_standard_sizes():
    """Returns statutory standard pack sizes table under Rule 5 and Second Schedule."""
    return jsonify(service.get_standard_sizes_info()), 200


@compliance_bp.route("/compliance/rules", methods=["GET"])
def get_rules():
    """Returns statutory rule references and violation taxonomy."""
    return jsonify(service.get_rules_reference_info()), 200


@compliance_bp.route("/compliance/exemptions", methods=["GET"])
def get_exemptions():
    """Returns statutory Rule 26 exemption information."""
    return jsonify({
        "legal_basis": "Rule 26, Legal Metrology (Packaged Commodities) Rules, 2011",
        "exemption_categories": [
            {
                "type": "VERY_SMALL_PACKAGE",
                "condition": "Net weight/measure <= 10g or <= 10ml",
                "scope": "Fully exempt from Chapter II declaration requirements."
            },
            {
                "type": "SMALL_PACKAGE_PARTIAL",
                "condition": "Net weight/measure > 10g and <= 20g (or 10ml-20ml)",
                "scope": "Exempt from manufacturer name, mfg date, consumer care; MRP and Net Quantity remain mandatory."
            },
            {
                "type": "FAST_FOOD",
                "condition": "Directly packed by restaurants/hotels for immediate sale",
                "scope": "Fully exempt from Chapter II."
            },
            {
                "type": "SCHEDULED_DRUG",
                "condition": "Formulations governed by Drugs (Price Control) Order",
                "scope": "Exempt from LM(PC) rules; governed by DPCO."
            },
            {
                "type": "LARGE_AGRICULTURAL_PRODUCE",
                "condition": "Agricultural produce packages > 50kg",
                "scope": "Exempt from standard packaged commodity rules."
            }
        ]
    }), 200
