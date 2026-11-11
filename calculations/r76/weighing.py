"""calculations/r76/weighing.py – OIML R 76 Weighing Test Calculator.

⚠ [VERIFY R76 §3.5.1 / Table 1] Error and MPE calculations.
"""
from decimal import Decimal
from typing import List, Optional
from calculations.base import AbstractTestCalculator, TestInput, TestResult
from calculations.constants import MPE_LIMITS_TABLE_1


class WeighingTestCalculator(AbstractTestCalculator):
    """
    Computes error, MPE, and Pass/Fail result for a single weighing test load point.

    OIML R 76-1 Clause 3.5.1 & Table 1:
        Error = Indication - Nominal Load
        MPE is determined by load expressed in units of e.
    """

    def validate_input(
        self,
        nominal_load: Decimal,
        indication: Decimal,
        accuracy_class: str,
        actual_scale_interval: Decimal,
    ) -> List[str]:
        errors: List[str] = []
        if actual_scale_interval <= 0:
            errors.append("Verification scale interval (e) must be positive.")
        if nominal_load < 0:
            errors.append("Nominal load cannot be negative.")
        if accuracy_class not in MPE_LIMITS_TABLE_1:
            errors.append(f"Unknown accuracy class '{accuracy_class}'.")
        return errors

    def get_mpe(
        self,
        nominal_load: Decimal,
        accuracy_class: str,
        actual_scale_interval: Decimal,
        is_initial_verification: bool = True,
    ) -> Decimal:
        """
        Calculates Maximum Permissible Error (MPE) in instrument units.
        ⚠ [VERIFY R76 Table 1]
        """
        e = actual_scale_interval
        m_in_e = nominal_load / e

        table_rows = MPE_LIMITS_TABLE_1.get(accuracy_class, [])
        mpe_e = Decimal("1.5")  # default fallback

        for min_e, max_e, mpe_initial, mpe_service in table_rows:
            if min_e <= m_in_e <= max_e:
                mpe_e = mpe_initial if is_initial_verification else mpe_service
                break

        return mpe_e * e

    def calculate(
        self,
        nominal_load: Decimal,
        indication: Decimal,
        accuracy_class: str,
        actual_scale_interval: Decimal,
        is_initial_verification: bool = True,
    ) -> TestResult:
        """
        Compute error, MPE, and pass/fail for one weighing observation.
        """
        val_errors = self.validate_input(
            nominal_load, indication, accuracy_class, actual_scale_interval
        )
        if val_errors:
            return TestResult(
                pass_fail="FAIL",
                warnings=val_errors,
            )

        # ⚠ [VERIFY R76 §3.5.1] Error formula
        error = indication - nominal_load
        mpe = self.get_mpe(
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
                "load_in_e": nominal_load / actual_scale_interval,
                "abs_error": abs(error),
            },
        )

