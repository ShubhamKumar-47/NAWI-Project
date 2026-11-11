"""tests/test_calculations/test_weighing.py – Unit tests for OIML R 76 Weighing Calculations."""
from decimal import Decimal
import unittest
from calculations.r76.weighing import WeighingTestCalculator
from calculations.constants import CLASS_III


class TestWeighingCalculator(unittest.TestCase):
    def setUp(self):
        self.calc = WeighingTestCalculator()

    def test_class_iii_low_load_mpe(self):
        """
        Class III, e = 0.005 kg:
        Load = 1.0 kg -> m_in_e = 1.0 / 0.005 = 200 e
        Under 500 e, Table 1 specifies MPE = ±0.5 e = ±0.0025 kg.
        """
        e = Decimal("0.005")
        nominal = Decimal("1.000")
        mpe = self.calc.get_mpe(nominal, CLASS_III, e)
        self.assertEqual(mpe, Decimal("0.0025"))

    def test_class_iii_pass_criterion(self):
        """Indication error within MPE results in PASS."""
        e = Decimal("0.005")
        nominal = Decimal("1.000")
        indication = Decimal("1.002")  # error = +0.002, mpe = 0.0025 -> PASS
        res = self.calc.calculate(nominal, indication, CLASS_III, e)
        self.assertEqual(res.pass_fail, "PASS")
        self.assertEqual(res.error, Decimal("0.002"))

    def test_class_iii_fail_criterion(self):
        """Indication error exceeding MPE results in FAIL."""
        e = Decimal("0.005")
        nominal = Decimal("1.000")
        indication = Decimal("1.004")  # error = +0.004, mpe = 0.0025 -> FAIL
        res = self.calc.calculate(nominal, indication, CLASS_III, e)
        self.assertEqual(res.pass_fail, "FAIL")

