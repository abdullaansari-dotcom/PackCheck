"""Product classification: which category's rules apply to this label?

The user's choice always wins. With ``category='auto'`` the label text is scored against the
evidence patterns in ``data.CATEGORY_EVIDENCE`` and the best category is used if it clears
``config.MIN_CATEGORY_CONF``; otherwise the label is treated as 'other'. With ``'other'`` (an
explicit user choice) nothing is overridden, but a suggestion is still reported.

Categories that switch on an exemption (fast food, scheduled drugs, bidis, incense, LPG,
agricultural produce) are never inferred, so an exemption can never be granted on a guess.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

from . import config
from .data import CATEGORY_EVIDENCE, CATEGORY_INFO


@dataclass
class Classification:
    category: str  # category the rules are evaluated for
    source: str  # "user" | "inferred" | "default"
    confidence: Optional[float] = None
    requested: str = "auto"
    suggestion: Optional[str] = None
    evidence: List[str] = field(default_factory=list)
    candidates: List[Tuple[str, float]] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "category": self.category, "source": self.source,
            "confidence": None if self.confidence is None else round(self.confidence, 2),
            "requested": self.requested, "suggestion": self.suggestion, "evidence": self.evidence,
            "candidates": [{"category": c, "score": round(s, 2)} for c, s in self.candidates[:4]],
        }


_INGREDIENTS = re.compile(
    r"\bingredients?\s*[:\-].{0,900}?(?=\ballergen|\bmarketed\b|\bmanufactured\b|\bmfd\b|\bpacked\s+by\b|\bnet\s+(?:qty|quantity|wt)\b|\bnutritional\b|\bfssai\b|\bcontains\b|\Z)",
    re.I | re.S)


def strip_ingredients(text: str) -> str:
    """Remove the ingredients list: 'iodised salt' in a snack's ingredients must not make it a salt pack."""
    return _INGREDIENTS.sub(" INGREDIENTS ", text)


def score_categories(text: str) -> List[Tuple[str, float, List[str]]]:
    text = strip_ingredients(text)
    out = []
    for cat, patterns in CATEGORY_EVIDENCE.items():
        if not CATEGORY_INFO.get(cat, {}).get("inferable"):
            continue
        total, ev = 0.0, []
        for pat, w in patterns:
            m = re.search(pat, text, re.I)
            if m:
                total += w
                ev.append(f"'{' '.join(m.group(0).split())}' (+{w:g})")
        if total > 0:
            out.append((cat, min(1.0, total), ev))
    # a more specific category beats its generic parent when both match (exercise book > notebook)
    out.sort(key=lambda c: (-c[1], -len(c[2])))
    return out


@dataclass
class CategoryHint:
    """A category suggested by the AI reader. Same limits as text inference: only inferable categories
    (never an exemption category) and only at or above ``config.MIN_CATEGORY_CONF``."""

    category: str
    confidence: float
    reason: str = ""

    @property
    def usable(self) -> bool:
        return bool(CATEGORY_INFO.get(self.category, {}).get("inferable")) and self.confidence >= config.MIN_CATEGORY_CONF


def classify(text: str, requested: str = "auto", hint: Optional[CategoryHint] = None) -> Classification:
    scores = score_categories(text)
    top = scores[0] if scores else None
    cands = [(c, s) for c, s, _ in scores]
    ai = hint if hint is not None and hint.usable else None
    if requested not in ("auto", "other"):
        sugg = top[0] if top and top[0] != requested and top[1] >= config.MIN_CATEGORY_CONF else None
        if sugg is None and ai and ai.category != requested:
            sugg = ai.category
        return Classification(requested, "user", None, requested, sugg, [], cands)
    text_ok = bool(top and top[1] >= config.MIN_CATEGORY_CONF)
    if requested == "auto" and ai and not text_ok:
        return Classification(ai.category, "ai", ai.confidence, requested, ai.category,
                              [f"AI reader: {ai.reason}"] if ai.reason else ["AI reader"], cands)
    if requested == "other" and ai and not text_ok:
        return Classification("other", "user", None, requested, ai.category,
                              [f"AI reader: {ai.reason}"] if ai.reason else [], cands)
    if top and top[1] >= config.MIN_CATEGORY_CONF:
        if requested == "auto":
            return Classification(top[0], "inferred", top[1], requested, top[0], top[2], cands)
        return Classification("other", "user", None, requested, top[0], top[2], cands)
    return Classification("other", "default" if requested == "auto" else "user",
                          top[1] if top else None, requested, top[0] if top else None,
                          top[2] if top else [], cands)
