"""AI-quoted fields (price, date, manufacturer, ...): used only when they are really printed on the label."""
from app.engine import analyze
from app.extract import (LabelText, Manufacturer, MfgDate, Mrp, ai_manufacturer, ai_mfg_date, ai_mrp,
                         find_manufacturer, find_mfg_date, find_mrp)
from app.layout import Line


def L(*texts):
    return LabelText([Line(t) for t in texts])


def field(r, name):
    return next(x for x in r.fields if x.field == name)


# ---------------------------------------------------------------- date
def test_date_quote_verified_and_anchored_in_the_full_text():
    lab = L("Origami So..Soft", "Batch A/S2627", "Mfd. & Pkd. : SEP/2026", "Best to use within 5 years")
    d = ai_mfg_date(lab, MfgDate(False), "Mfd. & Pkd. : SEP/2026")
    assert d.found and lab.text[d.hit.start:d.hit.end].upper().endswith("SEP/2026")


def test_date_quote_not_printed_is_ignored():
    lab = L("Origami", "Mfd. : SEP/2026")
    cur = MfgDate(False)
    assert ai_mfg_date(lab, cur, "Mfd. : OCT/2025") is cur


def test_date_quote_never_replaces_a_date_the_finder_already_has():
    lab = L("Mfd. : SEP/2026", "Mfd. : OCT/2025")
    cur = find_mfg_date(lab)
    assert ai_mfg_date(lab, cur, "Mfd. : OCT/2025") is cur


def test_expiry_quote_is_not_taken_as_manufacture_date():
    lab = L("Best before : 09/2027")
    assert not ai_mfg_date(lab, MfgDate(False), "Best before : 09/2027").found


# ---------------------------------------------------------------- manufacturer
def test_manufacturer_quote_gives_role_and_address():
    lab = L("Brand names are trademarks", "Manufactured by: ABC Foods Pvt Ltd, Plot 4, MIDC Hingna, Nagpur - 440016",
            "Net Wt. 200 g")
    cur = Manufacturer(False, False, False, False)
    m = ai_manufacturer(lab, cur, "Manufactured by: ABC Foods Pvt Ltd, Plot 4, MIDC Hingna, Nagpur - 440016")
    assert m.has_manufacturer and m.has_address and m.role == "manufacturer"
    assert "ABC Foods" in lab.text[m.hit.start:m.hit.end]


def test_manufacturer_quote_must_be_printed_and_must_improve_the_result():
    lab = L("Manufactured by: ABC Foods Pvt Ltd, Plot 4, MIDC Hingna, Nagpur - 440016")
    good = find_manufacturer(lab)
    assert ai_manufacturer(lab, good, "Manufactured by: ABC Foods Pvt Ltd, Plot 4, MIDC Hingna, Nagpur - 440016") is good
    cur = Manufacturer(False, False, False, False)
    assert ai_manufacturer(lab, cur, "Manufactured by: XYZ Mills, Pune - 411001") is cur


# ---------------------------------------------------------------- price
def test_price_quote_keeps_amount_and_adds_tax_wording():
    lab = L("MRP : Rs 100.00", "(Inclusive of all taxes)")
    cur = Mrp(True, find_mrp(lab).hit, 100.0, False, True, None, None, None)
    m = ai_mrp(lab, cur, "MRP : Rs 100.00 (Inclusive of all taxes)")
    assert m.found and m.amount == 100.0 and m.tax_phrase


def test_price_quote_with_a_different_amount_is_ignored():
    lab = L("MRP : Rs 100.00", "Offer price Rs 80.00 (Inclusive of all taxes)")
    cur = Mrp(True, find_mrp(lab).hit, 100.0, False, True, None, None, None)
    assert ai_mrp(lab, cur, "Offer price Rs 80.00 (Inclusive of all taxes)") is cur


def test_price_quote_fills_in_when_no_price_was_found():
    lab = L("Price : Rs. 60.00 (incl. of all taxes)")
    assert ai_mrp(lab, Mrp(False), "Price : Rs. 60.00 (incl. of all taxes)").found


# ---------------------------------------------------------------- through the engine
def test_engine_ignores_invented_quotes_and_reports_nothing_changed():
    lines = [Line("Origami Gold"), Line("Pure Glycerine Bar")]
    r = analyze(lines, "other", from_ocr=True, ai_fields={"mrp": "MRP Rs 999", "mfg_date": "Mfd SEP/2026",
                                                         "manufacturer": "Made by Nobody Ltd, Pune - 411001"})
    assert field(r, "mrp").status == "REVIEW" and field(r, "mfg_date").status == "REVIEW"
    assert "AI reader" not in (field(r, "mrp").detail or "")


def test_engine_marks_fields_located_with_the_ai_quote(monkeypatch):
    import app.engine as eng
    lines = [Line("Origami So..Soft"), Line("Mfd. & Pkd. : SEP/2026"), Line("Net Wt. 50 g")]
    monkeypatch.setattr(eng, "find_mfg_date", lambda lab: MfgDate(False))  # the pattern finder misses it
    r = analyze(lines, "other", from_ocr=True, ai_fields={"mfg_date": "Mfd. & Pkd. : SEP/2026"})
    d = field(r, "mfg_date")
    assert d.status == "PASS" and "AI reader" in d.detail
