"""calculations/services/weighing_performance.py – OIML R 76 Weighing Performance Test Service (§A.4.4)."""
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Dict, List, Optional

from calculations.models import CalculationCompliance, CalculationProcedureType, CalculationRecord
from .error_calculation import calculate_raw_error, calculate_turning_point_error, format_display_decimal
from .tolerance_rules import DEFAULT_STANDARD_EDITION, get_weighing_mpe
from .validation import coerce_decimal, validate_weighing_input


@dataclass
class WeighingCalculationResult:
    """Standardized output of a weighing performance calculation."""
    reference_load: Decimal
    indicated_reading: Decimal
    calculated_error: Decimal
    permissible_error_mpe: Optional[Decimal]
    comparison_result: str  # "PASS" | "FAIL" | "NOT_EVALUATED"
    is_rule_configured: bool
    standard_edition: str
    rule_version: str
    standard_clause: str
    explanation: str
    computed_metadata: Dict[str, Any]


class WeighingPerformanceService:
    """Service layer for evaluating Weighing Performance observations under OIML R 76."""

    @staticmethod
    def calculate_point(
        nominal_load: Any,
        indication: Any,
        accuracy_class: str,
        actual_scale_interval: Any,
        scale_interval: Optional[Any] = None,
        zero_indication: Any = Decimal("0"),
        small_weight_added: Optional[Any] = None,
        is_initial_verification: bool = True,
        standard_edition: str = DEFAULT_STANDARD_EDITION,
    ) -> WeighingCalculationResult:
        """Calculate single load point error and compare against OIML R 76 Table 1 MPE."""
        nom = coerce_decimal(nominal_load, "nominal_load")
        ind = coerce_decimal(indication, "indication")
        e_val = coerce_decimal(actual_scale_interval, "actual_scale_interval")
        z_ind = coerce_decimal(zero_indication, "zero_indication") if zero_indication is not None else Decimal("0")
        validate_weighing_input(nominal_load=nom, indication=ind)

        # Method of turning point (§A.4.4.3) if delta L supplied, else standard reading (§A.4.4.2)
        if small_weight_added is not None and scale_interval is not None:
            delta_l = coerce_decimal(small_weight_added, "small_weight_added")
            d_val = coerce_decimal(scale_interval, "scale_interval")
            error = calculate_turning_point_error(ind, d_val, delta_l, nom)
            method_desc = f"Turning point method (§A.4.4.3): E = (I + 0.5d - ΔL) - L = ({ind} + 0.5×{d_val} - {delta_l}) - {nom} = {format_display_decimal(error, 6, True)}"
        else:
            error = calculate_raw_error(ind, nom)
            method_desc = f"Direct indication error (§A.4.4.2): E = I - L = {ind} - {nom} = {format_display_decimal(error, 6, True)}"

        # Look up tolerance from rule set
        rule_eval = get_weighing_mpe(
            nominal_load=nom,
            accuracy_class=accuracy_class,
            actual_scale_interval=e_val,
            is_initial_verification=is_initial_verification,
            standard_edition=standard_edition,
        )

        m_in_e = nom / e_val
        computed_metadata = {
            "load_in_e": float(m_in_e),
            "zero_indication": float(z_ind),
            "is_initial": is_initial_verification,
        }

        if not rule_eval.is_configured:
            return WeighingCalculationResult(
                reference_load=nom,
                indicated_reading=ind,
                calculated_error=error,
                permissible_error_mpe=None,
                comparison_result=CalculationCompliance.NOT_EVALUATED,
                is_rule_configured=False,
                standard_edition=standard_edition,
                rule_version=rule_eval.rule_version,
                standard_clause=rule_eval.standard_clause,
                explanation=f"{method_desc}. {rule_eval.explanation}",
                computed_metadata=computed_metadata,
            )

        mpe = rule_eval.mpe_value
        is_pass = abs(error) <= mpe
        comparison_res = CalculationCompliance.PASS if is_pass else CalculationCompliance.FAIL

        verdict_str = "satisfies" if is_pass else "exceeds"
        full_explanation = (
            f"{method_desc}. Load m = {nom} corresponds to {m_in_e:.2f} e. "
            f"{rule_eval.explanation} "
            f"Comparison: |{format_display_decimal(error, 6)}| {verdict_str} MPE (±{format_display_decimal(mpe, 6)}). "
            f"Result: {comparison_res}."
        )

        return WeighingCalculationResult(
            reference_load=nom,
            indicated_reading=ind,
            calculated_error=error,
            permissible_error_mpe=mpe,
            comparison_result=comparison_res,
            is_rule_configured=True,
            standard_edition=standard_edition,
            rule_version=rule_eval.rule_version,
            standard_clause=rule_eval.standard_clause,
            explanation=full_explanation,
            computed_metadata=computed_metadata,
        )

    @classmethod
    def save_record(
        cls,
        session,
        nominal_load: Any,
        indication: Any,
        accuracy_class: str,
        actual_scale_interval: Any,
        scale_interval: Optional[Any] = None,
        sequence_number: int = 1,
        title: str = "",
        zero_indication: Any = Decimal("0"),
        small_weight_added: Optional[Any] = None,
        measurement_id: Optional[int] = None,
        calculated_by=None,
        is_initial_verification: bool = True,
        standard_edition: str = DEFAULT_STANDARD_EDITION,
    ) -> CalculationRecord:
        """Execute calculation and persist to the CalculationRecord database model."""
        res = cls.calculate_point(
            nominal_load=nominal_load,
            indication=indication,
            accuracy_class=accuracy_class,
            actual_scale_interval=actual_scale_interval,
            scale_interval=scale_interval,
            zero_indication=zero_indication,
            small_weight_added=small_weight_added,
            is_initial_verification=is_initial_verification,
            standard_edition=standard_edition,
        )

        record, _ = CalculationRecord.objects.update_or_create(
            session=session,
            procedure_type=CalculationProcedureType.WEIGHING,
            sequence_number=sequence_number,
            defaults={
                "title": title or f"Weighing Point #{sequence_number} ({res.reference_load})",
                "standard_edition": res.standard_edition,
                "rule_version": res.rule_version,
                "standard_clause": res.standard_clause,
                "is_rule_configured": res.is_rule_configured,
                "reference_load": res.reference_load,
                "indicated_reading": res.indicated_reading,
                "zero_indication": coerce_decimal(zero_indication, "zero_indication") if zero_indication is not None else Decimal("0"),
                "calculated_error": res.calculated_error,
                "permissible_error_mpe": res.permissible_error_mpe,
                "comparison_result": res.comparison_result,
                "explanation": res.explanation,
                "measurement_model": "WeighingMeasurement",
                "measurement_reference_id": measurement_id,
                "raw_data_snapshot": {
                    "nominal_load": str(res.reference_load),
                    "indication": str(res.indicated_reading),
                },
                "computed_metadata": res.computed_metadata,
                "calculated_by": calculated_by,
            },
        )
        return record
