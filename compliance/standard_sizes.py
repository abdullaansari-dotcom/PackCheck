"""
Part C - Standard Pack Sizes Engine (Rule 5 + Second Schedule)
SIH 2026 - Problem Statement SIH26034
Legal Metrology (Packaged Commodities) Rules, 2011

Certain commodities may ONLY be legally sold in specific, government-listed sizes.
If sold in a non-standard size, an explicit 'Non-standard size' disclaimer is mandatory.
"""

from typing import Optional, Dict, Any
from .models import FieldCheckResult, FieldStatus, ViolationCode
from .constants import (
    STANDARD_PACK_SIZES,
    NON_STANDARD_SIZE_DISCLAIMERS,
    RULE_REF_STANDARD_SIZES,
)


def is_allowed_standard_size(commodity: str, quantity_value: float, quantity_unit: str) -> bool:
    """
    Checks if a given quantity and unit match the statutory Second Schedule list.
    """
    comm_key = commodity.lower().strip().replace(" ", "_")
    
    # Map common aliases to keys
    if comm_key in ["tea", "tea_leaf", "tea_powder", "chai"]:
        comm_key = "tea"
    elif comm_key in ["biscuit", "biscuits", "cookies", "cookie"]:
        comm_key = "biscuits"
    elif comm_key in ["salt", "table_salt", "edible_salt"]:
        comm_key = "salt"
    elif comm_key in ["cement", "portland_cement", "white_cement"]:
        comm_key = "cement"
    elif comm_key in ["toilet_soap", "soap", "bathing_bar", "bath_soap"]:
        comm_key = "toilet_soap"
    elif comm_key in ["aerated_drink", "aerated_drinks", "soft_drink", "cold_drink", "soda", "carbonated_beverage"]:
        comm_key = "aerated_drinks"
    else:
        # Not a regulated standard-pack commodity
        return True

    cfg = STANDARD_PACK_SIZES.get(comm_key)
    if not cfg:
        return True

    unit = quantity_unit.lower().strip()

    # Convert to base unit of the commodity configuration
    val: float = quantity_value
    if cfg["unit"] == "g":
        if unit in ["kg", "kgs", "kilogram", "kilograms"]:
            val = quantity_value * 1000.0
        elif unit in ["g", "gm", "gms", "gram", "grams"]:
            val = quantity_value
        else:
            return False  # Non-mass unit for mass commodity

    elif cfg["unit"] == "ml":
        if unit in ["l", "lt", "ltr", "litre", "litres", "liter", "liters"]:
            val = quantity_value * 1000.0
        elif unit in ["ml", "m.l.", "m.l", "millilitre", "millilitres"]:
            val = quantity_value
        elif unit in ["cl"]:
            val = quantity_value * 10.0
        else:
            return False

    elif cfg["unit"] == "kg":
        if unit in ["g", "gm", "gms", "gram", "grams"]:
            val = quantity_value / 1000.0
        elif unit in ["kg", "kgs", "kilogram", "kilograms"]:
            val = quantity_value
        else:
            return False

    # Round to avoid floating point precision issues
    val = round(val, 2)

    # 1. Check fixed sizes
    if val in [round(float(s), 2) for s in cfg.get("fixed_sizes", [])]:
        return True

    # 2. Check special rules: Salt below 50g multiples of 10g
    if comm_key == "salt" and val < 50:
        return (val > 0) and (val % cfg.get("below_50g_step", 10) == 0)

    # 3. Check multiples after threshold
    multiples_after = cfg.get("multiples_after")
    multiple_step = cfg.get("multiple_step")
    if multiples_after is not None and multiple_step is not None and val > multiples_after:
        remainder = (val - multiples_after) % multiple_step
        if remainder == 0 or abs(remainder - multiple_step) < 1e-4:
            return True

    return False


def validate_standard_pack_size(
    commodity: Optional[str],
    quantity_value: Optional[float],
    quantity_unit: Optional[str],
    has_disclaimer: bool = False,
    raw_text: Optional[str] = None
) -> FieldCheckResult:
    """
    Validates commodity standard pack size under Rule 5 & Second Schedule.
    """
    if not commodity or quantity_value is None or not quantity_unit:
        return FieldCheckResult(
            field="standard_pack_size",
            status=FieldStatus.NOT_APPLICABLE,
            rule_reference=RULE_REF_STANDARD_SIZES,
            message="No regulated standard-pack commodity specified."
        )

    # Check for disclaimer in raw text if not explicitly flagged
    if not has_disclaimer and raw_text:
        text_lower = raw_text.lower()
        if any(d in text_lower for d in NON_STANDARD_SIZE_DISCLAIMERS):
            has_disclaimer = True

    is_standard = is_allowed_standard_size(commodity, quantity_value, quantity_unit)
    
    if is_standard:
        return FieldCheckResult(
            field="standard_pack_size",
            status=FieldStatus.PASS,
            detected_text=f"{quantity_value} {quantity_unit}",
            rule_reference=RULE_REF_STANDARD_SIZES,
            message=f"Pack size {quantity_value}{quantity_unit} complies with statutory standard sizes for {commodity}."
        )
    
    # If not a standard size, check if disclaimer is present
    if has_disclaimer:
        return FieldCheckResult(
            field="standard_pack_size",
            status=FieldStatus.PASS,
            detected_text=f"{quantity_value} {quantity_unit} [With 'Non-standard size' disclaimer]",
            rule_reference=RULE_REF_STANDARD_SIZES,
            message=f"Non-standard pack size ({quantity_value}{quantity_unit}) is permitted because required 'Non-standard size' disclaimer is present."
        )
    
    # Violation: Non-standard size without disclaimer
    cfg = STANDARD_PACK_SIZES.get(commodity.lower().strip().replace(" ", "_"), {})
    allowed_desc = cfg.get("description", "specified sizes in Second Schedule")

    return FieldCheckResult(
        field="standard_pack_size",
        status=FieldStatus.FAIL,
        violation_code=ViolationCode.NONSTANDARD_PACK,
        detected_text=f"{quantity_value} {quantity_unit}",
        rule_reference=RULE_REF_STANDARD_SIZES,
        message=f"Pack size {quantity_value}{quantity_unit} is NOT a standard legal size for '{commodity}' (Standard sizes: {allowed_desc}) and package lacks the mandatory 'Non-standard size' disclaimer."
    )
