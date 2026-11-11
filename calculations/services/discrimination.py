"""calculations/services/discrimination.py – OIML R 76 Discrimination Test Service (§A.4.8 / §3.8)."""
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Dict, Optional

from calculations.models import CalculationCompliance, CalculationProcedureType, CalculationRecord
from .error_calculation import format_display_decimal
from .tolerance_rules import DEFAULT_STANDARD_EDITION, get_discrimination_tolerance
from .validation import coerce_decimal, validate_discrimination_input


@dataclass
class DiscriminationCalculationResult:
    """Standardized output of discrimination evaluation."""
    test_load: Decimal
    indication_before: Decimal
    small_weight_added: Decimal
    indication_after: Decimal
    observed_change: Decimal
    required_minimum_change: Decimal
    comparison_result: str  # "PASS" | "FAIL" | "NOT_EVALUATED"
    is_rule_configured: bool
    standard_edition: str
    rule_version: str
    standard_clause: str
    explanation: str
    computed_metadata: Dict[str, Any]


class DiscriminationService:
    """Service layer for evaluating OIML R 76 Discrimination (sensitivity) tests."""

    @staticmethod
    def calculate_discrimination(
        test_load: Any,
        indication_before: Any,
        small_weight_added: Any,
        indication_after: Any,
        scale_interval: Any,
        standard_edition: str = DEFAULT_STANDARD_EDITION,
    ) -> DiscriminationCalculationResult:
        """Calculate indicator response to small added load and evaluate ΔI >= 1d."""
        load = coerce_decimal(test_load, "test_load")
        before = coerce_decimal(indication_before, "indication_before")
        delta_l = coerce_decimal(small_weight_added, "small_weight_added")
        after = coerce_decimal(indication_after, "indication_after")
        d_val = coerce_decimal(scale_interval, "scale_interval")

        validate_discrimination_input(test_load=load, small_weight_added=delta_l, scale_interval=d_val)

        change = after - before
        rule_eval = get_discrimination_tolerance(scale_interval=d_val, standard_edition=standard_edition)

        required_min = d_val
        is_pass = change >= required_min
        comp_res = CalculationCompliance.PASS if is_pass else CalculationCompliance.FAIL
        verdict = "satisfies" if is_pass else "fails"

        explanation = (
            f"Discrimination at load L = {load}: Reading before additional mass I1 = {before}. "
            f"Additional mass ΔL = {delta_l} placed gently on receptor resulted in I2 = {after}. "
            f"Observed change ΔI = I2 - I1 = {after} - {before} = {format_display_decimal(change, 6)}. "
            f"{rule_eval.explanation} "
            f"Comparison: Change {format_display_decimal(change, 6)} {verdict} minimum threshold (≥ {format_display_decimal(required_min, 6)}). "
            f"Result: {comp_res}."
        )

        computed_metadata = {
            "test_load": float(load),
            "indication_before": float(before),
            "small_weight_added": float(delta_l),
            "indication_after": float(after),
            "observed_change": float(change),
            "scale_interval": float(d_val),
        }

        return DiscriminationCalculationResult(
            test_load=load,
            indication_before=before,
            small_weight_added=delta_l,
            indication_after=after,
            observed_change=change,
            required_minimum_change=required_min,
            comparison_result=comp_res,
            is_rule_configured=True,
            standard_edition=standard_edition,
            rule_version=rule_eval.rule_version,
            standard_clause=rule_eval.standard_clause,
            explanation=explanation,
            computed_metadata=computed_metadata,
        )

    @classmethod
    def save_record(
        cls,
        session,
        test_load: Any,
        indication_before: Any,
        small_weight_added: Any,
        indication_after: Any,
        scale_interval: Any,
        sequence_number: int = 1,
        measurement_id: Optional[int] = None,
        calculated_by=None,
        standard_edition: str = DEFAULT_STANDARD_EDITION,
    ) -> CalculationRecord:
        """Persist discrimination check to CalculationRecord."""
        res = cls.calculate_discrimination(
            test_load=test_load,
            indication_before=indication_before,
            small_weight_added=small_weight_added,
            indication_after=indication_after,
            scale_interval=scale_interval,
            standard_edition=standard_edition,
        )

        record, _ = CalculationRecord.objects.update_or_create(
            session=session,
            procedure_type=CalculationProcedureType.DISCRIMINATION,
            sequence_number=sequence_number,
            defaults={
                "title": f"Discrimination Test @ {res.test_load}",
                "standard_edition": res.standard_edition,
                "rule_version": res.rule_version,
                "standard_clause": res.standard_clause,
                "is_rule_configured": res.is_rule_configured,
                "reference_load": res.test_load,
                "indicated_reading": res.indication_after,
                "zero_indication": res.indication_before,
                "calculated_error": res.observed_change,
                "permissible_error_mpe": res.required_minimum_change,
                "comparison_result": res.comparison_result,
                "explanation": res.explanation,
                "measurement_model": "DiscriminationMeasurement",
                "measurement_reference_id": measurement_id,
                "raw_data_snapshot": {
                    "test_load": str(res.test_load),
                    "indication_before": str(res.indication_before),
                    "small_weight_added": str(res.small_weight_added),
                    "indication_after": str(res.indication_after),
                },
                "computed_metadata": res.computed_metadata,
                "calculated_by": calculated_by,
            },
        )
        return record

