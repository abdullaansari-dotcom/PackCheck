"""
OCR Integration Contracts & Abstract Interfaces
SIH 2026 - Problem Statement SIH26034
PackCheck AI/OCR Pipeline Interop Layer
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Tuple


@dataclass
class OCRToken:
    """
    Represents an individual OCR token / word with spatial and confidence data.
    """
    text: str
    confidence: float = 1.0
    bbox: Optional[Tuple[float, float, float, float]] = None  # (x_min, y_min, x_max, y_max)
    polygon: Optional[List[Tuple[float, float]]] = None
    language: Optional[str] = None


@dataclass
class OCRBlock:
    """
    Represents a line or paragraph block of OCR text.
    """
    text: str
    tokens: List[OCRToken] = field(default_factory=list)
    confidence: float = 1.0
    bbox: Optional[Tuple[float, float, float, float]] = None


@dataclass
class OCRResult:
    """
    Standardized payload received from any OCR engine or platform.
    """
    raw_text: str
    tokens: List[OCRToken] = field(default_factory=list)
    blocks: List[OCRBlock] = field(default_factory=list)
    average_confidence: float = 1.0
    detected_languages: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "raw_text": self.raw_text,
            "average_confidence": round(self.average_confidence, 4),
            "detected_languages": self.detected_languages,
            "tokens_count": len(self.tokens),
            "blocks_count": len(self.blocks),
            "metadata": self.metadata,
        }


class BaseOCREngine(ABC):
    """
    Abstract interface for plugging in OCR engines (Tesseract, EasyOCR, Vision API, custom pipeline).
    """

    @abstractmethod
    def extract_text(self, source: Any) -> OCRResult:
        """
        Processes image or raw input and returns standardized OCRResult.
        """
        pass
