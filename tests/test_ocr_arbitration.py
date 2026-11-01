"""Stage test: English-primary / Devanagari-secondary arbitration (no EasyOCR needed)."""
from app.ocr import arbitrate


def test_english_reading_wins_for_digits():
    text, conf, engine, _ = arbitrate("140 Pages", 0.9, "२४० Pages", 0.7)
    assert (text, engine) == ("140 Pages", "easyocr-en")  # the Hindi model turned 140 into 240


def test_rupee_restored_only_when_both_models_agree_on_the_amount():
    assert arbitrate("MRP: 7 60.00", 0.86, "MRP: ₹ ६0.0०", 0.52)[0] == "MRP: ₹ 60.00"
    assert arbitrate("MRP: Z60.00", 0.8, "MRP: ₹६०.००", 0.6)[0] == "MRP: ₹60.00"
    assert arbitrate("MRP: 760.00", 0.8, "MRP: ₹७६०", 0.6)[0] == "MRP: 760.00"  # amounts disagree: untouched


def test_hindi_text_uses_hindi_reading():
    text, _, engine, note = arbitrate("Hct OaR", 0.3, "शुद्ध घी", 0.7)
    assert text == "शुद्ध घी" and engine == "easyocr-hi" and note


def test_no_secondary_reading():
    assert arbitrate("Net Wt. 100 g", 0.9, None, None)[:3] == ("Net Wt. 100 g", 0.9, "easyocr-en")


# ---------------------------------------------------------------- read_tokens wiring with a stand-in reader
import numpy as np  # noqa: E402

import app.ocr as ocr  # noqa: E402


class FakeReader:
    """Mimics easyocr.Reader.detect / recognize (same return shapes). Returns boxes in a different order
    from the detector on purpose: readings must be matched by box, not by position in the list."""

    def __init__(self, kind, fail=False):
        self.kind, self.fail = kind, fail

    def detect(self, img, **kw):
        return [[[0, 200, 0, 30], [300, 500, 0, 30]]], [[]]

    def recognize(self, img, horizontal_list, free_list, **kw):
        if self.fail:
            raise RuntimeError("model crashed")
        out = []
        for x0, x1, y0, y1 in reversed(horizontal_list):
            box = [[x0, y0], [x1, y0], [x1, y1], [x0, y1]]
            if self.kind == "primary":
                out.append((box, "140 Pages" if x0 == 0 else "MRP: 7 60.00", 0.9))
            else:
                out.append((box, "२४० Pages" if x0 == 0 else "MRP: ₹ ६0.0०", 0.6))
        return out


def test_read_tokens_matches_secondary_by_box(monkeypatch):
    monkeypatch.setattr(ocr, "_readers", {"primary": FakeReader("primary"), "secondary": FakeReader("secondary")})
    monkeypatch.setattr(ocr, "secondary_enabled", lambda: True)
    res = ocr.read_tokens(np.full((40, 600), 255, np.uint8))
    texts = {t.text: t for t in res.tokens}
    assert "140 Pages" in texts and texts["140 Pages"].alt_text == "२४० Pages"
    assert "MRP: ₹ 60.00" in texts and texts["MRP: ₹ 60.00"].note
    assert all(t.bbox for t in res.tokens)


def test_secondary_failure_does_not_break_the_scan(monkeypatch):
    monkeypatch.setattr(ocr, "_readers", {"primary": FakeReader("primary"), "secondary": FakeReader("s", fail=True)})
    monkeypatch.setattr(ocr, "secondary_enabled", lambda: True)
    res = ocr.read_tokens(np.full((40, 600), 255, np.uint8))
    assert {t.text for t in res.tokens} == {"140 Pages", "MRP: 7 60.00"}


def test_full_image_pipeline_wiring_with_stand_in_reader(monkeypatch):
    """Real photo through decode -> preprocess -> separators -> OCR (stand-in) -> layout -> rules."""
    from pathlib import Path

    from app.pipeline import NoTextFound, scan_image_bytes

    monkeypatch.setattr(ocr, "_readers", {"primary": FakeReader("primary"), "secondary": FakeReader("secondary")})
    monkeypatch.setattr(ocr, "secondary_enabled", lambda: True)
    data = (Path(__file__).parent / "fixtures" / "bhaskar_label.jpg").read_bytes()
    r = scan_image_bytes(data, "auto", reader="ocr")
    assert r.input_mode == "image" and r.ocr["preprocess"]["scale"] > 1
    assert r.ocr["separators"] and r.ocr["regions"]
    assert {f.field for f in r.fields} >= {"numeral_height", "clear_space", "contrast"}

    class Empty(FakeReader):
        def detect(self, img, **kw):
            return [[]], [[]]
    monkeypatch.setattr(ocr, "_readers", {"primary": Empty("primary"), "secondary": Empty("secondary")})
    import pytest
    with pytest.raises(NoTextFound):
        scan_image_bytes(data, "auto", reader="ocr")
