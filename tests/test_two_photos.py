"""Front + back: two photos checked together as one label (no EasyOCR or network needed)."""
import json

import cv2
import numpy as np
import pytest

from app import config, pipeline, vision
from app.layout import Token, build_lines
from app.ocr import OcrResult

FRONT_SIZE = (600, 800)  # (w, h)
BACK_SIZE = (640, 700)


def png(size, shade):
    w, h = size
    ok, buf = cv2.imencode(".png", np.full((h, w, 3), shade, np.uint8))
    assert ok
    return buf.tobytes()


FRONT, BACK = png(FRONT_SIZE, 250), png(BACK_SIZE, 240)


def tok(text, x, y, w=300, h=30):
    return Token(text, 0.95, (x, y, x + w, y + h), "fake-ocr")


FRONT_TOKENS = [tok("ALOO BHUJIA SEV", 100, 100, 400, 50), tok("Net Wt. 200 g", 100, 400, 220, 36)]
BACK_TOKENS = [
    tok("Mfd. by: Haldiram Snacks Food Pvt Ltd, Plot 12, MIDC Hingna, Nagpur - 440016", 40, 60, 560),
    tok("MRP Rs. 60.00 (Incl. of all taxes)", 40, 200, 380),
    tok("MFG DATE 10.09.26", 40, 260, 260),
    tok("Consumer care: 1800 123 4567  care@haldiram.example", 40, 320, 500),
    tok("Net Wt. 200 g", 40, 600, 220, 36),
]


def fake_ocr(monkeypatch, tokens_by_width, fail_on=()):
    def run(img, lean=False):
        h, w = img.shape[:2]
        if w in fail_on:
            res = OcrResult([], [], [], (w, h), "gray_enhanced", ["fake-ocr"], [])
        else:
            toks = tokens_by_width[w]
            res = OcrResult(toks, build_lines(toks, []), [], (w, h), "gray_enhanced", ["fake-ocr"], [])
        return res, [], cv2.cvtColor(img, cv2.COLOR_BGR2GRAY), {"variant": "gray_enhanced"}

    monkeypatch.setattr(pipeline, "_run_ocr", run)


@pytest.fixture
def ocr(monkeypatch):
    fake_ocr(monkeypatch, {FRONT_SIZE[0]: FRONT_TOKENS, BACK_SIZE[0]: BACK_TOKENS})


def field(r, name):
    return next(x for x in r.fields if x.field == name)


def test_front_alone_misses_what_the_back_carries(ocr):
    r = pipeline.scan_images_bytes([FRONT], "other", reader="ocr")
    assert field(r, "mrp").status == "REVIEW" and field(r, "mrp").sub_case == "NOT_FOUND_IN_PHOTO"
    assert r.ocr.get("images") is None  # single photo: nothing changes


def test_front_and_back_are_checked_as_one_label(ocr):
    r = pipeline.scan_images_bytes([FRONT, BACK], "other", reader="ocr")
    assert field(r, "mrp").violation_code != "MISSING" and "60" in (field(r, "mrp").detected_text or "")
    assert field(r, "consumer_care").status == "PASS"
    assert [i["label"] for i in r.ocr["images"]] == ["Front", "Back"]
    assert "ALOO BHUJIA SEV" in r.raw_text and "MRP" in r.raw_text


def test_evidence_says_which_photo_it_came_from(ocr):
    r = pipeline.scan_images_bytes([FRONT, BACK], "other", reader="ocr")
    assert {e.image for e in field(r, "mrp").evidence} == {1}
    regions = r.ocr["regions"]
    assert {g["image"] for g in regions} == {0, 1}
    assert next(g for g in regions if "ALOO" in g["text"])["image"] == 0


def test_clear_space_is_measured_on_one_photo_only(monkeypatch):
    # The back photo's text sits just "below" the front in the shared space; it must not count as crowding.
    fake_ocr(monkeypatch, {FRONT_SIZE[0]: FRONT_TOKENS, BACK_SIZE[0]: [t for t in BACK_TOKENS if "Net" not in t.text]})
    r = pipeline.scan_images_bytes([FRONT, BACK], "other", reader="ocr")
    cs = field(r, "clear_space")
    assert "front photo" in (cs.detail or "")
    assert "MRP" not in (cs.detail or "") and "Consumer" not in (cs.detail or "")
    assert cs.status in ("PASS", "REVIEW")


def test_unreadable_back_is_reported_but_front_still_checked(monkeypatch):
    fake_ocr(monkeypatch, {FRONT_SIZE[0]: FRONT_TOKENS}, fail_on=(BACK_SIZE[0],))
    r = pipeline.scan_images_bytes([FRONT, BACK], "other", reader="ocr")
    assert any("back photo" in n for n in r.ocr["notes"])
    assert [i["label"] for i in r.ocr["images"]] == ["Front"]


def test_nothing_readable_anywhere_raises(monkeypatch):
    fake_ocr(monkeypatch, {}, fail_on=(FRONT_SIZE[0], BACK_SIZE[0]))
    with pytest.raises(pipeline.NoTextFound):
        pipeline.scan_images_bytes([FRONT, BACK], "other", reader="ocr")


def test_more_than_two_photos_rejected():
    with pytest.raises(ValueError):
        pipeline.scan_images_bytes([FRONT, BACK, FRONT], "other", reader="ocr")


def test_bad_back_photo_names_the_photo():
    with pytest.raises(ValueError, match="Back photo"):
        pipeline.scan_images_bytes([FRONT, b"not an image"], "other", reader="ocr")


# ------------------------------------------------------------------ with the AI reader
FRONT_AI = {"lines": [{"text": "ALOO BHUJIA SEV", "region": "title", "lang": "en"},
                      {"text": "Net Wt. 200 g", "region": "front", "lang": "en"}],
            "category": "packaged_food", "category_confidence": 0.4, "category_reason": "front pack", "pack_type": None,
            "legible": True, "issues": ["glare top right"], "notes": []}
BACK_AI = {"lines": [{"text": "MRP Rs. 60.00 (Incl. of all taxes)", "region": "price", "lang": "en"},
                     {"text": "MFG DATE 10.09.26", "region": "price", "lang": "en"},
                     {"text": "Consumer care: 1800 123 4567  care@haldiram.example", "region": "care", "lang": "en"}],
           "category": "packaged_food", "category_confidence": 0.8, "category_reason": "snack back panel", "pack_type": None,
           "legible": True, "issues": [], "notes": []}


@pytest.fixture
def ai(monkeypatch):
    monkeypatch.setattr(config, "ANTHROPIC_API_KEY", "sk-test")
    monkeypatch.setattr(config, "GEMINI_API_KEY", "")
    monkeypatch.setattr(config, "VISION_PROVIDER", "")
    monkeypatch.setattr(config, "VISION_MODEL", "")

    def read_label(img):
        payload = BACK_AI if img.shape[1] == BACK_SIZE[0] else FRONT_AI
        return vision.parse_reading(json.dumps(payload), "anthropic", "claude-test")

    monkeypatch.setattr(vision, "read_label", read_label)


def test_hybrid_two_photos_merges_ai_summary(ai, monkeypatch):
    fake_ocr(monkeypatch, {FRONT_SIZE[0]: FRONT_TOKENS, BACK_SIZE[0]: BACK_TOKENS})
    r = pipeline.scan_images_bytes([FRONT, BACK], "auto", reader="hybrid")
    a = r.ocr["ai"]
    assert a["line_count"] == 5 and {l["image"] for l in a["lines"]} == {0, 1}
    assert a["category_confidence"] == 0.8 and any("Front: glare" in i for i in a["issues"])
    assert field(r, "mrp").violation_code != "MISSING"
    assert {e.image for e in field(r, "mrp").evidence} == {1}
    assert r.category == "packaged_food"
    assert field(r, "net_quantity").evidence[0].image == 0


def test_ai_only_two_photos(ai):
    r = pipeline.scan_images_bytes([FRONT, BACK], "auto", reader="ai")
    assert field(r, "mrp").violation_code != "MISSING"
    assert field(r, "consumer_care").status == "PASS"
    assert field(r, "clear_space").status in ("NOT_APPLICABLE", "REVIEW")


def test_ai_failure_on_one_photo_falls_back_to_ocr_for_that_photo(ai, monkeypatch):
    fake_ocr(monkeypatch, {FRONT_SIZE[0]: FRONT_TOKENS, BACK_SIZE[0]: BACK_TOKENS})
    good = vision.read_label

    def flaky(img):
        if img.shape[1] == BACK_SIZE[0]:
            raise vision.VisionError("The AI service timed out")
        return good(img)

    monkeypatch.setattr(vision, "read_label", flaky)
    r = pipeline.scan_images_bytes([FRONT, BACK], "auto", reader="hybrid")
    assert r.ocr["reader"]["fallback"] == "ocr"
    assert any(n.startswith("Back: The AI reader was unavailable") for n in r.ocr["notes"])
    assert field(r, "mrp").violation_code != "MISSING"  # the back photo still came in through OCR
