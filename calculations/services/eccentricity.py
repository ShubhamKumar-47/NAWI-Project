"""calculations/services/eccentricity.py – OIML R 76 Eccentricity Test Service (§A.4.7 / §3.6.2)."""
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Dict, List, Optional

from calculations.models import CalculationCompliance, CalculationProcedureType, CalculationRecord
from .error_calculation import calculate_raw_error, format_display_decimal
from .tolerance_rules import DEFAULT_STANDARD_EDITION, get_eccentricity_tolerance
from .validation import coerce_decimal, validate_eccentricity_input


@dataclass
class EccentricityPositionResult:
    """Evaluation result for one eccentricity load placement position."""
    position_key: str
    position_display: str
    reference_load: Decimal
    indicated_reading: Decimal
    calculated_error: Decimal
    permissible_error_mpe: Optional[Decimal]
    comparison_result: str  # "PASS" | "FAIL" | "NOT_EVALUATED"
    is_rule_configured: bool
    explanation: str


class EccentricityService:
    """Service layer for evaluating OIML R 76 Eccentricity (off-centre loading) tests."""

    POSITION_NAMES = {
        "CENTRE": "Position 1: Centre",
        "FRONT_LEFT": "Position 2: Front-Left (Quarter 1)",
        "BACK_LEFT": "Position 3: Back-Left (Quarter 2)",
        "BACK_RIGHT": "Position 4: Back-Right (Quarter 3)",
        "FRONT_RIGHT": "Position 5: Front-Right (Quarter 4)",
    }

    @classmethod
    def calculate_position(
        cls,
        nominal_load: Any,
        indication: Any,
        position: str,
        accuracy_class: str,
        actual_scale_interval: Any,
        zero_indication: Any = Decimal("0"),
        is_initial_verification: bool = True,
        standard_edition: str = DEFAULT_STANDARD_EDITION,
    ) -> EccentricityPositionResult:
        """Calculate error at a single off-centre position and evaluate against MPE."""
        nom = coerce_decimal(nominal_load, "nominal_load")
        ind = coerce_decimal(indication, "indication")
        e_val = coerce_decimal(actual_scale_interval, "actual_scale_interval")
        validate_eccentricity_input(nominal_load=nom, indication=ind, position=position)

        error = calculate_raw_error(ind, nom)
        pos_display = cls.POSITION_NAMES.get(position, position)

        rule_eval = get_eccentricity_tolerance(
            nominal_load=nom,
            accuracy_class=accuracy_class,
            actual_scale_interval=e_val,
            is_initial_verification=is_initial_verification,
            standard_edition=standard_edition,
        )

        if not rule_eval.is_configured:
            return EccentricityPositionResult(
                position_key=position,
                position_display=pos_display,
                reference_load=nom,
                indicated_reading=ind,
                calculated_error=error,
                permissible_error_mpe=None,
                comparison_result=CalculationCompliance.NOT_EVALUATED,
                is_rule_configured=False,
                explanation=f"{pos_display} @ {nom}: Error E = {error}. {rule_eval.explanation}",
            )

        mpe = rule_eval.mpe_value
        is_pass = abs(error) <= mpe
        comp_res = CalculationCompliance.PASS if is_pass else CalculationCompliance.FAIL
        verdict = "satisfies" if is_pass else "exceeds"

        explanation = (
            f"{pos_display} with reference load L = {nom}: Indication I = {ind}. "
            f"Error E = I - L = {ind} - {nom} = {format_display_decimal(error, 6, True)}. "
            f"{rule_eval.explanation} "
            f"Comparison: |{format_display_decimal(error, 6)}| {verdict} MPE (±{format_display_decimal(mpe, 6)}). "
            f"Result: {comp_res}."
        )

        return EccentricityPositionResult(
            position_key=position,
            position_display=pos_display,
            reference_load=nom,
            indicated_reading=ind,
            calculated_error=error,
            permissible_error_mpe=mpe,
            comparison_result=comp_res,
            is_rule_configured=True,
            explanation=explanation,
        )

    @classmethod
    def save_record(
        cls,
        session,
        nominal_load: Any,
        indication: Any,
        position: str,
        accuracy_class: str,
        actual_scale_interval: Any,
        sequence_number: int = 1,
        zero_indication: Any = Decimal("0"),
        measurement_id: Optional[int] = None,
        calculated_by=None,
        is_initial_verification: bool = True,
        standard_edition: str = DEFAULT_STANDARD_EDITION,
    ) -> CalculationRecord:
        """Persist eccentricity position calculation to CalculationRecord."""
        res = cls.calculate_position(
            nominal_load=nominal_load,
            indication=indication,
            position=position,
            accuracy_class=accuracy_class,
            actual_scale_interval=actual_scale_interval,
            zero_indication=zero_indication,
            is_initial_verification=is_initial_verification,
            standard_edition=standard_edition,
        )

        record, _ = CalculationRecord.objects.update_or_create(
            session=session,
            procedure_type=CalculationProcedureType.ECCENTRICITY,
            sequence_number=sequence_number,
            defaults={
                "title": f"Eccentricity {res.position_display}",
                "standard_edition": standard_edition,
                "rule_version": "R76-2006-v1.0",
                "standard_clause": f"{standard_edition} §3.6.2 & §A.4.7",
                "is_rule_configured": res.is_rule_configured,
                "reference_load": res.reference_load,
                "indicated_reading": res.indicated_reading,
                "zero_indication": coerce_decimal(zero_indication, "zero_indication") if zero_indication is not None else Decimal("0"),
                "calculated_error": res.calculated_error,
                "permissible_error_mpe": res.permissible_error_mpe,
                "comparison_result": res.comparison_result,
                "explanation": res.explanation,
                "measurement_model": "EccentricityMeasurement",
                "measurement_reference_id": measurement_id,
                "raw_data_snapshot": {
                    "position": res.position_key,
                    "nominal_load": str(res.reference_load),
                    "indication": str(res.indicated_reading),
                },
                "computed_metadata": {
                    "position": res.position_key,
                    "position_name": res.position_display,
                },
                "calculated_by": calculated_by,
            },
        )
        return record

