"""
PackCheck OCR Integration & Extraction Layer
SIH 2026 - Problem Statement SIH26034
"""

from .interface import BaseOCREngine, OCRResult, OCRToken, OCRBlock
from .preprocessor import normalize_ocr_text, analyze_ocr_scripts
from .extractor import PackageFieldExtractor
from .adapters import GenericOCRJsonAdapter, TesseractAdapter, CloudVisionAdapter

__all__ = [
    "BaseOCREngine",
    "OCRResult",
    "OCRToken",
    "OCRBlock",
    "normalize_ocr_text",
    "analyze_ocr_scripts",
    "PackageFieldExtractor",
    "GenericOCRJsonAdapter",
    "TesseractAdapter",
    "CloudVisionAdapter",
]
