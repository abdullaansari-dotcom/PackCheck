"""Primary regression sample: the Bhaskar Book Tech notebook label (tests/fixtures/bhaskar_label.jpg).

Three independent inputs are checked, so a fix cannot hide behind one lucky reading:

1. ``bhaskar_easyocr_screenshot.txt`` - the corrupted text the ORIGINAL app produced
   (EasyOCR en+hi, rows merged across columns, Devanagari digits).
2. ``bhaskar_tesseract_tokens.json`` - REAL word boxes from a different OCR engine on the
   preprocessed photo (noisy: missing words, junk boxes, '7' for the rupee sign).
3. ``bhaskar_synthetic_phrase_boxes.json`` - phrase boxes placed on the photo with the
   English/Devanagari model readings, run through arbitration + layout + rules.

No value from this label is hard-coded in app/: these tests only assert outcomes.
"""
import json
from pathlib import Path

import pytest

from app.engine import analyze
from app.extract import Line
from app.layout import Separator, tokens_from_dicts
from app.ocr import arbitrate
from app.pipeline import analyze_tokens

FIX = Path(__file__).parent / "fixtures"


def f(r, name):
    return next(x for x in r.fields if x.field == name)


def from_tokens(name, category="auto", with_image=True):
    d = json.loads((FIX / name).read_text(encoding="utf-8"))
    toks = [t for t in tokens_from_dicts(d["tokens"]) if t.conf >= 0.3]
    for t in toks:
        if t.alt_text:
            t.text, t.conf, t.engine, t.note = arbitrate(t.text, t.conf, t.alt_text, t.alt_conf)
    gray = None
    if with_image:
        cv2 = pytest.importorskip("cv2")
        from app.preprocess import preprocess_with_report
        _, rep = preprocess_with_report(cv2.imread(str(FIX / "bhaskar_label.jpg")), max_side=2560)
        gray = rep.raw_gray
    return analyze_tokens(toks, [Separator(**s) for s in d["separators"]], category, gray=gray,
                          image_size=tuple(d["image_size"]))


def from_screenshot(category="auto"):
    text = (FIX / "bhaskar_easyocr_screenshot.txt").read_text(encoding="utf-8")
    return analyze([Line(t, 0.57) for t in text.splitlines()], category, from_ocr=True)


ALL = [lambda: from_tokens("bhaskar_synthetic_phrase_boxes.json"), lambda: from_tokens("bhaskar_tesseract_tokens.json"),
       lambda: from_screenshot()]
IDS = ["synthetic_boxes", "real_tesseract_boxes", "original_app_screenshot_text"]


@pytest.fixture(params=range(3), ids=IDS)
def result(request):
    return ALL[request.param]()


# ---------------------------------------------------------------- the reported bugs
def test_mrp_is_found_not_missing(result):
    m = f(result, "mrp")
    assert m.violation_code != "MISSING"
    assert "60.00" in m.detected_text


def test_mrp_associated_with_incl_of_taxes(result):
    m = f(result, "mrp")
    assert any(e.label == "Tax wording" and "Taxes" in e.text for e in m.evidence)
    assert m.sub_case == "TAX_PHRASE_WITHOUT_ALL" and m.status == "REVIEW"  # policy: legal team to decide
    assert m.legal_question


def test_end_sheets_wording_is_not_mistaken_for_tax_wording(result):
    m = f(result, "mrp")
    assert not any("sheets" in e.text for e in m.evidence if e.label == "Tax wording")


def test_manufacturer_is_not_reported_missing(result):
    m = f(result, "manufacturer")
    assert m.violation_code != "MISSING"
    assert m.status == "REVIEW"
    assert any("562112" in e.text for e in m.evidence)


def test_page_count_is_not_net_quantity(result):
    n = f(result, "net_quantity")
    assert n.status == "REVIEW" and n.sub_case == "PAGE_COUNT_ONLY"
    assert n.violation_code != "MISSING"
    assert "page_count" in result.product_info


def test_mfg_date_genuinely_absent_is_still_reported(result):
    # a photo can miss text, so "not found" is a question for a person, not an automatic FAIL
    assert f(result, "mfg_date").status == "REVIEW" and f(result, "mfg_date").sub_case == "NOT_FOUND_IN_PHOTO"


def test_consumer_care_phone(result):
    c = f(result, "consumer_care")
    assert c.status == "PASS" and "080-29761413" in c.detected_text


def test_notebook_is_recognised_and_still_checked(result):
    assert result.category == "notebook"
    assert f(result, "numeral_height").status == "SKIPPED_BY_TEAM_DECISION"
    assert "Table II" in f(result, "numeral_height").detail
    assert f(result, "pack_size").status == "NOT_CONFIGURED"  # no tea/biscuit table applied
    assert f(result, "dimensions").status == "NOT_CONFIGURED"
    assert f(result, "language").status == "PASS"
    assert f(result, "clear_space").status in ("REVIEW", "NOT_APPLICABLE")
    assert result.verdict == "NEEDS_REVIEW"


# ---------------------------------------------------------------- per-input details
def test_screenshot_text_flags_devanagari_digits_as_uncertain():
    r = from_screenshot()
    m = f(r, "mrp")
    assert m.original_text == "MRP: ₹ ६0.0०" and m.normalized_text == "MRP: ₹ 60.00"
    assert any(n["uncertain"] for e in m.evidence for n in e.normalizations)
    assert "२" in r.original_text and "२" not in r.raw_text


def test_synthetic_boxes_full_extraction():
    r = from_tokens("bhaskar_synthetic_phrase_boxes.json")
    pi = r.product_info
    assert pi["business_name"]["text"] == "BHASKAR BOOK TECH"
    assert pi["business_name"]["legal_role"] == "not stated"
    assert pi["address"]["pin"] == "562112"
    assert "Plot No. 267/16A-267/16B" in pi["address"]["text"] and "Harohalli" in pi["address"]["text"]
    assert "Pages" not in pi["address"]["text"] and "MRP" not in pi["address"]["text"]
    assert pi["contacts"]["emails"] == ["bhaskarbook@yahoo.in"]
    assert pi["printed_size"]["parsed"] == "30 × 18 cm"
    assert pi["page_count"]["value"] == 140
    assert f(r, "manufacturer").sub_case == "ROLE_NOT_STATED"
    assert f(r, "contrast").status == "PASS"
    assert f(r, "legibility").status == "PASS"
    # the arbitration kept the English digits (140), not the Devanagari model's 240
    assert "140 Pages" in r.raw_text and "240" not in r.raw_text


def test_ocr_regions_are_reported():
    r = from_tokens("bhaskar_synthetic_phrase_boxes.json")
    regions = r.ocr["regions"]
    price = next(g for g in regions if "MRP" in g["text"])
    addr = next(g for g in regions if "Industrial" in g["text"])
    assert price["block"] != addr["block"] and price["column"] != addr["column"]
    assert all(g["bbox"] for g in regions)


def test_explicit_notebook_category_matches_auto():
    a = from_tokens("bhaskar_synthetic_phrase_boxes.json", "auto")
    b = from_tokens("bhaskar_synthetic_phrase_boxes.json", "notebook")
    assert [(x.field, x.status) for x in a.fields] == [(x.field, x.status) for x in b.fields]
    assert b.classification["source"] == "user"


def test_legal_questions_are_listed():
    ids = {q["id"] for q in from_tokens("bhaskar_synthetic_phrase_boxes.json").legal_questions}
    assert {"MANUFACTURER_ROLE_NOT_STATED", "PAGE_COUNT_AS_NET_QUANTITY", "STATIONERY_DIMENSIONS",
            "TAX_PHRASE_WITHOUT_ALL"} <= ids
