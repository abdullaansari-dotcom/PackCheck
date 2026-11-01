"""Compliance logic: rule applicability per category, status vocabulary, Rule 5/6/7/8/9/26."""
import pytest

from app.data import CATEGORY_INFO, STATIONERY_CATEGORIES
from app.engine import analyze, analyze_text
from app.extract import LabelText, Line, find_contacts, find_net_quantity
from app.models import STATUSES
from app.rules import FIELD_ORDER


def f(r, name):
    return next(x for x in r.fields if x.field == name)


# fictional labels
NOTEBOOK = ("Kalpa Stationers\nLong Notebook - Single Line\n172 Pages\nNet Qty: 1 N\nMRP Rs. 60.00 (Inclusive of all taxes)\n"
            "Mfd: 03/2026\nManufactured by: Kalpa Paper Works, Plot 9, Industrial Area, Hubballi - 580030\n"
            "Customer care: 1800 425 1111")
TEA = ("Hillgrove Assam Tea\nNet Wt. 250 g\nMRP Rs 140 Incl. of all taxes\nPkd: Jan 2026\n"
       "Packed by: Hillgrove Tea Co., Plot 4, Industrial Estate, Guwahati - 781001\ncare@hillgrove.in")
BEDSHEET = ("Cotton Bedsheet\nNet Qty: 1 N\nSize: 228 cm x 254 cm\nMRP Rs 899 inclusive of all taxes\nMfd: 02/2026\n"
            "Manufactured by: Loomcraft, 12 Mill Road, Panipat - 132103\nCall 1800 200 3000")


# ---------------------------------------------------------------- statuses
def test_every_field_present_with_rule_reference_and_known_status():
    r = analyze_text(NOTEBOOK, "auto")
    assert [x.field for x in r.fields] == FIELD_ORDER
    for x in r.fields:
        assert x.rule_reference.startswith("Rule") and x.status in STATUSES
        if x.status in ("FAIL", "REVIEW"):
            assert x.rule_reference and (x.detail or x.evidence)
    assert set(r.summary) == set(STATUSES)


# ---------------------------------------------------------------- notebook
def test_notebook_category_full_check():
    r = analyze_text(NOTEBOOK, "auto")
    assert r.category == "notebook" and r.verdict == "COMPLIANT"
    for name in ("manufacturer", "generic_name", "net_quantity", "mfg_date", "mrp", "consumer_care", "language"):
        assert f(r, name).status == "PASS", name
    assert f(r, "pack_size").status == "NOT_CONFIGURED"  # no unrelated tea/biscuit table
    assert f(r, "numeral_height").status == "SKIPPED_BY_TEAM_DECISION"
    assert f(r, "dimensions").status == "NOT_CONFIGURED"
    assert f(r, "clear_space").status == "NOT_APPLICABLE"  # text input; with a photo it is measured


def test_stationery_categories_are_not_excluded():
    for cat in STATIONERY_CATEGORIES:
        r = analyze_text(NOTEBOOK, cat)
        assert r.verdict != "EXEMPT" and not any(x.status == "EXEMPT" for x in r.fields), cat
        assert f(r, "numeral_height").status == "SKIPPED_BY_TEAM_DECISION"
        assert CATEGORY_INFO[cat]["rule7_table"] == "II"


def test_notebook_missing_net_quantity_with_page_count_goes_to_review():
    r = analyze_text(NOTEBOOK.replace("Net Qty: 1 N\n", ""), "notebook")
    assert f(r, "net_quantity").sub_case == "PAGE_COUNT_ONLY"
    q = find_net_quantity(LabelText.from_text("172 Pages"))
    assert q.kind == "none"  # pages never become a quantity


def test_count_declarations_for_countable_goods():
    for t in ["10 notebooks", "Net Qty: 1 N", "Contains 12 biscuits", "Pack of 5 pcs"]:
        q = find_net_quantity(LabelText.from_text(t))
        assert q.kind == "count", t


# ---------------------------------------------------------------- tea
def test_tea_standard_sizes_applied():
    r = analyze_text(TEA, "auto")
    assert r.category == "tea" and r.verdict == "COMPLIANT"
    assert f(r, "pack_size").status == "PASS"
    assert f(r, "numeral_height").status == "SKIPPED_BY_TEAM_DECISION"
    assert "Table I" in f(r, "numeral_height").detail
    bad = analyze_text(TEA.replace("250 g", "120 g"), "tea")
    assert f(bad, "pack_size").violation_code == "NONSTANDARD_PACK"


def test_tea_sizes_never_applied_to_notebook():
    r = analyze_text(NOTEBOOK.replace("Net Qty: 1 N", "Net Wt. 120 g"), "notebook")
    assert f(r, "pack_size").status == "NOT_CONFIGURED"


# ---------------------------------------------------------------- bedsheet
def test_bedsheet_dimensions_required():
    r = analyze_text(BEDSHEET, "auto")
    assert r.category == "bedsheet" and f(r, "dimensions").status == "PASS"
    r2 = analyze_text(BEDSHEET.replace("Size: 228 cm x 254 cm\n", ""), "bedsheet")
    assert f(r2, "dimensions").violation_code == "MISSING"
    assert f(r2, "numeral_height").status == "SKIPPED_BY_TEAM_DECISION"
    assert f(r2, "pack_size").status == "NOT_CONFIGURED"


# ---------------------------------------------------------------- unknown category
def test_unknown_category_is_checked_not_bypassed():
    r = analyze_text("Zorbo\nNet Wt. 100 g\nMRP Rs 20 incl. of all taxes", "auto")
    assert r.category == "other" and r.classification["source"] == "default"
    assert f(r, "generic_name").status == "REVIEW"
    assert f(r, "manufacturer").violation_code == "MISSING"
    assert f(r, "pack_size").status == "NOT_CONFIGURED"


# ---------------------------------------------------------------- Rule 6 distinctions
def test_missing_vs_uncertain_vs_format_error():
    assert f(analyze_text("Biscuits\nNet Wt. 100 g", "biscuits"), "mrp").violation_code == "MISSING"
    assert f(analyze_text("Biscuits\nNet Wt. 100 g\nMRP Rs 30", "biscuits"), "mrp").violation_code == "FORMAT_ERROR"
    unread = analyze_text("Biscuits\nNet Wt. 100 g\nMRP: ??", "biscuits")
    assert f(unread, "mrp").status == "REVIEW" and f(unread, "mrp").sub_case == "MRP_VALUE_UNREADABLE"
    partial = analyze_text("Biscuits\nNet Wt. 100 g\nMRP Rs 30\n(... of all Tax ...)", "biscuits")
    assert f(partial, "mrp").status in ("REVIEW", "PASS")


def test_tax_policy_switch(monkeypatch):
    import app.engine as eng
    t = "Biscuits\nNet Wt. 100 g\nMRP Rs 30 (Incl. of Taxes)"
    assert f(analyze_text(t, "biscuits"), "mrp").status == "REVIEW"
    monkeypatch.setattr(eng, "TAX_PHRASE_WITHOUT_ALL_POLICY", "accept")
    assert f(analyze_text(t, "biscuits"), "mrp").status == "PASS"
    monkeypatch.setattr(eng, "TAX_PHRASE_WITHOUT_ALL_POLICY", "format_error")
    assert f(analyze_text(t, "biscuits"), "mrp").violation_code == "FORMAT_ERROR"


def test_marketed_by_is_not_manufactured_by():
    r = analyze_text(TEA.replace("Packed by:", "Marketed by:"), "tea")
    assert f(r, "manufacturer").sub_case == "MARKETED_BY_ONLY"


def test_business_name_without_role_is_review_not_pass():
    t = TEA.replace("Packed by: ", "")
    assert f(analyze_text(t, "tea"), "manufacturer").sub_case == "ROLE_NOT_STATED"


def test_barcode_digits_are_not_a_phone_number():
    c = find_contacts(LabelText.from_text("Barcode 8901234567891\nHelp line : 080-29761413"))
    assert [h.text for h in c.phones] == ["080-29761413"]


def test_uncertain_normalization_never_passes_silently():
    r = analyze([Line("Biscuits", 0.9), Line("Net Wt. १५० g", 0.9), Line("MRP Rs 30 incl. of all taxes", 0.9)],
                "biscuits", from_ocr=True)
    assert f(r, "net_quantity").status == "REVIEW" and f(r, "net_quantity").sub_case == "UNCERTAIN_NORMALIZATION"


# ---------------------------------------------------------------- Rule 9
def test_language_hindi_english_other():
    assert f(analyze_text("शुद्ध घी निवल भार 500 ग्राम अधिकतम खुदरा मूल्य", "other"), "language").status == "PASS"
    assert f(analyze_text("ಹಾಲು ಪುಡಿ ನಿವ್ವಳ ತೂಕ ನೂರು ಗ್ರಾಂ ಬೆಲೆ", "other"), "language").violation_code == "LANGUAGE_ERROR"
    mixed = analyze_text(TEA + "\nಹಾಲು ಪುಡಿ", "tea")
    assert f(mixed, "language").status == "PASS"  # extra languages allowed alongside English


# ---------------------------------------------------------------- Rule 26
def test_unlabelled_small_quantity_does_not_bypass_checks():
    r = analyze_text("Glow Shampoo 8 ml sample\nBrand new formula", "other")
    assert r.exemption["level"] == "UNCONFIRMED"
    assert r.verdict == "NEEDS_REVIEW" and not any(x.status == "EXEMPT" for x in r.fields)


def test_reduced_exemption_keeps_mrp_and_quantity():
    r = analyze_text("Candy\nNet Wt. 15 g", "other")
    assert r.exemption["level"] == "REDUCED"
    assert f(r, "mrp").violation_code == "MISSING" and f(r, "manufacturer").status == "EXEMPT"


def test_uncertain_quantity_does_not_grant_exemption():
    r = analyze([Line("Glow Shampoo", 0.9), Line("Net Vol. ८ ml", 0.9)], "other", from_ocr=True)
    assert r.exemption["level"] == "UNCONFIRMED"
