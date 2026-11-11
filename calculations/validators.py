"""calculations/validators.py – Metrological input validation helpers."""
from decimal import Decimal
from typing import List
from .constants import ACCURACY_CLASSES


def validate_metrological_parameters(
    accuracy_class: str,
    max_capacity: Decimal,
    min_capacity: Decimal,
    scale_interval: Decimal,
    actual_scale_interval: Decimal,
) -> List[str]:
    """Validate fundamental metrological properties of the instrument."""
    errors: List[str] = []

    if accuracy_class not in ACCURACY_CLASSES:
        errors.append(f"Invalid accuracy class '{accuracy_class}'. Must be one of {ACCURACY_CLASSES}.")

    if max_capacity <= 0:
        errors.append("Max capacity must be greater than zero.")

    if min_capacity < 0:
        errors.append("Min capacity cannot be negative.")

    if min_capacity >= max_capacity:
        errors.append("Min capacity must be strictly less than Max capacity.")

    if scale_interval <= 0:
        errors.append("Scale interval (d) must be greater than zero.")

    if actual_scale_interval <= 0:
        errors.append("Verification scale interval (e) must be greater than zero.")

    return errors

