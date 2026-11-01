"""Stage test: text normalization (original kept, contextual, length-preserving, uncertainty flagged)."""
import pytest

from app.extract import LabelText, find_mrp
from app.normalize import normalize_line


def norm(t):
    return normalize_line(t).normalized


def test_devanagari_digits_in_english_text_are_normalized_and_flagged():
    r = normalize_line("Plot No. २६७/१६A २६७/१६B")
    assert r.normalized == "Plot No. 267/16A 267/16B"
    assert r.original == "Plot No. २६७/१६A २६७/१६B"  # original preserved
    assert all(c.uncertain for c in r.changes if c.kind.startswith("devanagari"))


def test_devanagari_numerals_in_hindi_text_keep_value_without_uncertainty():
    r = normalize_line("अधिकतम खुदरा मूल्य ₹ ६०.००")
    assert r.normalized.endswith("₹ 60.00")
    assert r.changes and not any(c.uncertain for c in r.changes)


def test_length_preserving_so_offsets_map_back_to_original():
    for t in ["MRP: ₹ ६0.0०", "Size ३Ox18Cms", "Net Wt 1OOg", "MRP: 7 60.00"]:
        assert len(norm(t)) == len(t)


@pytest.mark.parametrize("raw,expected", [
    ("MRP: ₹ ६0.0०", "MRP: ₹ 60.00"),
    ("२४० Pages", "240 Pages"),  # value-preserving only: see the uncertainty test below
    ("२nd Road, २nd Phase", "2nd Road, 2nd Phase"),
    ("Size ३Ox18Cms", "Size 30x18Cms"),
    ("6O.OO", "60.00"),
    ("Net Wt 1OOg", "Net Wt 100g"),
    ("Help line : 080-29761413", "Help line : 080-29761413"),
    ("Harohalli - 562112,", "Harohalli - 562112,"),
])
def test_numeral_normalization(raw, expected):
    assert norm(raw) == expected


def test_no_blind_letter_substitution():
    assert norm("No. 10 Oct, Industrial Area") == "No. 10 Oct, Industrial Area"  # 'O' in words untouched
    assert norm("Plot No. 1") == "Plot No. 1"
    assert norm("Inclusive of all taxes") == "Inclusive of all taxes"  # 'I' / 'l' in words untouched


@pytest.mark.parametrize("raw,expected", [
    ("MRP: 7 60.00", "MRP: ₹ 60.00"),  # Tesseract's real reading of the Bhaskar label
    ("MRP: Z60.00", "MRP: ₹60.00"),
    ("Price: F 45/-", "Price: ₹ 45/-"),
    ("MRP: Rs 45", "MRP: Rs 45"),  # a real abbreviation is left alone
    ("MRP 760.00", "MRP 760.00"),  # glued digit could be real: never guessed
])
def test_rupee_glyph_confusion_only_in_price_context(raw, expected):
    assert norm(raw) == expected


def test_decimal_point_preserved_and_amount_parsed():
    m = find_mrp(LabelText.from_text("MRP: ₹ ६0.0०\n(Incl. of all Taxes)"))
    assert m.found and m.amount == 60.0
    assert m.hit.original == "MRP: ₹ ६0.0०" and m.hit.text == "MRP: ₹ 60.00"
    assert m.hit.uncertain  # value came from Devanagari digits in English text


def test_rupee_variants_recognised():
    for t in ["MRP: ₹60.00", "M.R.P. Rs. 60/-", "Maximum Retail Price ₹60", "Retail Price: Rs. 60.00", "MRP INR 60",
              "MRP: ₹ 60 . 00"]:
        m = find_mrp(LabelText.from_text(t))
        assert m.found and m.amount == 60.0, t
