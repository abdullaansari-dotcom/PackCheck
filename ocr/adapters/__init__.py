"""
OCR Adapters for various OCR Platforms and formats
SIH 2026 - Problem Statement SIH26034
"""

from .generic_json_adapter import GenericOCRJsonAdapter
from .tesseract_adapter import TesseractAdapter
from .cloud_vision_adapter import CloudVisionAdapter

__all__ = [
    "GenericOCRJsonAdapter",
    "TesseractAdapter",
    "CloudVisionAdapter",
]
