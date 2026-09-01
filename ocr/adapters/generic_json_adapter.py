"""
Generic OCR JSON Payload Adapter
SIH 2026 - Problem Statement SIH26034
PackCheck AI/OCR Pipeline Interop Layer

Converts arbitrary JSON from OCR platforms into standardized OCRResult.
"""

from typing import Dict, Any, List
from ..interface import BaseOCREngine, OCRResult, OCRToken, OCRBlock


class GenericOCRJsonAdapter(BaseOCREngine):
    """
    Adapter that accepts generic JSON payloads with text, tokens, blocks, and confidences.
    """

    def extract_text(self, source: Any) -> OCRResult:
        if isinstance(source, str):
            return OCRResult(raw_text=source, average_confidence=1.0)

        if not isinstance(source, dict):
            return OCRResult(raw_text=str(source), average_confidence=1.0)

        raw_text = source.get("text") or source.get("raw_text") or source.get("full_text") or ""
        tokens_data = source.get("tokens") or source.get("words") or []
        blocks_data = source.get("blocks") or source.get("lines") or []
        avg_conf = float(source.get("confidence") or source.get("average_confidence") or 1.0)

        tokens: List[OCRToken] = []
        for t in tokens_data:
            if isinstance(t, str):
                tokens.append(OCRToken(text=t, confidence=1.0))
            elif isinstance(t, dict):
                tokens.append(OCRToken(
                    text=t.get("text") or t.get("word") or "",
                    confidence=float(t.get("confidence", 1.0)),
                    bbox=t.get("bbox") or t.get("box"),
                    polygon=t.get("polygon"),
                    language=t.get("language")
                ))

        blocks: List[OCRBlock] = []
        for b in blocks_data:
            if isinstance(b, str):
                blocks.append(OCRBlock(text=b, confidence=1.0))
            elif isinstance(b, dict):
                blocks.append(OCRBlock(
                    text=b.get("text") or b.get("line") or "",
                    confidence=float(b.get("confidence", 1.0)),
                    bbox=b.get("bbox") or b.get("box")
                ))

        # Reconstruct raw_text if not explicitly provided
        if not raw_text and blocks:
            raw_text = "\n".join(b.text for b in blocks)
        elif not raw_text and tokens:
            raw_text = " ".join(t.text for t in tokens)

        if tokens and avg_conf == 1.0:
            avg_conf = sum(t.confidence for t in tokens) / len(tokens)

        return OCRResult(
            raw_text=raw_text,
            tokens=tokens,
            blocks=blocks,
            average_confidence=avg_conf,
            metadata=source.get("metadata", {})
        )
