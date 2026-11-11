"""calculations/services/zero_tests.py – OIML R 76 Zero-Setting & Zero-Tracking Test Service (§A.4.1 – §A.4.3)."""
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Dict, Optional

from calculations.models import CalculationCompliance, CalculationProcedureType, CalculationRecord
from .error_calculation import format_display_decimal
from .tolerance_rules import DEFAULT_STANDARD_EDITION, get_zero_setting_tolerance
from .validation import coerce_decimal, validate_zero_test_input


@dataclass
class ZeroTestCalculationResult:
    """Standardized output of zero-setting evaluation."""
    operation_type: str
    zero_indication_before: Decimal
    zero_indication_after: Decimal
    small_weight_added: Decimal
    calculated_zero_error: Decimal
    permissible_mpe: Decimal
    comparison_result: str  # "PASS" | "FAIL" | "NOT_EVALUATED"
    is_rule_configured: bool
    standard_edition: str
    rule_version: str
    standard_clause: str
    explanation: str
    computed_metadata: Dict[str, Any]


class ZeroTestsService:
    """Service layer for evaluating OIML R 76 Zero-Setting and Zero-Tracking operations."""

    OPERATION_NAMES = {
        "NON_AUTOMATIC": "Non-Automatic Zero-Setting (§A.4.1.1)",
        "SEMI_AUTOMATIC": "Semi-Automatic Zero-Setting (§A.4.1.2)",
        "AUTOMATIC": "Automatic Zero-Setting (§A.4.1.3)",
        "INITIAL": "Initial Zero-Setting (§A.4.1.4)",
        "ZERO_TRACKING": "Zero-Tracking Test (§A.4.1.5)",
    }

    @classmethod
    def calculate_zero_check(
        cls,
        zero_indication_after: Any,
        scale_interval: Any,
        actual_scale_interval: Any,
        zero_indication_before: Any = Decimal("0"),
        small_weight_added: Optional[Any] = None,
        operation_type: str = "NON_AUTOMATIC",
        has_auxiliary_device: bool = False,
        standard_edition: str = DEFAULT_STANDARD_EDITION,
    ) -> ZeroTestCalculationResult:
        """Calculate zero error E0 and compare against ±0.25e (or ±0.5d)."""
        after = coerce_decimal(zero_indication_after, "zero_indication_after")
        before = coerce_decimal(zero_indication_before, "zero_indication_before") if zero_indication_before is not None else Decimal("0")
        d_val = coerce_decimal(scale_interval, "scale_interval")
        e_val = coerce_decimal(actual_scale_interval, "actual_scale_interval")
        delta_l = coerce_decimal(small_weight_added, "small_weight_added") if small_weight_added is not None else Decimal("0")

        validate_zero_test_input(scale_interval=d_val, actual_scale_interval=e_val, small_weight_added=delta_l)

        # Method of turning point (§A.4.1.2): E0 = I + 0.5d - ΔL
        if delta_l > Decimal("0"):
            zero_error = after + Decimal("0.5") * d_val - delta_l
            calc_formula = f"Turning point method (§A.4.1.2): E0 = I + 0.5d - ΔL = {after} + 0.5×{d_val} - {delta_l} = {format_display_decimal(zero_error, 6, True)}"
        else:
            zero_error = after
            calc_formula = f"Direct indication (§A.4.1): E0 = I = {format_display_decimal(zero_error, 6, True)}"

        rule_eval = get_zero_setting_tolerance(
            actual_scale_interval=e_val,
            scale_interval=d_val,
            has_auxiliary_device=has_auxiliary_device,
            standard_edition=standard_edition,
        )

        mpe = rule_eval.mpe_value
        is_pass = abs(zero_error) <= mpe
        comp_res = CalculationCompliance.PASS if is_pass else CalculationCompliance.FAIL
        verdict = "satisfies" if is_pass else "exceeds"
        op_title = cls.OPERATION_NAMES.get(operation_type, operation_type)

        explanation = (
            f"{op_title}: Indication after zeroing I = {after}. {calc_formula}. "
            f"{rule_eval.explanation} "
            f"Comparison: |{format_display_decimal(zero_error, 6)}| {verdict} tolerance limit (±{format_display_decimal(mpe, 6)}). "
            f"Result: {comp_res}."
        )

        computed_metadata = {
            "operation_type": operation_type,
            "operation_name": op_title,
            "zero_indication_before": float(before),
            "zero_indication_after": float(after),
            "small_weight_added": float(delta_l),
            "calculated_zero_error": float(zero_error),
        }

        return ZeroTestCalculationResult(
            operation_type=operation_type,
            zero_indication_before=before,
            zero_indication_after=after,
            small_weight_added=delta_l,
            calculated_zero_error=zero_error,
            permissible_mpe=mpe,
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
        zero_indication_after: Any,
        scale_interval: Any,
        actual_scale_interval: Any,
        sequence_number: int = 1,
        zero_indication_before: Any = Decimal("0"),
        small_weight_added: Optional[Any] = None,
        operation_type: str = "NON_AUTOMATIC",
        measurement_id: Optional[int] = None,
        calculated_by=None,
        has_auxiliary_device: bool = False,
        standard_edition: str = DEFAULT_STANDARD_EDITION,
    ) -> CalculationRecord:
        """Persist zero test evaluation to CalculationRecord."""
        res = cls.calculate_zero_check(
            zero_indication_after=zero_indication_after,
            scale_interval=scale_interval,
            actual_scale_interval=actual_scale_interval,
            zero_indication_before=zero_indication_before,
            small_weight_added=small_weight_added,
            operation_type=operation_type,
            has_auxiliary_device=has_auxiliary_device,
            standard_edition=standard_edition,
        )

        record, _ = CalculationRecord.objects.update_or_create(
            session=session,
            procedure_type=CalculationProcedureType.ZERO_SETTING,
            sequence_number=sequence_number,
            defaults={
                "title": f"Zero Test: {cls.OPERATION_NAMES.get(operation_type, operation_type)}",
                "standard_edition": res.standard_edition,
                "rule_version": res.rule_version,
                "standard_clause": res.standard_clause,
                "is_rule_configured": res.is_rule_configured,
                "reference_load": Decimal("0"),
                "indicated_reading": res.zero_indication_after,
                "zero_indication": res.zero_indication_before,
                "calculated_error": res.calculated_zero_error,
                "permissible_error_mpe": res.permissible_mpe,
                "comparison_result": res.comparison_result,
                "explanation": res.explanation,
                "measurement_model": "ZeroSettingMeasurement",
                "measurement_reference_id": measurement_id,
                "raw_data_snapshot": {
                    "operation_type": res.operation_type,
                    "zero_indication_before": str(res.zero_indication_before),
                    "zero_indication_after": str(res.zero_indication_after),
                    "small_weight_added": str(res.small_weight_added),
                },
                "computed_metadata": res.computed_metadata,
                "calculated_by": calculated_by,
            },
        )
        return record

