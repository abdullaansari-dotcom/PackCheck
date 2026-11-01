"""Rule registry: one entry per check, with its legal reference, applicability and stated
limitations. The engine (app/engine.py) evaluates the registry in order; nothing about *which*
rule applies to *which* category is hard-coded inside check functions.

Status vocabulary (see models.Status):
    PASS, FAIL, REVIEW (= needs review), NOT_APPLICABLE, EXEMPT,
    SKIPPED_BY_TEAM_DECISION, NOT_CONFIGURED
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Dict, List, Optional, Tuple

from .data import CATEGORY_INFO, DATE_EXEMPT_CATEGORIES, SIZE_TABLE_UNIT

# applicability(category) -> (status_if_not_evaluated or None, reason)
Applicability = Callable[[str], Tuple[Optional[str], Optional[str]]]


def _always(_cat: str):
    return None, None


def _dimensions(cat: str):
    mode = CATEGORY_INFO.get(cat, {}).get("dimensions", "not_required")
    if mode == "required":
        return None, "Dimensions are required for this category (rulebook 6(1)(f) whitelist)."
    if mode == "unresolved":
        return "NOT_CONFIGURED", ("The rulebook's dimensions whitelist names bedsheets and towels only; whether "
                                  "it applies to this category is an open legal question.")
    return "NOT_APPLICABLE", "Dimensions are only required for size-dependent goods (bedsheets, towels)."


def _mfg_date(cat: str):
    if cat in DATE_EXEMPT_CATEGORIES:
        return "EXEMPT", "Month/year of manufacture is not required for this category (bidis, incense sticks, LPG)."
    return None, None


def _pack_size(cat: str):
    if cat not in SIZE_TABLE_UNIT:
        return "NOT_CONFIGURED", ("No standard pack-size table is configured for this category. The rulebook lists "
                                  "tables for tea, biscuits, salt, cement, toilet soap and aerated drinks only. "
                                  "This is not a legal exemption.")
    return None, None


def _numeral_height(_cat: str):
    return "SKIPPED_BY_TEAM_DECISION", None


@dataclass(frozen=True)
class RuleSpec:
    field: str
    title: str
    rule_reference: str
    applicability: Applicability = _always
    limitation: Optional[str] = None
    kept_for_small_packages: bool = False  # Rule 26 10-20 g/ml: still evaluated


RULES: List[RuleSpec] = [
    RuleSpec("legibility", "Legibility", "Rule 9", kept_for_small_packages=True,
             limitation="Approximated from OCR confidence; not a direct measurement of the printed label."),
    RuleSpec("contrast", "Contrast", "Rule 9", kept_for_small_packages=True,
             limitation="Luminance contrast measured in the photo; lighting and camera affect it."),
    RuleSpec("language", "Language", "Rule 9", kept_for_small_packages=True,
             limitation="Checked on the whole label, not per declaration."),
    RuleSpec("manufacturer", "Manufacturer, packer or importer", "Rule 6(1)(a)"),
    RuleSpec("generic_name", "Common name of the product", "Rule 6(1)(b)"),
    RuleSpec("net_quantity", "Net quantity", "Rule 6(1)(c)", kept_for_small_packages=True),
    RuleSpec("mfg_date", "Month and year of manufacture", "Rule 6(1)(d)", _mfg_date),
    RuleSpec("mrp", "Retail price (MRP)", "Rule 6(1)(e)", kept_for_small_packages=True,
             limitation="The paise rounding rule is not checked."),
    RuleSpec("dimensions", "Dimensions", "Rule 6(1)(f)", _dimensions),
    RuleSpec("consumer_care", "Consumer care details", "Rule 6(2)"),
    RuleSpec("pack_size", "Standard pack size", "Rule 5 / Second Schedule", _pack_size),
    RuleSpec("numeral_height", "Numeral height (font size)", "Rule 7", _numeral_height,
             limitation="Not measured: a photo has no real-world scale (finalized team decision, rulebook Part B)."),
    RuleSpec("clear_space", "Clear space around net quantity", "Rule 8", kept_for_small_packages=True,
             limitation="Estimated from ratios inside the photo; passed only with a generous margin."),
]
RULE_BY_FIELD: Dict[str, RuleSpec] = {r.field: r for r in RULES}
FIELD_ORDER = [r.field for r in RULES]
REF = {r.field: r.rule_reference for r in RULES}
