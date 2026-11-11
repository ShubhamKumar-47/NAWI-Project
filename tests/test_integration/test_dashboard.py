"""tests/test_integration/test_dashboard.py – Unit tests for Dashboard components and filtering."""
from django.test import TestCase, Client
from django.urls import reverse
from apps.accounts.models import CustomUser, Organization
from apps.core.constants import UserRole, SessionStatus, AccuracyClass
from apps.instruments.models import Instrument
from apps.test_sessions.models import TestSession
from decimal import Decimal
import datetime


class TestDashboardComponents(TestCase):
    def setUp(self):
        self.client = Client()
        self.org = Organization.objects.create(name="Precision Standards Lab")
        self.user = CustomUser.objects.create_user(
            email="manager@psl.local",
            username="psl_manager",
            password="ManagerPassword123!",
            role=UserRole.LAB_MANAGER,
            organization=self.org,
            must_change_password=False,
        )
        self.client.login(username="manager@psl.local", password="ManagerPassword123!")

        # Create instruments
        self.inst1 = Instrument.objects.create(
            organization=self.org,
            serial_number="INS-01",
            manufacturer="Mettler",
            model_name="MS-300",
            accuracy_class=AccuracyClass.CLASS_II,
            max_capacity=Decimal("300.00"),
            min_capacity=Decimal("0.50"),
            scale_interval=Decimal("0.01"),
            actual_scale_interval=Decimal("0.01"),
            created_by=self.user,
        )

        today = datetime.date.today()

        # Create test records with various statuses
        TestSession.objects.create(
            organization=self.org,
            instrument=self.inst1,
            session_number="TS-DASH-01",
            test_date=today,
            technician=self.user,
            status=SessionStatus.IN_PROGRESS,
            created_by=self.user,
        )
        TestSession.objects.create(
            organization=self.org,
            instrument=self.inst1,
            session_number="TS-DASH-02",
            test_date=today,
            technician=self.user,
            status=SessionStatus.PENDING_REVIEW,
            created_by=self.user,
        )
        TestSession.objects.create(
            organization=self.org,
            instrument=self.inst1,
            session_number="TS-DASH-03",
            test_date=today - datetime.timedelta(days=10),
            technician=self.user,
            status=SessionStatus.APPROVED,
            created_by=self.user,
        )
        TestSession.objects.create(
            organization=self.org,
            instrument=self.inst1,
            session_number="TS-DASH-04",
            test_date=today - datetime.timedelta(days=40),
            technician=self.user,
            status=SessionStatus.REJECTED,
            created_by=self.user,
        )

    def test_dashboard_kpis_reflect_database_queries(self):
        """Dashboard KPI cards display actual counts from DB."""
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)

        # Context assertions
        kpi = response.context["kpi"]
        self.assertEqual(kpi["total_instruments"], 1)
        self.assertEqual(kpi["total_records"], 4)
        self.assertEqual(kpi["in_progress"], 1)
        self.assertEqual(kpi["pending_review"], 1)
        self.assertEqual(kpi["approved"], 1)
        self.assertEqual(kpi["rejected"], 1)

    def test_dashboard_status_filtering(self):
        """Filtering by status correctly reduces the visible records and KPIs."""
        response = self.client.get("/?status=PENDING_REVIEW")
        self.assertEqual(response.status_code, 200)

        kpi = response.context["kpi"]
        self.assertEqual(kpi["total_records"], 1)
        self.assertEqual(kpi["pending_review"], 1)
        self.assertEqual(kpi["approved"], 0)

    def test_dashboard_date_preset_filtering(self):
        """Preset date filtering limits query to specified date ranges."""
        response = self.client.get("/?preset=today")
        self.assertEqual(response.status_code, 200)

        kpi = response.context["kpi"]
        # Only TS-DASH-01 and TS-DASH-02 were created today
        self.assertEqual(kpi["total_records"], 2)

    def test_pending_approvals_rendered(self):
        """Sessions pending review are surfaced in the pending approvals section."""
        response = self.client.get("/")
        self.assertContains(response, "TS-DASH-02")
        self.assertContains(response, "Reports Pending Review")
