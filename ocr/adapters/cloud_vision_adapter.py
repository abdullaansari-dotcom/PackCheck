"""
Google Cloud Vision / AWS Textract JSON Payload Adapter
SIH 2026 - Problem Statement SIH26034
"""

from typing import Any, List, Dict
from ..interface import BaseOCREngine, OCRResult, OCRToken, OCRBlock


class CloudVisionAdapter(BaseOCREngine):
    """
    Adapter for Google Cloud Vision fullTextAnnotation or AWS Textract response payloads.
    """

    def extract_text(self, source: Any) -> OCRResult:
        if not isinstance(source, dict):
            return OCRResult(raw_text=str(source), average_confidence=1.0)

        # 1. Google Cloud Vision fullTextAnnotation
        if "fullTextAnnotation" in source or "textAnnotations" in source:
            raw_text = ""
            tokens: List[OCRToken] = []
            confs = []

            if "fullTextAnnotation" in source:
                raw_text = source["fullTextAnnotation"].get("text", "")
                pages = source["fullTextAnnotation"].get("pages", [])
                for page in pages:
                    for block in page.get("blocks", []):
                        for para in block.get("paragraphs", []):
                            for word in para.get("words", []):
                                w_text = "".join(s.get("text", "") for s in word.get("symbols", []))
                                w_conf = float(word.get("confidence", 1.0))
                                confs.append(w_conf)
                                tokens.append(OCRToken(text=w_text, confidence=w_conf))
            elif "textAnnotations" in source and len(source["textAnnotations"]) > 0:
                raw_text = source["textAnnotations"][0].get("description", "")
                for ann in source["textAnnotations"][1:]:
                    tokens.append(OCRToken(
                        text=ann.get("description", ""),
                        confidence=float(ann.get("confidence", 1.0))
                    ))

            avg_conf = (sum(confs) / len(confs)) if confs else 1.0
            return OCRResult(raw_text=raw_text, tokens=tokens, average_confidence=avg_conf)

        # 2. AWS Textract Blocks
        if "Blocks" in source:
            tokens = []
            lines = []
            confs = []
            for b in source["Blocks"]:
                if b.get("BlockType") == "WORD":
                    c = float(b.get("Confidence", 100.0)) / 100.0
                    tokens.append(OCRToken(text=b.get("Text", ""), confidence=c))
                    confs.append(c)
                elif b.get("BlockType") == "LINE":
                    lines.append(b.get("Text", ""))

            raw_text = "\n".join(lines) if lines else " ".join(t.text for t in tokens)
            avg_conf = (sum(confs) / len(confs)) if confs else 1.0
            return OCRResult(raw_text=raw_text, tokens=tokens, average_confidence=avg_conf)

        return OCRResult(raw_text=str(source), average_confidence=1.0)
