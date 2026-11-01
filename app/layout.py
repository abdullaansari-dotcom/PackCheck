"""Layout analysis: OCR boxes -> regions (blocks) -> lines, in reading order.

The original pipeline sorted every OCR box by its vertical centre and glued everything on the
same visual row into one line. On a label with several columns (logo | address | price |
barcode) that produced lines such as
``Kiadb Industrial Area, 140 Pages MRP: 60.00`` -- an address fragment, a page count and a
price fused together -- and the extractor then read across unrelated declarations.

This module keeps every box's coordinates and splits the label into regions with a
recursive XY-cut over the boxes:

* a *vertical* cut is made at a whitespace gutter that runs through two or more text rows
  (a real column boundary), or wherever a printed vertical rule (separator line detected by
  :func:`app.preprocess.find_vertical_rules`) passes between boxes;
* a *horizontal* cut is made at a clear gap between rows;
* the larger gap (relative to the text height) wins, which keeps columns together instead of
  interleaving them when two columns happen to have paragraph breaks at the same height;
* a single row is never split by whitespace alone, so ``Net Wt.      100g`` stays one line.

Inside each region, boxes on the same row are joined left to right. Regions are emitted in
reading order (the XY-cut order), and every :class:`Line` remembers its region, column,
bounding box and source tokens so the extractor can use spatial evidence.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from statistics import mean, median
from typing import Any, List, Optional, Sequence, Tuple

BBox = Tuple[float, float, float, float]  # x0, y0, x1, y1


@dataclass
class Token:
    """One OCR box. ``text`` is what the engine read (never edited here)."""

    text: str
    conf: float
    bbox: BBox
    engine: str = ""
    alt_text: Optional[str] = None  # second engine / model reading, if any
    alt_conf: Optional[float] = None
    note: Optional[str] = None  # arbitration note

    @property
    def x0(self) -> float:
        return self.bbox[0]

    @property
    def y0(self) -> float:
        return self.bbox[1]

    @property
    def x1(self) -> float:
        return self.bbox[2]

    @property
    def y1(self) -> float:
        return self.bbox[3]

    @property
    def h(self) -> float:
        return max(1.0, self.bbox[3] - self.bbox[1])

    @property
    def yc(self) -> float:
        return (self.bbox[1] + self.bbox[3]) / 2

    def as_dict(self) -> dict:
        return {"text": self.text, "conf": round(self.conf, 3), "bbox": [round(v, 1) for v in self.bbox],
                "engine": self.engine, "alt_text": self.alt_text,
                "alt_conf": None if self.alt_conf is None else round(self.alt_conf, 3), "note": self.note}


@dataclass
class Line:
    """One line of label text. Only ``text`` and ``conf`` are required (text input has no geometry)."""

    text: str
    conf: float = 1.0
    bbox: Optional[BBox] = None
    block: Optional[int] = None
    column: Optional[int] = None
    tokens: Optional[List[Token]] = field(default=None, compare=False, repr=False)
    image: Optional[int] = None  # which photo the line came from (0 = front, 1 = back); None for a single photo


@dataclass
class Panel:
    """One photo inside a multi-photo label. Lines of photo ``i`` live at ``y0 .. y0 + height`` in the shared
    coordinate space, so geometry checks (Rule 8, contrast) can be run against the right photo."""

    label: str
    y0: float
    width: int
    height: int
    gray: Any = field(default=None, compare=False, repr=False)  # unenhanced grayscale of that photo


@dataclass
class Separator:
    """A printed vertical rule on the label (x position and vertical extent)."""

    x: float
    y0: float
    y1: float


def token_from_easyocr(result, engine: str = "easyocr") -> Optional[Token]:
    bbox_pts, text, conf = result
    text = (text or "").strip()
    if not text:
        return None
    xs = [float(p[0]) for p in bbox_pts]
    ys = [float(p[1]) for p in bbox_pts]
    return Token(text, float(conf), (min(xs), min(ys), max(xs), max(ys)), engine)


# ------------------------------------------------------------------ helpers
def _union(boxes: Sequence[BBox]) -> BBox:
    return (min(b[0] for b in boxes), min(b[1] for b in boxes), max(b[2] for b in boxes), max(b[3] for b in boxes))


def _gaps(intervals: List[Tuple[float, float]]) -> List[Tuple[float, float]]:
    """Interior gaps of the union of 1-D intervals."""
    if not intervals:
        return []
    iv = sorted(intervals)
    gaps = []
    cur_end = iv[0][1]
    for a, b in iv[1:]:
        if a > cur_end:
            gaps.append((cur_end, a))
        cur_end = max(cur_end, b)
    return gaps


def group_into_rows(tokens: List[Token]) -> List[List[Token]]:
    """Boxes whose vertical centres are close (relative to their height) share a row."""
    if not tokens:
        return []
    med = median(t.h for t in tokens)
    # boxes much taller than the typical text (logo strokes, merged junk) must not glue two rows together
    normal = [t for t in tokens if t.h <= 1.8 * med]
    tall = [t for t in tokens if t.h > 1.8 * med]
    rows: List[dict] = []
    for t in sorted(normal, key=lambda t: t.yc):
        best = None
        for r in rows[-3:]:
            tol = 0.6 * min(t.h, r["h"])
            d = abs(t.yc - r["yc"])
            if d < tol and (best is None or d < best[0]):
                best = (d, r)
        if best:
            r = best[1]
            r["items"].append(t)
            r["yc"] = mean(i.yc for i in r["items"])
            r["h"] = median(i.h for i in r["items"])
        else:
            rows.append({"items": [t], "yc": t.yc, "h": t.h})
    for t in tall:  # attach to the row it overlaps most, or start its own row
        best = None
        for r in rows:
            ov = min(t.y1, r["yc"] + r["h"] / 2) - max(t.y0, r["yc"] - r["h"] / 2)
            if ov > 0 and (best is None or abs(t.yc - r["yc"]) < abs(t.yc - best["yc"])):
                best = r
        if best:
            best["items"].append(t)
        else:
            rows.append({"items": [t], "yc": t.yc, "h": t.h})
    rows.sort(key=lambda r: r["yc"])
    return [sorted(r["items"], key=lambda t: t.x0) for r in rows]


def _sep_in_gap(seps: Sequence[Separator], gx0: float, gx1: float, y0: float, y1: float) -> bool:
    span = max(1.0, y1 - y0)
    for s in seps:
        if gx0 - 2 <= s.x <= gx1 + 2:
            overlap = min(y1, s.y1) - max(y0, s.y0)
            if overlap >= 0.5 * span or overlap >= 0.5 * (s.y1 - s.y0):
                return True
    return False


# ------------------------------------------------------------------ XY-cut
H_GAP_MIN = 0.6  # horizontal cut: row gap >= 0.6 x text height
V_GAP_MIN = 1.0  # vertical cut: gutter >= 1 x text height through >= 2 rows
V_GAP_SEP_MIN = 0.3  # vertical cut at a printed separator line: gutter >= 0.3 x text height


def _xy_cut(tokens: List[Token], seps: Sequence[Separator], med_h: float, out: List[List[Token]], depth: int = 0) -> None:
    if len(tokens) <= 1 or depth > 40:
        out.append(tokens)
        return
    region = _union([t.bbox for t in tokens])
    rows = group_into_rows(tokens)

    best_v = None  # (score, cut_x)
    for gx0, gx1 in _gaps([(t.x0, t.x1) for t in tokens]):
        w = gx1 - gx0
        sep = _sep_in_gap(seps, gx0, gx1, region[1], region[3])
        if sep and w >= V_GAP_SEP_MIN * med_h:
            score = max(w / med_h, V_GAP_MIN) + 2.0  # a printed rule is strong evidence of a boundary
        elif len(rows) >= 2 and w >= V_GAP_MIN * med_h:
            # a gutter only counts if text sits on both sides of it in >= 2 rows
            both = sum(1 for r in rows if any(t.x1 <= gx0 + 1 for t in r) and any(t.x0 >= gx1 - 1 for t in r))
            if both < 2:
                # columns whose lines are not aligned: each side must hold >= 2 rows of its own and the
                # two sides must overlap vertically (otherwise it is a label/value gap on one row)
                left = [t for t in tokens if t.x1 <= gx0 + 1]
                right = [t for t in tokens if t.x0 >= gx1 - 1]
                if len(group_into_rows(left)) < 2 or len(group_into_rows(right)) < 2:
                    continue
                l0, l1 = min(t.y0 for t in left), max(t.y1 for t in left)
                r0, r1 = min(t.y0 for t in right), max(t.y1 for t in right)
                if min(l1, r1) - max(l0, r0) < 0.5 * min(l1 - l0, r1 - r0):
                    continue
            score = w / med_h
        else:
            continue
        if best_v is None or score > best_v[0]:
            best_v = (score, (gx0 + gx1) / 2)

    best_h = None
    for gy0, gy1 in _gaps([(t.y0, t.y1) for t in tokens]):
        g = gy1 - gy0
        if g >= H_GAP_MIN * med_h:
            score = g / med_h
            if best_h is None or score > best_h[0]:
                best_h = (score, (gy0 + gy1) / 2)

    if best_v and (not best_h or best_v[0] >= best_h[0]):
        cut = best_v[1]
        left = [t for t in tokens if (t.x0 + t.x1) / 2 < cut]
        right = [t for t in tokens if (t.x0 + t.x1) / 2 >= cut]
        if left and right:
            _xy_cut(left, seps, med_h, out, depth + 1)
            _xy_cut(right, seps, med_h, out, depth + 1)
            return
    if best_h:
        cut = best_h[1]
        top = [t for t in tokens if t.yc < cut]
        bottom = [t for t in tokens if t.yc >= cut]
        if top and bottom:
            _xy_cut(top, seps, med_h, out, depth + 1)
            _xy_cut(bottom, seps, med_h, out, depth + 1)
            return
    out.append(tokens)


def _assign_columns(blocks: List[BBox]) -> List[int]:
    """Blocks whose x-ranges overlap share a column; columns numbered left to right. Blocks that
    span more than half the label width (headers, stray noise) get their own column and never
    merge two real columns together."""
    if not blocks:
        return []
    page_w = max(b[2] for b in blocks) - min(b[0] for b in blocks) or 1.0
    order = sorted(range(len(blocks)), key=lambda i: blocks[i][0])
    col_of = [0] * len(blocks)
    cols: List[List[float]] = []  # [x0, x1, spanning]
    for i in order:
        x0, _, x1, _ = blocks[i]
        spanning = (x1 - x0) > 0.5 * page_w
        for ci, c in enumerate(cols):
            if spanning or c[2]:
                continue
            overlap = min(x1, c[1]) - max(x0, c[0])
            if overlap > 0.3 * min(x1 - x0, c[1] - c[0]):
                c[0], c[1] = min(c[0], x0), max(c[1], x1)
                col_of[i] = ci
                break
        else:
            cols.append([x0, x1, spanning])
            col_of[i] = len(cols) - 1
    rank = {ci: r for r, ci in enumerate(sorted(range(len(cols)), key=lambda c: cols[c][0]))}
    return [rank[c] for c in col_of]


def build_lines(tokens: Sequence[Token], separators: Sequence[Separator] = ()) -> List[Line]:
    """Tokens -> lines in reading order, each tagged with its region (block) and column."""
    toks = [t for t in tokens if t.text and t.text.strip()]
    if not toks:
        return []
    med_h = median(t.h for t in toks)
    regions: List[List[Token]] = []
    _xy_cut(toks, list(separators), med_h, regions)
    boxes = [_union([t.bbox for t in r]) for r in regions]
    cols = _assign_columns(boxes)
    lines: List[Line] = []
    for bi, region in enumerate(regions):
        for row in group_into_rows(region):
            lines.append(Line(
                " ".join(t.text.strip() for t in row),
                round(mean(t.conf for t in row), 3),
                _union([t.bbox for t in row]), bi, cols[bi], list(row)))
    return lines


def tokens_from_dicts(items: Sequence[dict]) -> List[Token]:
    return [Token(d["text"], float(d["conf"]), tuple(d["bbox"]), d.get("engine", ""), d.get("alt_text"),
                  d.get("alt_conf"), d.get("note")) for d in items]
