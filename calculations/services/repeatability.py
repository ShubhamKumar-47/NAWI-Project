"""calculations/services/repeatability.py – OIML R 76 Repeatability Test Service (§A.4.10 / §3.6.1)."""
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Dict, List, Optional, Sequence

from calculations.models import CalculationCompliance, CalculationProcedureType, CalculationRecord
from .error_calculation import format_display_decimal
from .tolerance_rules import DEFAULT_STANDARD_EDITION, get_repeatability_tolerance
from .validation import coerce_decimal, validate_repeatability_input


@dataclass
class RepeatabilityCalculationResult:
    """Standardized output of a repeatability evaluation."""
    reference_load: Decimal
    indications: List[Decimal]
    max_indication: Decimal
    min_indication: Decimal
    calculated_range: Decimal
    permissible_range_mpe: Optional[Decimal]
    comparison_result: str  # "PASS" | "FAIL" | "NOT_EVALUATED"
    is_rule_configured: bool
    standard_edition: str
    rule_version: str
    standard_clause: str
    explanation: str
    computed_metadata: Dict[str, Any]


class RepeatabilityService:
    """Service layer for evaluating OIML R 76 Repeatability test series."""

    @staticmethod
    def calculate_series(
        nominal_load: Any,
        indications: Sequence[Any],
        accuracy_class: str,
        actual_scale_interval: Any,
        series_name: str = "Series 1",
        is_initial_verification: bool = True,
        standard_edition: str = DEFAULT_STANDARD_EDITION,
    ) -> RepeatabilityCalculationResult:
        """Calculate series range (Max - Min) and evaluate against |MPE|."""
        nom = coerce_decimal(nominal_load, "nominal_load")
        e_val = coerce_decimal(actual_scale_interval, "actual_scale_interval")
        dec_indications = [coerce_decimal(ind, f"indication_{i+1}") for i, ind in enumerate(indications)]

        validate_repeatability_input(nominal_load=nom, indications=dec_indications)

        max_ind = max(dec_indications)
        min_ind = min(dec_indications)
        range_val = max_ind - min_ind

        rule_eval = get_repeatability_tolerance(
            nominal_load=nom,
            accuracy_class=accuracy_class,
            actual_scale_interval=e_val,
            is_initial_verification=is_initial_verification,
            standard_edition=standard_edition,
        )

        computed_metadata = {
            "series_name": series_name,
            "readings_count": len(dec_indications),
            "readings": [float(x) for x in dec_indications],
            "max_indication": float(max_ind),
            "min_indication": float(min_ind),
            "range": float(range_val),
        }

        readings_str = ", ".join(format_display_decimal(x, 4) for x in dec_indications)

        if not rule_eval.is_configured:
            return RepeatabilityCalculationResult(
                reference_load=nom,
                indications=dec_indications,
                max_indication=max_ind,
                min_indication=min_ind,
                calculated_range=range_val,
                permissible_range_mpe=None,
                comparison_result=CalculationCompliance.NOT_EVALUATED,
                is_rule_configured=False,
                standard_edition=standard_edition,
                rule_version=rule_eval.rule_version,
                standard_clause=rule_eval.standard_clause,
                explanation=f"Series '{series_name}' (n={len(dec_indications)}): [{readings_str}]. Range R = {range_val}. {rule_eval.explanation}",
                computed_metadata=computed_metadata,
            )

        mpe = rule_eval.mpe_value
        is_pass = range_val <= mpe
        comparison_res = CalculationCompliance.PASS if is_pass else CalculationCompliance.FAIL

        verdict_str = "satisfies" if is_pass else "exceeds"
        explanation = (
            f"Repeatability {series_name} at reference load L = {nom} with {len(dec_indications)} repetitions: [{readings_str}]. "
            f"Max = {format_display_decimal(max_ind, 4)}, Min = {format_display_decimal(min_ind, 4)}. "
            f"Observed Range R = I_max - I_min = {format_display_decimal(range_val, 6)}. "
            f"{rule_eval.explanation} "
            f"Comparison: Range {format_display_decimal(range_val, 6)} {verdict_str} allowable limit (≤ {format_display_decimal(mpe, 6)}). "
            f"Result: {comparison_res}."
        )

        return RepeatabilityCalculationResult(
            reference_load=nom,
            indications=dec_indications,
            max_indication=max_ind,
            min_indication=min_ind,
            calculated_range=range_val,
            permissible_range_mpe=mpe,
            comparison_result=comparison_res,
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
        nominal_load: Any,
        indications: Sequence[Any],
        accuracy_class: str,
        actual_scale_interval: Any,
        sequence_number: int = 1,
        series_name: str = "Series 1",
        calculated_by=None,
        is_initial_verification: bool = True,
        standard_edition: str = DEFAULT_STANDARD_EDITION,
    ) -> CalculationRecord:
        """Execute calculation and persist repeatability series summary to CalculationRecord."""
        res = cls.calculate_series(
            nominal_load=nominal_load,
            indications=indications,
            accuracy_class=accuracy_class,
            actual_scale_interval=actual_scale_interval,
            series_name=series_name,
            is_initial_verification=is_initial_verification,
            standard_edition=standard_edition,
        )

        record, _ = CalculationRecord.objects.update_or_create(
            session=session,
            procedure_type=CalculationProcedureType.REPEATABILITY,
            sequence_number=sequence_number,
            defaults={
                "title": f"Repeatability {series_name} ({res.reference_load})",
                "standard_edition": res.standard_edition,
                "rule_version": res.rule_version,
                "standard_clause": res.standard_clause,
                "is_rule_configured": res.is_rule_configured,
                "reference_load": res.reference_load,
                "indicated_reading": res.max_indication,
                "zero_indication": Decimal("0"),
                "calculated_error": res.calculated_range,
                "permissible_error_mpe": res.permissible_range_mpe,
                "comparison_result": res.comparison_result,
                "explanation": res.explanation,
                "measurement_model": "RepeatabilityMeasurement",
                "raw_data_snapshot": {
                    "nominal_load": str(res.reference_load),
                    "indications": [str(x) for x in res.indications],
                },
                "computed_metadata": res.computed_metadata,
                "calculated_by": calculated_by,
            },
        )
        return record

