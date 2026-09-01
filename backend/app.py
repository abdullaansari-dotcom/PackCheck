"""
PackCheck Compliance Engine - REST API Server
SIH 2026 - Problem Statement SIH26034
Legal Metrology (Packaged Commodities) Rules, 2011
"""

import os
import sys
from flask import Flask, jsonify, make_response
from .routes import compliance_bp


def create_app() -> Flask:
    """Application factory for PackCheck API Server."""
    app = Flask(__name__)

    # Enable CORS headers for frontend and microservice access
    @app.after_request
    def add_cors_headers(response):
        response.headers["Access-Control-Allow-Origin"] = "*"
        response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, OPTIONS"
        response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization, X-Requested-With"
        return response

    # Global Error Handlers
    @app.errorhandler(404)
    def not_found_handler(e):
        return jsonify({
            "error": "NOT_FOUND",
            "message": "The requested API endpoint was not found.",
            "available_endpoints": [
                "/api/health",
                "/api/compliance/check-text",
                "/api/compliance/check-fields",
                "/api/compliance/check-ocr",
                "/api/compliance/standard-sizes",
                "/api/compliance/rules",
                "/api/compliance/exemptions"
            ]
        }), 404

    @app.errorhandler(500)
    def internal_error_handler(e):
        return jsonify({
            "error": "INTERNAL_SERVER_ERROR",
            "message": "An unexpected error occurred within the compliance rules engine.",
            "detail": str(e)
        }), 500

    # Register API Blueprint
    app.register_blueprint(compliance_bp)

    @app.route("/", methods=["GET"])
    def root():
        return jsonify({
            "project": "PackCheck - Legal Metrology Compliance Engine",
            "hackathon": "Smart India Hackathon 2026",
            "problem_statement": "SIH26034",
            "status": "online",
            "documentation": "/api/compliance/rules"
        })

    return app


app = create_app()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    host = os.environ.get("HOST", "0.0.0.0")
    print(f"🚀 Starting PackCheck Compliance Engine on http://{host}:{port}")
    app.run(host=host, port=port, debug=True)
