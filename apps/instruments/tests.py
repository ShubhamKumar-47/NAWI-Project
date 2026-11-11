"""apps/instruments/tests.py – Comprehensive unit and integration tests for Instrument Management."""
from decimal import Decimal
from django.test import TestCase, Client
from django.urls import reverse
from django.utils import timezone
from apps.accounts.models import CustomUser, Organization
from apps.core.constants import UserRole, AccuracyClass, InstrumentStatus, SessionStatus
from apps.instruments.models import Instrument, CommonInstrumentType, MeasurementUnit
from apps.instruments.forms import InstrumentForm
from apps.test_sessions.models import TestSession


class InstrumentModelAndValidationTests(TestCase):
    """Unit tests for Instrument model logic, auto-calculation, and form validations."""

    def setUp(self):
        self.org1 = Organization.objects.create(name="Central Metrology Lab")
        self.org2 = Organization.objects.create(name="Regional Calibration Lab")

        self.admin = CustomUser.objects.create_user(
            email="admin@cml.local",
            username="admin_cml",
            password="Password123!",
            role=UserRole.ADMINISTRATOR,
            organization=self.org1,
        )

    def test_instrument_creation_and_auto_n_calculation(self):
        """Model auto-computes n = Max / e and sets default dates."""
        inst = Instrument.objects.create(
            organization=self.org1,
            serial_number="SN-XP205-01",
            manufacturer="Mettler Toledo",
            model_name="XP205",
            accuracy_class=AccuracyClass.CLASS_I,
            max_capacity=Decimal("220.0000"),
            min_capacity=Decimal("0.0010"),
            scale_interval=Decimal("0.00001"),
            actual_scale_interval=Decimal("0.0010"),
            unit_of_measurement="g",
        )
        self.assertEqual(inst.n_max, 220000)
        self.assertEqual(inst.display_name, "Mettler Toledo XP205")
        self.assertIsNotNone(inst.registration_date)
        self.assertFalse(inst.e_equals_d)
        self.assertFalse(inst.has_test_records)
        self.assertFalse(inst.has_approved_tests)

    def test_e_equals_d_property(self):
        """Verify e_equals_d property when scale_interval equals actual_scale_interval."""
        inst = Instrument.objects.create(
            organization=self.org1,
            serial_number="SN-DEF3000-01",
            manufacturer="Ohaus",
            model_name="Defender 3000",
            accuracy_class=AccuracyClass.CLASS_III,
            max_capacity=Decimal("60.0000"),
            min_capacity=Decimal("0.4000"),
            scale_interval=Decimal("0.0200"),
            actual_scale_interval=Decimal("0.0200"),
            unit_of_measurement="kg",
        )
        self.assertTrue(inst.e_equals_d)
        self.assertEqual(inst.n_max, 3000)

    def test_unique_serial_number_within_organization(self):
        """Enforces unique serial number within an organisation."""
        Instrument.objects.create(
            organization=self.org1,
            serial_number="DUP-SN-001",
            manufacturer="Mettler",
            model_name="Model A",
            accuracy_class=AccuracyClass.CLASS_II,
            max_capacity=Decimal("1000.0000"),
            min_capacity=Decimal("1.0000"),
            scale_interval=Decimal("0.1000"),
            actual_scale_interval=Decimal("0.1000"),
        )

        form = InstrumentForm(
            data={
                "instrument_name": "Test Scale",
                "manufacturer": "Mettler",
                "model_name": "Model B",
                "serial_number": "DUP-SN-001",  # duplicate
                "accuracy_class": AccuracyClass.CLASS_II,
                "unit_of_measurement": "g",
                "max_capacity": "500.0000",
                "min_capacity": "0.5000",
                "scale_interval": "0.0500",
                "actual_scale_interval": "0.0500",
                "status": InstrumentStatus.IN_LAB,
            },
            organization=self.org1,
        )
        self.assertFalse(form.is_valid())
        self.assertIn("serial_number", form.errors)

    def test_allow_same_serial_number_in_different_organization(self):
        """Different organisations can have the same manufacturer serial number."""
        Instrument.objects.create(
            organization=self.org1,
            serial_number="SHARED-SN-001",
            manufacturer="Sartorius",
            model_name="Model X",
            accuracy_class=AccuracyClass.CLASS_I,
            max_capacity=Decimal("100.0000"),
            min_capacity=Decimal("0.0010"),
            scale_interval=Decimal("0.0001"),
            actual_scale_interval=Decimal("0.0010"),
        )

        form = InstrumentForm(
            data={
                "instrument_name": "Different Org Instrument",
                "manufacturer": "Sartorius",
                "model_name": "Model X",
                "serial_number": "SHARED-SN-001",  # same serial, different org
                "accuracy_class": AccuracyClass.CLASS_I,
                "unit_of_measurement": "g",
                "max_capacity": "100.0000",
                "min_capacity": "0.0010",
                "scale_interval": "0.0001",
                "actual_scale_interval": "0.0010",
                "status": InstrumentStatus.IN_LAB,
            },
            organization=self.org2,
        )
        self.assertTrue(form.is_valid(), form.errors)

    def test_form_validation_min_must_be_less_than_max(self):
        """Form rejects when Min >= Max."""
        form = InstrumentForm(
            data={
                "manufacturer": "Kern",
                "model_name": "PCB",
                "serial_number": "KERN-001",
                "accuracy_class": AccuracyClass.CLASS_II,
                "unit_of_measurement": "g",
                "max_capacity": "500.0000",
                "min_capacity": "600.0000",  # Min > Max
                "scale_interval": "0.0100",
                "actual_scale_interval": "0.1000",
                "status": InstrumentStatus.IN_LAB,
            },
            organization=self.org1,
        )
        self.assertFalse(form.is_valid())
        self.assertIn("min_capacity", form.errors)

    def test_form_validation_d_cannot_exceed_e(self):
        """Form rejects when d > e per OIML R 76 §3.4."""
        form = InstrumentForm(
            data={
                "manufacturer": "Kern",
                "model_name": "PCB",
                "serial_number": "KERN-002",
                "accuracy_class": AccuracyClass.CLASS_II,
                "unit_of_measurement": "g",
                "max_capacity": "500.0000",
                "min_capacity": "1.0000",
                "scale_interval": "0.5000",  # d = 0.5
                "actual_scale_interval": "0.1000",  # e = 0.1 (d > e invalid)
                "status": InstrumentStatus.IN_LAB,
            },
            organization=self.org1,
        )
        self.assertFalse(form.is_valid())
        self.assertIn("scale_interval", form.errors)

    def test_form_validation_positive_metrological_values(self):
        """Form rejects negative or zero values for Max, d, and e."""
        form = InstrumentForm(
            data={
                "manufacturer": "Kern",
                "model_name": "PCB",
                "serial_number": "KERN-003",
                "accuracy_class": AccuracyClass.CLASS_II,
                "unit_of_measurement": "g",
                "max_capacity": "0",  # invalid
                "min_capacity": "-5",  # invalid
                "scale_interval": "0",  # invalid
                "actual_scale_interval": "-0.1",  # invalid
                "status": InstrumentStatus.IN_LAB,
            },
            organization=self.org1,
        )
        self.assertFalse(form.is_valid())
        self.assertIn("max_capacity", form.errors)
        self.assertIn("min_capacity", form.errors)
        self.assertIn("scale_interval", form.errors)
        self.assertIn("actual_scale_interval", form.errors)


class InstrumentViewsCRUDTests(TestCase):
    """Integration tests for Instrument views, search, filtering, and role permissions."""

    def setUp(self):
        self.client = Client()
        self.org = Organization.objects.create(name="National Metrology Institute")

        # Users for different roles
        self.admin = CustomUser.objects.create_user(
            email="admin@nmi.local",
            username="admin_nmi",
            password="AdminPassword123!",
            role=UserRole.ADMINISTRATOR,
            organization=self.org,
        )
        self.operator = CustomUser.objects.create_user(
            email="operator@nmi.local",
            username="operator_nmi",
            password="OperatorPassword123!",
            role=UserRole.LAB_OPERATOR,
            organization=self.org,
        )
        self.reviewer = CustomUser.objects.create_user(
            email="reviewer@nmi.local",
            username="reviewer_nmi",
            password="ReviewerPassword123!",
            role=UserRole.REVIEWER,
            organization=self.org,
        )

        # Seed sample instruments
        self.inst1 = Instrument.objects.create(
            organization=self.org,
            instrument_name="Ultra Microbalance",
            serial_number="SN-METTLER-001",
            manufacturer="Mettler Toledo",
            model_name="XPR2U",
            model_number="XPR-2U/A",
            customer_name="Pharma Lab Alpha",
            lab_reference_number="LAB-REF-001",
            accuracy_class=AccuracyClass.CLASS_I,
            max_capacity=Decimal("2.1000"),
            min_capacity=Decimal("0.0001"),
            scale_interval=Decimal("0.000001"),
            actual_scale_interval=Decimal("0.00001"),
            unit_of_measurement="g",
            status=InstrumentStatus.IN_LAB,
            created_by=self.operator,
        )
        self.inst2 = Instrument.objects.create(
            organization=self.org,
            instrument_name="Heavy Duty Platform Scale",
            serial_number="SN-AVERY-002",
            manufacturer="Avery Weigh-Tronix",
            model_name="BridgeScale 5000",
            customer_name="Logistics Depot Beta",
            lab_reference_number="LAB-REF-002",
            accuracy_class=AccuracyClass.CLASS_III,
            max_capacity=Decimal("3000.0000"),
            min_capacity=Decimal("20.0000"),
            scale_interval=Decimal("1.0000"),
            actual_scale_interval=Decimal("1.0000"),
            unit_of_measurement="kg",
            status=InstrumentStatus.IN_PROGRESS,
            created_by=self.operator,
        )

    def test_list_view_authentication_required(self):
        """Unauthenticated requests are redirected to login."""
        response = self.client.get(reverse("instruments:list"))
        self.assertEqual(response.status_code, 302)
        self.assertIn("/accounts/login/", response.url)

    def test_list_view_accessible_by_all_lab_staff(self):
        """Operator, Reviewer, and Administrator can all view instrument list."""
        for user in [self.operator, self.reviewer, self.admin]:
            self.client.force_login(user)
            response = self.client.get(reverse("instruments:list"))
            self.assertEqual(response.status_code, 200)
            self.assertContains(response, "Instrument Registry")
            self.assertContains(response, "SN-METTLER-001")
            self.assertContains(response, "SN-AVERY-002")

    def test_list_view_search_by_serial_number(self):
        """Search query filters results by serial number."""
        self.client.force_login(self.operator)
        response = self.client.get(reverse("instruments:list") + "?q=METTLER-001")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "SN-METTLER-001")
        self.assertNotContains(response, "SN-AVERY-002")

    def test_list_view_filter_by_manufacturer_and_class(self):
        """Filter results by manufacturer and accuracy class."""
        self.client.force_login(self.operator)
        # Filter by manufacturer
        response = self.client.get(reverse("instruments:list") + "?manufacturer=Avery Weigh-Tronix")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "BridgeScale 5000")
        self.assertNotContains(response, "XPR2U")

        # Filter by class
        response = self.client.get(reverse("instruments:list") + "?accuracy_class=I")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Ultra Microbalance")
        self.assertNotContains(response, "Heavy Duty Platform Scale")

    def test_detail_view_shows_full_specs_and_history(self):
        """Detail view displays metrological parameters, ownership, and test session history."""
        # Create an associated test session
        session = TestSession.objects.create(
            organization=self.org,
            instrument=self.inst1,
            test_date=timezone.now().date(),
            technician=self.operator,
            status=SessionStatus.IN_PROGRESS,
        )

        self.client.force_login(self.reviewer)
        response = self.client.get(reverse("instruments:detail", kwargs={"pk": self.inst1.pk}))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Ultra Microbalance")
        self.assertContains(response, "SN-METTLER-001")
        self.assertContains(response, "Pharma Lab Alpha")
        self.assertContains(response, "LAB-REF-001")
        self.assertContains(response, session.session_number)
        self.assertContains(response, "Instrument Test History &amp; Records")

    def test_create_instrument_by_operator(self):
        """Laboratory Operator can register new instruments."""
        self.client.force_login(self.operator)
        data = {
            "instrument_name": "Precision Top Pan Balance",
            "manufacturer": "Sartorius",
            "model_name": "Entris II",
            "model_number": "BCE224i-1S",
            "serial_number": "SN-SARTORIUS-8899",
            "instrument_type": "Precision Balance",
            "year_of_manufacture": 2024,
            "accuracy_class": AccuracyClass.CLASS_I,
            "unit_of_measurement": "g",
            "max_capacity": "220.0000",
            "min_capacity": "0.0100",
            "scale_interval": "0.0001",
            "actual_scale_interval": "0.0010",
            "customer_name": "BioTech Research Corp",
            "lab_reference_number": "LAB-REF-008",
            "location": "Calibration Bay 3",
            "registration_date": "2026-11-11",
            "received_date": "2026-11-11",
            "status": InstrumentStatus.IN_LAB,
        }
        response = self.client.post(reverse("instruments:create"), data=data)
        self.assertEqual(response.status_code, 302)  # Redirects to list
        self.assertTrue(Instrument.objects.filter(serial_number="SN-SARTORIUS-8899").exists())

    def test_reviewer_cannot_create_or_delete_instrument(self):
        """Reviewer role is read-only for instruments (cannot create or delete)."""
        self.client.force_login(self.reviewer)

        # Attempt to access create view -> 403 Forbidden
        response = self.client.get(reverse("instruments:create"))
        self.assertEqual(response.status_code, 403)

        # Attempt to access delete view -> 403 Forbidden
        response = self.client.get(reverse("instruments:delete", kwargs={"pk": self.inst1.pk}))
        self.assertEqual(response.status_code, 403)

    def test_update_instrument_by_operator(self):
        """Operator can update instrument specifications."""
        self.client.force_login(self.operator)
        data = {
            "instrument_name": "Updated Microbalance",
            "manufacturer": "Mettler Toledo",
            "model_name": "XPR2U",
            "serial_number": self.inst1.serial_number,
            "accuracy_class": AccuracyClass.CLASS_I,
            "unit_of_measurement": "g",
            "max_capacity": "2.1000",
            "min_capacity": "0.0001",
            "scale_interval": "0.000001",
            "actual_scale_interval": "0.00001",
            "location": "Cleanroom Suite 1",
            "status": InstrumentStatus.IN_LAB,
        }
        response = self.client.post(
            reverse("instruments:edit", kwargs={"pk": self.inst1.pk}),
            data=data,
        )
        self.assertEqual(response.status_code, 302)
        self.inst1.refresh_from_db()
        self.assertEqual(self.inst1.instrument_name, "Updated Microbalance")
        self.assertEqual(self.inst1.location, "Cleanroom Suite 1")

    def test_delete_instrument_by_administrator(self):
        """Administrator can delete (soft-delete) an instrument without approved tests."""
        self.client.force_login(self.admin)

        # GET confirmation page
        response = self.client.get(reverse("instruments:delete", kwargs={"pk": self.inst2.pk}))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Confirm Instrument Deletion")

        # POST deletion
        response = self.client.post(reverse("instruments:delete", kwargs={"pk": self.inst2.pk}))
        self.assertEqual(response.status_code, 302)

        self.inst2.refresh_from_db()
        self.assertTrue(self.inst2.is_deleted)
        self.assertIsNotNone(self.inst2.deleted_at)

    def test_delete_instrument_prevented_if_approved_tests_exist(self):
        """Instrument with approved certified test session cannot be deleted."""
        # Create an APPROVED test session
        TestSession.objects.create(
            organization=self.org,
            instrument=self.inst1,
            test_date=timezone.now().date(),
            technician=self.operator,
            reviewer=self.reviewer,
            status=SessionStatus.APPROVED,
        )

        self.client.force_login(self.admin)

        # GET should warn that deletion is blocked
        response = self.client.get(reverse("instruments:delete", kwargs={"pk": self.inst1.pk}))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Deletion Blocked: Metrological Compliance")

        # POST should refuse deletion and redirect back to detail view
        response = self.client.post(reverse("instruments:delete", kwargs={"pk": self.inst1.pk}))
        self.assertEqual(response.status_code, 302)
        self.inst1.refresh_from_db()
        self.assertFalse(self.inst1.is_deleted)
