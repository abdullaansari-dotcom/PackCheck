from app.extract import LabelText, find_mrp, find_net_quantity, script_counts


def lab(t):
    return LabelText.from_text(t)


def test_net_quantity_kg_and_litre_are_normalised():
    q = find_net_quantity(lab("Net Wt. 1.5 kg"))
    assert (q.base_value, q.base_unit) == (1500.0, "g")
    q = find_net_quantity(lab("Net Vol. 1.5 L"))
    assert (q.base_value, q.base_unit) == (1500.0, "ml")


def test_quantity_on_next_line_after_keyword():
    q = find_net_quantity(lab("Net Wt.\n100g"))
    assert q.kind == "std" and q.labelled and q.value == 100


def test_nutrition_per_100g_is_ignored():
    q = find_net_quantity(lab("Energy 250 kcal per 100g\nNet Wt. 80 g"))
    assert q.base_value == 80


def test_unlabelled_quantity_is_still_found():
    q = find_net_quantity(lab("Salty Chips 45g"))
    assert q.kind == "std" and not q.labelled


def test_no_quantity():
    assert find_net_quantity(lab("Hello world")).kind == "none"


def test_thousands_separator():
    assert find_net_quantity(lab("Net Wt. 1,000 g")).value == 1000


def test_mrp_variants():
    for t in ["MRP: Rs 45.00 (Inclusive of all taxes)", "M.R.P. ₹45 incl. of all taxes", "MRP Rs.45/- Inclusive of all taxes"]:
        m = find_mrp(lab(t))
        assert m.found and m.tax_phrase and m.amount == 45.0, t
    assert find_mrp(lab("MRP 45.00")).found
    assert not find_mrp(lab("Net Wt. 45 g")).found


def test_script_counts():
    lat, dev, oth = script_counts("Net Wt शुद्ध घी ಹಾಲು")
    assert lat == 5 and dev > 0 and oth > 0


def test_full_numeric_date_dd_mm_yy_is_a_manufacture_date():
    from app.engine import analyze_text
    r = analyze_text("NET QUANTITY: 200 g\nMFG. DATE: 10.09.26\nUSE BY: 09.03.27\nMRP: Rs.60.00 (Incl. of all taxes)", "other")
    f = [x for x in r.fields if x.field == "mfg_date"][0]
    assert f.status == "PASS" and "10.09.26" in f.detected_text
