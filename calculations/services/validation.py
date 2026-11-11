"""calculations/services/validation.py – Input validation for metrological parameters and observations."""
from decimal import Decimal, InvalidOperation
from typing import Any, List, Optional, Sequence

from calculations.constants import ACCURACY_CLASSES
from calculations.exceptions import InsufficientDataError, InvalidInputError


def coerce_decimal(value: Any, field_name: str) -> Decimal:
    """Safely coerce any numeric or string value to Decimal, raising InvalidInputError if invalid."""
    if value is None or (isinstance(value, str) and not value.strip()):
        raise InvalidInputError(f"Missing required numeric value for '{field_name}'.")
    try:
        return Decimal(str(value).strip())
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise InvalidInputError(f"Invalid numeric value '{value}' for '{field_name}': {exc}")


def validate_instrument_parameters(
    accuracy_class: str,
    max_capacity: Decimal,
    min_capacity: Decimal,
    scale_interval: Decimal,
    actual_scale_interval: Decimal,
) -> None:
    """Validate instrument metrological characteristics."""
    if accuracy_class not in ACCURACY_CLASSES:
        raise InvalidInputError(
            f"Invalid accuracy class '{accuracy_class}'. Must be one of: {ACCURACY_CLASSES}."
        )
    if max_capacity <= Decimal("0"):
        raise InvalidInputError(f"Max capacity must be strictly positive (got {max_capacity}).")
    if min_capacity < Decimal("0"):
        raise InvalidInputError(f"Min capacity cannot be negative (got {min_capacity}).")
    if min_capacity >= max_capacity:
        raise InvalidInputError(
            f"Min capacity ({min_capacity}) must be strictly less than Max capacity ({max_capacity})."
        )
    if scale_interval <= Decimal("0"):
        raise InvalidInputError(f"Actual scale interval (d) must be positive (got {scale_interval}).")
    if actual_scale_interval <= Decimal("0"):
        raise InvalidInputError(f"Verification scale interval (e) must be positive (got {actual_scale_interval}).")


def validate_weighing_input(
    nominal_load: Decimal,
    indication: Decimal,
    tare_applied: Decimal = Decimal("0"),
) -> None:
    """Validate a single weighing observation input."""
    if nominal_load < Decimal("0"):
        raise InvalidInputError(f"Nominal test load cannot be negative (got {nominal_load}).")
    if tare_applied < Decimal("0"):
        raise InvalidInputError(f"Applied tare cannot be negative (got {tare_applied}).")


def validate_repeatability_input(
    nominal_load: Decimal,
    indications: Sequence[Decimal],
    min_repetitions: int = 3,
) -> None:
    """Validate repeatability observations according to OIML R 76 §A.4.10."""
    if nominal_load <= Decimal("0"):
        raise InvalidInputError(f"Repeatability reference load must be strictly positive (got {nominal_load}).")
    if not indications or len(indications) < min_repetitions:
        raise InsufficientDataError(
            f"Repeatability test requires at least {min_repetitions} repetitions per OIML R 76 §A.4.10 "
            f"(received {len(indications) if indications else 0})."
        )


def validate_eccentricity_input(
    nominal_load: Decimal,
    indication: Decimal,
    position: str,
) -> None:
    """Validate eccentricity observation."""
    if nominal_load <= Decimal("0"):
        raise InvalidInputError(f"Eccentricity test load must be strictly positive (got {nominal_load}).")
    if not position or not position.strip():
        raise InvalidInputError("Receptor load position must be specified.")


def validate_discrimination_input(
    test_load: Decimal,
    small_weight_added: Decimal,
    scale_interval: Decimal,
) -> None:
    """Validate discrimination observation."""
    if test_load < Decimal("0"):
        raise InvalidInputError(f"Discrimination test load cannot be negative (got {test_load}).")
    if small_weight_added <= Decimal("0"):
        raise InvalidInputError(
            f"Small weight added (ΔL) must be strictly positive (got {small_weight_added})."
        )
    if scale_interval <= Decimal("0"):
        raise InvalidInputError("Scale interval (d) must be strictly positive.")


def validate_zero_test_input(
    scale_interval: Decimal,
    actual_scale_interval: Decimal,
    small_weight_added: Optional[Decimal] = None,
) -> None:
    """Validate zero setting and tracking observation."""
    if scale_interval <= Decimal("0") or actual_scale_interval <= Decimal("0"):
        raise InvalidInputError("Scale intervals (d and e) must be strictly positive.")
    if small_weight_added is not None and small_weight_added < Decimal("0"):
        raise InvalidInputError(f"Small weight added (ΔL) cannot be negative (got {small_weight_added}).")

