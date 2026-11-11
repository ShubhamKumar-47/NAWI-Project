"""apps/measurements/tests.py – Comprehensive test suite for test observation module."""
from decimal import Decimal
from django.test import TestCase, Client
from django.urls import reverse

from apps.accounts.models import CustomUser, Organization
from apps.core.constants import AccuracyClass, PassFail, UserRole, WeighingTestType
from apps.instruments.models import Instrument, CommonInstrumentType
from apps.test_sessions.models import TestSession
from apps.measurements.models import (
    WeighingMeasurement,
    RepeatabilityMeasurement,
    EccentricityMeasurement,
    DiscriminationMeasurement,
    TareMeasurement,
    ZeroSettingMeasurement,
)
from apps.measurements.forms import (
    WeighingMeasurementForm,
    RepeatabilityMeasurementForm,
    EccentricityMeasurementForm,
    DiscriminationMeasurementForm,
    TareMeasurementForm,
    ZeroSettingMeasurementForm,
)


class TestObservationModuleTestCase(TestCase):
    """Test suite covering OIML R 76 test observation models, forms, calculations, and views."""

    def setUp(self):
        self.org = Organization.objects.create(name="Metrology Standards Lab")
        self.other_org = Organization.objects.create(name="Competitor Lab")

        self.operator = CustomUser.objects.create_user(
            username="operator1",
            email="op@lab.com",
            password="StrongPassword123!",
            role=UserRole.LAB_OPERATOR,
            organization=self.org,
        )

        self.other_operator = CustomUser.objects.create_user(
            username="other_op",
            email="other@lab.com",
            password="StrongPassword123!",
            role=UserRole.LAB_OPERATOR,
            organization=self.other_org,
        )

        self.instrument = Instrument.objects.create(
            organization=self.org,
            instrument_name="Precision Analytical Balance",
            manufacturer="Mettler Toledo",
            model_name="XPR205",
            model_number="XPR205",
            serial_number="MT-2026-XPR-001",
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
            session_number="TEST-2026-0001",
            technician=self.operator,
            status="IN_PROGRESS",
            temperature_start=Decimal("20.5"),
            humidity_start=Decimal("50.0"),
            proc_weighing=True,
            proc_repeatability=True,
            proc_eccentricity=True,
            proc_discrimination=True,
            proc_tare=True,
            proc_zero_setting=True,
        )

        self.client = Client()
        self.client.force_login(self.operator)

    # ─────────────────────────────────────────────────────────────────────────
    # 1. Weighing Performance Tests
    # ─────────────────────────────────────────────────────────────────────────

    def test_weighing_form_validation(self):
        """Test form validates nominal loads and reject negative values."""
        form = WeighingMeasurementForm(data={
            "test_type": WeighingTestType.INCREASING,
            "sequence_order": 1,
            "nominal_load": Decimal("-10.0000"),
            "indication": Decimal("10.0000"),
            "zero_indication": Decimal("0"),
            "tare_applied": Decimal("0"),
        })
        self.assertFalse(form.is_valid())
        self.assertIn("nominal_load", form.errors)

    def test_weighing_add_view_and_calculation(self):
        """Test adding a single weighing measurement runs through calculation engine."""
        url = reverse("measurements:weighing_add", kwargs={"session_pk": self.session.pk})
        resp = self.client.post(url, {
            "test_type": WeighingTestType.INCREASING,
            "sequence_order": 1,
            "nominal_load": "100.0000",
            "indication": "100.0005",
            "zero_indication": "0.0000",
            "tare_applied": "0.0000",
            "temperature": "20.5",
            "observations": "Clear indication",
        })
        self.assertEqual(resp.status_code, 302)
        m = WeighingMeasurement.objects.get(session=self.session, nominal_load=Decimal("100.0000"))
        self.assertEqual(m.error, Decimal("0.0005"))
        self.assertIsNotNone(m.mpe)
        self.assertIn(m.pass_fail, [PassFail.PASS, PassFail.FAIL])
        self.assertEqual(m.created_by, self.operator)

    def test_weighing_batch_save_view(self):
        """Test dynamic batch table save saves multiple rows and handles drafts."""
        url = reverse("measurements:weighing_batch_save", kwargs={"session_pk": self.session.pk})
        resp = self.client.post(url, {
            "action": "save",
            "row_test_type[]": ["INCREASING", "INCREASING", "DECREASING"],
            "row_nominal_load[]": ["10.0000", "50.0000", "50.0000"],
            "row_indication[]": ["10.0000", "50.0002", "50.0003"],
            "row_zero_indication[]": ["0", "0", "0"],
            "row_tare_applied[]": ["0", "0", "0"],
            "row_temperature[]": ["20.5", "20.5", "20.5"],
            "row_observations[]": ["Step 1", "Step 2", "Step 3 (unload)"],
        })
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(WeighingMeasurement.objects.filter(session=self.session).count(), 3)
        self.assertFalse(WeighingMeasurement.objects.filter(session=self.session, is_draft=True).exists())

    def test_weighing_batch_save_as_draft(self):
        """Test batch save with action='draft' marks observations as draft."""
        url = reverse("measurements:weighing_batch_save", kwargs={"session_pk": self.session.pk})
        resp = self.client.post(url, {
            "action": "draft",
            "row_test_type[]": ["INCREASING"],
            "row_nominal_load[]": ["20.0000"],
            "row_indication[]": ["20.0001"],
            "row_zero_indication[]": ["0"],
            "row_tare_applied[]": ["0"],
            "row_temperature[]": ["20.5"],
            "row_observations[]": ["Preliminary loading"],
        })
        self.assertEqual(resp.status_code, 302)
        m = WeighingMeasurement.objects.get(session=self.session, nominal_load=Decimal("20.0000"))
        self.assertTrue(m.is_draft)

    def test_weighing_delete(self):
        """Test deleting an observation."""
        m = WeighingMeasurement.objects.create(
            session=self.session,
            test_type=WeighingTestType.INCREASING,
            sequence_order=1,
            nominal_load=Decimal("10.0000"),
            indication=Decimal("10.0000"),
            created_by=self.operator,
        )
        url = reverse("measurements:weighing_delete", kwargs={"session_pk": self.session.pk, "pk": m.pk})
        resp = self.client.post(url)
        self.assertEqual(resp.status_code, 302)
        self.assertFalse(WeighingMeasurement.objects.filter(pk=m.pk).exists())

    # ─────────────────────────────────────────────────────────────────────────
    # 2. Repeatability Tests
    # ─────────────────────────────────────────────────────────────────────────

    def test_repeatability_batch_save_and_range_calculation(self):
        """Test repeatability series save calculates range and compares with MPE."""
        url = reverse("measurements:repeatability_batch_save", kwargs={"session_pk": self.session.pk})
        resp = self.client.post(url, {
            "action": "save",
            "series_name": "Series 1 (~0.5 Max)",
            "nominal_load": "100.0000",
            "temperature": "20.5",
            "observations": "Series check",
            "rep_indication[]": ["100.0001", "100.0002", "100.0000"],
            "rep_zero_indication[]": ["0", "0", "0"],
        })
        self.assertEqual(resp.status_code, 302)
        measurements = RepeatabilityMeasurement.objects.filter(session=self.session, series_name="Series 1 (~0.5 Max)")
        self.assertEqual(measurements.count(), 3)
        # All repetitions should inherit the series result
        first = measurements.first()
        self.assertEqual(first.pass_fail, PassFail.PASS)
        self.assertIsNotNone(first.mpe)

    # ─────────────────────────────────────────────────────────────────────────
    # 3. Eccentricity Tests
    # ─────────────────────────────────────────────────────────────────────────

    def test_eccentricity_batch_save(self):
        """Test batch-saving all 5 standard positions for eccentricity."""
        url = reverse("measurements:eccentricity_batch_save", kwargs={"session_pk": self.session.pk})
        resp = self.client.post(url, {
            "action": "save",
            "pos_key[]": ["CENTRE", "FRONT_LEFT", "BACK_LEFT", "BACK_RIGHT", "FRONT_RIGHT"],
            "pos_nominal_load[]": ["70.0000", "70.0000", "70.0000", "70.0000", "70.0000"],
            "pos_indication[]": ["70.0001", "70.0002", "70.0000", "70.0001", "70.0002"],
            "pos_zero_indication[]": ["0", "0", "0", "0", "0"],
            "pos_temperature[]": ["20.5", "20.5", "20.5", "20.5", "20.5"],
            "pos_observations[]": ["", "", "", "", ""],
        })
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(EccentricityMeasurement.objects.filter(session=self.session).count(), 5)
        for m in EccentricityMeasurement.objects.filter(session=self.session):
            self.assertEqual(m.pass_fail, PassFail.PASS)
            self.assertIsNotNone(m.error)

    # ─────────────────────────────────────────────────────────────────────────
    # 4. Discrimination Tests
    # ─────────────────────────────────────────────────────────────────────────

    def test_discrimination_batch_save_and_evaluation(self):
        """Test discrimination records calculate change and evaluate delta >= 1d."""
        url = reverse("measurements:discrimination_batch_save", kwargs={"session_pk": self.session.pk})
        # Scale interval d = 0.0001; 1.4d = 0.00014
        # Case 1: change is 0.0002 (>= 1d -> PASS)
        resp = self.client.post(url, {
            "action": "save",
            "disc_test_load[]": ["50.0000"],
            "disc_before[]": ["50.0000"],
            "disc_delta[]": ["0.00014"],
            "disc_after[]": ["50.0002"],
            "disc_temp[]": ["20.5"],
            "disc_obs[]": ["Clear digit advance"],
        })
        self.assertEqual(resp.status_code, 302)
        m = DiscriminationMeasurement.objects.get(session=self.session, test_load=Decimal("50.0000"))
        self.assertEqual(m.change, Decimal("0.0002"))
        self.assertEqual(m.pass_fail, PassFail.PASS)

    # ─────────────────────────────────────────────────────────────────────────
    # 5. Tare Weighing Tests
    # ─────────────────────────────────────────────────────────────────────────

    def test_tare_batch_save_and_calculation(self):
        """Test tare weighing observations evaluate net error against MPE."""
        url = reverse("measurements:tare_batch_save", kwargs={"session_pk": self.session.pk})
        resp = self.client.post(url, {
            "action": "save",
            "tare_load[]": ["20.0000"],
            "tare_net_load[]": ["50.0000"],
            "tare_gross[]": ["70.0000"],
            "tare_net[]": ["50.0002"],
            "tare_temp[]": ["20.5"],
            "tare_obs[]": ["Tare pan applied"],
        })
        self.assertEqual(resp.status_code, 302)
        m = TareMeasurement.objects.get(session=self.session, tare_load=Decimal("20.0000"))
        self.assertEqual(m.error, Decimal("0.0002"))
        self.assertEqual(m.pass_fail, PassFail.PASS)

    # ─────────────────────────────────────────────────────────────────────────
    # 6. Zero-Setting & Tracking Tests
    # ─────────────────────────────────────────────────────────────────────────

    def test_zero_setting_batch_save_and_tolerance(self):
        """Test zero-setting check computes E0 = I + 0.5d - delta and compares with ±0.25e."""
        url = reverse("measurements:zero_setting_batch_save", kwargs={"session_pk": self.session.pk})
        # e = 0.0010; MPE = 0.25e = 0.00025
        # d = 0.0001
        # turning point with delta = 0.00005 -> E0 = 0 + 0.5(0.0001) - 0.00005 = 0.0000 -> PASS
        resp = self.client.post(url, {
            "action": "save",
            "zero_op[]": ["NON_AUTOMATIC"],
            "zero_before[]": ["0.0000"],
            "zero_after[]": ["0.0000"],
            "zero_delta[]": ["0.00005"],
            "zero_temp[]": ["20.5"],
            "zero_obs[]": ["Zero verified"],
        })
        self.assertEqual(resp.status_code, 302)
        m = ZeroSettingMeasurement.objects.get(session=self.session)
        self.assertEqual(m.calculated_error, Decimal("0.0000"))
        self.assertEqual(m.pass_fail, PassFail.PASS)
        self.session.refresh_from_db()
        self.assertTrue(self.session.zero_test_passed)

    # ─────────────────────────────────────────────────────────────────────────
    # 7. Session Locking & Multi-Tenancy Protection
    # ─────────────────────────────────────────────────────────────────────────

    def test_locked_session_prevents_observation_edits(self):
        """Approved or locked session prevents all write operations."""
        self.session.is_locked = True
        self.session.status = "APPROVED"
        self.session.save()

        # Attempt to add weighing measurement
        url = reverse("measurements:weighing_add", kwargs={"session_pk": self.session.pk})
        resp = self.client.post(url, {
            "test_type": WeighingTestType.INCREASING,
            "sequence_order": 1,
            "nominal_load": "10.0000",
            "indication": "10.0000",
        })
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(WeighingMeasurement.objects.filter(session=self.session).count(), 0)

    def test_multi_tenancy_isolation(self):
        """Operator from another organization cannot view or modify observations."""
        self.client.force_login(self.other_operator)
        url = reverse("measurements:weighing_list", kwargs={"session_pk": self.session.pk})
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 404)
