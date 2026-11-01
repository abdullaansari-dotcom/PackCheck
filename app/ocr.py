"""EasyOCR wrapper: detection once, recognition by an English model plus (optionally) the
Devanagari model, with per-box arbitration.

Root cause this fixes
---------------------
The original created ``easyocr.Reader(['en', 'hi'])``. With Hindi in the list EasyOCR loads
its *Devanagari* recognition model for every box. That model's character set mixes Latin and
Devanagari glyphs, and on English text it regularly emits Devanagari digits for look-alike
Latin digits (2 -> ``२``, 6 -> ``६``, 0 -> ``०``) and sometimes the wrong digit altogether
(``140`` -> ``२४०``, which is 240). That is the corrupted text seen in the Bhaskar sample.

What this module does instead
-----------------------------
1. Detect text boxes once (CRAFT, via the English reader).
2. Recognise every box with the English model (``english_g2``): this is the authoritative
   reading for Latin text and all digits.
3. If Hindi is configured, recognise the *same boxes* with the Devanagari model and keep that
   reading only when the box really contains Devanagari letters (not just digits) and the
   model is at least as confident. Both readings are kept on the token for transparency.
4. The English model has no ``₹`` in its character set; when the Devanagari reading shows a
   ``₹`` and the amounts agree after normalization, the English reading's stand-in glyph is
   replaced by ``₹`` (cross-model validation, recorded in the token note).
5. If the result is weak (low mean confidence), one alternative preprocessing variant is
   tried and kept only if it is measurably better.

EasyOCR is not replaced: tests in this repository show the failures came from model
selection, box grouping and downstream parsing, not from EasyOCR's detector.
"""
from __future__ import annotations

import logging
import re
import threading
from dataclasses import dataclass, field
from statistics import mean
from typing import List, Optional, Sequence, Tuple

import numpy as np

from . import config
from .layout import Line, Separator, Token, build_lines, token_from_easyocr
from .normalize import DEVANAGARI_DIGITS, RUPEE_CONFUSABLES, normalize_line

log = logging.getLogger("packcheck.ocr")

_readers = {}
_lock = threading.Lock()


class OcrUnavailable(RuntimeError):
    pass


def _get_reader(kind: str):
    """kind = 'primary' (English, with detector) or 'secondary' (Devanagari, recogniser only)."""
    with _lock:
        if kind not in _readers:
            try:
                import easyocr  # imported lazily so the rest of the app works without it
            except ImportError as e:  # pragma: no cover - depends on environment
                raise OcrUnavailable(f"EasyOCR is not installed: {e}") from e
            if kind == "primary":
                _readers[kind] = easyocr.Reader(["en"], gpu=config.OCR_GPU, verbose=False)
            else:
                langs = [l for l in config.OCR_LANGS if l != "en"] + ["en"]
                _readers[kind] = easyocr.Reader(langs, gpu=config.OCR_GPU, detector=False, verbose=False)
    return _readers[kind]


def secondary_enabled() -> bool:
    return config.OCR_SECONDARY_SCRIPT and any(l != "en" for l in config.OCR_LANGS)


# ------------------------------------------------------------------ arbitration
def devanagari_letters(text: str) -> int:
    return sum(1 for ch in text if "ऀ" <= ch <= "ॿ" and ch not in DEVANAGARI_DIGITS and ch.isalpha())


_AMOUNT = re.compile(r"\d+(?:\.\d{1,2})?")


def arbitrate(en_text: str, en_conf: float, alt_text: Optional[str], alt_conf: Optional[float]) -> Tuple[str, float, str, Optional[str]]:
    """Choose a reading for one box. Returns (text, conf, engine_used, note)."""
    if not alt_text:
        return en_text, en_conf, "easyocr-en", None
    alt_conf = alt_conf or 0.0
    if devanagari_letters(alt_text) >= 2 and (alt_conf >= en_conf or en_conf < 0.3):
        return alt_text, alt_conf, "easyocr-hi", "Devanagari text: Hindi model reading kept"
    note = None
    if "₹" in alt_text and "₹" not in en_text:
        alt_norm = normalize_line(alt_text).normalized
        m_alt = re.search(r"₹\s*(" + _AMOUNT.pattern + ")", alt_norm)
        if m_alt:
            amount = m_alt.group(1)
            # the English model's stand-in glyph directly before the same amount
            m_en = re.search(r"(?P<g>[" + re.escape(RUPEE_CONFUSABLES) + r"]|[^\w\s.,/()\-:])\s?" + re.escape(amount) + r"(?![\d])", en_text)
            if m_en:
                i = m_en.start("g")
                en_text = en_text[:i] + "₹" + en_text[i + 1:]
                note = f"'₹' restored: Devanagari model read '₹' before the same amount {amount}"
    return en_text, en_conf, "easyocr-en", note


# ------------------------------------------------------------------ result
@dataclass
class OcrResult:
    tokens: List[Token]
    lines: List[Line]
    separators: List[Separator] = field(default_factory=list)
    image_size: Tuple[int, int] = (0, 0)
    variant: str = "gray_enhanced"
    engines: List[str] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)

    @property
    def mean_conf(self) -> float:
        return round(mean(t.conf for t in self.tokens), 3) if self.tokens else 0.0


def _recognize(gray: np.ndarray, lean: bool = False) -> List[Token]:
    primary = _get_reader("primary")
    horizontal, free = primary.detect(gray, width_ths=0.5, add_margin=0.1)
    horizontal, free = horizontal[0], free[0]
    if not horizontal and not free:
        return []
    en = primary.recognize(gray, horizontal_list=horizontal, free_list=free, detail=1, paragraph=False)
    alt = None
    if secondary_enabled() and not lean:
        try:
            secondary = _get_reader("secondary")
            alt = secondary.recognize(gray, horizontal_list=horizontal, free_list=free, detail=1, paragraph=False)
        except Exception:  # the secondary pass is an enhancement; never let it break a scan
            log.exception("secondary (Devanagari) recognition failed; continuing with English only")
            alt = None
    def key(res):
        return tuple(round(float(v), 1) for p in res[0] for v in p)

    alt_by_box = {key(r): r for r in alt} if alt is not None else {}
    tokens: List[Token] = []
    for res in en:
        tok = token_from_easyocr(res, "easyocr-en")
        if tok is None:
            continue
        a_text, a_conf = None, None
        a = alt_by_box.get(key(res))  # same detected box, read by the secondary model
        if a is not None:
            a_text, a_conf = (a[1] or "").strip() or None, float(a[2])
        orig_en = tok.text
        text, conf, engine, note = arbitrate(tok.text, tok.conf, a_text, a_conf)
        tok.text, tok.conf, tok.engine, tok.note = text, conf, engine, note
        tok.alt_text, tok.alt_conf = (a_text, a_conf) if engine == "easyocr-en" else (orig_en, float(res[2]))
        tokens.append(tok)
    return tokens


def read_tokens(gray: np.ndarray, separators: Sequence[Separator] = (), lean: bool = False) -> OcrResult:
    """Full OCR pass on a preprocessed grayscale image, with one controlled fallback variant.

    ``lean=True`` (used when the AI reader runs alongside) skips the Hindi pass and the fallback variant:
    OCR is then only the second opinion and the source of box positions, so it can be much faster."""
    from .preprocess import variants

    tokens = [t for t in _recognize(gray, lean) if t.conf >= config.MIN_TOKEN_CONF]
    res = OcrResult(tokens, build_lines(tokens, separators), list(separators), (gray.shape[1], gray.shape[0]),
                    engines=["easyocr-en"] + (["easyocr-hi"] if secondary_enabled() and not lean else []))
    if not lean and config.OCR_FALLBACK_VARIANTS and (not tokens or res.mean_conf < config.MIN_OVERALL_CONF + 0.1):
        for name, img in variants(gray).items():
            alt_tokens = [t for t in _recognize(img) if t.conf >= config.MIN_TOKEN_CONF]
            alt = OcrResult(alt_tokens, build_lines(alt_tokens, separators), list(separators),
                            (gray.shape[1], gray.shape[0]), name, res.engines)
            # better = higher confidence without losing a meaningful amount of text
            if alt.tokens and alt.mean_conf > res.mean_conf + 0.05 and \
                    sum(len(t.text) for t in alt.tokens) >= 0.8 * sum(len(t.text) for t in res.tokens):
                alt.notes.append(f"fallback variant '{name}' kept: mean confidence {alt.mean_conf} vs {res.mean_conf}")
                res = alt
    return res


# ------------------------------------------------------------------ backward compatibility
def group_rows(results) -> List[Line]:
    """Legacy helper: EasyOCR (bbox, text, conf) triples -> lines, now via the layout engine."""
    tokens = [t for t in (token_from_easyocr(r) for r in results) if t is not None]
    return [Line(l.text, l.conf) for l in build_lines(tokens)]


def read_label(image: np.ndarray) -> List[Line]:
    """Legacy entry point: preprocessed image -> lines."""
    from .preprocess import find_vertical_rules

    import cv2

    gray = image if image.ndim == 2 else cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    return read_tokens(gray, find_vertical_rules(gray)).lines
