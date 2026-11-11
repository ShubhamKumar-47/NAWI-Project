"""calculations/r76/zero_setting.py – OIML R 76 Zero-Setting & Zero-Tracking Calculator.

⚠ [VERIFY R76 §A.4.1 – §A.4.3]
Error of zero-setting:
For non-automatic and semi-automatic zero-setting:
The indication at zero is brought to zero. Small weights (e.g. 0.1d steps) are added until the
indication changes to (0 + d). The error is:
    E0 = I + 0.5d - ΔL
Acceptance criterion: |E0| <= 0.25e (or <= 0.5d for instruments with auxiliary device).
"""
from decimal import Decimal
from typing import List, Optional
from calculations.base import AbstractTestCalculator, TestResult


class ZeroSettingCalculator(AbstractTestCalculator):
    """
    Evaluates zero-setting and zero-tracking tests against OIML R 76 tolerances.
    """

    def validate_input(
        self,
        zero_indication: Decimal,
        small_weight_added: Optional[Decimal] = None,
    ) -> List[str]:
        errors: List[str] = []
        return errors

    def calculate(
        self,
        zero_indication_after: Decimal,
        scale_interval: Decimal,
        actual_scale_interval: Decimal,
        small_weight_added: Optional[Decimal] = None,
    ) -> TestResult:
        """
        Calculate zero-setting error.
        If small_weight_added is provided (method of turning point):
            E0 = zero_indication_after + 0.5 * scale_interval - small_weight_added
        Otherwise, if directly evaluated from indication:
            E0 = zero_indication_after
        MPE is ±0.25e (or 0.5d if d < e with auxiliary device).
        """
        warnings = self.validate_input(zero_indication_after, small_weight_added)

        d = scale_interval
        e = actual_scale_interval

        if small_weight_added is not None and small_weight_added > 0:
            error = zero_indication_after + Decimal("0.5") * d - small_weight_added
        else:
            error = zero_indication_after

        # ⚠ [VERIFY R76 §A.4.1.2] MPE for zero-setting: ±0.25e
        mpe = Decimal("0.25") * e

        pass_fail = "PASS" if abs(error) <= mpe else "FAIL"

        return TestResult(
            pass_fail=pass_fail,
            error=error,
            mpe=mpe,
            computed_fields={
                "zero_error": error,
                "abs_error": abs(error),
                "mpe": mpe,
                "scale_interval": d,
                "verification_interval": e,
            },
            warnings=warnings,
        )

