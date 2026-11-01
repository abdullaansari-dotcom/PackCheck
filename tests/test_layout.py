"""Stage test: layout analysis (boxes preserved, columns separated, reading order)."""
import json
from pathlib import Path

from app.layout import Separator, Token, build_lines, tokens_from_dicts

FIX = Path(__file__).parent / "fixtures"


def tok(text, x0, y0, x1, y1, conf=0.9):
    return Token(text, conf, (x0, y0, x1, y1))


def load(name):
    d = json.loads((FIX / name).read_text(encoding="utf-8"))
    return d, [t for t in tokens_from_dicts(d["tokens"]) if t.conf >= 0.3], [Separator(**s) for s in d["separators"]]


def test_three_columns_are_not_merged_into_rows():
    toks = [
        tok("ADDRESS LINE ONE", 0, 0, 400, 20), tok("ADDRESS LINE TWO", 0, 28, 400, 48), tok("PIN 562112", 0, 56, 200, 76),
        tok("MRP Rs 60.00", 500, 2, 700, 22), tok("(Incl. of all Taxes)", 500, 30, 700, 50), tok("Size 30x18 cm", 500, 58, 700, 78),
    ]
    lines = build_lines(toks)
    texts = [l.text for l in lines]
    assert "ADDRESS LINE ONE" in texts and "MRP Rs 60.00" in texts
    assert not any("ADDRESS" in t and "MRP" in t for t in texts)
    # reading order: whole left column, then right column
    assert texts.index("PIN 562112") < texts.index("MRP Rs 60.00")
    cols = {l.text: l.column for l in lines}
    assert cols["ADDRESS LINE ONE"] == cols["PIN 562112"] != cols["MRP Rs 60.00"]


def test_label_and_value_on_one_row_stay_together():
    lines = build_lines([tok("Net Wt.", 10, 100, 90, 120), tok("100g", 200, 102, 280, 122)])
    assert [l.text for l in lines] == ["Net Wt. 100g"]


def test_printed_separator_splits_even_a_single_row():
    toks = [tok("Harohalli - 562112,", 0, 0, 300, 20), tok("(Inclusive of both end sheets)", 330, 0, 700, 20)]
    assert len(build_lines(toks, [Separator(315, -20, 60)])) == 2
    assert len(build_lines(toks)) == 1


def test_bounding_boxes_and_tokens_preserved():
    lines = build_lines([tok("Net Wt.", 10, 100, 90, 120), tok("100g", 200, 102, 280, 122)])
    assert lines[0].bbox == (10, 100, 280, 122)
    assert [t.text for t in lines[0].tokens] == ["Net Wt.", "100g"]


def test_real_tesseract_boxes_from_bhaskar_photo_separate_columns():
    _, toks, seps = load("bhaskar_tesseract_tokens.json")
    for use_seps in (seps, []):
        lines = build_lines(toks, use_seps)
        texts = [l.text for l in lines]
        price = next(l for l in lines if "MRP" in l.text)
        assert "Pages" in price.text and "Industrial" not in price.text and "Road" not in price.text
        addr = next(l for l in lines if "Industrial" in l.text)
        assert addr.block != price.block
        assert "(Incl. of Taxes)" in texts
        # the tax line sits in the same region as the price
        assert next(l for l in lines if l.text == "(Incl. of Taxes)").block == price.block


def test_separator_lines_detected_in_fixture_match_label_rules():
    d, _, seps = load("bhaskar_tesseract_tokens.json")
    xs = sorted(s.x for s in seps)
    # the two printed vertical rules on the label (between address|price and price|barcode)
    assert any(1700 < x < 1790 for x in xs) and any(2320 < x < 2420 for x in xs)
