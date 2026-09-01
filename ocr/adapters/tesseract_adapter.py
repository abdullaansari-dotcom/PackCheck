"""
Tesseract OCR Adapter for PackCheck
SIH 2026 - Problem Statement SIH26034
"""

from typing import Any, List, Dict
from ..interface import BaseOCREngine, OCRResult, OCRToken, OCRBlock


class TesseractAdapter(BaseOCREngine):
    """
    Adapter for pytesseract image_to_data or image_to_string output dictionaries.
    """

    def extract_text(self, source: Any) -> OCRResult:
        if isinstance(source, str):
            return OCRResult(raw_text=source, average_confidence=1.0)

        # Handle pytesseract.image_to_data dict format: {'text': [...], 'conf': [...], 'left': [...], ...}
        if isinstance(source, dict) and "text" in source and isinstance(source["text"], list):
            texts = source["text"]
            confs = source.get("conf", [100] * len(texts))
            lefts = source.get("left", [0] * len(texts))
            tops = source.get("top", [0] * len(texts))
            widths = source.get("width", [0] * len(texts))
            heights = source.get("height", [0] * len(texts))

            tokens: List[OCRToken] = []
            valid_confs = []

            for i, text in enumerate(texts):
                t_clean = str(text).strip()
                if not t_clean:
                    continue
                try:
                    c_val = float(confs[i])
                    conf_norm = max(0.0, c_val / 100.0) if c_val >= 0 else 0.0
                except (ValueError, IndexError):
                    conf_norm = 1.0

                valid_confs.append(conf_norm)
                x0, y0 = float(lefts[i]), float(tops[i])
                x1, y1 = x0 + float(widths[i]), y0 + float(heights[i])

                tokens.append(OCRToken(
                    text=t_clean,
                    confidence=conf_norm,
                    bbox=(x0, y0, x1, y1)
                ))

            avg_conf = (sum(valid_confs) / len(valid_confs)) if valid_confs else 1.0
            full_text = " ".join(t.text for t in tokens)

            return OCRResult(
                raw_text=full_text,
                tokens=tokens,
                average_confidence=avg_conf
            )

        return OCRResult(raw_text=str(source), average_confidence=1.0)
