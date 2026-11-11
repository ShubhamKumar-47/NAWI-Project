"""calculations/services/error_calculation.py – Core metrological error calculation functions.

Maintains absolute precision using Python Decimal throughout intermediate calculations.
Separates internal calculation precision from display-level rounding.
"""
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional


def calculate_raw_error(indication: Decimal, reference_load: Decimal) -> Decimal:
    """
    Error of indication per OIML R 76 §A.4.4.2:
    E = I - L
    """
    return indication - reference_load


def calculate_corrected_error(
    raw_error: Decimal,
    zero_error: Decimal = Decimal("0"),
) -> Decimal:
    """
    Corrected error of indication per OIML R 76 §A.4.4.3:
    Ec = E - E0
    """
    return raw_error - zero_error


def calculate_turning_point_indication(
    indication: Decimal,
    scale_interval: Decimal,
    small_weights_added: Decimal,
) -> Decimal:
    """
    True indication before rounding per OIML R 76 Clause A.4.4.3:
    P = I + 0.5d - ΔL
    """
    return indication + Decimal("0.5") * scale_interval - small_weights_added


def calculate_turning_point_error(
    indication: Decimal,
    scale_interval: Decimal,
    small_weights_added: Decimal,
    reference_load: Decimal,
) -> Decimal:
    """
    Error determined by turning-point method per OIML R 76 Clause A.4.4.3:
    E = P - L = (I + 0.5d - ΔL) - L
    """
    p = calculate_turning_point_indication(indication, scale_interval, small_weights_added)
    return p - reference_load


def calculate_net_error(
    tare_load: Decimal,
    gross_indication: Decimal,
    net_indication: Decimal,
) -> Decimal:
    """
    Net weighing error per OIML R 76 Clause 3.5.3.4:
    E_net = I_net - (I_gross - L_tare)
    """
    effective_net = gross_indication - tare_load
    return net_indication - effective_net


def format_display_decimal(
    val: Optional[Decimal],
    decimal_places: int = 4,
    show_plus_sign: bool = False,
) -> str:
    """
    Format a Decimal for user interface display.
    Never mutates internal Decimal calculation objects.
    """
    if val is None:
        return "—"
    quant = Decimal("10") ** (-decimal_places)
    rounded = val.quantize(quant, rounding=ROUND_HALF_UP)
    if show_plus_sign and rounded > 0:
        return f"+{rounded:.{decimal_places}f}"
    return f"{rounded:.{decimal_places}f}"

