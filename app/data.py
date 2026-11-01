"""Reference data from the PackCheck Compliance Rulebook (v4): categories, rule applicability,
generic-name keywords, standard pack sizes (Part C), exemptions (Part E) and limitations.

Everything a legal reviewer may want to change lives in this file, as data, not in the engine.
Where the rulebook does not answer a question the value is marked ``"unresolved"`` and the
question is listed in ``LEGAL_QUESTIONS`` (also published in docs/LEGAL_QUESTIONS.md).
"""
from typing import Dict, List, Optional, Tuple

# ------------------------------------------------------------------ categories
# key -> metadata
#   group:        display grouping
#   rule7_table:  'I' (weight/volume), 'II' (length/area/count) or None (decided by the declared unit).
#                 Used only to *explain* the skipped Rule 7 check; Rule 7 is never measured.
#   dimensions:   Rule 6(1)(f) applicability: 'required' | 'not_required' | 'unresolved'
#   inferable:    may PackCheck infer this category from label text? Categories that switch on an
#                 exemption (Rule 26 or the 6(1)(d) date exemption) are never inferred: the user must
#                 select them, so an exemption is never granted on a guess.
CATEGORY_INFO: Dict[str, dict] = {
    "auto": dict(label="Detect automatically", group="", rule7_table=None, dimensions="not_required", inferable=False),
    "other": dict(label="Other / not listed", group="", rule7_table=None, dimensions="not_required", inferable=False),
    # Part C commodities (weight / volume)
    "tea": dict(label="Tea", group="Food & drink", rule7_table="I", dimensions="not_required", inferable=True),
    "biscuits": dict(label="Biscuits", group="Food & drink", rule7_table="I", dimensions="not_required", inferable=True),
    "salt": dict(label="Salt", group="Food & drink", rule7_table="I", dimensions="not_required", inferable=True),
    "aerated_drinks": dict(label="Aerated / carbonated drinks", group="Food & drink", rule7_table="I", dimensions="not_required", inferable=True),
    "cement": dict(label="Cement", group="Building", rule7_table="I", dimensions="not_required", inferable=True),
    "white_cement": dict(label="White cement", group="Building", rule7_table="I", dimensions="not_required", inferable=True),
    "packaged_food": dict(label="Packaged food / snacks (not in the Rule 7 tables)", group="Food & drink", rule7_table=None, dimensions="not_required", inferable=True),
    "personal_care": dict(label="Personal care / household (not in the Rule 7 tables)", group="Personal care", rule7_table=None, dimensions="not_required", inferable=True),
    "toilet_soap": dict(label="Toilet soap", group="Personal care", rule7_table="I", dimensions="not_required", inferable=True),
    # size-dependent goods (rulebook 6(1)(f) examples)
    "bedsheet": dict(label="Bedsheet", group="Textiles", rule7_table="II", dimensions="required", inferable=True),
    "towel": dict(label="Towel", group="Textiles", rule7_table="II", dimensions="required", inferable=True),
    # stationery: Rule 7 Table II names notebooks explicitly. NOT excluded from any check.
    "notebook": dict(label="Notebook", group="Stationery", rule7_table="II", dimensions="unresolved", inferable=True),
    "exercise_book": dict(label="Exercise book", group="Stationery", rule7_table="II", dimensions="unresolved", inferable=True),
    "textbook": dict(label="Textbook", group="Stationery", rule7_table="II", dimensions="unresolved", inferable=True),
    "drawing_book": dict(label="Drawing book", group="Stationery", rule7_table="II", dimensions="unresolved", inferable=True),
    "register": dict(label="Register", group="Stationery", rule7_table="II", dimensions="unresolved", inferable=True),
    "diary": dict(label="Diary", group="Stationery", rule7_table="II", dimensions="unresolved", inferable=True),
    "writing_pad": dict(label="Writing pad", group="Stationery", rule7_table="II", dimensions="unresolved", inferable=True),
    "paper_product": dict(label="Other countable paper product", group="Stationery", rule7_table="II", dimensions="unresolved", inferable=True),
    # categories that carry an exemption: user selection only
    "bidi": dict(label="Bidi", group="Exemption categories", rule7_table=None, dimensions="not_required", inferable=False),
    "incense": dict(label="Incense sticks", group="Exemption categories", rule7_table=None, dimensions="not_required", inferable=False),
    "lpg_cylinder": dict(label="LPG cylinder (14.2 kg / 5 kg PSU)", group="Exemption categories", rule7_table="I", dimensions="not_required", inferable=False),
    "fast_food": dict(label="Fast food (packed by restaurant/hotel for immediate sale)", group="Exemption categories", rule7_table=None, dimensions="not_required", inferable=False),
    "scheduled_drug": dict(label="Scheduled drug formulation", group="Exemption categories", rule7_table=None, dimensions="not_required", inferable=False),
    "agri_produce": dict(label="Agricultural produce", group="Exemption categories", rule7_table="I", dimensions="not_required", inferable=False),
}
CATEGORIES: List[Tuple[str, str]] = [(k, v["label"]) for k, v in CATEGORY_INFO.items()]
CATEGORY_KEYS = set(CATEGORY_INFO)
STATIONERY_CATEGORIES = {k for k, v in CATEGORY_INFO.items() if v["group"] == "Stationery"}
# Categories with no commodity-specific rule in the rulebook: treated exactly like 'other' by the engine.
UNLISTED_CATEGORIES = {"other", "packaged_food", "personal_care"}

# Rule 6(1)(d): month/year of manufacture not required for these (rulebook Part A)
DATE_EXEMPT_CATEGORIES = {"bidi", "incense", "lpg_cylinder"}
# Rule 6(1)(f): kept for backward compatibility; derived from CATEGORY_INFO
DIMENSION_CATEGORIES = {k for k, v in CATEGORY_INFO.items() if v["dimensions"] == "required"}
DIMENSION_UNRESOLVED_CATEGORIES = {k for k, v in CATEGORY_INFO.items() if v["dimensions"] == "unresolved"}
# Rule 26: whole-package exemptions decided by category (rulebook Part E)
FULL_EXEMPT_CATEGORIES = {
    "fast_food": "Packed directly by restaurants/hotels for immediate sale",
    "scheduled_drug": "Scheduled drug formulation (governed by the Drugs (Price Control) Order)",
}

# ------------------------------------------------------------------ generic names (Rule 6(1)(b))
_STATIONERY_WORDS = ["notebook", "note book", "exercise book", "long book", "long note book", "ruled book",
                     "single line book", "four line book", "practical book", "record book"]
GENERIC_KEYWORDS: Dict[str, List[str]] = {
    "tea": ["tea", "chai"],
    "biscuits": ["biscuit", "cookie", "cracker"],
    "salt": ["salt"],
    "packaged_food": ["namkeen", "bhujia", "sev", "mixture", "chivda", "snack", "chips", "wafers", "papad", "sweets", "mithai",
                      "chocolate", "noodles", "masala", "spice", "pickle", "sauce", "jam", "cereal", "oats"],
    "personal_care": ["shampoo", "conditioner", "lotion", "cream", "toothpaste", "detergent", "face wash", "hair oil", "deodorant"],
    "cement": ["cement"],
    "white_cement": ["cement"],
    "toilet_soap": ["soap"],
    "aerated_drinks": ["aerated", "carbonated", "soft drink", "drink", "beverage", "soda", "cola", "juice"],
    "bedsheet": ["bed sheet", "bedsheet", "bed linen", "bedspread"],
    "towel": ["towel"],
    "notebook": _STATIONERY_WORDS,
    "exercise_book": ["exercise book", "exercise note book"] + _STATIONERY_WORDS,
    "textbook": ["textbook", "text book"],
    "drawing_book": ["drawing book", "sketch book", "sketchbook", "drawing pad", "art book"],
    "register": ["register"],
    "diary": ["diary", "planner", "organiser", "organizer"],
    "writing_pad": ["writing pad", "note pad", "notepad", "memo pad", "letter pad"],
    "paper_product": ["copier paper", "a4 paper", "paper ream", "sheets of paper", "graph book", "scrap book",
                      "scrapbook", "envelope"] + _STATIONERY_WORDS,
}
# Used for every category as a fallback. Deliberately does NOT contain 'book' / 'tech' etc.:
# those appear inside brand names ("BHASKAR BOOK TECH") and would turn a brand into a generic name.
GENERAL_GENERIC_WORDS = [
    "biscuit", "cookie", "tea", "coffee", "salt", "sugar", "rice", "flour", "atta", "maida", "suji",
    "oil", "ghee", "butter", "milk", "curd", "juice", "drink", "beverage", "soda", "cola", "water",
    "soap", "shampoo", "detergent", "toothpaste", "cream", "lotion", "powder", "noodles", "pasta",
    "masala", "spice", "snack", "chips", "namkeen", "chocolate", "candy", "sauce", "ketchup", "jam",
    "pickle", "dal", "pulses", "egg", "fruit", "vegetable", "wheat", "mustard", "sunflower", "coconut", "honey",
    "cereal", "oats", "cornflakes", "bread", "cake", "paneer", "tissue", "napkin", "wipes", "diaper", "bhujia", "sev", "mixture", "chivda", "papad", "wafers", "sweets",
    "notebook", "note book", "exercise book", "drawing book", "sketch book", "textbook", "text book",
    "register", "diary", "writing pad", "notepad", "note pad", "towel", "bedsheet", "bed sheet",
]

# ------------------------------------------------------------------ category inference evidence
# (regex, weight). Scores per category are summed and squashed to 0..1 in app/classify.py.
CATEGORY_EVIDENCE: Dict[str, List[Tuple[str, float]]] = {
    "tea": [(r"\btea\b", 0.7), (r"\bchai\b", 0.5), (r"\bdust\s+tea|\bctc\b|\bleaf\s+tea", 0.4)],
    "biscuits": [(r"\bbiscuits?\b", 0.7), (r"\bcookies?\b", 0.6), (r"\bcrackers?\b", 0.5)],
    "salt": [(r"\b(?:iodi[sz]ed\s+)?salt\b", 0.7)],
    "packaged_food": [(r"\bnamkeen\b|\bbhujia\b|\bsev\b|\bchivda\b|\bmixture\b|\bpapad\b|\bwafers?\b|\bchips\b|\bsnacks?\b|\bnoodles\b|\bpickle\b|\bmasala\b|\bsweets?\b|\bchocolates?\b", 0.6),
                      (r"\bfssai\b", 0.35), (r"\bnutritional\s+information\b|\bnutrition\s+facts\b", 0.3),
                      (r"\bingredients?\b", 0.2), (r"\bbest\s+before\b|\bshelf\s+life\b|\bveg(?:etarian)?\b", 0.1)],
    "personal_care": [(r"\bshampoo\b|\bconditioner\b|\bdetergent\b|\btoothpaste\b|\bface\s?wash\b|\bhair\s+oil\b|\bdeodorant\b|\blotion\b|\bmoisturi[sz]er\b", 0.7)],
    "cement": [(r"\bcement\b", 0.7), (r"\bportland\b|\bopc\b|\bppc\b", 0.4)],
    "white_cement": [(r"\bwhite\s+cement\b", 0.9)],
    "toilet_soap": [(r"\bsoap\b", 0.6), (r"\btoilet\s+soap\b|\bbathing\s+bar\b", 0.4)],
    "aerated_drinks": [(r"\bcarbonated\b|\baerated\b", 0.7), (r"\bsoft\s+drink\b|\bsoda\b|\bcola\b", 0.5)],
    "bedsheet": [(r"\bbed\s?sheets?\b|\bbed\s+linen\b|\bbedspread\b", 0.8), (r"\bthread\s+count\b", 0.3)],
    "towel": [(r"\btowels?\b", 0.8), (r"\bgsm\b", 0.1)],
    "notebook": [(r"\bnote\s?books?\b|\blong\s+books?\b|\bruled\b|\bsingle\s+line\b|\bfour\s+line\b", 0.8),
                 (r"\b\d{2,4}\s*pages?\b|\bpages?\s*[:\-]?\s*\d{2,4}\b", 0.45),
                 (r"\bend\s*sheets?\b|\bruling\b|\bbinding\b|\bstapled\b|\bspiral\b", 0.3),
                 (r"\b\d{2,3}\s*gsm\b", 0.15)],
    "exercise_book": [(r"\bexercise\s+(?:note\s?)?books?\b", 0.9)],
    "textbook": [(r"\btext\s?books?\b|\bisbn\b|\bedition\b|\bpublished\s+by\b", 0.6)],
    "drawing_book": [(r"\bdrawing\s+(?:book|pad)\b|\bsketch\s?(?:book|pad)\b", 0.9)],
    "register": [(r"\bregisters?\b", 0.7), (r"\b(?:attendance|stock|cash)\s+register\b", 0.3)],
    "diary": [(r"\bdiar(?:y|ies)\b|\bplanner\b", 0.8)],
    "writing_pad": [(r"\bwriting\s+pad\b|\bnote\s?pad\b|\bmemo\s+pad\b|\bletter\s+pad\b", 0.9)],
}

# ------------------------------------------------------------------ Rule 6(1)(e) tax wording policy
# The rulebook requires "inclusive of all taxes" "(or accepted equivalent wording)" but does not
# list the accepted equivalents. Wording that contains "all taxes" is accepted. Wording that omits
# "all" (e.g. "Incl. of Taxes") is handled by this policy until the legal team rules on it:
#   "review" -> REVIEW (human decides)   "accept" -> PASS   "format_error" -> FAIL/FORMAT_ERROR
TAX_PHRASE_WITHOUT_ALL_POLICY = "review"


# ------------------------------------------------------------------ standard sizes (Part C)
def _is_mult(v: float, k: float) -> bool:
    q = v / k
    return v > 0 and abs(q - round(q)) < 1e-9


def _in(v: float, values) -> bool:
    return any(abs(v - x) < 1e-9 for x in values)


# category -> unit the table is expressed in (after normalising to g / ml)
SIZE_TABLE_UNIT = {
    "tea": "g", "biscuits": "g", "salt": "g", "toilet_soap": "g",
    "cement": "g", "white_cement": "g", "aerated_drinks": "ml",
}


def is_standard_size(
    category: str, value: float, pack_type: Optional[str] = None
) -> Tuple[Optional[bool], Optional[str]]:
    """value is in g or ml (see SIZE_TABLE_UNIT). Returns (is_standard, note).
    (None, None) means the category has no table."""
    if category == "tea":
        return _in(value, [25, 50, 100, 125, 250, 500]) or (value >= 1000 and _is_mult(value, 1000)), None
    if category == "biscuits":
        return _in(value, [25, 50, 75, 100, 150, 200, 250, 300]) or (value > 300 and _is_mult(value, 100)), None
    if category == "salt":
        if value < 50:
            return _is_mult(value, 10), None
        return _in(value, [50, 100, 200, 500, 750, 1000, 2000, 5000]) or (value > 5000 and _is_mult(value, 5000)), None
    if category in ("cement", "white_cement"):
        kg = value / 1000.0
        if _in(kg, [40]) and category != "white_cement":
            return False, "40 kg is a standard size for white cement only"
        allowed = [1, 2, 5, 10, 20, 25, 50] + ([40] if category == "white_cement" else [])
        return _in(kg, allowed), None
    if category == "toilet_soap":
        return _in(value, [25, 50, 75, 100, 125, 150]) or (value > 150 and _is_mult(value, 50)), None
    if category == "aerated_drinks":
        if _in(value, [330]):
            if pack_type is None:
                return True, "330 ml is standard for cans only; pack type was not given, assumed can"
            return pack_type == "can", "330 ml is standard for cans only"
        return _in(value, [65, 100, 125, 150, 200, 250, 300, 500, 750, 1000, 1500, 2000, 3000, 4000, 5000]), None
    return None, None


# ------------------------------------------------------------------ limitations & legal questions
LIMITATIONS = [
    "Rule 7 (numeral height) is not measured: a photo has no real-world scale. This is a finalized team "
    "decision (rulebook Part B). It skips the measurement only; no product category is excluded.",
    "Rule 8 (clear space around the net quantity) is estimated from the photo's own geometry (ratios to the "
    "numeral height, so no real-world scale is needed). It is only passed when the margin is generous; "
    "otherwise it goes to human review. Text input cannot be assessed.",
    "Language (Rule 9) is checked on the whole label, not per declaration.",
    "Legibility uses OCR confidence as a proxy; contrast is measured as luminance contrast around each "
    "declaration. Neither is a substitute for inspecting the physical label.",
    "Results depend on what is in the photo. A declaration printed on another face of the pack will be reported "
    "as not found; low-confidence and partially read fields go to human review instead of pass/fail.",
    "Standard pack sizes (Rule 5) are configured only for the six commodities in rulebook Part C. Other "
    "categories show NOT_CONFIGURED, which is not a legal exemption.",
    "The MRP rounding rule (paise) is not checkable from a photo and is not implemented.",
]

LEGAL_QUESTIONS = {
    "MANUFACTURER_ROLE_NOT_STATED": "A business name and full address are printed but the label does not say "
        "'Manufactured / Packed / Imported by'. Does that satisfy Rule 6(1)(a)? (Currently: needs review.)",
    "PAGE_COUNT_AS_NET_QUANTITY": "For notebooks and other paper products, can a page count (e.g. '140 Pages') "
        "serve as the net-quantity declaration, or is a unit count (e.g. '1 N') required? (Currently: needs review.)",
    "STATIONERY_DIMENSIONS": "Is Rule 6(1)(f) (dimensions) applicable to notebooks and other stationery? "
        "(Currently: not configured; any printed size is shown as evidence only.)",
    "TAX_PHRASE_WITHOUT_ALL": "Is 'Inclusive of Taxes' / 'Incl. of Taxes' (without 'all') an accepted "
        "equivalent of 'inclusive of all taxes'? (Currently: needs review; set TAX_PHRASE_WITHOUT_ALL_POLICY.)",
}
