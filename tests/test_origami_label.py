"""Regression for the Origami tissue-box label (back of pack): the readers were right, the rules were not."""
from app.engine import analyze, analyze_text
from app.extract import LabelText, find_net_quantity, locate_snippet
from app.layout import Line

TEXT = """Origami So..Soft
For any feedback contact our Customer Care Executive at:
Regd. Office: ORIGAMI CELLULO Pvt. Ltd.,
126A, Sriranga Complex, Ashwathnagar, Bengaluru - 560 094
Karnataka, India.
t: + 91 80 4346 2000; e: customercare@origamiindia.com
Item : Origami Face Tissue Box
Number of usable Sheets : 100 N
Net Quantity (Box) : 1 N Sheet Ply : 2 Ply
Sheet size : (L x B) 19cm x 20cm
MRP (Inclusive of all taxes) : Rs 100.00
Mfd. & Pkd. : SEP/2026"""


def lab():
    return LabelText([Line(t) for t in TEXT.splitlines()])


def field(r, name):
    return next(x for x in r.fields if x.field == name)


def test_net_quantity_is_the_net_quantity_line_not_the_sheet_count():
    q = find_net_quantity(lab())
    assert q.kind == "count" and q.value == 1 and "Net Quantity" in q.hit.text


def test_product_name_read_from_item_line():
    r = analyze([Line(t) for t in TEXT.splitlines()], "other", from_ocr=True)
    g = field(r, "generic_name")
    assert g.status == "PASS" and "Face Tissue Box" in g.detected_text


def test_regd_office_prefix_is_not_part_of_the_business_name():
    r = analyze([Line(t) for t in TEXT.splitlines()], "other", from_ocr=True)
    assert r.product_info["business_name"]["text"].startswith("ORIGAMI CELLULO")


def test_international_format_phone_number_is_found():
    r = analyze([Line(t) for t in TEXT.splitlines()], "other", from_ocr=True)
    assert any("4346" in p for p in r.product_info["contacts"]["phones"])


def test_missing_declaration_in_a_photo_is_review_but_pasted_text_still_fails():
    photo = analyze([Line("Origami Tissue", 0.9)], "other", from_ocr=True)
    assert field(photo, "mrp").status == "REVIEW"
    pasted = analyze_text("Origami Tissue", "other")
    assert field(pasted, "mrp").status == "FAIL"


def test_ai_fields_are_used_only_when_printed_on_the_label():
    plain = [Line("Origami Gold"), Line("Best Quality"), Line("Net Weight Approx : 50 x 2")]
    # AI quotes something that is NOT in the text: ignored
    r = analyze(plain, "other", from_ocr=True, ai_fields={"product_name": "Facial Tissues Deluxe"})
    assert field(r, "generic_name").status == "REVIEW"
    # AI quotes a name that IS printed: accepted, and says it came from the AI
    lines = [Line("Origami Gold"), Line("Pure Glycerine Bar")]
    r2 = analyze(lines, "other", from_ocr=True, ai_fields={"product_name": "Pure Glycerine Bar"})
    g = field(r2, "generic_name")
    assert g.status == "PASS" and "AI reader" in g.detail


def test_locate_snippet_ignores_case_and_line_breaks():
    l = LabelText([Line("Item :"), Line("Face Tissue Box")])
    assert locate_snippet(l, "item : face tissue box") is not None
    assert locate_snippet(l, "Hand Towel") is None
