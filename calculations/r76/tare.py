"""calculations/r76/tare.py – OIML R 76 Tare Weighing Test Calculator.

⚠ [VERIFY R76 §3.5.3.3 & §3.5.3.4] Error of tare device and net weighing.
"""
from decimal import Decimal
from typing import List
from calculations.base import AbstractTestCalculator, TestResult
from calculations.r76.weighing import WeighingTestCalculator


class TareCalculator(AbstractTestCalculator):
    """
    Evaluates net weighing with tare against MPE.
    """

    def __init__(self):
        self.weighing_calc = WeighingTestCalculator()

    def validate_input(
        self,
        tare_load: Decimal,
        gross_indication: Decimal,
        net_indication: Decimal,
    ) -> List[str]:
        errors: List[str] = []
        if tare_load < 0:
            errors.append("Tare load cannot be negative.")
        return errors

    def calculate(
        self,
        tare_load: Decimal,
        gross_indication: Decimal,
        net_indication: Decimal,
        accuracy_class: str,
        actual_scale_interval: Decimal,
        is_initial_verification: bool = True,
    ) -> TestResult:
        warnings = self.validate_input(tare_load, gross_indication, net_indication)

        # ⚠ [VERIFY R76] Net error calculation: Net Indication - (Gross Indication - Tare Load)
        effective_net = gross_indication - tare_load
        error = net_indication - effective_net

        mpe = self.weighing_calc.get_mpe(
            net_indication,
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
                "effective_net": effective_net,
                "abs_error": abs(error),
            },
            warnings=warnings,
        )

