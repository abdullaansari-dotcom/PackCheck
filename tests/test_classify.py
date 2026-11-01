"""Stage test: product classification."""
from app.classify import classify


def test_notebook_inferred_from_page_count_and_end_sheets():
    c = classify("140 Pages - MRP: ₹60.00\n(Inclusive of both end sheets)", "auto")
    assert (c.category, c.source) == ("notebook", "inferred")
    assert any("Pages" in e for e in c.evidence)


def test_brand_word_book_alone_does_not_make_a_notebook():
    assert classify("BHASKAR BOOK TECH\nHelp line : 080-29761413", "auto").category == "other"


def test_user_choice_always_wins_but_suggestion_is_reported():
    c = classify("Long Notebook 172 Pages", "tea")
    assert (c.category, c.source, c.suggestion) == ("tea", "user", "notebook")


def test_explicit_other_is_not_overridden():
    c = classify("Assam Tea Net Wt 250 g", "other")
    assert c.category == "other" and c.suggestion == "tea"


def test_exemption_categories_are_never_inferred():
    for text in ["Veg burger packed by restaurant", "Bidi 25 sticks", "Incense sticks agarbatti", "LPG cylinder 14.2 kg"]:
        assert classify(text, "auto").category == "other"


def test_specific_stationery_categories():
    assert classify("Exercise Book 100 pages", "auto").category == "exercise_book"
    assert classify("A4 Drawing Book 36 pages", "auto").category == "drawing_book"
    assert classify("Writing Pad 80 sheets", "auto").category == "writing_pad"
    assert classify("Attendance Register 200 pages", "auto").category == "register"


def test_salt_in_ingredients_does_not_make_a_snack_a_salt_pack():
    from app.classify import classify
    text = ("ALOO BHUJIA SEV\nINGREDIENTS: Potato, Edible Vegetable Oil, Iodised Salt, Black Salt.\n"
            "Allergen: May Contains Wheat\nMARKETED BY: HALDIRAM SNACKS FOOD PRIVATE LIMITED\n"
            "FSSAI Lic. No. 10014011001919\nNUTRITIONAL INFORMATION (Approximate Values)")
    c = classify(text, "auto")
    assert c.category == "packaged_food"


def test_real_salt_pack_is_still_salt():
    from app.classify import classify
    assert classify("TATA SALT\nVacuum evaporated iodised salt\nNet Wt. 1 kg", "auto").category == "salt"
