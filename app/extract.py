"""Declaration extraction: OCR lines -> structured evidence for each Rule 6 field.

Everything here works on text plus (optional) geometry, so it can be unit tested without
images. Each finder returns a small dataclass; the rules in ``engine.py`` decide pass/fail.

Key behaviours (each one fixes a failure seen on the Bhaskar Book Tech sample):

* Lines are normalized (``app.normalize``) before matching; the original OCR text is kept and
  every :class:`Hit` carries both readings plus any *uncertain* normalization inside it.
* Values are associated with nearby wording using layout regions when geometry exists (same
  region, or a vertically adjacent line that overlaps horizontally) and a character window
  when it does not (pasted text).
* Semantics are explicit: a page count is product information, a dimension is a dimension,
  a business name without "Manufactured by" is an *entity* whose legal role is not stated.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from statistics import mean
from typing import List, Optional, Sequence, Tuple

from .data import GENERAL_GENERIC_WORDS, GENERIC_KEYWORDS
from .layout import Line  # re-exported: ``from app.extract import Line`` keeps working
from .normalize import Change, NormalizedText, normalize_line

__all__ = ["Line", "LabelText", "Hit"]


@dataclass
class Hit:
    text: str  # normalized reading
    start: int
    end: int
    conf: float
    original: str = ""  # what the OCR engine actually produced
    changes: List[Change] = field(default_factory=list)
    bbox: Optional[Tuple[float, float, float, float]] = None
    lines: List[int] = field(default_factory=list)
    image: Optional[int] = None  # photo the hit was read from (multi-photo labels only)

    @property
    def uncertain(self) -> List[Change]:
        return [c for c in self.changes if c.uncertain]


class LabelText:
    """All lines joined with newlines (normalized), remembering per-line confidence, geometry and
    the original OCR reading."""

    def __init__(self, lines: List[Line]):
        self.lines: List[Line] = []
        for l in lines:
            if l.text and l.text.strip():
                self.lines.append(Line(l.text.strip(), l.conf, l.bbox, l.block, l.column, l.tokens, l.image))
        self.norm: List[NormalizedText] = [normalize_line(l.text) for l in self.lines]
        self.text = "\n".join(n.normalized for n in self.norm)
        self.original_text = "\n".join(l.text for l in self.lines)
        self._spans: List[Tuple[int, int]] = []
        pos = 0
        for n in self.norm:
            self._spans.append((pos, pos + len(n.normalized)))
            pos += len(n.normalized) + 1
        self.avg_conf = round(mean(l.conf for l in self.lines), 3) if self.lines else 0.0
        self.has_geometry = any(l.bbox is not None for l in self.lines)

    @classmethod
    def from_text(cls, text: str) -> "LabelText":
        return cls([Line(t) for t in text.splitlines()])

    # ---------------------------------------------------------------- offsets
    def line_index(self, pos: int) -> int:
        for i, (s, e) in enumerate(self._spans):
            if s <= pos <= e:
                return i
        return len(self._spans) - 1

    def lines_in(self, start: int, end: int) -> List[int]:
        return [i for i, (s, e) in enumerate(self._spans) if s < max(end, start + 1) and e >= start]

    def conf_at(self, start: int, end: int) -> float:
        cs = [self.lines[i].conf for i in self.lines_in(start, end)]
        return round(mean(cs), 3) if cs else self.avg_conf

    def changes_in(self, start: int, end: int) -> List[Change]:
        out = []
        for i in self.lines_in(start, end):
            s0 = self._spans[i][0]
            for c in self.norm[i].changes:
                if s0 + c.start < end and s0 + c.end > start:
                    out.append(c)
        return out

    def hit(self, start: int, end: int) -> Hit:
        end = min(end, len(self.text))
        idx = self.lines_in(start, end)
        boxes = [self.lines[i].bbox for i in idx if self.lines[i].bbox]
        bbox = (min(b[0] for b in boxes), min(b[1] for b in boxes), max(b[2] for b in boxes),
                max(b[3] for b in boxes)) if boxes else None
        orig = self.original_text[start:end] if len(self.original_text) == len(self.text) else ""
        image = next((self.lines[i].image for i in idx if self.lines[i].image is not None), None)
        return Hit(" ".join(self.text[start:end].split()), start, end, self.conf_at(start, end),
                   " ".join(orig.split()), self.changes_in(start, end), bbox, idx, image)

    def line_hit(self, i: int) -> Hit:
        s, e = self._spans[i]
        return self.hit(s, e)

    def span_of_line(self, i: int) -> Tuple[int, int]:
        return self._spans[i]

    # ---------------------------------------------------------------- spatial association
    def related_lines(self, i: int, max_rows: float = 2.6) -> List[int]:
        """Lines that belong with line i: same layout region, or (with geometry) vertically close
        and horizontally overlapping. Without geometry: the line itself and its neighbours."""
        n = len(self.lines)
        if not self.has_geometry:
            return [j for j in range(max(0, i - 2), min(n, i + 3))]
        li = self.lines[i]
        out = []
        for j, lj in enumerate(self.lines):
            if j == i:
                out.append(j)
                continue
            if li.block is not None and li.block == lj.block:
                out.append(j)
                continue
            if li.bbox and lj.bbox:
                h = max(1.0, min(li.bbox[3] - li.bbox[1], lj.bbox[3] - lj.bbox[1]))
                vgap = max(lj.bbox[1] - li.bbox[3], li.bbox[1] - lj.bbox[3], 0)
                xov = min(li.bbox[2], lj.bbox[2]) - max(li.bbox[0], lj.bbox[0])
                if vgap <= max_rows * h and xov > 0:
                    out.append(j)
        return out

    def related_text_spans(self, start: int, end: int, before: int = 80, after: int = 120) -> List[Tuple[int, int]]:
        """Character ranges that may hold wording belonging to the value at [start, end)."""
        if not self.has_geometry:
            return [(max(0, start - before), min(len(self.text), end + after))]
        idx = set()
        for i in self.lines_in(start, end):
            idx.update(self.related_lines(i))
        return [self._spans[j] for j in sorted(idx)]

    def search_related(self, rx: "re.Pattern", start: int, end: int, before: int = 80, after: int = 120):
        """First match of rx in the text related to [start, end), nearest first."""
        best = None
        for s, e in self.related_text_spans(start, end, before, after):
            for m in rx.finditer(self.text, s, e):
                d = abs(m.start() - start)
                if best is None or d < best[0]:
                    best = (d, m)
        return best[1] if best else None


# ---------------------------------------------------------------- numbers / units
NUM = r"\d+(?:[.,]\d+)?"
UNITS = r"kilograms?|kgs?|grams?|gms?|gm|g|millilit(?:re|er)s?|ml|lit(?:re|er)s?|ltrs?|l"

QTY_RE = re.compile(
    rf"(?:(?P<q>\b(?:approx\w*|about|nearly|minimum|min|maximum|max|around|roughly)\b|~)\.?\s*[:\-]?\s*)?"
    rf"(?<![\d.])(?P<num>{NUM})\s*(?P<unit>{UNITS})\b"
    rf"(?:\s*(?P<q2>\bapprox\w*|\bminimum\b|\bnearly\b|\bmin\b))?",
    re.I,
)
NET_KW_RE = re.compile(
    r"net\s*(?:wt|weight|qty|quantity|content|contents|vol|volume|mass)\b|\bnet\b|\bn\.?\s*wt\b"
    r"|\bcontents?\b|\bcontains?\b|\bquantity\b|\bqty\b",
    re.I,
)
# Rule 13(4): units that may not be used for the declaration (rulebook example: dozen)
DOZEN_RE = re.compile(rf"(?P<num>{NUM})\s*(?P<unit>dozens?|doz)\b\.?", re.I)
COUNT_NOUNS = (r"pcs?|pieces?|nos?|units?|n|sticks?|bags?|sheets?|tablets?|biscuits?|cookies?|capsules?"
               r"|note\s?books?|books?|registers?|diar(?:y|ies)|pads?|pencils?|pens?|sachets?|packets?|pairs?|sets?")
COUNT_RE = re.compile(
    rf"\b(?:contains?|pack\s*of|count|qty|quantity|net\s*(?:qty|quantity|content))\b\s*(?:\([^)\n]{{0,25}}\))?\s*[:.\-]?\s*(?P<num>\d+)\s*"
    rf"(?P<unit>{COUNT_NOUNS})?\b",
    re.I,
)
# a bare count of countable goods ("10 notebooks", "1 N", "2 pcs"). Pages are deliberately absent.
BARE_COUNT_RE = re.compile(
    r"(?<![\d.,/])\b(?P<num>\d{1,4})\s*(?P<unit>pcs?|pieces?|nos?\.?|n\b|units?|note\s?books?|registers?|diar(?:y|ies)"
    r"|exercise\s+books?|drawing\s+books?|writing\s+pads?)(?=\W|$)",
    re.I,
)
# "Number of usable Sheets : 100 N" counts the sheets inside the box; it is not the net quantity
SHEET_COUNT_BEFORE_RE = re.compile(r"(?:usable|sheets?|leaves|pulls?|wipes?|servings?|number\s+of)\b[^\n]{0,25}$", re.I)
PAGE_RE = re.compile(r"(?<![\d.])(?P<num>\d{1,4})\s*(?:pages?|pgs?\.?|pp\.?)(?=\W|$)|\bpages?\s*[:\-]?\s*(?P<num2>\d{1,4})\b", re.I)


def parse_num(s: str) -> float:
    s = s.strip()
    if re.fullmatch(r"\d{1,3}(?:,\d{3})+", s):  # 1,000 -> thousands separator
        return float(s.replace(",", ""))
    return float(s.replace(",", "."))


def norm_unit(u: str) -> str:
    u = u.lower()
    if u.startswith("kilo") or u.startswith("kg"):
        return "kg"
    if u.startswith("milli") or u == "ml":
        return "ml"
    if u.startswith("lit") or u.startswith("ltr") or u == "l":
        return "l"
    return "g"


@dataclass
class NetQty:
    kind: str  # "std" | "count" | "dozen" | "none"
    hit: Optional[Hit] = None
    value: Optional[float] = None
    unit: Optional[str] = None  # g kg ml l count dozen
    base_value: Optional[float] = None  # in g / ml / count
    base_unit: Optional[str] = None  # g / ml / count
    qualifier: Optional[str] = None
    labelled: bool = False


def _std(lab: LabelText, m: re.Match, labelled: bool) -> NetQty:
    value = parse_num(m.group("num"))
    unit = norm_unit(m.group("unit"))
    base_value, base_unit = value, unit
    if unit == "kg":
        base_value, base_unit = value * 1000, "g"
    elif unit == "l":
        base_value, base_unit = value * 1000, "ml"
    q = m.group("q") or m.group("q2")
    return NetQty("std", lab.hit(m.start(), m.end()), value, unit, base_value, base_unit, q, labelled)


def _labelled(lab: LabelText, start: int) -> bool:
    """Is there 'Net Wt' / 'Contents' wording just before this value (same line or previous line)?"""
    t = lab.text
    if NET_KW_RE.search(t[max(0, start - 45): start]):
        # but not if that window crosses into an unrelated region
        if lab.has_geometry:
            kw = list(NET_KW_RE.finditer(t, max(0, start - 45), start))[-1]
            i, j = lab.line_index(kw.start()), lab.line_index(start)
            return i == j or j in lab.related_lines(i, max_rows=1.5)
        return True
    return False


def find_net_quantity(lab: LabelText) -> NetQty:
    t = lab.text
    cands = []
    for m in QTY_RE.finditer(t):
        if re.search(r"per\s*$", t[max(0, m.start() - 8): m.start()], re.I):
            continue  # nutrition table: "per 100 g"
        cands.append((_labelled(lab, m.start()), m))

    labelled_c = [m for lbl, m in cands if lbl]
    if labelled_c:
        return _std(lab, labelled_c[0], True)

    dz = DOZEN_RE.search(t)
    if dz:
        v = parse_num(dz.group("num"))
        return NetQty("dozen", lab.hit(dz.start(), dz.end()), v, "dozen", v, "dozen")

    ct = COUNT_RE.search(t)
    if ct:
        v = float(ct.group("num"))
        return NetQty("count", lab.hit(ct.start(), ct.end()), v, "count", v, "count", labelled=True)

    if cands:
        return _std(lab, cands[0][1], False)

    bc = next((m for m in BARE_COUNT_RE.finditer(t) if not SHEET_COUNT_BEFORE_RE.search(t[max(0, m.start() - 40): m.start()])), None)
    if bc:
        v = float(bc.group("num"))
        return NetQty("count", lab.hit(bc.start(), bc.end()), v, "count", v, "count", labelled=False)
    return NetQty("none")


@dataclass
class PageCount:
    value: int
    hit: Hit


def find_page_count(lab: LabelText) -> Optional[PageCount]:
    """'140 Pages' is product information (how many pages a notebook has), never a net quantity."""
    m = PAGE_RE.search(lab.text)
    if not m:
        return None
    return PageCount(int(m.group("num") or m.group("num2")), lab.hit(m.start(), m.end()))


# ---------------------------------------------------------------- MRP
AMT = r"\d+(?:\s?[.,]\s?\d{1,2})?"
CURRENCY = r"(?:\b(?:rs|inr|rupees?)\b\.?|₹|रु\.?|रू\.?)"
PRICE_RE = re.compile(
    rf"(?:{CURRENCY}\s*[:\-]?\s*(?P<a>{AMT})(?:\s*/-)?|(?<![\d.])(?P<b>{AMT})\s*(?:/-|₹|\brs\b))",
    re.I,
)
MRP_KW = (r"\bm\s?\.?\s?r\s?\.?\s?p\b\.?|maximum\s*retail\s*price|retail\s*(?:sale\s*)?price"
          r"|अधिकतम\s*खुदरा\s*मूल्य|एम\.?\s*आर\.?\s*पी")
MRP_BARE_RE = re.compile(rf"(?:{MRP_KW})\W{{0,10}}(?P<c>{AMT})(?!\d)", re.I)
MRP_KW_RE = re.compile(MRP_KW, re.I)
# accepted wordings of the mandatory tax-inclusion phrase (contain "all taxes")
_INC = r"[iIl1|]nc(?:l(?:\.|usive|uding|uded)?)?\.?"
TAX_RE = re.compile(
    rf"{_INC}\s*(?:of\s*)?all\s*tax(?:es)?|all\s*tax(?:es)?\s*incl(?:uded|usive|\.)?|सभी\s*करों\s*सहित",
    re.I,
)
# wording that mentions taxes being included but omits "all" ("Incl. of Taxes")
TAX_WITHOUT_ALL_RE = re.compile(
    rf"{_INC}\s*(?:of\s*)?tax(?:es)?\b|tax(?:es)?\s*incl(?:uded|usive|\.)?|including\s*tax(?:es)?|करों\s*सहित",
    re.I,
)
TAX_WORD_RE = re.compile(r"\btax(?:es)?\b|\bgst\b|कर", re.I)


@dataclass
class Mrp:
    found: bool
    hit: Optional[Hit] = None
    amount: Optional[float] = None
    tax_phrase: bool = False  # accepted wording ("... all taxes") associated with the price
    has_mrp_keyword: bool = False
    tax_variant: Optional[str] = None  # "all" | "without_all" | None
    tax_hit: Optional[Hit] = None
    partial_tax: Optional[Hit] = None  # the word "tax" nearby, but no readable inclusion phrase
    keyword_only: Optional[Hit] = None  # MRP keyword visible, amount not readable


def find_mrp(lab: LabelText) -> Mrp:
    t = lab.text
    cands = []
    for rx in (PRICE_RE, MRP_BARE_RE):
        for m in rx.finditer(t):
            kw = MRP_KW_RE.search(t, max(0, m.start() - 20), m.end())
            cands.append((0 if kw else 1, m.start(), m, kw))
    if not cands:
        kw = MRP_KW_RE.search(t)
        if kw:
            return Mrp(False, has_mrp_keyword=True, keyword_only=lab.hit(kw.start(), min(len(t), kw.end() + 12)))
        return Mrp(False)
    cands.sort(key=lambda c: (c[0], c[1]))
    _, _, best, kw = cands[0]
    amt = next(g for g in (best.groupdict().get("a"), best.groupdict().get("b"), best.groupdict().get("c")) if g)
    amount = parse_num(re.sub(r"\s", "", amt))
    start = kw.start() if kw else best.start()

    tax_variant, tax_hit, partial = None, None, None
    tax = lab.search_related(TAX_RE, best.start(), best.end())
    if tax:
        tax_variant, tax_hit = "all", lab.hit(tax.start(), tax.end())
    else:
        tax2 = lab.search_related(TAX_WITHOUT_ALL_RE, best.start(), best.end())
        if tax2:
            tax_variant, tax_hit = "without_all", lab.hit(tax2.start(), tax2.end())
        else:
            tw = lab.search_related(TAX_WORD_RE, best.start(), best.end())
            if tw:
                partial = lab.hit(tw.start(), tw.end())
    hit = lab.hit(start, best.end())
    return Mrp(True, hit, amount, tax_variant == "all", bool(kw), tax_variant, tax_hit, partial)


# ---------------------------------------------------------------- manufacturer / entity / address
MFR_RE = re.compile(
    r"\b(?:(?:manufactured|mfd?\.?|mfg\.?|packed|pkd\.?|produced|made)\s*(?:and|&|/)?\s*"
    r"(?:(?:marketed|distributed|packed|packaged)\s*)?(?:by|at)\b|(?:manufacturer|packer|packaged\s*by)\s*[:\-])"
    r"|निर्माता|द्वारा\s*निर्मित",
    re.I,
)
IMPORT_RE = re.compile(r"\bimported\s*by\b|\bimporter\s*[:\-]|आयातक", re.I)
MARKET_RE = re.compile(r"\b(?:marketed|distributed|sold|marketing)\s*(?:and|&|/)?\s*(?:marketed|distributed)?\s*by\b", re.I)
PIN_RE = re.compile(r"(?<![\d\-/])\b[1-9]\d{2}\s?\d{3}\b(?![\-/]\d)")
ADDRESS_WORDS = re.compile(
    r"\b(?:plot|no\.|door|flat|shop|unit|survey|sy\.?\s*no|road|rd\.?|street|st\.|lane|cross|main|marg|nagar|"
    r"layout|colony|sector|phase|block|stage|area|industrial|estate|kiadb|midc|gidc|sidco|ksidc|village|vill\.?|"
    r"post|taluk|tq\.?|dist(?:rict)?\.?|city|town|state|near|opp\.?|behind|floor|building|complex|park|"
    r"karnataka|maharashtra|tamil\s*nadu|kerala|gujarat|delhi|telangana|andhra|punjab|haryana|rajasthan|"
    r"uttar\s*pradesh|west\s*bengal|bihar|odisha|assam|madhya\s*pradesh|india)\b",
    re.I,
)
BUSINESS_SUFFIX = re.compile(
    r"\b(?:pvt|private|ltd|limited|llp|inc|co\.?|company|corp(?:oration)?|industries|enterprises?|traders?|"
    r"mills?|foods?|products?|agencies|exports?|imports?|tech|technologies|works|udyog|udyam|sons|bros|brothers|"
    r"group|manufacturers?|publications?|publishers?|stationers?|stationery|book\s*(?:house|depot|tech|co))\b",
    re.I,
)
EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
# OCR often drops the dot before the TLD ("bhaskarbook@yahoo in"): accepted as evidence, flagged
EMAIL_LOOSE_RE = re.compile(r"(?P<user>[\w.+-]+)\s?@\s?(?P<dom>[\w-]+)(?:[\s,]|\.\s)(?P<tld>in|com|co\.in|org|net|co)\b", re.I)
PHONE_HINT_RE = re.compile(r"help\s*line|helpline|toll\s*free|\bph(?:one)?\b|\btel\b|customer\s*care", re.I)


@dataclass
class Entity:
    name: str
    hit: Hit
    evidence: List[str]


@dataclass
class Address:
    hit: Hit
    pin: Optional[str]
    words: List[str]


@dataclass
class Manufacturer:
    has_manufacturer: bool
    has_importer: bool
    has_marketer: bool
    has_address: bool
    hit: Optional[Hit] = None
    role: Optional[str] = None  # manufacturer | packer | importer | marketer | None (not stated)
    entity: Optional[Entity] = None
    address: Optional[Address] = None


def find_address(lab: LabelText) -> Optional[Address]:
    """A run of address-like lines ending at a PIN code (same region when geometry exists)."""
    t = lab.text
    best = None
    for pm in PIN_RE.finditer(t):
        li = lab.line_index(pm.start())
        group = lab.related_lines(li) if lab.has_geometry else list(range(max(0, li - 3), li + 1))
        group = [j for j in group if j <= li and (not lab.has_geometry or lab.lines[j].block == lab.lines[li].block or j == li)]
        addr_lines = []
        misses = 0
        for j in sorted(group, reverse=True):
            s, e = lab.span_of_line(j)
            seg = t[s:e]
            if EMAIL_RE.search(seg) or PHONE_HINT_RE.search(seg) or MRP_KW_RE.search(seg):
                break
            if j == li or ADDRESS_WORDS.search(seg) or re.search(r"\d+\s*/\s*\d+|\b\d+(?:st|nd|rd|th)\b", seg):
                addr_lines.append(j)
                misses = 0
            elif misses == 0 and j > 0:
                misses += 1  # tolerate one partly read line inside an address
            else:
                break
        if not addr_lines:
            continue
        words = []
        for j in addr_lines:
            s, e = lab.span_of_line(j)
            words += [w.group(0) for w in ADDRESS_WORDS.finditer(t[s:e])]
        score = len(words) + len(addr_lines)
        if best is None or score > best[0]:
            s = lab.span_of_line(min(addr_lines))[0]
            # trim anything after the PIN on that line (e.g. a merged price column)
            best = (score, Address(lab.hit(s, pm.end()), re.sub(r"\s", "", pm.group(0)), words))
    return best[1] if best else None


def _email_tokens(lab: LabelText) -> List[str]:
    out = []
    for m in EMAIL_RE.finditer(lab.text):
        user, dom = m.group(0).split("@", 1)
        out += [user.lower(), dom.split(".")[0].lower()]
    for m in EMAIL_LOOSE_RE.finditer(lab.text):
        out += [m.group("user").lower(), m.group("dom").lower()]
    return [re.sub(r"[^a-z]", "", x) for x in out if len(x) >= 4]


def find_entity_name(lab: LabelText, exclude: Sequence[Tuple[int, int]] = ()) -> Optional[Entity]:
    """Best candidate for the business name printed on the label (brand / company).

    Generic evidence only: business suffixes (Pvt, Ltd, Industries, Tech...), a trademark mark,
    upper-case lettering, agreement with the e-mail user/domain, and closeness to the address.
    Consecutive upper-case lines in the same region are joined ('BHASKAR' + 'BOOK TECH')."""
    t = lab.text
    email_keys = _email_tokens(lab)
    cands = []
    n = len(lab.lines)
    i = 0
    while i < n:
        s, e = lab.span_of_line(i)
        seg = t[s:e].strip()
        letters = [c for c in seg if c.isalpha()]
        if len(letters) < 3 or any(a < e and b > s for a, b in exclude) or EMAIL_RE.search(seg) \
                or PIN_RE.search(seg) or re.search(r"\d{3,}", seg) or MRP_KW_RE.search(seg):
            i += 1
            continue
        j = i
        # join following upper-case lines of the same region (logo text split over lines)
        while j + 1 < n and (lab.lines[j + 1].block == lab.lines[i].block or
                             (lab.has_geometry and j + 1 in lab.related_lines(j, max_rows=2.5))):
            s2, e2 = lab.span_of_line(j + 1)
            nxt = t[s2:e2].strip()
            if nxt and sum(c.isupper() for c in nxt) >= 0.7 * max(1, sum(c.isalpha() for c in nxt)) and not re.search(r"\d", nxt):
                j += 1
            else:
                break
        es = lab.span_of_line(j)[1]
        name = " ".join(t[s:es].split())
        name_clean = re.sub(r"\b(?:tm|®|™)\b", "", name, flags=re.I).strip(" ,.-")
        name_clean = re.sub(r"^(?:(?:regd|registered|reg)\.?\s*)?(?:office|offc)\s*[:\-]\s*", "", name_clean, flags=re.I)
        ev, score = [], 0.0
        alpha = [c for c in name_clean if c.isalpha()]
        if alpha and sum(c.isupper() for c in alpha) / len(alpha) > 0.8 and len(name_clean.split()) <= 6:
            score += 0.3
            ev.append("upper-case lettering")
        if BUSINESS_SUFFIX.search(name_clean):
            score += 0.4
            ev.append("business-name word ('" + BUSINESS_SUFFIX.search(name_clean).group(0) + "')")
        squashed = re.sub(r"[^a-z]", "", name_clean.lower())
        for k in email_keys:
            if k and squashed and (k in squashed or squashed in k or (len(k) >= 6 and k[:6] in squashed)):
                score += 0.5
                ev.append(f"matches e-mail name '{k}'")
                break
        if re.search(r"™|®|\bTM\b", t[max(0, s - 6): es + 6]):
            score += 0.1
            ev.append("trademark mark")
        if ADDRESS_WORDS.search(name_clean) or len(name_clean.split()) > 8:
            score -= 0.6
        if score >= 0.5:
            cands.append((score, Entity(name_clean, lab.hit(s, es), ev)))
        i = j + 1
    if not cands:
        return None
    cands.sort(key=lambda c: -c[0])
    return cands[0][1]


def _name_at_address_start(lab: LabelText, addr: "Address") -> Optional[Entity]:
    """'Hillgrove Tea Co., Plot 4, ...': a business name written as the first part of the address."""
    t = lab.text
    s = addr.hit.start
    m = re.match(r"\s*([^,\d\n]{3,60}?),", t[s:addr.hit.end])
    if m and BUSINESS_SUFFIX.search(m.group(1)) and not ADDRESS_WORDS.search(m.group(1)):
        name = " ".join(m.group(1).split())
        return Entity(name, lab.hit(s + m.start(1), s + m.end(1)), ["business-name word at the start of the address"])
    return None


def find_manufacturer(lab: LabelText) -> Manufacturer:
    t = lab.text
    mfr, imp, mkt = MFR_RE.search(t), IMPORT_RE.search(t), MARKET_RE.search(t)
    addr = find_address(lab)
    anchor = mfr or imp or mkt
    if not anchor:
        ent = find_entity_name(lab, [(addr.hit.start, addr.hit.end)] if addr else ())
        if ent is None and addr is not None:
            ent = _name_at_address_start(lab, addr)
        hit = None
        if ent and addr:
            a, b = sorted([ent.hit, addr.hit], key=lambda h: h.start)
            hit = Hit(f"{ent.name} | {addr.hit.text}", a.start, b.end, round(min(ent.hit.conf, addr.hit.conf), 3),
                      f"{ent.hit.original} | {addr.hit.original}", ent.hit.changes + addr.hit.changes)
        elif addr:
            hit = addr.hit
        elif ent:
            hit = ent.hit
        return Manufacturer(False, False, False, bool(addr and addr.pin), hit, None, ent, addr)
    ws = anchor.start()
    we = min(len(t), anchor.end() + 220)
    pin = PIN_RE.search(t[ws:we])
    hit = lab.hit(ws, ws + pin.end() if pin else min(len(t), anchor.end() + 120))
    role = "manufacturer" if mfr else ("importer" if imp else "marketer")
    if mfr and re.match(r"(?i)pack|pkd", mfr.group(0)):
        role = "packer"
    return Manufacturer(bool(mfr), bool(imp), bool(mkt), bool(pin), hit, role, None, addr)


# ---------------------------------------------------------------- generic name
@dataclass
class Generic:
    found: bool
    keyword: Optional[str] = None
    hit: Optional[Hit] = None


ITEM_LINE_RE = re.compile(
    r"(?:^|\n)\s*(?:item(?:\s*name)?|product(?:\s*name)?|name\s+of\s+(?:the\s+)?(?:product|commodity)|commodity)\s*"
    r"(?:[:\-]\s*|\n\s*[:\-]\s*)(?P<name>[A-Za-z][^\n]{2,80})",
    re.I,
)


def locate_snippet(lab: LabelText, snippet: str) -> Optional[Tuple[int, int]]:
    """Where a text quoted by the AI reader sits in the label text (None if it is not really printed there).
    This is the check that keeps AI-supplied fields honest: a value that is not in the text is ignored."""
    norm = normalize_line(snippet or "").normalized
    words = norm.split()
    if len(norm) < 3 or not words:
        return None
    m = re.search(r"\s*".join(re.escape(w) for w in words), lab.text, re.I)
    return (m.start(), m.end()) if m else None


def ai_net_quantity(lab: LabelText, current: "NetQty", snippet: str) -> "NetQty":
    """Use the net-quantity declaration the AI quoted, if it is printed on the label and the rules' own parser can
    read a quantity from it, and the pattern finder found nothing better (nothing, or only an unlabelled count)."""
    if current.kind != "none" and current.labelled:
        return current
    span = locate_snippet(lab, snippet)
    if not span:
        return current
    q = find_net_quantity(LabelText.from_text(lab.text[span[0]:span[1]]))
    if q.kind == "none" or q.hit is None:
        return current
    q.hit = lab.hit(span[0] + q.hit.start, span[0] + q.hit.end)
    q.labelled = True
    return q


def _reanchor(lab: LabelText, obj, off: int):
    """Move every Hit inside a finder result (found in a quoted snippet) to its place in the full label text."""
    from dataclasses import fields, is_dataclass, replace

    if isinstance(obj, Hit):
        return lab.hit(obj.start + off, obj.end + off)
    if is_dataclass(obj):
        upd = {}
        for f in fields(obj):
            v = getattr(obj, f.name)
            if isinstance(v, Hit) or (is_dataclass(v) and not isinstance(v, type)):
                upd[f.name] = _reanchor(lab, v, off)
        return replace(obj, **upd)
    return obj


def _quoted_sublabel(lab: LabelText, snippet: str):
    """(LabelText of the quoted snippet, its offset in the full text), or None when the snippet is not printed on the
    label or cannot be re-read faithfully."""
    span = locate_snippet(lab, snippet)
    if not span:
        return None
    piece = lab.text[span[0]:span[1]]
    sub = LabelText.from_text(piece)
    if sub.text != piece:
        return None
    return sub, span[0]


def ai_mrp(lab: LabelText, current: "Mrp", snippet: str) -> "Mrp":
    """The AI quoted the MRP declaration. Used when the pattern finder found no price, or found one but not its tax
    wording and the quoted text has both (same amount)."""
    if current.found and current.tax_phrase:
        return current
    q = _quoted_sublabel(lab, snippet)
    if not q:
        return current
    cand = find_mrp(q[0])
    if not cand.found or cand.hit is None:
        return current
    if current.found and (current.amount != cand.amount or not cand.tax_phrase):
        return current
    return _reanchor(lab, cand, q[1])


def ai_mfg_date(lab: LabelText, current: "MfgDate", snippet: str) -> "MfgDate":
    """The AI quoted the manufacture / packing date. Used only when the pattern finder found none."""
    if current.found:
        return current
    q = _quoted_sublabel(lab, snippet)
    if not q:
        return current
    cand = find_mfg_date(q[0])
    if not cand.found or cand.hit is None or cand.only_expiry:
        return current
    return _reanchor(lab, cand, q[1])


def _mfr_score(m: "Manufacturer") -> int:
    return 2 * bool(m.has_manufacturer or m.has_importer or m.has_marketer) + bool(m.has_address) + bool(m.entity)


def ai_manufacturer(lab: LabelText, current: "Manufacturer", snippet: str) -> "Manufacturer":
    """The AI quoted the block naming the manufacturer / packer / importer and its address. Used only when re-reading
    that block with the rules' own finder gives a more complete answer than the whole-label search."""
    q = _quoted_sublabel(lab, snippet)
    if not q:
        return current
    cand = find_manufacturer(q[0])
    if _mfr_score(cand) <= _mfr_score(current):
        return current
    return _reanchor(lab, cand, q[1])


def find_generic_name(lab: LabelText, category: str, exclude: Sequence[Tuple[int, int]] = ()) -> Generic:
    """A plain-language product word, outside the brand/business name (``exclude`` spans)."""
    im = ITEM_LINE_RE.search(lab.text)
    if im:
        s, e = im.start("name"), im.end("name")
        if not any(a < e and b > s for a, b in exclude):
            return Generic(True, "an 'Item' / 'Product' line", lab.hit(s, e))
    words = list(GENERIC_KEYWORDS.get(category, [])) + GENERAL_GENERIC_WORDS
    for w in words:
        pat = r"\s*".join(re.escape(p) for p in w.split())
        for m in re.finditer(rf"\b{pat}(?:s|es)?\b", lab.text, re.I):
            if any(a < m.end() and b > m.start() for a, b in exclude):
                continue
            return Generic(True, w, lab.hit(m.start(), m.end()))
    return Generic(False)


# ---------------------------------------------------------------- manufacture date
MONTHS = (
    r"jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|aug(?:ust)?"
    r"|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?"
)
DATE_ALPHA_RE = re.compile(rf"\b(?:{MONTHS})\b\.?[\s.,'\-/]*(?:20\d{{2}}|\d{{2}})(?!\d)", re.I)
DATE_NUM_RE = re.compile(
    r"(?<![\d./])(?:0?[1-9]|1[0-2])\s*[/\-]\s*(?:20\d{2}|\d{2})(?![\d/A-Za-z])"
    r"|(?<![\d./])(?:0?[1-9]|1[0-2])\s*\.\s*20\d{2}(?!\d)"
)
# full numeric dates printed as dd.mm.yy / dd/mm/yyyy (e.g. batch stamps "10.09.26"): they contain the month and year
DATE_FULL_RE = re.compile(r"(?<![\d./\-])(?:0?[1-9]|[12]\d|3[01])\s?[./\-]\s?(?:0?[1-9]|1[0-2])\s?[./\-]\s?(?:20\d{2}|\d{2})(?![\d/A-Za-z])")
EXPIRY_KW_RE = re.compile(r"(?:exp\w*|best\s*before|use\s*(?:by|before))\W{0,12}$", re.I)
MFG_KW_RE = re.compile(
    r"(?:mfg|mfd|manufactur\w*|pkd|pack\w*|month\s*(?:&|and)\s*year|date\s*of\s*(?:mfg|manufacture|packing))\b(?:\W|date|dt|of|on)*$",
    re.I,
)


@dataclass
class MfgDate:
    found: bool
    hit: Optional[Hit] = None
    near_keyword: bool = False
    only_expiry: bool = False
    keyword_only: Optional[Hit] = None  # "Mfg:" visible but the date was not readable


MFG_LABEL_RE = re.compile(r"\b(?:mfg|mfd|pkd|month\s*(?:&|and)\s*year\s*of\s*(?:mfg|manufacture|packing)|date\s*of\s*(?:mfg|manufacture|packing))\b", re.I)


def find_mfg_date(lab: LabelText) -> MfgDate:
    t = lab.text
    cands = []
    for rx in (DATE_ALPHA_RE, DATE_NUM_RE, DATE_FULL_RE):
        for m in rx.finditer(t):
            # a date inside an address token ("267/16") or phone number is not a date
            ctx = t[max(0, m.start() - 3): m.end() + 2]
            if re.search(r"\d/\d+[A-Za-z]", ctx):
                continue
            before = t[max(0, m.start() - 28): m.start()]
            cands.append((m, bool(EXPIRY_KW_RE.search(before)), bool(MFG_KW_RE.search(before))))
    good = sorted((c for c in cands if not c[1]), key=lambda c: (not c[2], c[0].start()))
    if good:
        m, _, kw = good[0]
        return MfgDate(True, lab.hit(m.start(), m.end()), kw)
    kw = MFG_LABEL_RE.search(t)
    return MfgDate(False, only_expiry=bool(cands), keyword_only=lab.hit(kw.start(), min(len(t), kw.end() + 15)) if kw else None)


# ---------------------------------------------------------------- dimensions
_DU = r"(?:cms?|mms?|mtrs?|m|inches|inch|in|ft|feet|\")"
DIM_RE = re.compile(rf"\d+(?:\.\d+)?\s*{_DU}?\s*[x×*X]\s*\d+(?:\.\d+)?(?:\s*[x×*X]\s*\d+(?:\.\d+)?)?\s*{_DU}(?=\W|$)", re.I)


def find_dimensions(lab: LabelText) -> Optional[Hit]:
    m = DIM_RE.search(lab.text)
    return lab.hit(m.start(), m.end()) if m else None


def parse_dimensions(text: str) -> Optional[str]:
    """'30x18Cms' -> '30 × 18 cm' (display form; units normalized, numbers untouched)."""
    nums = re.findall(r"\d+(?:\.\d+)?", text)
    um = re.search(r"(cms?|mms?|mtrs?|inch(?:es)?|in|ft|feet|m|\")\W*$", text, re.I)
    if len(nums) < 2:
        return None
    unit = {"cms": "cm", "mms": "mm", "mtrs": "m", "mtr": "m", "inches": "in", "inch": "in", "feet": "ft", '"': "in"}
    u = um.group(1).lower() if um else ""
    return " × ".join(nums) + (" " + unit.get(u, u) if u else "")


# ---------------------------------------------------------------- barcodes
EAN_RE = re.compile(r"(?<!\d)(\d[\s]?\d{6}[\s]?\d{6}|\d{8}|\d{12,13})(?!\d)")


def _ean_ok(digits: str) -> bool:
    if len(digits) not in (8, 12, 13):
        return False
    ds = [int(c) for c in digits]
    body, check = ds[:-1], ds[-1]
    rev = body[::-1]
    total = sum(d * (3 if i % 2 == 0 else 1) for i, d in enumerate(rev))
    return (10 - total % 10) % 10 == check


def find_barcode_numbers(lab: LabelText) -> List[Hit]:
    """Human-readable barcode digits (EAN-8/UPC-A/EAN-13 with a valid check digit). These are not
    phone numbers and are not decoded into declarations."""
    out = []
    for m in EAN_RE.finditer(lab.text):
        d = re.sub(r"\s", "", m.group(1))
        if _ean_ok(d):
            out.append(lab.hit(m.start(), m.end()))
    return out


# ---------------------------------------------------------------- consumer care
PHONE_RE = re.compile(
    r"(?<!\d)(?:\+?91[\s\-]?)?(?:1800[\s\-]?\d{2,3}[\s\-]?\d{3,4}|1860[\s\-]?\d{3}[\s\-]?\d{4}"
    r"|[6-9]\d{4}[\s\-]?\d{5}|0\d{2,4}[\s\-]?\d{3,4}[\s\-]?\d{3,4})(?!\d)"
    r"|(?<!\d)\+\s?91[\s\-]?\d{2,4}[\s\-]?\d{3,4}[\s\-]?\d{3,4}(?!\d)"
)
CARE_KW_RE = re.compile(
    r"customer\s*care|consumer\s*(?:care|complaint)s?|complaints?|for\s*(?:queries|feedback)|help\s*line|helpline"
    r"|toll\s*free|\bcall\b|\bph(?:one)?\b\.?|\btel\b\.?|\bcontact\b|e-?mail|उपभोक्ता",
    re.I,
)


@dataclass
class Contacts:
    phones: List[Hit] = field(default_factory=list)
    emails: List[Hit] = field(default_factory=list)
    loose_emails: List[Hit] = field(default_factory=list)  # read with a missing dot; flagged
    care_keyword: Optional[Hit] = None


def find_contacts(lab: LabelText) -> Contacts:
    t = lab.text
    barcodes = [(h.start, h.end) for h in find_barcode_numbers(lab)]
    c = Contacts()
    for m in PHONE_RE.finditer(t):
        if any(a < m.end() and b > m.start() for a, b in barcodes):
            continue
        if PIN_RE.fullmatch(m.group(0).strip()):
            continue
        c.phones.append(lab.hit(m.start(), m.end()))
    c.emails = [lab.hit(m.start(), m.end()) for m in EMAIL_RE.finditer(t)]
    if not c.emails:
        c.loose_emails = [lab.hit(m.start(), m.end()) for m in EMAIL_LOOSE_RE.finditer(t)]
    kw = CARE_KW_RE.search(t)
    if kw:
        c.care_keyword = lab.hit(kw.start(), kw.end())
    # prefer phones that sit next to a care keyword
    if len(c.phones) > 1:
        def near_kw(h: Hit) -> int:
            return 0 if CARE_KW_RE.search(t[max(0, h.start - 30): h.start]) else 1
        c.phones.sort(key=near_kw)
    return c


def find_consumer_care(lab: LabelText) -> Optional[Hit]:
    c = find_contacts(lab)
    if c.phones:
        return c.phones[0]
    if c.emails:
        return c.emails[0]
    t = lab.text
    kw = CARE_KW_RE.search(t)
    if kw:
        window_end = min(len(t), kw.end() + 200)
        pin = PIN_RE.search(t[kw.start():window_end])
        if pin:  # a dedicated care address
            return lab.hit(kw.start(), kw.start() + pin.end())
    if c.loose_emails:
        return c.loose_emails[0]
    return None


# ---------------------------------------------------------------- language (Rule 9)
def script_counts(text: str) -> Tuple[int, int, int]:
    """(latin letters, devanagari letters, letters in any other script)"""
    lat = dev = oth = 0
    for ch in text:
        if not ch.isalpha():
            continue
        o = ord(ch)
        if o < 0x250:
            lat += 1
        elif 0x0900 <= o <= 0x097F:
            dev += 1
        else:
            oth += 1
    return lat, dev, oth
