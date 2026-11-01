"""End-to-end: real photo -> preprocessing -> EasyOCR -> layout -> rules.

Requires EasyOCR (and its model download on first run). Skipped automatically when EasyOCR is
not installed. Run it on a developer machine after ``pip install -r requirements.txt``:

    pytest tests/test_pipeline_image.py -v
"""
from pathlib import Path

import pytest

pytest.importorskip("easyocr")

from app.pipeline import scan_image_bytes  # noqa: E402

LABEL = Path(__file__).parent / "fixtures" / "bhaskar_label.jpg"


@pytest.fixture(scope="module")
def result():
    return scan_image_bytes(LABEL.read_bytes(), "auto")


def f(r, name):
    return next(x for x in r.fields if x.field == name)


def test_no_devanagari_digits_in_english_label(result):
    assert not any("०" <= ch <= "९" for ch in result.raw_text)


def test_columns_are_separate_regions(result):
    regions = result.ocr["regions"]
    price = [g for g in regions if "MRP" in g["text"]]
    assert price and not any("Industrial" in g["text"] for g in price)


def test_key_declarations_found(result):
    assert f(result, "mrp").violation_code != "MISSING"
    assert "60" in (f(result, "mrp").detected_text or "")
    assert f(result, "consumer_care").status == "PASS"
    assert f(result, "manufacturer").violation_code != "MISSING"
    assert f(result, "net_quantity").sub_case == "PAGE_COUNT_ONLY"
    assert result.product_info.get("page_count", {}).get("value") == 140


def test_category_and_rule7(result):
    assert result.category == "notebook"
    assert f(result, "numeral_height").status == "SKIPPED_BY_TEAM_DECISION"
