"""calculations/constants.py – OIML R 76 Numeric Tables and Constants.

⚠ [VERIFY vs. OIML R 76] All constants, MPE tables, and class limits
must be verified against the official OIML R 76 edition (e.g., R 76-1:2006)
and national metrology legislation adopted by the laboratory.
"""
from decimal import Decimal

# ── Accuracy Classes (OIML R 76-1 Clause 3.2) ────────────────────────────────
# ⚠ [VERIFY R76 §3.2]
CLASS_I = "I"        # Special accuracy
CLASS_II = "II"      # High accuracy
CLASS_III = "III"    # Medium accuracy
CLASS_IIII = "IIII"  # Ordinary accuracy

ACCURACY_CLASSES = [CLASS_I, CLASS_II, CLASS_III, CLASS_IIII]

# ── MPE (Maximum Permissible Error) on Initial Verification ───────────────────
# OIML R 76-1 Table 1: Maximum permissible errors for loads m expressed in verification scale intervals e.
# Format: (min_m_in_e, max_m_in_e, mpe_initial_in_e, mpe_service_in_e)
# ⚠ [VERIFY R76 §3.5 Table 1]
MPE_LIMITS_TABLE_1 = {
    CLASS_I: [
        (Decimal("0"), Decimal("50000"), Decimal("0.5"), Decimal("1.0")),
        (Decimal("50000"), Decimal("200000"), Decimal("1.0"), Decimal("2.0")),
        (Decimal("200000"), Decimal("Infinity"), Decimal("1.5"), Decimal("3.0")),
    ],
    CLASS_II: [
        (Decimal("0"), Decimal("5000"), Decimal("0.5"), Decimal("1.0")),
        (Decimal("5000"), Decimal("20000"), Decimal("1.0"), Decimal("2.0")),
        (Decimal("20000"), Decimal("100000"), Decimal("1.5"), Decimal("3.0")),
    ],
    CLASS_III: [
        (Decimal("0"), Decimal("500"), Decimal("0.5"), Decimal("1.0")),
        (Decimal("500"), Decimal("2000"), Decimal("1.0"), Decimal("2.0")),
        (Decimal("2000"), Decimal("10000"), Decimal("1.5"), Decimal("3.0")),
    ],
    CLASS_IIII: [
        (Decimal("0"), Decimal("50"), Decimal("0.5"), Decimal("1.0")),
        (Decimal("50"), Decimal("200"), Decimal("1.0"), Decimal("2.0")),
        (Decimal("200"), Decimal("1000"), Decimal("1.5"), Decimal("3.0")),
    ],
}

# ── Verification Scale Interval Limits ────────────────────────────────────────
# ⚠ [VERIFY R76 §3.4.2 Table 2]
MIN_SCALE_INTERVALS = {
    CLASS_I: Decimal("50000"),
    CLASS_II: Decimal("100"),
    CLASS_III: Decimal("100"),
    CLASS_IIII: Decimal("100"),
}

