"""calculations/r76/eccentricity.py – OIML R 76 Eccentricity Test Calculator.

⚠ [VERIFY R76 §3.6.2] Errors on off-centre loading shall not exceed MPE for that load.
"""
from decimal import Decimal
from typing import List
from calculations.base import AbstractTestCalculator, TestResult
from calculations.r76.weighing import WeighingTestCalculator


class EccentricityCalculator(AbstractTestCalculator):
    """
    Evaluates eccentricity test error at a given position against the MPE.
    """

    def __init__(self):
        self.weighing_calc = WeighingTestCalculator()

    def validate_input(
        self,
        nominal_load: Decimal,
        indication: Decimal,
        position: str,
    ) -> List[str]:
        errors: List[str] = []
        if nominal_load <= 0:
            errors.append("Nominal load must be greater than zero.")
        if not position:
            errors.append("Load position must be specified.")
        return errors

    def calculate(
        self,
        nominal_load: Decimal,
        indication: Decimal,
        position: str,
        accuracy_class: str,
        actual_scale_interval: Decimal,
        is_initial_verification: bool = True,
    ) -> TestResult:
        warnings = self.validate_input(nominal_load, indication, position)
        error = indication - nominal_load

        # ⚠ [VERIFY R76 §3.6.2] MPE for eccentricity test
        mpe = self.weighing_calc.get_mpe(
            nominal_load,
            accuracy_class,
            actual_scale_interval,
            is_initial_verification=is_initial_verification,
        )

        pass_fail = "PASS" if abs(error) <= mpe else "FAIL"

        return TestResult(
            pass_fail=pass_fail,
            error=error,
            mpe=mpe,
            computed_fields={
                "position": position,
                "abs_error": abs(error),
            },
            warnings=warnings,
        )

