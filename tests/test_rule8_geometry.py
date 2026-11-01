"""Rule 8 (clear space around the net quantity) is evaluated independently of Rule 7."""
import numpy as np
import pytest

cv2 = pytest.importorskip("cv2")

from app.engine import analyze
from app.geometry import assess_clear_space, text_contrast
from app.layout import Token, build_lines

W, H = 1600, 900


def draw(items):
    img = np.full((H, W), 245, np.uint8)
    toks = []
    for text, x, y, scale in items:
        (tw, th), base = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, scale, 2)
        cv2.putText(img, text, (x, y), cv2.FONT_HERSHEY_SIMPLEX, scale, 20, 2)
        toks.append(Token(text, 0.95, (x - 4, y - th - 4, x + tw + 4, y + base + 4)))
    return img, toks


BASE = [("Crunchy Cream Biscuits", 100, 120, 1.4), ("MRP Rs 30.00 inclusive of all taxes", 100, 820, 0.9),
        ("Mfg: 03/2026", 1100, 820, 0.9)]


def run(items):
    img, toks = draw(items)
    lines = build_lines(toks)
    return analyze(lines, "biscuits", from_ocr=True, gray=img, image_size=(W, H))


def field(r, name):
    return next(f for f in r.fields if f.field == name)


def test_isolated_net_quantity_passes_rule8_while_rule7_is_skipped():
    r = run(BASE + [("Net Wt. 150 g", 600, 450, 1.6)])
    assert field(r, "clear_space").status == "PASS"
    assert field(r, "clear_space").sub_case == "ESTIMATED_FROM_PHOTO"
    assert field(r, "numeral_height").status == "SKIPPED_BY_TEAM_DECISION"


def test_crowded_net_quantity_goes_to_review_never_auto_fail():
    r = run(BASE + [("Net Wt. 150 g", 600, 450, 1.6), ("Best before 6 months", 600, 490, 0.7)])
    cs = field(r, "clear_space")
    assert cs.status == "REVIEW" and cs.sub_case == "POSSIBLE_CROWDING"
    assert "below" in cs.detail


def test_fine_print_not_detected_by_ocr_is_still_noticed_from_pixels():
    img, toks = draw(BASE + [("Net Wt. 150 g", 600, 450, 1.6)])
    cv2.putText(img, "tiny print", (600, 485), cv2.FONT_HERSHEY_SIMPLEX, 0.6, 20, 1)  # no OCR token for it
    r = analyze(build_lines(toks), "biscuits", from_ocr=True, gray=img, image_size=(W, H))
    assert field(r, "clear_space").status == "REVIEW"


def test_zone_off_the_photo_edge_is_not_verifiable():
    res = assess_clear_space((0, 400, 300, 450), [], (W, H), None)
    assert res.status == "REVIEW"


def test_rule8_not_assessable_from_text_input():
    from app.engine import analyze_text
    r = analyze_text("Biscuits\nNet Wt. 150 g\nMRP Rs 30 incl. of all taxes", "biscuits")
    assert field(r, "clear_space").status == "NOT_APPLICABLE"
    assert field(r, "numeral_height").status == "SKIPPED_BY_TEAM_DECISION"


def test_contrast_measurement():
    img = np.full((100, 300), 240, np.uint8)
    cv2.putText(img, "MRP 30", (10, 70), cv2.FONT_HERSHEY_SIMPLEX, 1.5, 20, 3)
    assert text_contrast(img, (0, 0, 300, 100)) > 0.6
    faint = np.full((100, 300), 240, np.uint8)
    cv2.putText(faint, "MRP 30", (10, 70), cv2.FONT_HERSHEY_SIMPLEX, 1.5, 215, 3)
    assert text_contrast(faint, (0, 0, 300, 100)) < 0.25
