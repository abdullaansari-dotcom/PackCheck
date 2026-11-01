"""End-to-end orchestration: image bytes -> preprocessing -> OCR -> layout -> rules.

Kept separate from the FastAPI layer so it can be called from scripts and tests.

    IMAGE -> PREPROCESSING -> OCR (detect once, recognise en [+ hi], arbitrate)
          (in parallel) AI VISION READER (transcription, category hint)
          -> FUSION (AI text placed on the OCR boxes, AI vs OCR numbers compared)
          -> TEXT NORMALIZATION (inside LabelText) -> LAYOUT ANALYSIS (regions, columns, reading order)
          -> DECLARATION EXTRACTION -> PRODUCT CLASSIFICATION -> RULE APPLICABILITY
          -> COMPLIANCE EVALUATION -> RESULT
"""
from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field, replace
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np

from . import config
from . import vision
from .classify import CategoryHint
from .engine import analyze
from .fusion import fuse
from .layout import Line, Panel, Separator, Token, build_lines
from .models import ScanResult

log = logging.getLogger("packcheck.pipeline")


class NoTextFound(ValueError):
    pass


def _region_meta(lines: Sequence[Line], tokens: Sequence[Token], separators: Sequence[Separator], ocr_meta: Optional[dict]) -> dict:
    meta = dict(ocr_meta or {})
    meta["regions"] = [
        {"line": i, "block": l.block, "column": l.column, "text": l.text, "conf": l.conf,
         "bbox": [round(v, 1) for v in l.bbox] if l.bbox else None,
         **({"image": l.image} if l.image is not None else {})}
        for i, l in enumerate(lines)
    ]
    meta["separators"] = [{"x": round(s.x, 1), "y0": round(s.y0, 1), "y1": round(s.y1, 1)} for s in separators]
    meta["tokens"] = [t.as_dict() for t in tokens]
    return meta


def analyze_tokens(
    tokens: Sequence[Token],
    separators: Sequence[Separator] = (),
    category: str = "auto",
    pack_type: Optional[str] = None,
    gray: Optional[np.ndarray] = None,
    image_size: Optional[Tuple[int, int]] = None,
    ocr_meta: Optional[dict] = None,
) -> ScanResult:
    lines = build_lines(list(tokens), separators)
    meta = _region_meta(lines, tokens, separators, ocr_meta)
    return analyze(lines, category, pack_type, from_ocr=True, gray=gray, image_size=image_size, ocr_meta=meta)


# ------------------------------------------------------------------ reader selection
def resolve_reader(requested: Optional[str] = None) -> str:
    """'ocr' | 'ai' | 'hybrid'. 'auto' means hybrid when an AI key is configured, otherwise OCR."""
    mode = (requested or config.READER_MODE or "auto").strip().lower()
    if mode not in ("auto", "ocr", "ai", "hybrid"):
        raise ValueError(f"Unknown reader '{mode}'. Use auto, hybrid, ai or ocr.")
    if mode == "auto":
        return "hybrid" if vision.is_configured() else "ocr"
    if mode in ("ai", "hybrid") and not vision.is_configured():
        raise vision.VisionNotConfigured(
            "The AI reader is not configured. Set ANTHROPIC_API_KEY or GEMINI_API_KEY in .env, or use the OCR reader.")
    return mode


def _run_ocr(img: np.ndarray, lean: bool = False):
    """Preprocess + EasyOCR. Returns (OcrResult, separators, raw_gray, preprocess_report_dict)."""
    from .ocr import read_tokens
    from .preprocess import find_vertical_rules, preprocess_with_report

    if config.PREPROCESS:
        max_side = config.HYBRID_OCR_MAX_SIDE if (lean and config.HYBRID_OCR_MAX_SIDE) else config.PREPROCESS_MAX_SIDE
        gray, rep = preprocess_with_report(img, max_side=max_side,
                                           perspective=config.PERSPECTIVE_CORRECTION)
        raw, prep = rep.raw_gray, rep.as_dict()
    else:
        import cv2

        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        raw, prep = gray, {"variant": "none"}
    seps = find_vertical_rules(gray)
    res = read_tokens(gray, seps, lean=lean and bool(config.HYBRID_OCR_MAX_SIDE))
    if res.variant != "gray_enhanced":
        prep["variant"] = res.variant
    return res, seps, raw, prep



# ------------------------------------------------------------------ one photo -> one reading
PHOTO_LABELS = ("Front", "Back")
MAX_PHOTOS = len(PHOTO_LABELS)
PANEL_GAP = 120  # px between photos in the shared coordinate space (keeps their text from ever looking adjacent)


@dataclass
class _Read:
    """Everything one photo contributed: lines in that photo's own coordinates plus how it was read."""

    lines: List[Line]
    tokens: List[Token]
    seps: List[Separator]
    gray: Optional[np.ndarray]
    image_size: Tuple[int, int]
    prep: dict
    engines: List[str]
    variant: str
    notes: List[str]
    mean_conf: Optional[float]
    ai: Optional[dict] = None  # AI reader summary (reading.as_dict() + fusion + lines) or {"error": ...}
    reading: Optional[vision.VisionReading] = None
    fallback: Optional[str] = None  # 'ocr' (AI failed) or 'ai' (OCR failed)


def _ocr_read(img, ocr_out, extra_notes: List[str], ai: Optional[dict] = None, fallback: Optional[str] = None) -> _Read:
    res, seps, raw, prep = ocr_out
    if not res.tokens:
        raise NoTextFound("No text could be read from this image. Try a clearer, closer photo.")
    tokens = list(res.tokens)
    return _Read(build_lines(tokens, seps), tokens, list(seps), raw, res.image_size, prep, list(res.engines),
                 res.variant, list(res.notes) + extra_notes, res.mean_conf, ai, None, fallback)


def _ai_read(img, reading, ocr_out, ocr_err, mode: str) -> Tuple[_Read, Optional[str]]:
    """AI reading (optionally grounded on OCR boxes). Returns the read and the fallback tag."""
    ocr_lines: List[Line] = []
    tokens: List[Token] = []
    seps: List[Separator] = []
    notes: List[str] = []
    fallback = None
    engines = [f"vision:{reading.provider}/{reading.model}"]
    if ocr_out is not None:
        res, seps, raw, prep = ocr_out
        tokens = list(res.tokens)
        ocr_lines = build_lines(tokens, seps)
        engines += list(res.engines)
        image_size, gray = res.image_size, raw
        notes += list(res.notes)
    else:
        import cv2

        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        image_size = (gray.shape[1], gray.shape[0])
        prep = {"variant": "none"}
        if mode == "hybrid":
            notes.append(f"OCR was unavailable ({ocr_err}); this result uses the AI reading only, so position "
                         "based checks (clear space, contrast) are limited.")
            fallback = "ai"
    lines, rep = fuse(reading, ocr_lines)
    if not lines:
        raise NoTextFound("No text could be read from this image. Try a clearer, closer photo.")
    for d in rep["disagreements"]:
        notes.append(f"AI and OCR read different numbers on one line ({', '.join(d['numbers_not_seen_by_ocr'])} "
                     f"not seen by OCR): AI \"{d['ai']}\" / OCR \"{d['ocr']}\".")
    ai_meta = {**reading.as_dict(), "fusion": rep,
               "lines": [{"text": l.text, "region": l.region, "lang": l.lang} for l in reading.lines]}
    read = _Read(lines, tokens, list(seps), gray, image_size, prep, engines, "ai+ocr" if ocr_lines else "ai", notes,
                 rep["mean_confidence"], ai_meta, reading, fallback)
    return read, fallback


def _read_photos(imgs: Sequence[np.ndarray], mode: str, info: dict) -> List[Optional[_Read]]:
    """Reads every photo. The AI calls run in parallel (network-bound) alongside a single OCR worker that goes
    through the photos in turn (CPU-bound). A photo with no readable text yields None (the caller decides)."""
    from .ocr import OcrUnavailable

    n = len(imgs)
    reads: List[Optional[_Read]] = [None] * n
    errors: List[Optional[Exception]] = [None] * n
    if mode == "ocr":
        for i, img in enumerate(imgs):
            try:
                reads[i] = _ocr_read(img, _run_ocr(img), [])
            except NoTextFound as e:
                errors[i] = e
        return _check_reads(reads, errors)

    def ocr_all():
        out = []
        for img in imgs:  # lean mode when the AI reader runs alongside, as before
            try:
                out.append((_run_ocr(img, True), None))
            except Exception as e:  # OCR is the second reader here: never let it sink an AI result
                if not isinstance(e, (OcrUnavailable, ImportError)):
                    log.exception("OCR failed during hybrid scan")
                out.append((None, e))
        return out

    with ThreadPoolExecutor(max_workers=n + 1) as pool:
        ai_futs = [pool.submit(vision.read_label, img) for img in imgs]
        ocr_fut = pool.submit(ocr_all) if mode == "hybrid" else None
        readings: List[Optional[vision.VisionReading]] = []
        ai_errs: List[Optional[vision.VisionError]] = []
        for f in ai_futs:
            try:
                readings.append(f.result())
                ai_errs.append(None)
            except vision.VisionError as e:
                readings.append(None)
                ai_errs.append(e)
        ocr_results = ocr_fut.result() if ocr_fut is not None else [(None, None)] * n

    for i, img in enumerate(imgs):
        ocr_out, ocr_err = ocr_results[i]
        reading, ai_err = readings[i], ai_errs[i]
        try:
            if reading is None:  # AI failed on this photo
                if mode == "ai" or ocr_out is None:
                    raise ai_err
                info["fallback"] = "ocr"
                notes = [f"The AI reader was unavailable ({ai_err}); this result uses OCR only."]
                reads[i] = _ocr_read(img, ocr_out, notes, {"error": str(ai_err)}, "ocr")
            else:
                reads[i], fb = _ai_read(img, reading, ocr_out, ocr_err, mode)
                if fb:
                    info["fallback"] = info.get("fallback") or fb
        except NoTextFound as e:
            errors[i] = e
    return _check_reads(reads, errors)


def _check_reads(reads: List[Optional[_Read]], errors: List[Optional[Exception]]) -> List[Optional[_Read]]:
    if not any(reads):
        raise next(e for e in errors if e is not None)
    return reads


# ------------------------------------------------------------------ merging photos into one label
def _shift_line(l: Line, dy: float, image: int) -> Line:
    shift = lambda b: (b[0], b[1] + dy, b[2], b[3] + dy)
    toks = [replace(t, bbox=shift(t.bbox)) for t in l.tokens] if l.tokens else l.tokens
    return Line(l.text, l.conf, shift(l.bbox) if l.bbox else None,
                None if l.block is None else l.block + image * 100000, l.column, toks, image)


def _merge_ai(reads: List[Tuple[int, _Read]], total: int) -> Optional[dict]:
    """One AI summary for the whole label (the UI reads one 'ai' block)."""
    ok = [(i, r) for i, r in reads if r.ai and "error" not in r.ai]
    failed = [(i, r) for i, r in reads if r.ai and "error" in r.ai]
    if not ok:
        return {"error": "; ".join(f"{PHOTO_LABELS[i]}: {r.ai['error']}" for i, r in failed)} if failed else None
    first = ok[0][1].ai
    lines: List[dict] = []
    dis: List[dict] = []
    issues: List[str] = []
    notes: List[str] = []
    fus = {"ai_lines": 0, "ocr_lines": 0, "grounded": 0, "ai_only_lines": 0}
    confs: List[float] = []
    for i, r in ok:
        a = r.ai
        off = len(lines)
        lines += [{**l, "image": i} for l in a["lines"]]
        f = a.get("fusion") or {}
        dis += [{**d, "line": d["line"] + off, "image": i} for d in f.get("disagreements", [])]
        for k in ("ai_lines", "ocr_lines", "grounded"):
            fus[k] += f.get(k) or 0
        fus["ai_only_lines"] += f.get("ai_only_lines") or 0
        if f.get("mean_confidence") is not None:
            confs.append(f["mean_confidence"])
        tag = f"{PHOTO_LABELS[i]}: " if total > 1 else ""
        issues += [tag + x for x in a.get("issues", [])]
        notes += [tag + x for x in a.get("notes", [])]
    cats = [(r.ai.get("category_confidence") or 0.0, r.ai.get("category"), r.ai.get("category_reason", ""))
            for _, r in ok if r.ai.get("category")]
    best = max(cats, key=lambda c: c[0]) if cats else (None, None, "")
    legibles = [r.ai.get("legible") for _, r in ok]
    out = {**first, "line_count": len(lines), "lines": lines, "issues": issues, "notes": notes,
           "fusion": {**fus, "disagreements": dis, "mean_confidence": round(sum(confs) / len(confs), 3) if confs else None},
           "category": best[1], "category_confidence": best[0] if best[1] else None, "category_reason": best[2],
           "legible": False if False in legibles else (True if all(x is True for x in legibles) else None)}
    if failed:
        out["partial_errors"] = [f"{PHOTO_LABELS[i]}: {r.ai['error']}" for i, r in failed]
    return out


def scan_images_bytes(images: Sequence[bytes], category: str = "auto", pack_type: Optional[str] = None,
                      reader: Optional[str] = None) -> ScanResult:
    """Scan one label from one or two photos (front, then back) and check it as a single label.

    Each photo is read on its own (AI and/or OCR). Their lines are then placed one below the other in a shared
    coordinate space (so the declaration finders see the whole label) while geometry checks still run on the photo
    each declaration was printed on. Raises the same errors as :func:`scan_image_bytes`."""
    from .preprocess import decode_image

    if not images:
        raise ValueError("No image was provided.")
    if len(images) > MAX_PHOTOS:
        raise ValueError(f"At most {MAX_PHOTOS} photos (front and back) can be checked together.")
    mode = resolve_reader(reader)
    multi = len(images) > 1
    decoded = []
    for i, data in enumerate(images):
        try:
            decoded.append(decode_image(data))
        except ValueError as e:
            raise ValueError(f"{PHOTO_LABELS[i]} photo: {e}" if multi else str(e))
    info = {"mode": mode, "requested": (reader or config.READER_MODE or "auto"), "fallback": None}
    reads = _read_photos(decoded, mode, info)
    used = [(i, r) for i, r in enumerate(reads) if r is not None]
    notes: List[str] = []
    for i, r in enumerate(reads):
        if r is None:
            notes.append(f"No text could be read from the {PHOTO_LABELS[i].lower()} photo, so only the other photo "
                         "was checked. Retake it if it carries declarations.")

    def tag(i: int, msgs: Sequence[str]) -> List[str]:
        return [f"{PHOTO_LABELS[i]}: {m}" if multi else m for m in msgs]

    # ---- single photo: unchanged behaviour (coordinates stay the photo's own)
    if len(used) == 1 and not multi:
        r = used[0][1]
        meta = {"reader": info, "engines": r.engines, "variant": r.variant, "preprocess": r.prep,
                "notes": r.notes, "mean_token_confidence": r.mean_conf}
        if r.ai is not None:
            meta["ai"] = r.ai
        if r.reading is not None:
            meta = _region_meta(r.lines, r.tokens, r.seps, meta)
            hint = (CategoryHint(r.reading.category, r.reading.category_confidence or 0.0, r.reading.category_reason)
                    if r.reading.category else None)
            return analyze(r.lines, category, pack_type or r.reading.pack_type, from_ocr=True, gray=r.gray,
                           image_size=r.image_size, ocr_meta=meta, category_hint=hint, ai_fields=r.reading.fields)
        return analyze_tokens(r.tokens, r.seps, category, pack_type, gray=r.gray, image_size=r.image_size, ocr_meta=meta)

    # ---- two photos (or one of two that read): shared coordinate space
    lines: List[Line] = []
    tokens: List[Token] = []
    seps: List[Separator] = []
    panels: List[Panel] = []
    images_meta: List[dict] = []
    y = 0.0
    for i, r in used:
        w, h = r.image_size
        panels.append(Panel(PHOTO_LABELS[i], y, w, h, r.gray))
        shifted = [_shift_line(l, y, i) for l in r.lines]
        lines += shifted
        tokens += [replace(t, bbox=(t.bbox[0], t.bbox[1] + y, t.bbox[2], t.bbox[3] + y)) for t in r.tokens]
        seps += [Separator(s.x, s.y0 + y, s.y1 + y) for s in r.seps]
        images_meta.append({"index": i, "label": PHOTO_LABELS[i], "width": w, "height": h, "lines": len(r.lines),
                            "engines": r.engines, "mean_confidence": r.mean_conf})
        notes += tag(i, r.notes)
        y += h + PANEL_GAP
    engines: List[str] = []
    for _, r in used:
        engines += [e for e in r.engines if e not in engines]
    variants = {r.variant for _, r in used}
    confs = [(r.mean_conf, len(r.lines)) for _, r in used if r.mean_conf is not None]
    mean_conf = round(sum(c * n for c, n in confs) / sum(n for _, n in confs), 3) if confs else None
    meta = {"reader": info, "engines": engines, "variant": variants.pop() if len(variants) == 1 else "mixed",
            "preprocess": {"variant": "multi", "images": [r.prep for _, r in used]}, "notes": notes,
            "mean_token_confidence": mean_conf, "images": images_meta}
    ai = _merge_ai(used, len(images))
    if ai is not None:
        meta["ai"] = ai
    readings = [r.reading for _, r in used if r.reading is not None]
    hint = None
    cands = [rd for rd in readings if rd.category]
    if cands:
        b = max(cands, key=lambda rd: rd.category_confidence or 0.0)
        hint = CategoryHint(b.category, b.category_confidence or 0.0, b.category_reason)
    pt = pack_type or next((rd.pack_type for rd in readings if rd.pack_type), None)
    meta = _region_meta(lines, tokens, seps, meta)
    ai_fields: dict = {}
    for rd in readings:
        for k, v in rd.fields.items():
            ai_fields.setdefault(k, v)  # first photo that quotes a value wins; the engine verifies it in the text
    return analyze(lines, category, pt, from_ocr=True, ocr_meta=meta, category_hint=hint, ai_fields=ai_fields,
                   panels=panels)


def scan_image_bytes(data: bytes, category: str = "auto", pack_type: Optional[str] = None,
                     reader: Optional[str] = None) -> ScanResult:
    """One photo. Raises ValueError for undecodable images, NoTextFound when nothing could be read,
    app.ocr.OcrUnavailable when EasyOCR is not installed (OCR-only mode) and
    app.vision.VisionError / VisionNotConfigured when the AI reader is required but unusable."""
    return scan_images_bytes([data], category, pack_type, reader)
