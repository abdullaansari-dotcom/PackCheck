import json

import pytest

from app import config
from app.engine import analyze, analyze_text
from app.extract import Line

GOOD = (
    "Crunchy Bites\nCream Biscuits\nNet Wt. 150 g\nMRP Rs. 30.00 (Inclusive of all taxes)\n"
    "Mfg: 03/2026\nManufactured by: Sunrise Foods Pvt. Ltd., Plot 14, Industrial Area, Nashik, "
    "Maharashtra - 422010\nFor queries contact: 1800-123-4567 / care@sunrisefoods.com"
)


def f(result, name):
    return next(x for x in result.fields if x.field == name)


def test_compliant_label():
    r = analyze_text(GOOD, "biscuits")
    assert r.verdict == "COMPLIANT", [(x.field, x.status, x.violation_code) for x in r.fields]
    assert f(r, "dimensions").status == "NOT_APPLICABLE"
    assert f(r, "pack_size").status == "PASS"


def test_mrp_without_tax_phrase_is_format_error_not_missing():
    r = analyze_text(GOOD.replace(" (Inclusive of all taxes)", ""), "biscuits")
    x = f(r, "mrp")
    assert (x.status, x.violation_code, x.rule_reference) == ("FAIL", "FORMAT_ERROR", "Rule 6(1)(e)")


def test_mrp_missing_entirely():
    r = analyze_text(GOOD.replace("MRP Rs. 30.00 (Inclusive of all taxes)\n", ""), "biscuits")
    assert f(r, "mrp").violation_code == "MISSING"


@pytest.mark.parametrize("phrase", ["Incl. of all taxes", "inclusive of all taxes", "(Inc. of all taxes)", "all taxes included"])
def test_tax_phrase_variants(phrase):
    r = analyze_text(GOOD.replace("Inclusive of all taxes", phrase), "biscuits")
    assert f(r, "mrp").status == "PASS"


@pytest.mark.parametrize("qty", ["approx 100g", "Approx. 100 g", "minimum 100g", "about 100g", "100g min"])
def test_vague_quantity(qty):
    r = analyze_text(GOOD.replace("150 g", qty), "biscuits")
    assert f(r, "net_quantity").violation_code == "VAGUE_LANGUAGE"


def test_dozen_is_unit_error():
    r = analyze_text("Eggs\nNet Qty: 2 dozen\nMRP Rs 160 incl. of all taxes", "other")
    x = f(r, "net_quantity")
    assert x.violation_code == "UNIT_ERROR"


def test_count_quantity_passes():
    r = analyze_text(GOOD.replace("Net Wt. 150 g", "Contains 12 biscuits"), "other")
    assert f(r, "net_quantity").status == "PASS"


def test_tea_120g_needs_disclaimer():
    base = "Tea\nNet Wt. 120g\nMRP Rs 50 incl. of all taxes"
    assert f(analyze_text(base, "tea"), "pack_size").violation_code == "NONSTANDARD_PACK"
    ok = analyze_text(base + "\nNon-standard size", "tea")
    assert f(ok, "pack_size").status == "PASS"


@pytest.mark.parametrize("cat,qty,expected", [
    ("tea", "100 g", "PASS"), ("tea", "125 g", "PASS"), ("tea", "1 kg", "PASS"), ("tea", "3 kg", "PASS"),
    ("tea", "1.5 kg", "FAIL"),
    ("biscuits", "400 g", "PASS"), ("biscuits", "350 g", "FAIL"),
    ("salt", "30 g", "PASS"), ("salt", "35 g", "FAIL"), ("salt", "750 g", "PASS"), ("salt", "10 kg", "PASS"), ("salt", "7 kg", "FAIL"),
    ("cement", "50 kg", "PASS"), ("cement", "40 kg", "FAIL"), ("white_cement", "40 kg", "PASS"),
    ("toilet_soap", "125 g", "PASS"), ("toilet_soap", "175 g", "FAIL"), ("toilet_soap", "200 g", "PASS"),
    ("aerated_drinks", "1.5 l", "PASS"), ("aerated_drinks", "600 ml", "FAIL"), ("aerated_drinks", "2 l", "PASS"),
])
def test_standard_sizes(cat, qty, expected):
    r = analyze_text(f"Product\nNet Wt. {qty}\nMRP Rs 10 incl. of all taxes", cat)
    assert f(r, "pack_size").status == expected


def test_330ml_only_for_cans():
    t = "Cola Drink\nNet Vol. 330 ml\nMRP Rs 20 incl. of all taxes"
    assert f(analyze_text(t, "aerated_drinks", "can"), "pack_size").status == "PASS"
    assert f(analyze_text(t, "aerated_drinks", "bottle"), "pack_size").violation_code == "NONSTANDARD_PACK"


def test_marketed_by_only_is_distinct_edge_case():
    r = analyze_text(GOOD.replace("Manufactured by:", "Marketed by:"), "biscuits")
    x = f(r, "manufacturer")
    assert (x.status, x.violation_code, x.sub_case) == ("FAIL", "FORMAT_ERROR", "MARKETED_BY_ONLY")


def test_manufacturer_without_address():
    r = analyze_text(GOOD.replace(", Plot 14, Industrial Area, Nashik, Maharashtra - 422010", ""), "biscuits")
    assert f(r, "manufacturer").sub_case == "ADDRESS_INCOMPLETE"


def test_importer_needs_foreign_manufacturer():
    r = analyze_text(GOOD.replace("Manufactured by:", "Imported by:"), "biscuits")
    assert f(r, "manufacturer").sub_case == "IMPORTER_ONLY"


def test_mfg_date_formats():
    for d in ["March 2026", "03/2026", "Mar-26", "Pkd: 03.2026"]:
        r = analyze_text(GOOD.replace("Mfg: 03/2026", f"Mfg: {d}"), "biscuits")
        assert f(r, "mfg_date").status == "PASS", d


def test_only_expiry_date_is_not_a_mfg_date():
    r = analyze_text(GOOD.replace("Mfg: 03/2026", "Best before: 09/2026"), "biscuits")
    x = f(r, "mfg_date")
    assert x.violation_code == "MISSING" and x.sub_case == "ONLY_EXPIRY_DATE"


def test_price_is_not_mistaken_for_date():
    r = analyze_text(GOOD.replace("Mfg: 03/2026\n", ""), "biscuits")
    assert f(r, "mfg_date").violation_code == "MISSING"


@pytest.mark.parametrize("cat", ["bidi", "incense", "lpg_cylinder"])
def test_date_exempt_categories(cat):
    r = analyze_text(GOOD.replace("Mfg: 03/2026\n", ""), cat)
    assert f(r, "mfg_date").status == "EXEMPT"


def test_dimensions_only_for_bedsheets():
    bed = "Cotton Bedsheet\nNet Qty: 1 N\nMRP Rs 499 incl. of all taxes"
    assert f(analyze_text(bed, "bedsheet"), "dimensions").violation_code == "MISSING"
    assert f(analyze_text(bed + "\nSize: 90cm x 180cm", "bedsheet"), "dimensions").status == "PASS"
    assert f(analyze_text(GOOD, "biscuits"), "dimensions").status == "NOT_APPLICABLE"


def test_consumer_care_variants():
    base = GOOD.replace("For queries contact: 1800-123-4567 / care@sunrisefoods.com", "")
    assert f(analyze_text(base, "biscuits"), "consumer_care").violation_code == "MISSING"
    assert f(analyze_text(base + "Call 1800 102 3456", "biscuits"), "consumer_care").status == "PASS"
    assert f(analyze_text(base + "mail us: help@brand.in", "biscuits"), "consumer_care").status == "PASS"


def test_generic_name_missing_for_known_category():
    t = "ZOOMO BLAST\nNet Vol. 500 ml\nMRP Rs 20 incl. of all taxes"
    assert f(analyze_text(t, "aerated_drinks"), "generic_name").violation_code == "MISSING"
    assert f(analyze_text(t + "\nCarbonated Fruit Drink", "aerated_drinks"), "generic_name").status == "PASS"


def test_generic_name_unknown_category_goes_to_review():
    t = "Zorbo\nNet Wt. 100 g\nMRP Rs 20 incl. of all taxes"
    x = f(analyze_text(t, "other"), "generic_name")
    assert x.status == "REVIEW"


# ---- Rule 26 exemptions
def test_tiny_package_fully_exempt():
    r = analyze_text("Glow Shampoo\nNet Vol. 8 ml", "other")
    assert r.verdict == "EXEMPT" and all(x.status == "EXEMPT" for x in r.fields)


def test_10g_boundary_is_exempt_11g_is_reduced():
    assert analyze_text("Net Wt. 10 g", "other").verdict == "EXEMPT"
    r = analyze_text("Candy\nNet Wt. 15 g", "other")
    assert r.exemption["level"] == "REDUCED"
    assert f(r, "net_quantity").status == "PASS"
    assert f(r, "mrp").violation_code == "MISSING"            # still required
    assert f(r, "consumer_care").status == "EXEMPT"           # not required


def test_over_20g_not_exempt():
    assert analyze_text("Candy\nNet Wt. 21 g", "other").exemption is None


def test_category_exemptions():
    assert analyze_text("burger", "fast_food").verdict == "EXEMPT"
    assert analyze_text("tablet", "scheduled_drug").verdict == "EXEMPT"
    assert analyze_text("Wheat\nNet Wt. 60 kg", "agri_produce").verdict == "EXEMPT"
    assert analyze_text("Wheat\nNet Wt. 40 kg", "agri_produce").verdict != "EXEMPT"


# ---- Rule 9
def test_language_error_for_regional_only():
    kannada = "ಹಾಲು ಪುಡಿ ನಿವ್ವಳ ತೂಕ ನೂರು ಗ್ರಾಂ ಬೆಲೆ ಐವತ್ತು ರೂಪಾಯಿ"
    r = analyze_text(kannada, "other")
    assert f(r, "language").violation_code == "LANGUAGE_ERROR"


def test_hindi_label_passes_language():
    hindi = "शुद्ध घी निवल भार 500 ग्राम अधिकतम खुदरा मूल्य रुपये सौ"
    assert f(analyze_text(hindi, "other"), "language").status == "PASS"


def test_low_ocr_confidence_downgrades_to_review():
    lines = [Line("Net Wt. 150 g", 0.2), Line("Cream Biscuits", 0.9)]
    r = analyze(lines, "biscuits", from_ocr=True)
    x = f(r, "net_quantity")
    assert (x.status, x.violation_code) == ("REVIEW", "LOW_CONFIDENCE")


def test_missing_field_on_blurry_photo_is_review_not_fail():
    lines = [Line("Cream Biscuits", 0.3), Line("Net Wt. 150 g", 0.3)]
    r = analyze(lines, "biscuits", from_ocr=True)
    assert f(r, "mrp").status == "REVIEW"
    assert f(r, "legibility").status == "REVIEW"
    assert r.verdict == "NEEDS_REVIEW"


def test_unknown_category_raises():
    with pytest.raises(ValueError):
        analyze_text("x", "nope")


def test_samples_run_and_serialise():
    for s in json.load(open(config.SAMPLES_FILE)):
        r = analyze_text(s["text"], s["category"], s["pack_type"])
        json.loads(r.model_dump_json())


def test_every_failure_has_rule_reference():
    for s in json.load(open(config.SAMPLES_FILE)):
        r = analyze_text(s["text"], s["category"], s["pack_type"])
        for x in r.fields:
            assert x.rule_reference.startswith("Rule")
            if x.status == "PASS":
                assert x.violation_code is None
