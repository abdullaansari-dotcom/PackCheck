"""Text normalization for OCR output.

Design rules (see docs/ARCHITECTURE.md):

* The original OCR text is never modified. Normalization produces a *separate* string.
* Every substitution is length-preserving (one character in, one character out), so a
  character offset in the normalized text is also the offset in the original text. Evidence
  shown to the user can therefore always quote both the original and the normalized reading.
* Substitutions are contextual. Nothing is replaced globally: an ``O`` only becomes ``0`` when
  it sits between digits, a Devanagari digit is only converted inside a numeric run, a stray
  glyph only becomes ``₹`` when it sits between an MRP keyword and an amount.
* Every substitution is recorded as a :class:`Change`. Changes that might alter a value (for
  example Devanagari digits inside an English line, which usually means the recogniser
  misread a Latin digit) are marked ``uncertain`` so the rules engine can send the affected
  field to human review instead of trusting it.

Normalization is not evidence of compliance. It only makes the text parseable.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from typing import List, Tuple

DEVANAGARI_DIGITS = "०१२३४५६७८९"
_DEV_DIGIT_MAP = {ord(c): str(i) for i, c in enumerate(DEVANAGARI_DIGITS)}
_DEV_DIGIT_SET = set(DEVANAGARI_DIGITS)

# one-to-one punctuation clean-up (dashes, quotes, multiplication-like signs keep their meaning)
_PUNCT_MAP = {
    "‐": "-", "‑": "-", "‒": "-", "–": "-", "—": "-", "−": "-",
    "‘": "'", "’": "'", "“": '"', "”": '"', " ": " ", " ": " ",
    " ": " ", "：": ":",
}
# characters EasyOCR / Tesseract commonly emit in place of the rupee sign (the English
# recogniser has no ₹ in its character set)
RUPEE_CONFUSABLES = "ZzF7?<€2%R"
MRP_KEYWORD = r"(?:\bm\s?\.?\s?r\s?\.?\s?p\b\.?|maximum\s+retail\s+price|retail\s+(?:sale\s+)?price|\bprice\b)"


@dataclass
class Change:
    kind: str
    start: int
    end: int
    original: str
    normalized: str
    uncertain: bool = False
    note: str = ""

    def as_dict(self) -> dict:
        return {
            "kind": self.kind, "start": self.start, "end": self.end, "original": self.original,
            "normalized": self.normalized, "uncertain": self.uncertain, "note": self.note,
        }


@dataclass
class NormalizedText:
    original: str
    normalized: str
    changes: List[Change] = field(default_factory=list)

    def uncertain_in(self, start: int, end: int) -> List[Change]:
        return [c for c in self.changes if c.uncertain and c.start < end and c.end > start]

    def changes_in(self, start: int, end: int) -> List[Change]:
        return [c for c in self.changes if c.start < end and c.end > start]


def _letter_script(ch: str) -> str:
    if not ch.isalpha():
        return ""
    o = ord(ch)
    if o < 0x250:
        return "latin"
    if 0x0900 <= o <= 0x097F:
        return "devanagari"
    return "other"


def dominant_script(text: str) -> str:
    """'latin', 'devanagari', 'other' or '' (no letters)."""
    counts = {"latin": 0, "devanagari": 0, "other": 0}
    for ch in text:
        s = _letter_script(ch)
        if s:
            counts[s] += 1
    if not any(counts.values()):
        return ""
    return max(counts, key=counts.get)


def _is_digitlike(ch: str) -> bool:
    return ch.isdigit() or ch in _DEV_DIGIT_SET


def _numeric_runs(text: str) -> List[Tuple[int, int]]:
    """Spans of digit runs (Latin or Devanagari) including internal . , / - x separators."""
    runs = []
    i, n = 0, len(text)
    while i < n:
        if _is_digitlike(text[i]):
            j = i + 1
            while j < n and (_is_digitlike(text[j]) or (text[j] in ".,/-" and j + 1 < n and _is_digitlike(text[j + 1]))):
                j += 1
            runs.append((i, j))
            i = j
        else:
            i += 1
    return runs


def normalize_line(text: str) -> NormalizedText:
    """Normalize one OCR line. Length-preserving, contextual, every change recorded."""
    chars = list(text)
    changes: List[Change] = []

    def sub(i: int, new: str, kind: str, uncertain: bool = False, note: str = "") -> None:
        if chars[i] == new:
            return
        changes.append(Change(kind, i, i + 1, chars[i], new, uncertain, note))
        chars[i] = new

    # 1. typographic punctuation and full-width forms (1:1 only)
    for i, ch in enumerate(chars):
        if ch in _PUNCT_MAP:
            sub(i, _PUNCT_MAP[ch], "punctuation")
        elif "０" <= ch <= "９":  # full-width digits
            sub(i, str(ord(ch) - 0xFF10), "fullwidth_digit")

    # 2. Devanagari digits inside numeric runs. In a Devanagari line they are genuine
    #    numerals (value preserved). In a Latin line they are almost always a misread
    #    Latin digit, so the value is flagged uncertain.
    line_script = dominant_script(text)
    for s, e in _numeric_runs("".join(chars)):
        run = "".join(chars[s:e])
        if not any(c in _DEV_DIGIT_SET for c in run):
            continue
        # look at letters immediately around the run (e.g. '२nd', '१६A') and at the whole line
        ctx = "".join(chars[max(0, s - 12): s]) + "".join(chars[e: e + 12])
        local = dominant_script(ctx) or line_script
        mixed = any(c.isdigit() and c not in _DEV_DIGIT_SET for c in run)
        latin_context = local == "latin" or line_script == "latin" or mixed
        for i in range(s, e):
            if chars[i] in _DEV_DIGIT_SET:
                if latin_context:
                    sub(i, chars[i].translate(_DEV_DIGIT_MAP), "devanagari_digit_in_latin_text", True,
                        "Devanagari digit inside English text: probably a misread Latin digit, value unconfirmed")
                else:
                    sub(i, chars[i].translate(_DEV_DIGIT_MAP), "devanagari_numeral", False,
                        "Devanagari numeral converted to the same value in Arabic digits")

    cur = "".join(chars)

    # 3. letter/digit confusions, only *inside* numbers: 3O -> 30, 6O.OO -> 60.00, 2l6 -> 216
    zero_rx = re.compile(
        r"(?<=\d)[Oo](?=[\dOo.,xX×*]|\s*(?:cms?|mm|kg|g|ml|l)\b|$|[\s)/-])"  # 3O x 18, 6O.00
        r"|(?<=\d\.)[Oo]"  # 60.O0
        r"|(?<=[\s₹(])[Oo](?=[\d.]\d)"  # ₹ O.50
    )
    for _ in range(4):  # 6O.OO needs several passes; each pass only looks at digit neighbours
        cur = "".join(chars)
        hits = list(zero_rx.finditer(cur))
        if not hits:
            break
        for m in hits:
            sub(m.start(), "0", "letter_O_as_zero", note="'O' inside a number read as zero")
    cur = "".join(chars)
    for m in re.finditer(r"(?<=\d)[lI|](?=\d)", cur):
        sub(m.start(), "1", "letter_l_as_one", note="'l'/'I' between digits read as one")
    cur = "".join(chars)

    # 4. rupee-sign confusion: "MRP: Z 60.00", "MRP: 7 60.00", "MRP:F60" -> ₹. Only directly
    #    after an MRP/price keyword and directly before an amount; a glued '7'/'2' (MRP 760)
    #    is never touched because it could be a real digit.
    rx = re.compile(MRP_KEYWORD + r"\s*[:\-.]?\s*(?P<g>[" + re.escape(RUPEE_CONFUSABLES) + r"])(?P<sp>\s*)(?=\d)", re.I)
    for m in rx.finditer(cur):
        g = m.group("g")
        if g in "72" and not m.group("sp"):
            continue  # glued digit: ambiguous, leave it
        if g in "Rr" and cur[m.end("g"): m.end("g") + 1].lower() == "s":
            continue  # 'Rs' is a valid rupee abbreviation, not a glyph confusion
        sub(m.start("g"), "₹", "rupee_glyph", note=f"'{g}' between the MRP keyword and the amount read as ₹")
    cur = "".join(chars)

    return NormalizedText(text, cur, changes)


def normalize_lines(lines: List[str]) -> List[NormalizedText]:
    return [normalize_line(t) for t in lines]


def nfkc_display(text: str) -> str:
    """Compatibility-normalized copy for display only (may change length; never used for offsets)."""
    return unicodedata.normalize("NFKC", text)
