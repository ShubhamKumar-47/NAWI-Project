"""calculations/r76/influence_quantities.py – OIML R 76 Influence Factor Tests.

⚠ [VERIFY R76 §3.9 & Clause 5] Static temperatures, voltage variations, and humidity tests.
"""
from decimal import Decimal
from typing import List, Optional
from calculations.base import AbstractTestCalculator, TestResult
from calculations.r76.weighing import WeighingTestCalculator


class InfluenceQuantityCalculator(AbstractTestCalculator):
    """
    Evaluates measurement error under influence quantities (e.g., temperature extremes, supply voltage).
    """

    def __init__(self):
        self.weighing_calc = WeighingTestCalculator()

    def validate_input(
        self,
        nominal_load: Decimal,
        indication: Decimal,
        quantity_type: str,
        quantity_value: Decimal,
    ) -> List[str]:
        errors: List[str] = []
        if not quantity_type:
            errors.append("Influence quantity type is required.")
        return errors

    def calculate(
        self,
        nominal_load: Decimal,
        indication: Decimal,
        quantity_type: str,
        quantity_value: Decimal,
        accuracy_class: str,
        actual_scale_interval: Decimal,
        is_initial_verification: bool = True,
    ) -> TestResult:
        warnings = self.validate_input(
            nominal_load, indication, quantity_type, quantity_value
        )
        error = indication - nominal_load

        # ⚠ [VERIFY R76 Clause 5] Errors under influence factors must remain within MPE
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
                "quantity_type": quantity_type,
                "quantity_value": quantity_value,
                "abs_error": abs(error),
            },
            warnings=warnings,
        )

