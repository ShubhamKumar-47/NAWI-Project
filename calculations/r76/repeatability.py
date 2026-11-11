"""calculations/r76/repeatability.py – OIML R 76 Repeatability Test Calculator.

⚠ [VERIFY R76 §3.6.1] Difference between results of several weighings of the same load
shall not exceed the absolute value of the maximum permissible error for that load.
"""
from decimal import Decimal
from typing import List, Sequence
from calculations.base import AbstractTestCalculator, TestResult
from calculations.r76.weighing import WeighingTestCalculator


class RepeatabilityCalculator(AbstractTestCalculator):
    """
    Computes repeatability range (Max indication - Min indication) and compares
    against the applicable MPE for that nominal load.
    """

    def __init__(self):
        self.weighing_calc = WeighingTestCalculator()

    def validate_input(self, indications: Sequence[Decimal]) -> List[str]:
        errors: List[str] = []
        if len(indications) < 3:
            errors.append("Repeatability test requires at least 3 repetitions. ⚠ Verify with R 76.")
        return errors

    def calculate(
        self,
        nominal_load: Decimal,
        indications: Sequence[Decimal],
        accuracy_class: str,
        actual_scale_interval: Decimal,
        is_initial_verification: bool = True,
    ) -> TestResult:
        warnings = self.validate_input(indications)
        if not indications:
            return TestResult(pass_fail="PENDING", warnings=warnings)

        max_ind = max(indications)
        min_ind = min(indications)
        diff_range = max_ind - min_ind

        # ⚠ [VERIFY R76 §3.6.1] Acceptance criterion: range <= |MPE|
        mpe = self.weighing_calc.get_mpe(
            nominal_load,
            accuracy_class,
            actual_scale_interval,
            is_initial_verification=is_initial_verification,
        )

        pass_fail = "PASS" if diff_range <= mpe else "FAIL"

        return TestResult(
            pass_fail=pass_fail,
            error=diff_range,
            mpe=mpe,
            computed_fields={
                "max_indication": max_ind,
                "min_indication": min_ind,
                "range": diff_range,
                "count": len(indications),
            },
            warnings=warnings,
        )

