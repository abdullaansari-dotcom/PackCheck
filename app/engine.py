"""Compliance rules engine (Legal Metrology (Packaged Commodities) Rules, 2011).

Pipeline position: ... -> declaration extraction -> PRODUCT CLASSIFICATION -> RULE APPLICABILITY
-> COMPLIANCE EVALUATION -> result.

* Rule 26 exemptions are decided first (rulebook Part E), and only on confirmed evidence.
* The registry in ``app/rules.py`` decides, per category, whether each rule is evaluated,
  not applicable, not configured, exempt or skipped by team decision.
* Every result carries a rule_reference, supporting evidence (original + normalized OCR text)
  and, where relevant, the limitation or open legal question behind it.
* "Not read" is never treated as "absent" when the photo was poor: low confidence, uncertain
  normalization and partially read declarations go to REVIEW.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from functools import cached_property
from typing import Dict, List, Optional, Tuple

import numpy as np

from . import config
from .classify import Classification, classify
from .data import (
    CATEGORY_INFO,
    CATEGORY_KEYS,
    FULL_EXEMPT_CATEGORIES,
    LEGAL_QUESTIONS,
    LIMITATIONS,
    SIZE_TABLE_UNIT,
    STATIONERY_CATEGORIES,
    UNLISTED_CATEGORIES,
    TAX_PHRASE_WITHOUT_ALL_POLICY,
    is_standard_size,
)
from .extract import (
    ai_manufacturer,
    ai_mfg_date,
    ai_mrp,
    ai_net_quantity,
    locate_snippet,
    NET_KW_RE,
    Hit,
    LabelText,
    Line,
    NetQty,
    find_barcode_numbers,
    find_contacts,
    find_dimensions,
    find_entity_name,
    find_generic_name,
    find_manufacturer,
    find_mfg_date,
    find_mrp,
    find_net_quantity,
    find_page_count,
    parse_dimensions,
    script_counts,
)
from .geometry import assess_clear_space, text_contrast
from .layout import Panel
from .models import STATUSES, Evidence, FieldResult, ScanResult
from .rules import FIELD_ORDER, REF, RULE_BY_FIELD, RULES

MIN_READABLE_LETTERS = 15  # Latin + Devanagari letters needed to call the label readable


@dataclass
class Ctx:
    lab: LabelText
    category: str
    pack_type: Optional[str]
    qty: NetQty
    from_ocr: bool
    classification: Optional[Classification] = None
    gray: Optional[np.ndarray] = None  # unenhanced grayscale in OCR coordinates
    image_size: Optional[Tuple[int, int]] = None
    panels: Optional[List[Panel]] = None  # set when the label was scanned from two photos (front + back)
    ai_fields: Dict[str, str] = field(default_factory=dict)  # values the AI quoted from the label (verified before use)
    ai_used: set = field(default_factory=set)  # which of them actually changed the answer
    results: Dict[str, FieldResult] = field(default_factory=dict)
    questions: Dict[str, str] = field(default_factory=dict)

    def locate(self, box) -> Optional[Tuple[Panel, Tuple[float, float, float, float]]]:
        """For a multi-photo label: the photo a box lies on and the box in that photo's own coordinates."""
        if not self.panels:
            return None
        yc = (box[1] + box[3]) / 2
        p = next((p for p in self.panels if p.y0 <= yc < p.y0 + p.height), None)
        if p is None:
            p = min(self.panels, key=lambda q: abs(yc - (q.y0 + q.height / 2)))
        return p, (box[0], box[1] - p.y0, box[2], box[3] - p.y0)

    def _via_ai(self, key: str, finder, current):
        """Apply the AI-quoted value for ``key`` if there is one; remember when it changed the answer."""
        snippet = self.ai_fields.get(key)
        if not snippet:
            return current
        better = finder(self.lab, current, snippet)
        if better is not current:
            self.ai_used.add(key)
        return better

    @cached_property
    def mfr(self):
        return self._via_ai("manufacturer", ai_manufacturer, find_manufacturer(self.lab))

    @cached_property
    def mrp(self):
        return self._via_ai("mrp", ai_mrp, find_mrp(self.lab))

    @cached_property
    def date(self):
        return self._via_ai("mfg_date", ai_mfg_date, find_mfg_date(self.lab))

    @cached_property
    def contacts(self):
        return find_contacts(self.lab)

    @cached_property
    def pages(self):
        return find_page_count(self.lab)

    @cached_property
    def dims(self):
        return find_dimensions(self.lab)

    @cached_property
    def entity(self):
        if self.mfr.entity:
            return self.mfr.entity
        exclude = [(self.mfr.address.hit.start, self.mfr.address.hit.end)] if self.mfr.address else []
        return find_entity_name(self.lab, exclude)

    def ask(self, key: str) -> str:
        self.questions[key] = LEGAL_QUESTIONS[key]
        return LEGAL_QUESTIONS[key]


# ------------------------------------------------------------------ helpers
def ev(label: str, hit: Optional[Hit]) -> List[Evidence]:
    if hit is None:
        return []
    return [Evidence(
        label=label, text=hit.text,
        original=hit.original if hit.original and hit.original != hit.text else None,
        confidence=hit.conf, bbox=[round(v, 1) for v in hit.bbox] if hit.bbox else None,
        normalizations=[c.as_dict() for c in hit.changes], image=hit.image,
    )]


def _res(field, status, code=None, hit=None, detail=None, sub_case=None, ref=None, evidence=None,
         legal_question=None) -> FieldResult:
    spec = RULE_BY_FIELD[field]
    return FieldResult(
        field=field,
        status=status,
        violation_code=code,
        detected_text=hit.text if hit else None,
        rule_reference=ref or REF[field],
        detail=detail,
        sub_case=sub_case,
        confidence=hit.conf if hit else None,
        title=spec.title,
        original_text=hit.original if hit else None,
        normalized_text=hit.text if hit else None,
        evidence=evidence if evidence is not None else ev("Detected", hit),
        limitation=spec.limitation,
        legal_question=legal_question,
    )


def _fin(r: FieldResult, ctx: Ctx, hit: Optional[Hit] = None) -> FieldResult:
    """Downgrade to REVIEW when the evidence itself is shaky: low OCR confidence, or a value that
    only exists because of an uncertain normalization (e.g. Devanagari digits in English text)."""
    if r.status not in ("PASS", "FAIL"):
        return r
    was = r.status + (f"/{r.violation_code}" if r.violation_code else "")
    if ctx.from_ocr and r.confidence is not None and r.confidence < config.MIN_FIELD_CONF:
        r.detail = f"OCR confidence {r.confidence:.2f} is too low to trust this (would have been {was}). " + (r.detail or "")
        r.status, r.violation_code = "REVIEW", "LOW_CONFIDENCE"
    elif hit is not None and hit.uncertain:
        bits = ", ".join(f"'{c.original}'->'{c.normalized}'" for c in hit.uncertain[:4])
        r.detail = (f"The value depends on uncertain character normalization ({bits}): digits in another script "
                    f"inside English text usually mean the OCR misread them. Confirm the reading "
                    f"(would have been {was}). " + (r.detail or ""))
        r.status, r.violation_code, r.sub_case = "REVIEW", "LOW_CONFIDENCE", r.sub_case or "UNCERTAIN_NORMALIZATION"
    return r


def _absent(ctx: Ctx, field: str, detail: str, sub_case: str = None, evidence=None) -> FieldResult:
    spec = RULE_BY_FIELD[field]
    if ctx.from_ocr and ctx.lab.avg_conf < config.MIN_OVERALL_CONF:
        return FieldResult(
            field=field, status="REVIEW", violation_code="LOW_CONFIDENCE", rule_reference=REF[field],
            detail=f"Not found, but overall OCR confidence is low ({ctx.lab.avg_conf:.2f}), so the text may "
                   f"simply not have been read. {detail}",
            sub_case=sub_case, confidence=ctx.lab.avg_conf, title=spec.title, evidence=evidence or [],
            limitation=spec.limitation,
        )
    if ctx.from_ocr:
        # A photo can miss text for many reasons (angle, glare, another face of the pack), so "not found" is a
        # question for a person, never an automatic FAIL. FAIL is kept for pasted text and for wrong formats.
        where = "on either photo" if ctx.panels and len(ctx.panels) > 1 else "in the photographed text"
        more = "" if ctx.panels and len(ctx.panels) > 1 else " If it is printed on another face of the pack, add a photo of that face."
        return FieldResult(field=field, status="REVIEW", violation_code="LOW_CONFIDENCE", rule_reference=REF[field],
                           detail=f"{detail} Not found {where}. A person should check the physical label.{more}",
                           sub_case=sub_case or "NOT_FOUND_IN_PHOTO", title=spec.title, evidence=evidence or [],
                           limitation=spec.limitation)
    return FieldResult(field=field, status="FAIL", violation_code="MISSING", rule_reference=REF[field],
                       detail=detail, sub_case=sub_case, title=spec.title, evidence=evidence or [],
                       limitation=spec.limitation)


def _status(field, status, detail, **kw) -> FieldResult:
    spec = RULE_BY_FIELD[field]
    return FieldResult(field=field, status=status, rule_reference=kw.pop("ref", None) or REF[field], detail=detail,
                       title=spec.title, limitation=spec.limitation, **kw)


def _na(field, detail) -> FieldResult:
    return _status(field, "NOT_APPLICABLE", detail)


def _exempt(field, detail) -> FieldResult:
    return _status(field, "EXEMPT", detail, ref="Rule 26")


# ------------------------------------------------------------------ Rule 9
def check_legibility(ctx: Ctx) -> FieldResult:
    if not ctx.from_ocr:
        return _na("legibility", "Text input: there is no OCR confidence to judge legibility from.")
    c = ctx.lab.avg_conf
    if c < config.MIN_OVERALL_CONF:
        return _status("legibility", "REVIEW", f"Average OCR confidence {c:.2f} is below {config.MIN_OVERALL_CONF}. "
                       "Blur, glare or low contrast likely. Retake the photo.", violation_code="LOW_CONFIDENCE",
                       confidence=c)
    return _status("legibility", "PASS", f"Average OCR confidence {c:.2f}.", confidence=c)


def check_contrast(ctx: Ctx) -> FieldResult:
    if ctx.gray is None and not ctx.panels:
        return _na("contrast", "No image pixels available (text input), so contrast cannot be measured.")
    targets = []
    for name, hit in (("MRP", ctx.mrp.hit), ("Net quantity", ctx.qty.hit), ("Date", ctx.date.hit),
                      ("Address", ctx.mfr.address.hit if ctx.mfr.address else None)):
        if hit is not None and hit.bbox:
            targets.append((name, hit))
    if not targets:
        targets = [(f"line {i + 1}", ctx.lab.line_hit(i)) for i, l in enumerate(ctx.lab.lines) if l.bbox][:12]
    def measure(h):
        if ctx.panels:  # measure on the photo the declaration is printed on
            panel, local = ctx.locate(h.bbox)
            return None if panel.gray is None else text_contrast(panel.gray, local)
        return text_contrast(ctx.gray, h.bbox)

    vals = [(n, h, measure(h)) for n, h in targets]
    vals = [(n, h, v) for n, h, v in vals if v is not None]
    if not vals:
        return _status("contrast", "REVIEW", "Could not measure contrast around the declarations.",
                       violation_code="LOW_CONFIDENCE")
    low = [(n, h, v) for n, h, v in vals if v < config.MIN_TEXT_CONTRAST]
    desc = ", ".join(f"{n} {v:.2f}" for n, _, v in vals)
    evidence = [e for n, h, v in vals for e in ev(f"{n} (contrast {v:.2f})", h)]
    if low:
        return _status("contrast", "REVIEW", f"Low text/background contrast in the photo ({desc}); threshold "
                       f"{config.MIN_TEXT_CONTRAST}. Check the physical label.", violation_code="LOW_CONFIDENCE",
                       sub_case="LOW_CONTRAST", evidence=evidence)
    return _status("contrast", "PASS", f"Text/background contrast in the photo: {desc}.", evidence=evidence)


def check_language(ctx: Ctx) -> FieldResult:
    lat, dev, oth = script_counts(ctx.lab.text)
    if lat + dev >= MIN_READABLE_LETTERS:
        note = f"English letters: {lat}, Devanagari letters: {dev}."
        if oth:
            note += f" Other scripts: {oth} (allowed alongside Hindi/English)."
        return _res("language", "PASS", detail=note, evidence=[])
    if oth > 0:
        return _res("language", "FAIL", "LANGUAGE_ERROR", evidence=[],
                    detail="Text is in another script with no (or almost no) Hindi or English. "
                           "Declarations must be in Hindi (Devanagari) or English.")
    return _status("language", "REVIEW", "Too little readable text to judge the language.",
                   violation_code="LOW_CONFIDENCE")


# ------------------------------------------------------------------ Rule 6
def check_manufacturer(ctx: Ctx) -> FieldResult:
    m = ctx.mfr
    if not (m.has_manufacturer or m.has_importer or m.has_marketer):
        ent, addr = ctx.entity, m.address
        evidence = ev("Business name", ent.hit if ent else None) + ev("Address", addr.hit if addr else None)
        if ent and addr and addr.pin:
            r = _res("manufacturer", "REVIEW", "LOW_CONFIDENCE", m.hit, sub_case="ROLE_NOT_STATED",
                     evidence=evidence, legal_question=ctx.ask("MANUFACTURER_ROLE_NOT_STATED"),
                     detail=f"Business name '{ent.name}' ({'; '.join(ent.evidence)}) and a complete address "
                            f"(PIN {addr.pin}) are printed, but the label does not say whether this is the "
                            "manufacturer, packer or importer. PackCheck does not assign a legal role on its own.")
            return r
        if addr and addr.pin:
            return _res("manufacturer", "REVIEW", "LOW_CONFIDENCE", m.hit, sub_case="NAME_NOT_IDENTIFIED",
                        evidence=evidence,
                        detail="A complete address is printed, but no business name or 'Manufactured/Packed/"
                               "Imported by' wording was identified with it.")
        if ent:
            return _absent(ctx, "manufacturer", f"Only a brand/business name ('{ent.name}') was found: no "
                           "'Manufactured/Packed/Imported by' wording and no complete address.",
                           sub_case="NAME_WITHOUT_ADDRESS", evidence=evidence)
        return _absent(ctx, "manufacturer", "No manufacturer / packer / importer name found.")
    if not m.has_manufacturer and not m.has_importer:
        return _fin(_res("manufacturer", "FAIL", "FORMAT_ERROR", m.hit, sub_case="MARKETED_BY_ONLY",
                         detail="Only 'Marketed/Distributed by' is stated. That is not the same as the "
                                "manufacturer or packer."), ctx, m.hit)
    if m.has_importer and not m.has_manufacturer:
        return _fin(_res("manufacturer", "FAIL", "FORMAT_ERROR", m.hit, sub_case="IMPORTER_ONLY",
                         detail="Importer is stated but the foreign manufacturer is not. Both are required."), ctx, m.hit)
    if not m.has_address:
        return _fin(_res("manufacturer", "FAIL", "FORMAT_ERROR", m.hit, sub_case="ADDRESS_INCOMPLETE",
                         detail="Name found but no complete address (no PIN code found near it)."), ctx, m.hit)
    return _fin(_res("manufacturer", "PASS", hit=m.hit, detail=f"Role stated: {m.role}."), ctx, m.hit)


def check_generic_name(ctx: Ctx) -> FieldResult:
    exclude = [(ctx.entity.hit.start, ctx.entity.hit.end)] if ctx.entity else []
    g = find_generic_name(ctx.lab, ctx.category, exclude)
    if g.found:
        return _fin(_res("generic_name", "PASS", hit=g.hit, detail=f"Matched '{g.keyword}'."), ctx, g.hit)
    name = ctx.ai_fields.get("product_name")
    span = locate_snippet(ctx.lab, name) if name else None
    if span and not (ctx.entity and ctx.entity.name.strip().lower() == name.strip().lower()):
        hit = ctx.lab.hit(*span)
        return _fin(_res("generic_name", "PASS", hit=hit, detail="The AI reader identified this as the product name and "
                         "it is printed on the label (verified against the transcription)."), ctx, hit)
    if ctx.category in STATIONERY_CATEGORIES and ctx.pages:
        return _res("generic_name", "REVIEW", "LOW_CONFIDENCE", None, sub_case="PRODUCT_TYPE_IMPLIED_ONLY",
                    evidence=ev("Product information", ctx.pages.hit),
                    detail=f"No plain product name such as 'Notebook' was found. The product type is only implied "
                           f"by '{ctx.pages.hit.text}'. A person should confirm whether the label (e.g. the front "
                           "cover) names the product, apart from the brand.")
    if ctx.category in UNLISTED_CATEGORIES:
        return _status("generic_name", "REVIEW",
                       "No common product word recognised and the category is 'other'. "
                       "A person should confirm the label states what the product is, apart from the brand.",
                       violation_code="LOW_CONFIDENCE", sub_case="CATEGORY_UNKNOWN")
    return _absent(ctx, "generic_name", "No plain-language product name found, only a brand name may be present.")


def check_net_quantity(ctx: Ctx) -> FieldResult:
    q = ctx.qty
    if q.kind == "none":
        if ctx.pages and (ctx.category in STATIONERY_CATEGORIES or ctx.category in UNLISTED_CATEGORIES):
            return _res("net_quantity", "REVIEW", "LOW_CONFIDENCE", None, sub_case="PAGE_COUNT_ONLY",
                        evidence=ev("Page count (product information)", ctx.pages.hit),
                        legal_question=ctx.ask("PAGE_COUNT_AS_NET_QUANTITY"),
                        detail=f"No net-quantity declaration (e.g. '1 N', 'Net Qty: 1 notebook') was found. "
                               f"'{ctx.pages.hit.text}' is a page count: it is recorded as product information, "
                               "not as the net quantity.")
        return _absent(ctx, "net_quantity", "No net quantity found.")
    if q.kind == "dozen":
        return _fin(_res("net_quantity", "FAIL", "UNIT_ERROR", q.hit, ref="Rule 6(1)(c) / Rule 13(4)",
                         detail="Declared in 'dozen', which is not a permitted unit for net quantity."), ctx, q.hit)
    if q.qualifier:
        return _fin(_res("net_quantity", "FAIL", "VAGUE_LANGUAGE", q.hit,
                         detail=f"Banned qualifier '{q.qualifier}'. Net quantity must be a definite number."), ctx, q.hit)
    note = None if q.labelled else "No 'Net Wt / Net Qty' wording found next to this quantity."
    return _fin(_res("net_quantity", "PASS", hit=q.hit, detail=note), ctx, q.hit)


def check_mfg_date(ctx: Ctx) -> FieldResult:
    d = ctx.date
    if not d.found:
        if d.keyword_only:
            return _res("mfg_date", "REVIEW", "LOW_CONFIDENCE", d.keyword_only, sub_case="DATE_UNREADABLE",
                        detail="A manufacture/packing label was read but no month + year next to it could be read.")
        if d.only_expiry:
            return _absent(ctx, "mfg_date", "Only an expiry / best-before date was found.",
                           sub_case="ONLY_EXPIRY_DATE")
        return _absent(ctx, "mfg_date", "No month + year of manufacture or packing found.")
    note = None if d.near_keyword else "Date found but no Mfg/Pkd wording next to it; it could be another date."
    return _fin(_res("mfg_date", "PASS", hit=d.hit, detail=note), ctx, d.hit)


def check_mrp(ctx: Ctx) -> FieldResult:
    m = ctx.mrp
    if not m.found:
        if m.keyword_only:
            return _res("mrp", "REVIEW", "LOW_CONFIDENCE", m.keyword_only, sub_case="MRP_VALUE_UNREADABLE",
                        detail="The MRP label was read but the amount next to it could not be read. "
                               "This is an OCR problem, not evidence that the price is missing.")
        return _absent(ctx, "mrp", "No retail price found.")
    evidence = ev("Price", m.hit) + ev("Tax wording", m.tax_hit) + ev("Tax word (partial)", m.partial_tax)
    amount = f"{m.amount:.2f}"
    if m.tax_variant == "all":
        return _fin(_res("mrp", "PASS", hit=m.hit, evidence=evidence,
                         detail=f"Price {amount} with '{m.tax_hit.text}' associated."), ctx, m.hit)
    if m.tax_variant == "without_all":
        detail = (f"Price {amount} found with '{m.tax_hit.text}'. The rulebook requires 'inclusive of all taxes' "
                  "or accepted equivalent wording; this wording omits 'all'.")
        q = ctx.ask("TAX_PHRASE_WITHOUT_ALL")
        if TAX_PHRASE_WITHOUT_ALL_POLICY == "accept":
            return _fin(_res("mrp", "PASS", hit=m.hit, evidence=evidence, detail=detail + " Accepted by policy.",
                             sub_case="TAX_PHRASE_WITHOUT_ALL", legal_question=q), ctx, m.hit)
        if TAX_PHRASE_WITHOUT_ALL_POLICY == "format_error":
            return _fin(_res("mrp", "FAIL", "FORMAT_ERROR", m.hit, evidence=evidence, detail=detail,
                             sub_case="TAX_PHRASE_WITHOUT_ALL", legal_question=q), ctx, m.hit)
        return _fin(_res("mrp", "REVIEW", "LOW_CONFIDENCE", m.hit, evidence=evidence, detail=detail,
                         sub_case="TAX_PHRASE_WITHOUT_ALL", legal_question=q), ctx, m.hit)
    if m.partial_tax:
        return _res("mrp", "REVIEW", "LOW_CONFIDENCE", m.hit, evidence=evidence, sub_case="TAX_PHRASE_UNREADABLE",
                    detail=f"Price {amount} found and the word '{m.partial_tax.text}' is next to it, but the full "
                           "tax-inclusion wording could not be read.")
    return _fin(_res("mrp", "FAIL", "FORMAT_ERROR", m.hit, sub_case="MISSING_TAX_PHRASE", evidence=evidence,
                     detail="Price is present but 'inclusive of all taxes' is not stated next to it."), ctx, m.hit)


def check_dimensions(ctx: Ctx) -> FieldResult:
    status, reason = RULE_BY_FIELD["dimensions"].applicability(ctx.category)
    h = ctx.dims
    if status == "NOT_CONFIGURED":
        q = ctx.ask("STATIONERY_DIMENSIONS")
        extra = (f" Printed size found (evidence only): '{h.text}' = {parse_dimensions(h.text)}." if h
                 else " No printed size was found.")
        return FieldResult(field="dimensions", status="NOT_CONFIGURED", rule_reference=REF["dimensions"],
                           detail=reason + extra, title=RULE_BY_FIELD["dimensions"].title,
                           detected_text=h.text if h else None, original_text=h.original if h else None,
                           normalized_text=h.text if h else None, evidence=ev("Printed size", h),
                           applicability="unresolved", legal_question=q)
    if status == "NOT_APPLICABLE":
        r = _na("dimensions", reason)
        if h:
            r.evidence = ev("Printed size (not required)", h)
        return r
    if not h:
        return _absent(ctx, "dimensions", "No dimensions (e.g. 90 cm x 180 cm) found.")
    return _fin(_res("dimensions", "PASS", hit=h), ctx, h)


def check_consumer_care(ctx: Ctx) -> FieldResult:
    c = ctx.contacts
    evidence = [e for h in c.phones[:2] for e in ev("Phone", h)] + [e for h in c.emails[:2] for e in ev("E-mail", h)] \
        + [e for h in c.loose_emails[:1] for e in ev("E-mail (dot not read)", h)]
    parts = []
    if c.phones:
        parts.append("phone")
    if c.emails or c.loose_emails:
        parts.append("e-mail")
    if ctx.mfr.address and ctx.mfr.address.pin:
        parts.append("address")
    if ctx.entity:
        parts.append("name")
    if c.phones or c.emails:
        hit = c.phones[0] if c.phones else c.emails[0]
        return _fin(_res("consumer_care", "PASS", hit=hit, evidence=evidence,
                         detail=f"Found: {', '.join(parts)}. Manufacturer contact details may serve as consumer care "
                                "details (rulebook 6(2))."), ctx, hit)
    if c.loose_emails:
        h = c.loose_emails[0]
        return _res("consumer_care", "REVIEW", "LOW_CONFIDENCE", h, evidence=evidence, sub_case="EMAIL_PARTIAL",
                    detail="An e-mail address was read without the dot before the domain ending. Confirm it.")
    kw = c.care_keyword
    if kw is not None:
        from .extract import PIN_RE

        t = ctx.lab.text
        pin = PIN_RE.search(t, kw.start, min(len(t), kw.end + 200))
        if pin:
            hit = ctx.lab.hit(kw.start, pin.end())
            return _fin(_res("consumer_care", "PASS", hit=hit, detail="Dedicated consumer-care address found."), ctx, hit)
    return _absent(ctx, "consumer_care", "No phone number, email or care address found.")


# ------------------------------------------------------------------ Rule 5
def check_pack_size(ctx: Ctx) -> FieldResult:
    cat, q = ctx.category, ctx.qty
    status, reason = RULE_BY_FIELD["pack_size"].applicability(cat)
    if status:
        return _status("pack_size", status, reason, applicability="not_configured")
    if q.kind != "std" or q.base_value is None:
        return _na("pack_size", "No usable net quantity to compare against the standard sizes.")
    if q.base_unit != SIZE_TABLE_UNIT[cat]:
        return _na("pack_size", f"Quantity is in {q.base_unit}, table is in {SIZE_TABLE_UNIT[cat]}.")
    ok, note = is_standard_size(cat, q.base_value, ctx.pack_type)
    if ok:
        return _fin(_res("pack_size", "PASS", hit=q.hit, detail=note), ctx, q.hit)
    disclaimer = re.search(r"non[\s\-]*standard", ctx.lab.text, re.I)
    if disclaimer:
        return _fin(_res("pack_size", "PASS", hit=q.hit, detail="Non-standard size, but the disclaimer is present."),
                    ctx, q.hit)
    return _fin(_res("pack_size", "FAIL", "NONSTANDARD_PACK", q.hit,
                     detail=("Not a standard size for this category and no 'Non-standard size' disclaimer found. "
                             + (note or ""))), ctx, q.hit)


# ------------------------------------------------------------------ Rule 7 (skipped) and Rule 8
def check_numeral_height(ctx: Ctx) -> FieldResult:
    table = CATEGORY_INFO.get(ctx.category, {}).get("rule7_table")
    if table is None and ctx.qty.kind == "std":
        table = "I"
    elif table is None and ctx.qty.kind == "count":
        table = "II"
    which = {"I": "Table I (weight/volume products)", "II": "Table II (length/area/count products, e.g. notebooks)"}
    tdesc = f" For this product the applicable table would be {which[table]}." if table else ""
    return _status("numeral_height", "SKIPPED_BY_TEAM_DECISION",
                   "Numeral height is not measured: a photo has no real-world scale, and the team decided (rulebook "
                   "Part B, finalized) not to build a partial or best-effort check. Only this measurement is "
                   "skipped; the product is still checked against every other applicable rule." + tdesc,
                   applicability="skipped_by_team_decision")


def _declaration_tokens(ctx: Ctx, hit: Hit):
    """OCR tokens that make up the net-quantity declaration (keyword + value), plus all others."""
    lab = ctx.lab
    t = lab.text
    start = hit.start
    kw = list(NET_KW_RE.finditer(t, max(0, start - 45), start))
    if kw and lab.line_index(kw[-1].start()) == lab.line_index(start):
        start = kw[-1].start()
    decl, others = [], []
    for i, line in enumerate(lab.lines):
        toks = line.tokens or []
        s0, _ = lab.span_of_line(i)
        pos = s0
        for tok in toks:
            a, b = pos, pos + len(tok.text.strip())
            pos = b + 1
            if a < hit.end and b > start:
                decl.append(tok)
            else:
                others.append(tok)
    return decl, others


def check_clear_space(ctx: Ctx) -> FieldResult:
    q = ctx.qty
    nq = ctx.results.get("net_quantity")
    if q.kind == "none" or q.hit is None:
        if nq is not None and nq.status == "REVIEW":
            return _status("clear_space", "REVIEW", "Rule 8 is assessed around the net-quantity declaration. It "
                           "cannot be assessed until the net quantity (sent to review) is confirmed.",
                           violation_code="LOW_CONFIDENCE", sub_case="NET_QUANTITY_UNCONFIRMED")
        return _na("clear_space", "No net-quantity declaration was found, so there is nothing to measure around. "
                   "The missing declaration itself is reported under Rule 6(1)(c).")
    if not ctx.lab.has_geometry:
        return _na("clear_space", "Text input has no image geometry, so the space around the net quantity cannot be "
                   "assessed. Scan a photo to assess Rule 8.")
    decl, others = _declaration_tokens(ctx, q.hit)
    if not decl or (ctx.image_size is None and not ctx.panels):
        return _status("clear_space", "REVIEW", "The net quantity was found but its position in the photo could not be "
                       "isolated, so the clear space could not be measured.", violation_code="LOW_CONFIDENCE",
                       sub_case="NOT_MEASURABLE", evidence=ev("Net quantity", q.hit))
    box = (min(t.x0 for t in decl), min(t.y0 for t in decl), max(t.x1 for t in decl), max(t.y1 for t in decl))
    where = ""
    if ctx.panels:  # judge the clear space on the photo the declaration is printed on, using only that photo's text
        panel, local_box = ctx.locate(box)
        same = [t for t in others if ctx.locate(t.bbox)[0] is panel]
        res = assess_clear_space(local_box, [(t.text, ctx.locate(t.bbox)[1]) for t in same],
                                 (panel.width, panel.height), panel.gray)
        where = f" (measured on the {panel.label.lower()} photo)"
    else:
        res = assess_clear_space(box, [(t.text, t.bbox) for t in others], ctx.image_size, ctx.gray)
    meas = ", ".join(f"{k} {'-' if v is None else f'{v:.2f}x'}" for k, v in res.measurements.items())
    base = (f"Estimated numeral height {res.numeral_height_px:.0f} px{where}. Nearest other text, as a multiple of "
            f"the required space (above/below 1x height, left/right 2x height): {meas}.")
    evidence = ev("Net quantity declaration", q.hit)
    if res.status == "PASS":
        return _status("clear_space", "PASS", base + " Clear zone inside the photo and free of printed matter.",
                       sub_case="ESTIMATED_FROM_PHOTO", evidence=evidence, confidence=0.6)
    reasons = res.crowded_by + res.reasons
    return _status("clear_space", "REVIEW", base + " " + "; ".join(reasons) + ".", violation_code="LOW_CONFIDENCE",
                   sub_case="POSSIBLE_CROWDING" if res.crowded_by else "NOT_VERIFIABLE", evidence=evidence)


CHECKS = {
    "legibility": check_legibility, "contrast": check_contrast, "language": check_language,
    "manufacturer": check_manufacturer, "generic_name": check_generic_name, "net_quantity": check_net_quantity,
    "mfg_date": check_mfg_date, "mrp": check_mrp, "dimensions": check_dimensions,
    "consumer_care": check_consumer_care, "pack_size": check_pack_size,
    "numeral_height": check_numeral_height, "clear_space": check_clear_space,
}


# ------------------------------------------------------------------ Rule 26
def exemption_level(category: str, qty: NetQty, from_ocr: bool = False) -> Tuple[Optional[str], Optional[str]]:
    """Returns ('FULL'|'REDUCED'|'UNCONFIRMED'|None, reason).

    Category exemptions only come from the user's own category choice (never inferred).
    Quantity exemptions need a labelled, confidently read quantity; otherwise 'UNCONFIRMED'
    (all checks still run and a failure becomes NEEDS_REVIEW, not NON_COMPLIANT)."""
    if category in FULL_EXEMPT_CATEGORIES:
        return "FULL", FULL_EXEMPT_CATEGORIES[category]
    if qty.kind == "std" and qty.base_value is not None and qty.base_unit in ("g", "ml"):
        v, u = qty.base_value, qty.base_unit
        reason = None
        level = None
        if v <= 10:
            level, reason = "FULL", f"Net quantity {v:g}{u} is 10{u} or less (very small package)"
        elif v <= 20:
            level, reason = "REDUCED", f"Net quantity {v:g}{u} is between 10 and 20{u} (only MRP and net quantity are required)"
        elif category == "agri_produce" and u == "g" and v > 50000:
            level, reason = "FULL", "Agricultural produce package above 50 kg"
        if level:
            shaky = (not qty.labelled) or (qty.hit is not None and qty.hit.uncertain) or \
                    (from_ocr and qty.hit is not None and qty.hit.conf < config.MIN_FIELD_CONF)
            if shaky:
                return "UNCONFIRMED", (f"Possible Rule 26 exemption ({reason}), but the quantity is not clearly "
                                       "declared or not confidently read, so every check was still run.")
            return level, reason
    return None, None


# ------------------------------------------------------------------ main entry
def analyze(
    lines: List[Line],
    category: str = "other",
    pack_type: Optional[str] = None,
    from_ocr: bool = False,
    gray: Optional[np.ndarray] = None,
    image_size: Optional[Tuple[int, int]] = None,
    ocr_meta: Optional[dict] = None,
    category_hint=None,
    ai_fields: Optional[Dict[str, str]] = None,
    panels: Optional[List[Panel]] = None,
) -> ScanResult:
    if category not in CATEGORY_KEYS:
        raise ValueError(f"Unknown category '{category}'")
    lab = LabelText(lines)
    cls = classify(lab.text, category, category_hint)
    qty = find_net_quantity(lab)
    fields_in = {k: v for k, v in (ai_fields or {}).items() if isinstance(v, str) and v.strip()}
    qty_via_ai = False
    if fields_in.get("net_quantity"):
        better = ai_net_quantity(lab, qty, fields_in["net_quantity"])
        qty_via_ai, qty = better is not qty, better
    ctx = Ctx(lab, cls.category, pack_type, qty, from_ocr, cls, gray,
              image_size or ((gray.shape[1], gray.shape[0]) if gray is not None else None), panels or None,
              ai_fields=fields_in)
    if qty_via_ai:
        ctx.ai_used.add("net_quantity")

    level, reason = exemption_level(cls.category, ctx.qty, from_ocr)
    results: List[FieldResult] = []
    for spec in RULES:
        name = spec.field
        if level == "FULL":
            r = _exempt(name, reason)
        elif level == "REDUCED" and not spec.kept_for_small_packages:
            r = _exempt(name, reason)
        else:
            status, why = spec.applicability(cls.category)
            if status == "EXEMPT":
                r = _status(name, "EXEMPT", why)
            else:
                r = CHECKS[name](ctx)
                if name in ctx.ai_used:
                    r.detail = ((r.detail or "") + " (Located with the help of the AI reader's quote of this "
                                "declaration, which was verified against the transcription.)").strip()
        if r.applicability is None:
            r.applicability = {"NOT_APPLICABLE": "not_applicable", "EXEMPT": "exempt",
                               "SKIPPED_BY_TEAM_DECISION": "skipped_by_team_decision",
                               "NOT_CONFIGURED": "not_configured"}.get(r.status, "applicable")
        ctx.results[name] = r
        results.append(r)

    summary = {s: sum(1 for r in results if r.status == s) for s in STATUSES}
    if level == "FULL":
        verdict = "EXEMPT"
    elif summary["FAIL"]:
        verdict = "NEEDS_REVIEW" if level == "UNCONFIRMED" else "NON_COMPLIANT"
    elif summary["REVIEW"]:
        verdict = "NEEDS_REVIEW"
    else:
        verdict = "COMPLIANT"

    product_info = {}
    if ctx.pages:
        product_info["page_count"] = {"value": ctx.pages.value, "text": ctx.pages.hit.text,
                                      "original": ctx.pages.hit.original}
    if ctx.dims:
        product_info["printed_size"] = {"text": ctx.dims.text, "original": ctx.dims.original,
                                        "parsed": parse_dimensions(ctx.dims.text)}
    if ctx.entity:
        product_info["business_name"] = {"text": ctx.entity.name, "evidence": ctx.entity.evidence,
                                         "legal_role": ctx.mfr.role or "not stated"}
    if ctx.mfr.address:
        product_info["address"] = {"text": ctx.mfr.address.hit.text, "pin": ctx.mfr.address.pin}
    if ctx.contacts.phones or ctx.contacts.emails or ctx.contacts.loose_emails:
        product_info["contacts"] = {"phones": [h.text for h in ctx.contacts.phones],
                                    "emails": [h.text for h in ctx.contacts.emails + ctx.contacts.loose_emails]}
    bars = find_barcode_numbers(lab)
    if bars:
        product_info["barcode_digits"] = [{"text": h.text, "note": "printed digits only; barcode not decoded"} for h in bars]

    return ScanResult(
        input_mode="image" if from_ocr else "text",
        category=cls.category,
        pack_type=pack_type,
        verdict=verdict,
        summary=summary,
        exemption={"level": level, "reason": reason} if level else None,
        fields=results,
        limitations=LIMITATIONS,
        raw_text=lab.text,
        avg_ocr_confidence=lab.avg_conf if from_ocr else None,
        original_text=lab.original_text,
        classification=cls.as_dict(),
        product_info=product_info,
        legal_questions=[{"id": k, "question": v} for k, v in ctx.questions.items()],
        ocr=ocr_meta,
    )


def analyze_text(text: str, category: str = "other", pack_type: Optional[str] = None) -> ScanResult:
    return analyze(LabelText.from_text(text).lines, category, pack_type, from_ocr=False)
