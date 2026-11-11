"""calculations/services/tare.py – OIML R 76 Tare Weighing Test Service (§A.4.6 / §3.5.3)."""
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Dict, Optional

from calculations.models import CalculationCompliance, CalculationProcedureType, CalculationRecord
from .error_calculation import calculate_net_error, format_display_decimal
from .tolerance_rules import DEFAULT_STANDARD_EDITION, get_weighing_mpe
from .validation import coerce_decimal


@dataclass
class TareCalculationResult:
    """Standardized output of tare weighing evaluation."""
    tare_load: Decimal
    net_load: Decimal
    gross_indication: Decimal
    net_indication: Decimal
    calculated_net_error: Decimal
    permissible_mpe: Optional[Decimal]
    comparison_result: str  # "PASS" | "FAIL" | "NOT_EVALUATED"
    is_rule_configured: bool
    standard_edition: str
    rule_version: str
    standard_clause: str
    explanation: str
    computed_metadata: Dict[str, Any]


class TareService:
    """Service layer for evaluating OIML R 76 Tare balancing and weighing operations."""

    @staticmethod
    def calculate_tare_point(
        tare_load: Any,
        gross_indication: Any,
        net_indication: Any,
        accuracy_class: str,
        actual_scale_interval: Any,
        net_load: Any = Decimal("0"),
        is_initial_verification: bool = True,
        standard_edition: str = DEFAULT_STANDARD_EDITION,
    ) -> TareCalculationResult:
        """Calculate net error E_net = I_net - (I_gross - L_tare) and evaluate against net MPE."""
        t_load = coerce_decimal(tare_load, "tare_load")
        g_ind = coerce_decimal(gross_indication, "gross_indication")
        n_ind = coerce_decimal(net_indication, "net_indication")
        n_load = coerce_decimal(net_load, "net_load") if net_load is not None else Decimal("0")
        e_val = coerce_decimal(actual_scale_interval, "actual_scale_interval")

        net_error = calculate_net_error(tare_load=t_load, gross_indication=g_ind, net_indication=n_ind)

        # MPE applies to the net indication value
        rule_eval = get_weighing_mpe(
            nominal_load=n_ind,
            accuracy_class=accuracy_class,
            actual_scale_interval=e_val,
            is_initial_verification=is_initial_verification,
            standard_edition=standard_edition,
        )

        effective_net = g_ind - t_load
        clause = f"{standard_edition} §3.5.3.4 & §A.4.6"

        computed_metadata = {
            "tare_load": float(t_load),
            "net_load": float(n_load),
            "gross_indication": float(g_ind),
            "net_indication": float(n_ind),
            "effective_net": float(effective_net),
            "net_error": float(net_error),
        }

        if not rule_eval.is_configured:
            return TareCalculationResult(
                tare_load=t_load,
                net_load=n_load,
                gross_indication=g_ind,
                net_indication=n_ind,
                calculated_net_error=net_error,
                permissible_mpe=None,
                comparison_result=CalculationCompliance.NOT_EVALUATED,
                is_rule_configured=False,
                standard_edition=standard_edition,
                rule_version=rule_eval.rule_version,
                standard_clause=clause,
                explanation=f"Tare load {t_load}: Net error = {net_error}. {rule_eval.explanation}",
                computed_metadata=computed_metadata,
            )

        mpe = rule_eval.mpe_value
        is_pass = abs(net_error) <= mpe
        comp_res = CalculationCompliance.PASS if is_pass else CalculationCompliance.FAIL
        verdict = "satisfies" if is_pass else "exceeds"

        explanation = (
            f"Tare weighing at tare load T = {t_load}: Gross indication I_G = {g_ind}, Net indication I_N = {n_ind}. "
            f"Effective net load = I_G - T = {effective_net}. "
            f"Net error E_net = I_N - (I_G - T) = {n_ind} - {effective_net} = {format_display_decimal(net_error, 6, True)}. "
            f"Per {clause}: Allowable MPE for net value ({n_ind}) is ±{format_display_decimal(mpe, 6)}. "
            f"Comparison: |{format_display_decimal(net_error, 6)}| {verdict} permissible error (±{format_display_decimal(mpe, 6)}). "
            f"Result: {comp_res}."
        )

        return TareCalculationResult(
            tare_load=t_load,
            net_load=n_load,
            gross_indication=g_ind,
            net_indication=n_ind,
            calculated_net_error=net_error,
            permissible_mpe=mpe,
            comparison_result=comp_res,
            is_rule_configured=True,
            standard_edition=standard_edition,
            rule_version=rule_eval.rule_version,
            standard_clause=clause,
            explanation=explanation,
            computed_metadata=computed_metadata,
        )

    @classmethod
    def save_record(
        cls,
        session,
        tare_load: Any,
        gross_indication: Any,
        net_indication: Any,
        accuracy_class: str,
        actual_scale_interval: Any,
        net_load: Any = Decimal("0"),
        sequence_number: int = 1,
        measurement_id: Optional[int] = None,
        calculated_by=None,
        is_initial_verification: bool = True,
        standard_edition: str = DEFAULT_STANDARD_EDITION,
    ) -> CalculationRecord:
        """Persist tare weighing calculation to CalculationRecord."""
        res = cls.calculate_tare_point(
            tare_load=tare_load,
            gross_indication=gross_indication,
            net_indication=net_indication,
            accuracy_class=accuracy_class,
            actual_scale_interval=actual_scale_interval,
            net_load=net_load,
            is_initial_verification=is_initial_verification,
            standard_edition=standard_edition,
        )

        record, _ = CalculationRecord.objects.update_or_create(
            session=session,
            procedure_type=CalculationProcedureType.TARE,
            sequence_number=sequence_number,
            defaults={
                "title": f"Tare Weighing Test @ {res.tare_load}",
                "standard_edition": res.standard_edition,
                "rule_version": res.rule_version,
                "standard_clause": res.standard_clause,
                "is_rule_configured": res.is_rule_configured,
                "reference_load": res.tare_load,
                "indicated_reading": res.net_indication,
                "zero_indication": res.gross_indication,
                "calculated_error": res.calculated_net_error,
                "permissible_error_mpe": res.permissible_mpe,
                "comparison_result": res.comparison_result,
                "explanation": res.explanation,
                "measurement_model": "TareMeasurement",
                "measurement_reference_id": measurement_id,
                "raw_data_snapshot": {
                    "tare_load": str(res.tare_load),
                    "gross_indication": str(res.gross_indication),
                    "net_indication": str(res.net_indication),
                },
                "computed_metadata": res.computed_metadata,
                "calculated_by": calculated_by,
            },
        )
        return record

