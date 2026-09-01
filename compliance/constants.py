"""
Legal Metrology Constants and Legal Rule References
SIH 2026 - Problem Statement SIH26034
Legal Metrology (Packaged Commodities) Rules, 2011 (GSR 202(E))
"""

from typing import Dict, List, Set, Any

# ==========================================
# Legal Rule References (Exact statutory clauses)
# ==========================================
RULE_REF_MANUFACTURER = "Rule 6(1)(a)"
RULE_REF_GENERIC_NAME = "Rule 6(1)(b)"
RULE_REF_NET_QUANTITY = "Rule 6(1)(c)"
RULE_REF_MFG_DATE = "Rule 6(1)(d)"
RULE_REF_MRP = "Rule 6(1)(e)"
RULE_REF_DIMENSIONS = "Rule 6(1)(f)"
RULE_REF_CONSUMER_CARE = "Rule 6(2)"
RULE_REF_STANDARD_SIZES = "Rule 5 / Second Schedule"
RULE_REF_NUMERAL_HEIGHT = "Rule 7 / Rule 8"
RULE_REF_LEGIBILITY_LANGUAGE = "Rule 9"
RULE_REF_EXEMPTIONS = "Rule 26"

# ==========================================
# Part E - Rule 26 Exemption Thresholds
# ==========================================
VERY_SMALL_PACKAGE_MAX_WEIGHT_G = 10.0      # <= 10g fully exempt from Chapter II
VERY_SMALL_PACKAGE_MAX_VOLUME_ML = 10.0    # <= 10ml fully exempt from Chapter II

SMALL_PACKAGE_PARTIAL_MAX_WEIGHT_G = 20.0   # 10g-20g requires MRP + Net Qty only
SMALL_PACKAGE_PARTIAL_MAX_VOLUME_ML = 20.0 # 10ml-20ml requires MRP + Net Qty only

LARGE_AGRICULTURAL_PRODUCE_MIN_WEIGHT_KG = 50.0  # > 50kg exempt

# ==========================================
# Part A - Rule 6(1)(c) Net Quantity Constants
# ==========================================
BANNED_QUALIFIERS: Set[str] = {
    "approx",
    "approx.",
    "approximate",
    "approximately",
    "about",
    "nearly",
    "minimum",
    "min",
    "min.",
    "+/-",
    "±",
    "at least",
    "not less than",
    "around",
    "roughly",
}

STANDARD_MASS_UNITS: Set[str] = {
    "g", "gm", "gms", "gram", "grams",
    "kg", "kgs", "kilogram", "kilograms",
    "mg", "mgs", "milligram", "milligrams"
}

STANDARD_VOLUME_UNITS: Set[str] = {
    "ml", "m.l.", "m.l", "millilitre", "millilitres", "milliliter", "milliliters",
    "l", "lt", "ltr", "litre", "litres", "liter", "liters", "cl"
}

STANDARD_COUNT_UNITS: Set[str] = {
    "count", "units", "unit", "pieces", "piece", "pcs", "pc",
    "tablets", "capsules", "caps", "tabs",
    "n", "u", "no.", "nos", "nos.", "numbers",
    "packs", "sachets", "wipes", "sheets", "rolls", "pairs", "sets"
}

STANDARD_LENGTH_AREA_UNITS: Set[str] = {
    "cm", "m", "mm", "metre", "metres", "meter", "meters",
    "sq cm", "sq m", "sq. m", "sq. cm", "sqm", "sqcm", "sq.m", "sq.cm"
}

ALL_STANDARD_UNITS = STANDARD_MASS_UNITS | STANDARD_VOLUME_UNITS | STANDARD_COUNT_UNITS | STANDARD_LENGTH_AREA_UNITS

# Non-standard / banned units under Rule 13(4) / Legal Metrology
BANNED_UNITS: Set[str] = {
    "dozen", "dozens", "dz",
    "lbs", "lb", "pound", "pounds",
    "oz", "ounce", "ounces",
    "ft", "feet", "inch", "inches", "in",
    "gallon", "gallons", "quart", "quarts", "pint", "pints"
}

# ==========================================
# Part A - Rule 6(1)(e) MRP Tax Phrases
# ==========================================
TAX_INCLUSION_PHRASES: List[str] = [
    "inclusive of all taxes",
    "incl. of all taxes",
    "incl of all taxes",
    "incl. all taxes",
    "incl all taxes",
    "inclusive all taxes",
    "inc. of all taxes",
    "inc of all taxes",
    "all taxes included",
    "inclusive of taxes",
    "taxes included",
    "सभी कर सहित",
    "सभी करों सहित",
    "कर सहित",
    "अधिकतम खुदरा मूल्य (सभी कर सहित)",
]

# ==========================================
# Part A - Rule 6(1)(d) Mfg Date Exemptions
# ==========================================
MFG_DATE_EXEMPT_CATEGORIES: Set[str] = {
    "bidi", "bidis", "beedi", "beedis",
    "incense", "incense sticks", "agarbatti", "agarbathi", "dhoop",
    "lpg", "lpg cylinder", "lpg cylinders", "gas cylinder", "gas cylinders"
}

# ==========================================
# Part A - Rule 6(1)(f) Dimensions Whitelist
# ==========================================
DIMENSIONS_REQUIRED_CATEGORIES: Set[str] = {
    "bedsheet", "bed sheet", "bedsheets",
    "towel", "towels",
    "cloth", "fabric", "textile", "textiles",
    "tile", "tiles",
    "rug", "rugs", "carpet", "carpets", "mat", "mats",
    "wallpaper", "wallpapers",
    "napkin", "napkins", "tablecloth", "table cloth",
    "curtain", "curtains", "blanket", "blankets",
    "quilt", "pillow cover", "pillow covers", "mattress"
}

# ==========================================
# Part C - Rule 5 + Second Schedule Standard Pack Sizes
# Standard pack sizes in grams (for mass) or millilitres (for volume) or kg (for cement)
# ==========================================
STANDARD_PACK_SIZES: Dict[str, Dict[str, Any]] = {
    "tea": {
        "unit": "g",
        "fixed_sizes": [25, 50, 100, 125, 250, 500, 1000],
        "multiples_after": 1000,
        "multiple_step": 1000,  # Multiples of 1kg (1000g, 2000g, 3000g, ...)
        "description": "25g, 50g, 100g, 125g, 250g, 500g, 1kg, then multiples of 1kg"
    },
    "biscuits": {
        "unit": "g",
        "fixed_sizes": [25, 50, 75, 100, 150, 200, 250, 300],
        "multiples_after": 300,
        "multiple_step": 100,  # Multiples of 100g (400g, 500g, ...)
        "description": "25g, 50g, 75g, 100g, 150g, 200g, 250g, 300g, then multiples of 100g"
    },
    "salt": {
        "unit": "g",
        "below_50g_step": 10,  # Below 50g: multiples of 10g (10g, 20g, 30g, 40g)
        "fixed_sizes": [10, 20, 30, 40, 50, 100, 200, 500, 750, 1000, 2000, 5000],
        "multiples_after": 5000,
        "multiple_step": 5000,  # Multiples of 5kg (10kg, 15kg, ...)
        "description": "Below 50g: multiples of 10g. Then 50g, 100g, 200g, 500g, 750g, 1kg, 2kg, 5kg, then multiples of 5kg"
    },
    "cement": {
        "unit": "kg",
        "fixed_sizes": [1, 2, 5, 10, 20, 25, 40, 50],
        "notes": "40kg is allowed for white cement ONLY; 50kg for standard cement",
        "description": "1, 2, 5, 10, 20, 25, 40kg (white cement ONLY), 50kg"
    },
    "toilet_soap": {
        "unit": "g",
        "fixed_sizes": [25, 50, 75, 100, 125, 150],
        "multiples_after": 150,
        "multiple_step": 50,  # Multiples of 50g (200g, 250g, ...)
        "description": "25g, 50g, 75g, 100g, 125g, 150g, then multiples of 50g"
    },
    "aerated_drinks": {
        "unit": "ml",
        "fixed_sizes": [65, 100, 125, 150, 200, 250, 300, 330, 500, 750, 1000, 1500, 2000, 3000, 4000, 5000],
        "notes": "330ml is permitted for cans only",
        "description": "65ml, 100ml, 125ml, 150ml, 200ml, 250ml, 300ml, 330ml (cans only), 500ml, 750ml, 1L, 1.5L, 2L, 3L, 4L, 5L"
    }
}

NON_STANDARD_SIZE_DISCLAIMERS: List[str] = [
    "non-standard size",
    "non standard size",
    "non-standard pack",
    "non standard pack",
    "special pack",
    "promotional pack",
    "promo pack"
]

# ==========================================
# Part F - Rule 9 Language & Legibility
# ==========================================
# Hindi Devanagari Unicode range: \u0900 - \u097F
# English Latin range: [a-zA-Z]
DEFAULT_MIN_OCR_CONFIDENCE_THRESHOLD = 0.60
