"""
Legal Metrology Rule Verification Modules
SIH 2026 - Problem Statement SIH26034
"""

from .rule_6_1_a_manufacturer import check_manufacturer_details
from .rule_6_1_b_generic_name import check_generic_name
from .rule_6_1_c_net_quantity import check_net_quantity
from .rule_6_1_d_mfg_date import check_mfg_packing_date
from .rule_6_1_e_mrp import check_mrp_declaration
from .rule_6_1_f_dimensions import check_dimensions_declaration
from .rule_6_2_consumer_care import check_consumer_care_details
from .rule_9_language_legibility import check_language_compliance, detect_scripts

__all__ = [
    "check_manufacturer_details",
    "check_generic_name",
    "check_net_quantity",
    "check_mfg_packing_date",
    "check_mrp_declaration",
    "check_dimensions_declaration",
    "check_consumer_care_details",
    "check_language_compliance",
    "detect_scripts",
]
