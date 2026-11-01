"""Fuse the AI transcription with the OCR layout.

The AI reading supplies the *text* (it is far better on digits, the rupee sign and Hindi). The OCR
reading supplies *geometry* (where each line sits in the photo, which Rules 8 and 9 need) and acts as
an independent second opinion.

For every AI line:
1. find the OCR lines that cover the same text (fuzzy match, each OCR line used once);
2. if found, the fused line takes their union box, layout region and column;
3. if both readings contain numbers, compare them. A number the OCR did not see (for example the
   Devanagari-digit error ``140`` -> ``240``) is recorded as a *disagreement*, and the line gets the
   lower confidence ``config.AI_DISAGREEMENT_CONF``;
4. agreement gives high confidence; an AI-only line (no OCR counterpart) gets a middling one.

If the AI says the photo is not legible, confidence is capped so affected declarations go to review.
"""
from __future__ import annotations

import re
from difflib import SequenceMatcher
from statistics import mean
from typing import Dict, List, Optional, Sequence, Tuple

from . import config
from .layout import Line, Token
from .normalize import _DEV_DIGIT_MAP
from .vision import VisionReading

CONF_AGREE = 0.95
CONF_AI_ONLY = 0.85
CONF_ILLEGIBLE_CAP = 0.35
_NUM_RE = re.compile(r"\d+(?:[.,]\d+)?")


def _ascii_digits(s: str) -> str:
    return s.translate(_DEV_DIGIT_MAP)


def _key(s: str) -> str:
    """Comparison key: lower case, Devanagari digits as ASCII, only letters and digits."""
    return "".join(c for c in _ascii_digits(s).lower() if c.isalnum())


def _numbers(s: str) -> List[str]:
    return [n.replace(",", ".") for n in _NUM_RE.findall(_ascii_digits(s))]


def _num_present(n: str, hay: str) -> bool:
    if n in hay:
        return True
    if "." in n:  # 60.00 vs 60.0 vs 60
        base = n.rstrip("0").rstrip(".")
        return bool(base) and base in hay
    return False


def match_lines(ai_texts: Sequence[str], ocr_lines: Sequence[Line]) -> Dict[int, List[int]]:
    """AI line index -> OCR line indices that cover the same text. Each OCR line goes to one AI line."""
    ai_keys = [_key(t) for t in ai_texts]
    out: Dict[int, List[int]] = {}
    for j, ol in enumerate(ocr_lines):
        ok = _key(ol.text)
        if len(ok) < 3:
            continue
        best: Optional[Tuple[float, int]] = None
        for i, ak in enumerate(ai_keys):
            if len(ak) < 3:
                continue
            sm = SequenceMatcher(None, ak, ok, autojunk=False)
            m = sm.find_longest_match(0, len(ak), 0, len(ok))
            if m.size < 3:
                continue
            cov_o, cov_a = m.size / len(ok), m.size / len(ak)
            ratio = sm.ratio()  # whole-line similarity: keeps lines whose digits differ matched
            score = max(cov_o, cov_a * 0.9, ratio)
            ok_match = cov_o >= 0.6 or (cov_a >= 0.7 and m.size >= 4) or ratio >= 0.62
            if ok_match and (best is None or score > best[0]):
                best = (score, i)
        if best:
            out.setdefault(best[1], []).append(j)
    return out


def fuse(reading: VisionReading, ocr_lines: Optional[Sequence[Line]] = None) -> Tuple[List[Line], dict]:
    """Returns (lines for the rules engine, report dict for the UI)."""
    ocr_lines = list(ocr_lines or [])
    texts = [l.text for l in reading.lines]
    matches = match_lines(texts, ocr_lines) if ocr_lines else {}
    region_ids: Dict[str, int] = {}
    lines: List[Line] = []
    disagreements: List[dict] = []
    grounded = 0
    for i, vl in enumerate(reading.lines):
        js = sorted(matches.get(i, []))
        olines = [ocr_lines[j] for j in js]
        bbox = None
        block = column = None
        ocr_text = None
        if olines:
            boxes = [o.bbox for o in olines if o.bbox]
            if boxes:
                bbox = (min(b[0] for b in boxes), min(b[1] for b in boxes),
                        max(b[2] for b in boxes), max(b[3] for b in boxes))
                grounded += 1
            block, column = olines[0].block, olines[0].column
            ocr_text = " ".join(o.text for o in olines)
        elif vl.region:  # no OCR counterpart: keep the AI's own region grouping
            block = 1000 + region_ids.setdefault(vl.region, len(region_ids))
        if ocr_lines:
            if olines:
                ocr_digits = _ascii_digits(ocr_text).replace(",", ".")
                missing = [n for n in _numbers(vl.text) if len(n.replace(".", "")) >= 2 and not _num_present(n, ocr_digits)]
                if missing:
                    conf = config.AI_DISAGREEMENT_CONF
                    disagreements.append({"line": i, "ai": vl.text, "ocr": ocr_text, "numbers_not_seen_by_ocr": missing})
                else:
                    conf = CONF_AGREE
            else:
                conf = CONF_AI_ONLY
        else:
            conf = CONF_AI_ONLY
        if reading.legible is False:
            conf = min(conf, CONF_ILLEGIBLE_CAP)
        tok = Token(vl.text, conf, bbox, "vision", alt_text=ocr_text) if bbox else None
        lines.append(Line(vl.text, conf, bbox, block, column, [tok] if tok else None))
    report = {
        "ai_lines": len(reading.lines), "ocr_lines": len(ocr_lines), "grounded": grounded,
        "ai_only_lines": sum(1 for i in range(len(reading.lines)) if i not in matches) if ocr_lines else None,
        "disagreements": disagreements,
        "mean_confidence": round(mean(l.conf for l in lines), 3) if lines else None,
    }
    return lines, report
