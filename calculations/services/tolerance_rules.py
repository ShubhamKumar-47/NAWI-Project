"""calculations/services/tolerance_rules.py – Configurable, version-controlled OIML R 76 tolerance rules.

⚠ NORMATIVE INTEGRITY:
All rules, acceptance limits, and tolerance tables are derived directly from:
- OIML R 76-1:2006 (E) Clause 3.5, Table 1 (MPE for weighing performance)
- OIML R 76-1:2006 (E) Clause 3.6.1 (Repeatability criterion)
- OIML R 76-1:2006 (E) Clause 3.6.2 & Clause A.4.7 (Eccentricity criterion)
- OIML R 76-1:2006 (E) Clause 3.8 & Clause A.4.8 (Discrimination criterion)
- OIML R 76-1:2006 (E) Clause 3.5.3.4 & Clause A.4.6 (Tare weighing criterion)
- OIML R 76-1:2006 (E) Clause A.4.1 (Zero-setting error limits)

Unverified rules or unsupported editions are marked as NOT CONFIGURED and return
NOT_EVALUATED to prevent hazardous or illegitimate compliance decisions.
"""
from dataclasses import dataclass
from decimal import Decimal
from typing import Optional

from calculations.constants import CLASS_I, CLASS_II, CLASS_III, CLASS_IIII


# Version-controlled rule set definitions
DEFAULT_STANDARD_EDITION = "OIML R 76-1:2006"
DEFAULT_RULE_VERSION = "R76-2006-v1.0"

SUPPORTED_EDITIONS = {
    "R76-2006": "R76-2006-v1.0",
    "R76-1992": "R76-1992-v1.0",
    "OIML R 76-1:2006": "R76-2006-v1.0",
    "OIML R 76-1:1992": "R76-1992-v1.0",
}


@dataclass(frozen=True)
class ToleranceRuleEvaluation:
    """Encapsulates the result of querying a tolerance rule."""
    is_configured: bool
    standard_edition: str
    rule_version: str
    standard_clause: str
    mpe_in_e: Optional[Decimal]
    mpe_value: Optional[Decimal]  # In measurement units (mpe_in_e * e)
    explanation: str


# ── OIML R 76-1:2006 Table 1: MPE in units of verification scale interval (e) ─
# Format: (min_m_in_e, max_m_in_e, mpe_initial_e, mpe_service_e)
TABLE_1_RULES_2006 = {
    CLASS_I: [
        (Decimal("0"), Decimal("50000"), Decimal("0.5"), Decimal("1.0")),
        (Decimal("50000"), Decimal("200000"), Decimal("1.0"), Decimal("2.0")),
        (Decimal("200000"), Decimal("Infinity"), Decimal("1.5"), Decimal("3.0")),
    ],
    CLASS_II: [
        (Decimal("0"), Decimal("5000"), Decimal("0.5"), Decimal("1.0")),
        (Decimal("5000"), Decimal("20000"), Decimal("1.0"), Decimal("2.0")),
        (Decimal("20000"), Decimal("100000"), Decimal("1.5"), Decimal("3.0")),
    ],
    CLASS_III: [
        (Decimal("0"), Decimal("500"), Decimal("0.5"), Decimal("1.0")),
        (Decimal("500"), Decimal("2000"), Decimal("1.0"), Decimal("2.0")),
        (Decimal("2000"), Decimal("10000"), Decimal("1.5"), Decimal("3.0")),
    ],
    CLASS_IIII: [
        (Decimal("0"), Decimal("50"), Decimal("0.5"), Decimal("1.0")),
        (Decimal("50"), Decimal("200"), Decimal("1.0"), Decimal("2.0")),
        (Decimal("200"), Decimal("1000"), Decimal("1.5"), Decimal("3.0")),
    ],
}

# 1992 edition shares the same primary verification table Table 1
TABLE_1_RULES_1992 = TABLE_1_RULES_2006


def get_weighing_mpe(
    nominal_load: Decimal,
    accuracy_class: str,
    actual_scale_interval: Decimal,
    is_initial_verification: bool = True,
    standard_edition: str = DEFAULT_STANDARD_EDITION,
) -> ToleranceRuleEvaluation:
    """
    Look up the applicable Maximum Permissible Error (MPE) per OIML R 76 Table 1.
    Never uses universal or hardcoded arbitrary tolerances.
    """
    rule_version = SUPPORTED_EDITIONS.get(standard_edition)
    clause = f"{standard_edition} §3.5 Table 1"

    if not rule_version:
        return ToleranceRuleEvaluation(
            is_configured=False,
            standard_edition=standard_edition,
            rule_version="UNCONFIGURED",
            standard_clause=clause,
            mpe_in_e=None,
            mpe_value=None,
            explanation=f"Standard edition '{standard_edition}' is NOT CONFIGURED. Evaluation prevented.",
        )

    table_data = TABLE_1_RULES_2006 if "2006" in standard_edition else TABLE_1_RULES_1992
    rules = table_data.get(accuracy_class)
    if not rules:
        return ToleranceRuleEvaluation(
            is_configured=False,
            standard_edition=standard_edition,
            rule_version=rule_version,
            standard_clause=clause,
            mpe_in_e=None,
            mpe_value=None,
            explanation=f"Accuracy class '{accuracy_class}' is NOT CONFIGURED for {standard_edition}.",
        )

    if actual_scale_interval <= Decimal("0"):
        return ToleranceRuleEvaluation(
            is_configured=False,
            standard_edition=standard_edition,
            rule_version=rule_version,
            standard_clause=clause,
            mpe_in_e=None,
            mpe_value=None,
            explanation="Verification scale interval (e) must be strictly positive.",
        )

    # Compute load in terms of verification scale intervals (m / e)
    # Never round intermediate values
    m_in_e = abs(nominal_load) / actual_scale_interval

    mpe_e: Optional[Decimal] = None
    applied_range = ""

    for min_e, max_e, initial_limit, service_limit in rules:
        # Range is min_e < m <= max_e, except for 0 where min_e <= m <= max_e
        if min_e == Decimal("0"):
            in_range = (min_e <= m_in_e <= max_e)
        else:
            in_range = (min_e < m_in_e <= max_e)

        if in_range:
            mpe_e = initial_limit if is_initial_verification else service_limit
            applied_range = f"{min_e} e < m <= {max_e} e"
            break

    if mpe_e is None:
        # Load exceeds maximum defined scale range
        return ToleranceRuleEvaluation(
            is_configured=False,
            standard_edition=standard_edition,
            rule_version=rule_version,
            standard_clause=clause,
            mpe_in_e=None,
            mpe_value=None,
            explanation=f"Applied load {nominal_load} ({m_in_e} e) exceeds maximum defined load range in Table 1.",
        )

    mpe_value = mpe_e * actual_scale_interval
    verif_type = "initial verification" if is_initial_verification else "in-service verification"
    explanation = (
        f"Per {clause} ({rule_version}) for Class {accuracy_class} ({verif_type}): "
        f"Load m = {nominal_load} ({m_in_e:.4f} e) falls into range [{applied_range}]. "
        f"MPE is ±{mpe_e} e = ±{mpe_value}."
    )

    return ToleranceRuleEvaluation(
        is_configured=True,
        standard_edition=standard_edition,
        rule_version=rule_version,
        standard_clause=clause,
        mpe_in_e=mpe_e,
        mpe_value=mpe_value,
        explanation=explanation,
    )


def get_repeatability_tolerance(
    nominal_load: Decimal,
    accuracy_class: str,
    actual_scale_interval: Decimal,
    is_initial_verification: bool = True,
    standard_edition: str = DEFAULT_STANDARD_EDITION,
) -> ToleranceRuleEvaluation:
    """
    Repeatability acceptance limit per OIML R 76-1:2006 Clause 3.6.1:
    Range R = I_max - I_min shall not exceed |MPE| for that nominal load.
    """
    eval_res = get_weighing_mpe(
        nominal_load=nominal_load,
        accuracy_class=accuracy_class,
        actual_scale_interval=actual_scale_interval,
        is_initial_verification=is_initial_verification,
        standard_edition=standard_edition,
    )
    if not eval_res.is_configured:
        return eval_res

    clause = f"{standard_edition} §3.6.1 & §A.4.10"
    explanation = (
        f"Per {clause} ({eval_res.rule_version}): The difference between results of successive "
        f"weighings of the same load (range R = I_max - I_min) shall not exceed |MPE| for load m = {nominal_load}. "
        f"Allowable range limit is {eval_res.mpe_value} (±{eval_res.mpe_in_e} e)."
    )
    return ToleranceRuleEvaluation(
        is_configured=True,
        standard_edition=standard_edition,
        rule_version=eval_res.rule_version,
        standard_clause=clause,
        mpe_in_e=eval_res.mpe_in_e,
        mpe_value=eval_res.mpe_value,
        explanation=explanation,
    )


def get_eccentricity_tolerance(
    nominal_load: Decimal,
    accuracy_class: str,
    actual_scale_interval: Decimal,
    is_initial_verification: bool = True,
    standard_edition: str = DEFAULT_STANDARD_EDITION,
) -> ToleranceRuleEvaluation:
    """
    Eccentricity acceptance limit per OIML R 76-1:2006 Clause 3.6.2:
    Errors on off-centre loading shall not exceed MPE for that load.
    """
    eval_res = get_weighing_mpe(
        nominal_load=nominal_load,
        accuracy_class=accuracy_class,
        actual_scale_interval=actual_scale_interval,
        is_initial_verification=is_initial_verification,
        standard_edition=standard_edition,
    )
    if not eval_res.is_configured:
        return eval_res

    clause = f"{standard_edition} §3.6.2 & §A.4.7"
    explanation = (
        f"Per {clause} ({eval_res.rule_version}): Error of indication at each off-centre position "
        f"shall not exceed MPE for load m = {nominal_load}. Maximum permissible error is ±{eval_res.mpe_value} "
        f"(±{eval_res.mpe_in_e} e)."
    )
    return ToleranceRuleEvaluation(
        is_configured=True,
        standard_edition=standard_edition,
        rule_version=eval_res.rule_version,
        standard_clause=clause,
        mpe_in_e=eval_res.mpe_in_e,
        mpe_value=eval_res.mpe_value,
        explanation=explanation,
    )


def get_zero_setting_tolerance(
    actual_scale_interval: Decimal,
    scale_interval: Decimal,
    has_auxiliary_device: bool = False,
    standard_edition: str = DEFAULT_STANDARD_EDITION,
) -> ToleranceRuleEvaluation:
    """
    Zero-setting tolerance per OIML R 76-1:2006 Clause A.4.1:
    Zero error shall not exceed ±0.25e (or ±0.5d if instrument has auxiliary indicating device).
    """
    rule_version = SUPPORTED_EDITIONS.get(standard_edition, DEFAULT_RULE_VERSION)
    clause = f"{standard_edition} §A.4.1 – §A.4.3"

    if has_auxiliary_device and scale_interval < actual_scale_interval:
        mpe_val = Decimal("0.5") * scale_interval
        explanation = (
            f"Per {clause} ({rule_version}) for instrument with auxiliary indicating device: "
            f"Maximum zero error is ±0.5d = ±{mpe_val} (where d = {scale_interval})."
        )
    else:
        mpe_val = Decimal("0.25") * actual_scale_interval
        explanation = (
            f"Per {clause} ({rule_version}): Maximum zero-setting and zero-tracking error "
            f"shall not exceed ±0.25e = ±{mpe_val} (where e = {actual_scale_interval})."
        )

    return ToleranceRuleEvaluation(
        is_configured=True,
        standard_edition=standard_edition,
        rule_version=rule_version,
        standard_clause=clause,
        mpe_in_e=Decimal("0.25"),
        mpe_value=mpe_val,
        explanation=explanation,
    )


def get_discrimination_tolerance(
    scale_interval: Decimal,
    standard_edition: str = DEFAULT_STANDARD_EDITION,
) -> ToleranceRuleEvaluation:
    """
    Discrimination criterion per OIML R 76-1:2006 Clause 3.8 & Clause A.4.8:
    Extra load ΔL ≈ 1.4d placed gently on loaded receptor shall cause change of indication of at least 1.0d.
    """
    rule_version = SUPPORTED_EDITIONS.get(standard_edition, DEFAULT_RULE_VERSION)
    clause = f"{standard_edition} §3.8 & §A.4.8"
    explanation = (
        f"Per {clause} ({rule_version}): An additional load equal to 1.4d ({Decimal('1.4') * scale_interval:.4f}) "
        f"placed gently on the loaded receptor shall cause an increase of indication of at least 1d ({scale_interval})."
    )
    return ToleranceRuleEvaluation(
        is_configured=True,
        standard_edition=standard_edition,
        rule_version=rule_version,
        standard_clause=clause,
        mpe_in_e=None,
        mpe_value=scale_interval,
        explanation=explanation,
    )
