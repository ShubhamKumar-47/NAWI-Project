"""calculations/r76/discrimination.py – OIML R 76 Discrimination Test Calculator.

⚠ [VERIFY R76 §3.8] Discrimination requirement for digital indicating instruments.
"""
from decimal import Decimal
from typing import List
from calculations.base import AbstractTestCalculator, TestResult


class DiscriminationCalculator(AbstractTestCalculator):
    """
    Evaluates discrimination sensitivity when an additional small load is applied.
    """

    def validate_input(
        self,
        test_load: Decimal,
        indication_before: Decimal,
        small_weight_added: Decimal,
        indication_after: Decimal,
    ) -> List[str]:
        errors: List[str] = []
        if small_weight_added <= 0:
            errors.append("Small weight added must be positive.")
        return errors

    def calculate(
        self,
        test_load: Decimal,
        indication_before: Decimal,
        small_weight_added: Decimal,
        indication_after: Decimal,
        scale_interval: Decimal,
    ) -> TestResult:
        warnings = self.validate_input(
            test_load, indication_before, small_weight_added, indication_after
        )
        change = indication_after - indication_before

        # ⚠ [VERIFY R76 §3.8] Digital instruments: extra load of 1.4 d must change indication by at least 1 d
        pass_fail = "PASS" if change >= scale_interval else "FAIL"

        return TestResult(
            pass_fail=pass_fail,
            error=change,
            mpe=scale_interval,
            computed_fields={
                "change": change,
                "required_min_change": scale_interval,
            },
            warnings=warnings,
        )

