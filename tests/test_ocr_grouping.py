from app.ocr import group_rows


def box(x, y, w=80, h=20):
    return [[x, y], [x + w, y], [x + w, y + h], [x, y + h]]


def test_boxes_on_same_row_are_merged_left_to_right():
    results = [
        (box(200, 102), "100g", 0.9),
        (box(10, 100), "Net Wt.", 0.8),
        (box(10, 160), "MRP Rs. 45", 0.7),
    ]
    lines = group_rows(results)
    assert [l.text for l in lines] == ["Net Wt. 100g", "MRP Rs. 45"]
    assert lines[0].conf == 0.85


def test_empty_text_is_dropped():
    assert group_rows([(box(0, 0), "  ", 0.9)]) == []
