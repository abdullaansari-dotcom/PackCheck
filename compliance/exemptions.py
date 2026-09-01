"""
Part E - Exemptions Engine (Rule 26)
SIH 2026 - Problem Statement SIH26034
Legal Metrology (Packaged Commodities) Rules, 2011

Rule 26 specifies exemptions from declaration requirements.
This module is evaluated FIRST before running field-level compliance checks.
"""

from typing import Optional
from .models import ExemptionResult, PackageCategory
from .constants import (
    VERY_SMALL_PACKAGE_MAX_WEIGHT_G,
    VERY_SMALL_PACKAGE_MAX_VOLUME_ML,
    SMALL_PACKAGE_PARTIAL_MAX_WEIGHT_G,
    SMALL_PACKAGE_PARTIAL_MAX_VOLUME_ML,
    LARGE_AGRICULTURAL_PRODUCE_MIN_WEIGHT_KG,
    RULE_REF_EXEMPTIONS,
)


def evaluate_exemption(
    category: Optional[PackageCategory | str] = None,
    net_quantity_value: Optional[float] = None,
    net_quantity_unit: Optional[str] = None,
    is_fast_food: bool = False,
    is_scheduled_drug: bool = False,
    is_agricultural_produce: bool = False
) -> ExemptionResult:
    """
    Evaluates whether a package qualifies for full or partial exemption under Rule 26.
    
    Returns:
        ExemptionResult indicating if package is exempt, if partial exemption applies,
        and statutory justification.
    """
    cat_str = str(category).lower() if category else ""

    # 1. Fast Food Check
    if is_fast_food or cat_str == PackageCategory.FAST_FOOD.value or "fast_food" in cat_str or "restaurant" in cat_str:
        return ExemptionResult(
            is_exempt=True,
            is_partial_exemption=False,
            exemption_type="FAST_FOOD",
            reason="Package packed directly by restaurant/hotel for immediate sale is exempt under Rule 26.",
            rule_reference=RULE_REF_EXEMPTIONS
        )

    # 2. Scheduled Drug Formulations Check (DPCO)
    if is_scheduled_drug or cat_str == PackageCategory.SCHEDULED_DRUG.value or "scheduled_drug" in cat_str or "dpco" in cat_str:
        return ExemptionResult(
            is_exempt=True,
            is_partial_exemption=False,
            exemption_type="SCHEDULED_DRUG",
            reason="Scheduled drug formulations are governed by the Drugs (Price Control) Order and exempt under Rule 26.",
            rule_reference=RULE_REF_EXEMPTIONS
        )

    # 3. Large Agricultural Produce (> 50kg)
    if (is_agricultural_produce or cat_str == PackageCategory.LARGE_AGRICULTURAL.value or "agricultural" in cat_str) and net_quantity_value is not None:
        unit = (net_quantity_unit or "").lower()
        val_kg = net_quantity_value
        if unit in ["g", "gm", "grams", "gram"]:
            val_kg = net_quantity_value / 1000.0
        
        if val_kg > LARGE_AGRICULTURAL_PRODUCE_MIN_WEIGHT_KG:
            return ExemptionResult(
                is_exempt=True,
                is_partial_exemption=False,
                exemption_type="LARGE_AGRICULTURAL_PRODUCE",
                reason=f"Agricultural produce package ({val_kg}kg) exceeds 50kg threshold and is exempt under Rule 26.",
                rule_reference=RULE_REF_EXEMPTIONS
            )

    # 4. Very Small Packages (<= 10g or <= 10ml) - Fully Exempt from Chapter II
    if net_quantity_value is not None and net_quantity_unit:
        unit = net_quantity_unit.lower()
        
        # Normalize to grams / ml
        normalized_mass_g: Optional[float] = None
        normalized_vol_ml: Optional[float] = None

        if unit in ["g", "gm", "gms", "gram", "grams"]:
            normalized_mass_g = net_quantity_value
        elif unit in ["mg", "mgs", "milligram", "milligrams"]:
            normalized_mass_g = net_quantity_value / 1000.0
        elif unit in ["kg", "kgs", "kilogram", "kilograms"]:
            normalized_mass_g = net_quantity_value * 1000.0
        
        if unit in ["ml", "m.l.", "m.l", "millilitre", "millilitres", "milliliter", "milliliters"]:
            normalized_vol_ml = net_quantity_value
        elif unit in ["l", "lt", "ltr", "litre", "litres", "liter", "liters"]:
            normalized_vol_ml = net_quantity_value * 1000.0
        elif unit in ["cl"]:
            normalized_vol_ml = net_quantity_value * 10.0

        if (normalized_mass_g is not None and normalized_mass_g <= VERY_SMALL_PACKAGE_MAX_WEIGHT_G) or \
           (normalized_vol_ml is not None and normalized_vol_ml <= VERY_SMALL_PACKAGE_MAX_VOLUME_ML):
            return ExemptionResult(
                is_exempt=True,
                is_partial_exemption=False,
                exemption_type="VERY_SMALL_PACKAGE",
                reason=f"Package net content ({net_quantity_value} {net_quantity_unit}) <= 10g/10ml is fully exempt from Chapter II under Rule 26.",
                rule_reference=RULE_REF_EXEMPTIONS
            )

        # 5. Small Packages Partial Exemption (10g-20g / 10ml-20ml)
        # Exempt from most rules, but MRP + Net Quantity still required
        if (normalized_mass_g is not None and VERY_SMALL_PACKAGE_MAX_WEIGHT_G < normalized_mass_g <= SMALL_PACKAGE_PARTIAL_MAX_WEIGHT_G) or \
           (normalized_vol_ml is not None and VERY_SMALL_PACKAGE_MAX_VOLUME_ML < normalized_vol_ml <= SMALL_PACKAGE_PARTIAL_MAX_VOLUME_ML):
            return ExemptionResult(
                is_exempt=False,
                is_partial_exemption=True,
                exemption_type="SMALL_PACKAGE_PARTIAL",
                reason=f"Small package ({net_quantity_value} {net_quantity_unit}) is exempt from manufacturer, date, consumer care declarations under Rule 26, but Net Quantity and MRP are still mandatory.",
                rule_reference=RULE_REF_EXEMPTIONS
            )

    # No exemption
    return ExemptionResult(
        is_exempt=False,
        is_partial_exemption=False,
        exemption_type=None,
        reason="Package does not qualify for exemptions under Rule 26.",
        rule_reference=RULE_REF_EXEMPTIONS
    )
