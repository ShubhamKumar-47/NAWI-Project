"""calculations/tests.py – Comprehensive unit tests for OIML R 76 calculation service layer."""
from decimal import Decimal
from django.test import TestCase, Client
from django.urls import reverse

from apps.accounts.models import CustomUser, Organization
from apps.core.constants import AccuracyClass, PassFail, UserRole
from apps.instruments.models import Instrument, CommonInstrumentType
from apps.test_sessions.models import TestSession
from apps.measurements.models import WeighingMeasurement
from calculations.constants import CLASS_I, CLASS_II, CLASS_III, CLASS_IIII
from calculations.exceptions import InsufficientDataError, InvalidInputError
from calculations.models import CalculationCompliance, CalculationProcedureType, CalculationRecord
from calculations.services import (
    DEFAULT_RULE_VERSION,
    DEFAULT_STANDARD_EDITION,
    DiscriminationService,
    EccentricityService,
    RepeatabilityService,
    SessionCalculationCoordinator,
    TareService,
    WeighingPerformanceService,
    ZeroTestsService,
    calculate_corrected_error,
    calculate_net_error,
    calculate_raw_error,
    calculate_turning_point_error,
    format_display_decimal,
    get_discrimination_tolerance,
    get_eccentricity_tolerance,
    get_repeatability_tolerance,
    get_weighing_mpe,
    get_zero_setting_tolerance,
    validate_instrument_parameters,
    validate_repeatability_input,
)


class ToleranceRulesTestCase(TestCase):
    """Test official OIML R 76-1:2006 Table 1 MPE limits across all accuracy classes."""

    def test_class_i_table_1_mpe_limits(self):
        """
        OIML R 76-1:2006 Table 1 Class I:
        0 <= m <= 50,000 e: ±0.5 e
        50,000 e < m <= 200,000 e: ±1.0 e
        m > 200,000 e: ±1.5 e
        """
        e_val = Decimal("0.0010")  # e = 1 mg = 0.0010 g

        # Point 1: 25 g = 25,000 e -> Range 1 -> MPE = 0.5 e = 0.0005 g
        res1 = get_weighing_mpe(Decimal("25.0000"), CLASS_I, e_val, is_initial_verification=True)
        self.assertTrue(res1.is_configured)
        self.assertEqual(res1.mpe_in_e, Decimal("0.5"))
        self.assertEqual(res1.mpe_value, Decimal("0.00050"))

        # Point 2: 100 g = 100,000 e -> Range 2 -> MPE = 1.0 e = 0.0010 g
        res2 = get_weighing_mpe(Decimal("100.0000"), CLASS_I, e_val, is_initial_verification=True)
        self.assertTrue(res2.is_configured)
        self.assertEqual(res2.mpe_in_e, Decimal("1.0"))
        self.assertEqual(res2.mpe_value, Decimal("0.0010"))

        # Point 3: 220 g = 220,000 e -> Range 3 -> MPE = 1.5 e = 0.0015 g
        res3 = get_weighing_mpe(Decimal("220.0000"), CLASS_I, e_val, is_initial_verification=True)
        self.assertTrue(res3.is_configured)
        self.assertEqual(res3.mpe_in_e, Decimal("1.5"))
        self.assertEqual(res3.mpe_value, Decimal("0.00150"))

    def test_class_ii_table_1_mpe_limits(self):
        """
        OIML R 76-1:2006 Table 1 Class II:
        0 <= m <= 5,000 e: ±0.5 e
        5,000 e < m <= 20,000 e: ±1.0 e
        20,000 e < m <= 100,000 e: ±1.5 e
        """
        e_val = Decimal("0.05")

        # 200 g = 4,000 e -> Range 1 -> 0.5 e = 0.025 g
        res1 = get_weighing_mpe(Decimal("200.0"), CLASS_II, e_val)
        self.assertEqual(res1.mpe_in_e, Decimal("0.5"))
        self.assertEqual(res1.mpe_value, Decimal("0.025"))

        # 500 g = 10,000 e -> Range 2 -> 1.0 e = 0.050 g
        res2 = get_weighing_mpe(Decimal("500.0"), CLASS_II, e_val)
        self.assertEqual(res2.mpe_in_e, Decimal("1.0"))
        self.assertEqual(res2.mpe_value, Decimal("0.050"))

        # 2,000 g = 40,000 e -> Range 3 -> 1.5 e = 0.075 g
        res3 = get_weighing_mpe(Decimal("2000.0"), CLASS_II, e_val)
        self.assertEqual(res3.mpe_in_e, Decimal("1.5"))
        self.assertEqual(res3.mpe_value, Decimal("0.075"))

    def test_class_iii_table_1_and_in_service_mpe(self):
        """Class III limits: initial vs in-service inspection (2x initial)."""
        e_val = Decimal("0.010")  # 10 g

        # Initial verification at 10 kg = 1,000 e -> Range 2 (500 < m <= 2,000 e) -> 1.0 e = 0.010 kg
        res_initial = get_weighing_mpe(Decimal("10.000"), CLASS_III, e_val, is_initial_verification=True)
        self.assertEqual(res_initial.mpe_in_e, Decimal("1.0"))
        self.assertEqual(res_initial.mpe_value, Decimal("0.010"))

        # In-service inspection at 10 kg -> 2.0 e = 0.020 kg
        res_service = get_weighing_mpe(Decimal("10.000"), CLASS_III, e_val, is_initial_verification=False)
        self.assertEqual(res_service.mpe_in_e, Decimal("2.0"))
        self.assertEqual(res_service.mpe_value, Decimal("0.020"))

    def test_unconfigured_rule_safeguard(self):
        """Unsupported edition or invalid class must be reported as unconfigured and NOT evaluated."""
        res_bad_edition = get_weighing_mpe(
            Decimal("100.0"),
            CLASS_I,
            Decimal("0.01"),
            standard_edition="OIML R 76-UNKNOWN:2099",
        )
        self.assertFalse(res_bad_edition.is_configured)
        self.assertIn("NOT CONFIGURED", res_bad_edition.explanation)
        self.assertIsNone(res_bad_edition.mpe_value)

        res_bad_class = get_weighing_mpe(Decimal("100.0"), "INVALID_CLASS", Decimal("0.01"))
        self.assertFalse(res_bad_class.is_configured)
        self.assertIn("NOT CONFIGURED", res_bad_class.explanation)


class ErrorCalculationHelpersTestCase(TestCase):
    """Test precision arithmetic and metrological error calculations without intermediate rounding."""

    def test_calculate_raw_error(self):
        # Indication - Reference load
        err = calculate_raw_error(Decimal("100.0005"), Decimal("100.0000"))
        self.assertEqual(err, Decimal("0.0005"))

    def test_calculate_corrected_error(self):
        # Ec = E - E0
        raw = Decimal("0.0005")
        zero_err = Decimal("0.0001")
        corr = calculate_corrected_error(raw, zero_err)
        self.assertEqual(corr, Decimal("0.0004"))

    def test_calculate_turning_point_error(self):
        # E = (I + 0.5d - ΔL) - L
        # L = 100.0000, I = 100.0000, d = 0.0001, ΔL = 0.00003
        # True indication P = 100.0000 + 0.00005 - 0.00003 = 100.00002
        # E = 100.00002 - 100.0000 = +0.00002
        err = calculate_turning_point_error(
            indication=Decimal("100.0000"),
            scale_interval=Decimal("0.0001"),
            small_weights_added=Decimal("0.00003"),
            reference_load=Decimal("100.0000"),
        )
        self.assertEqual(err, Decimal("0.00002"))

    def test_format_display_decimal(self):
        val = Decimal("0.00054321")
        self.assertEqual(format_display_decimal(val, 4), "0.0005")
        self.assertEqual(format_display_decimal(val, 4, show_plus_sign=True), "+0.0005")
        self.assertEqual(format_display_decimal(None), "—")


class ValidationServiceTestCase(TestCase):
    """Test input validation for parameters and observations."""

    def test_validate_instrument_parameters_success(self):
        validate_instrument_parameters(
            accuracy_class=CLASS_I,
            max_capacity=Decimal("220.0"),
            min_capacity=Decimal("0.01"),
            scale_interval=Decimal("0.0001"),
            actual_scale_interval=Decimal("0.0010"),
        )

    def test_validate_instrument_parameters_negative_capacity(self):
        with self.assertRaises(InvalidInputError):
            validate_instrument_parameters(
                accuracy_class=CLASS_I,
                max_capacity=Decimal("-10.0"),
                min_capacity=Decimal("0.01"),
                scale_interval=Decimal("0.0001"),
                actual_scale_interval=Decimal("0.0010"),
            )

    def test_validate_repeatability_minimum_repetitions(self):
        # Must have at least 3 readings
        with self.assertRaises(InsufficientDataError):
            validate_repeatability_input(
                nominal_load=Decimal("100.0"),
                indications=[Decimal("100.0"), Decimal("100.0")],
                min_repetitions=3,
            )


class ProcedureServicesTestCase(TestCase):
    """Test procedure services for Weighing, Repeatability, Eccentricity, Zero, Discrimination, Tare."""

    def test_weighing_performance_service_pass_and_fail(self):
        # Class I: e = 0.0010 g, Load = 100.0000 g -> MPE = ±0.0010 g
        res_pass = WeighingPerformanceService.calculate_point(
            nominal_load="100.0000",
            indication="100.0008",
            accuracy_class=CLASS_I,
            actual_scale_interval="0.0010",
        )
        self.assertEqual(res_pass.calculated_error, Decimal("0.0008"))
        self.assertEqual(res_pass.permissible_error_mpe, Decimal("0.0010"))
        self.assertEqual(res_pass.comparison_result, CalculationCompliance.PASS)
        self.assertIn("satisfies", res_pass.explanation)

        # Indication error exceeds MPE (0.0015 > 0.0010)
        res_fail = WeighingPerformanceService.calculate_point(
            nominal_load="100.0000",
            indication="100.0015",
            accuracy_class=CLASS_I,
            actual_scale_interval="0.0010",
        )
        self.assertEqual(res_fail.calculated_error, Decimal("0.0015"))
        self.assertEqual(res_fail.comparison_result, CalculationCompliance.FAIL)
        self.assertIn("exceeds", res_fail.explanation)

    def test_repeatability_service_evaluation(self):
        # Class I: e = 0.0010 g, Load = 100 g -> MPE = 0.0010 g
        # Readings: [100.0001, 100.0003, 100.0000] -> Range = 0.0003 <= 0.0010 -> PASS
        res = RepeatabilityService.calculate_series(
            nominal_load="100.0000",
            indications=["100.0001", "100.0003", "100.0000"],
            accuracy_class=CLASS_I,
            actual_scale_interval="0.0010",
            series_name="Series 1 (~0.5 Max)",
        )
        self.assertEqual(res.calculated_range, Decimal("0.0003"))
        self.assertEqual(res.permissible_range_mpe, Decimal("0.0010"))
        self.assertEqual(res.comparison_result, CalculationCompliance.PASS)
        self.assertIn("Range R = I_max - I_min = 0.0003", res.explanation)

    def test_eccentricity_service_evaluation(self):
        # Class I: e = 0.0010 g, Load = 70 g -> MPE = 0.0010 g
        res = EccentricityService.calculate_position(
            nominal_load="70.0000",
            indication="70.0004",
            position="FRONT_LEFT",
            accuracy_class=CLASS_I,
            actual_scale_interval="0.0010",
        )
        self.assertEqual(res.calculated_error, Decimal("0.0004"))
        self.assertEqual(res.comparison_result, CalculationCompliance.PASS)
        self.assertEqual(res.position_key, "FRONT_LEFT")

    def test_zero_tests_service_evaluation(self):
        # e = 0.0010 g, d = 0.0001 g -> MPE = ±0.25e = ±0.00025 g
        # turning point method: I = 0, ΔL = 0.00005 -> E0 = 0 + 0.5(0.0001) - 0.00005 = 0.0000
        res = ZeroTestsService.calculate_zero_check(
            zero_indication_after="0.0000",
            scale_interval="0.0001",
            actual_scale_interval="0.0010",
            small_weight_added="0.00005",
            operation_type="NON_AUTOMATIC",
        )
        self.assertEqual(res.calculated_zero_error, Decimal("0.00000"))
        self.assertEqual(res.permissible_mpe, Decimal("0.00025"))
        self.assertEqual(res.comparison_result, CalculationCompliance.PASS)

    def test_discrimination_service_evaluation(self):
        # d = 0.0001 g. Threshold is >= 1d = 0.0001
        # Before = 50.0000, After = 50.0002 -> Change = 0.0002 >= 0.0001 -> PASS
        res_pass = DiscriminationService.calculate_discrimination(
            test_load="50.0000",
            indication_before="50.0000",
            small_weight_added="0.00014",
            indication_after="50.0002",
            scale_interval="0.0001",
        )
        self.assertEqual(res_pass.observed_change, Decimal("0.0002"))
        self.assertEqual(res_pass.comparison_result, CalculationCompliance.PASS)

        # Inadequate response: Change = 0.0000 < 0.0001 -> FAIL
        res_fail = DiscriminationService.calculate_discrimination(
            test_load="50.0000",
            indication_before="50.0000",
            small_weight_added="0.00014",
            indication_after="50.0000",
            scale_interval="0.0001",
        )
        self.assertEqual(res_fail.observed_change, Decimal("0.0000"))
        self.assertEqual(res_fail.comparison_result, CalculationCompliance.FAIL)

    def test_tare_service_evaluation(self):
        # Tare = 20 g, Gross = 70.0000 g, Net = 50.0002 g
        # Effective net = 70 - 20 = 50. Error = 50.0002 - 50 = +0.0002
        res = TareService.calculate_tare_point(
            tare_load="20.0000",
            gross_indication="70.0000",
            net_indication="50.0002",
            accuracy_class=CLASS_I,
            actual_scale_interval="0.0010",
        )
        self.assertEqual(res.calculated_net_error, Decimal("0.0002"))
        self.assertEqual(res.comparison_result, CalculationCompliance.PASS)


class CoordinatorAndIntegrationTestCase(TestCase):
    """Test full session evaluation, database persistence, and calculation results view."""

    def setUp(self):
        self.org = Organization.objects.create(name="Federal Metrology Institute")
        self.operator = CustomUser.objects.create_user(
            username="metrologist",
            email="metro@lab.gov",
            password="StrongPassword123!",
            role=UserRole.LAB_OPERATOR,
            organization=self.org,
        )

        self.instrument = Instrument.objects.create(
            organization=self.org,
            instrument_name="Analytical Micro-Balance",
            manufacturer="Sartorius",
            model_name="Cubis II",
            model_number="MCA225S",
            serial_number="SAR-2026-0099",
            instrument_type=CommonInstrumentType.ANALYTICAL_BALANCE,
            accuracy_class=AccuracyClass.CLASS_I,
            max_capacity=Decimal("220.0000"),
            min_capacity=Decimal("0.0100"),
            actual_scale_interval=Decimal("0.0010"),  # e = 1 mg
            scale_interval=Decimal("0.0001"),         # d = 0.1 mg
            unit_of_measurement="g",
            created_by=self.operator,
        )

        self.session = TestSession.objects.create(
            organization=self.org,
            instrument=self.instrument,
            session_number="TEST-2026-CALC-01",
            technician=self.operator,
            status="IN_PROGRESS",
            temperature_start=Decimal("20.0"),
            proc_weighing=True,
            proc_repeatability=True,
        )

        # Create sample raw weighing measurements
        WeighingMeasurement.objects.create(
            session=self.session,
            sequence_order=1,
            nominal_load=Decimal("50.0000"),
            indication=Decimal("50.0002"),
            created_by=self.operator,
        )
        WeighingMeasurement.objects.create(
            session=self.session,
            sequence_order=2,
            nominal_load=Decimal("100.0000"),
            indication=Decimal("100.0005"),
            created_by=self.operator,
        )

        self.client = Client()
        self.client.force_login(self.operator)

    def test_coordinator_evaluates_and_persists_session(self):
        """Test coordinator calculates all observations and saves CalculationRecords to DB."""
        records = SessionCalculationCoordinator.evaluate_session(self.session, calculated_by=self.operator)
        self.assertEqual(len(records), 2)

        # Verify records stored in database
        db_records = CalculationRecord.objects.filter(session=self.session)
        self.assertEqual(db_records.count(), 2)

        rec1 = db_records.get(sequence_number=1)
        self.assertEqual(rec1.reference_load, Decimal("50.0000"))
        self.assertEqual(rec1.calculated_error, Decimal("0.0002"))
        self.assertEqual(rec1.comparison_result, CalculationCompliance.PASS)
        self.assertEqual(rec1.standard_edition, "OIML R 76-1:2006")
        self.assertEqual(rec1.rule_version, "R76-2006-v1.0")
        self.assertIn("Table 1", rec1.explanation)

        # Verify session overall result updated
        self.session.refresh_from_db()
        self.assertEqual(self.session.overall_result, "PASS")

    def test_calculation_results_page_view(self):
        """Test calculation results page loads successfully and displays metrological explanations."""
        url = reverse("calculations:session_results", kwargs={"session_pk": self.session.pk})
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Automated Metrological Calculation Results")
        self.assertContains(resp, "50.0000")
        self.assertContains(resp, "PASS")
        self.assertContains(resp, "OIML R 76-1:2006")
        self.assertContains(resp, "Explanation of the Calculation")

    def test_session_recalculate_view(self):
        """Test recalculate endpoint re-triggers calculation engine."""
        url = reverse("calculations:session_recalculate", kwargs={"session_pk": self.session.pk})
        resp = self.client.post(url)
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(CalculationRecord.objects.filter(session=self.session).exists())

