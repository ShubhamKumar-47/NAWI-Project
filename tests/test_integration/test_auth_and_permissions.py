"""tests/test_integration/test_auth_and_permissions.py – Comprehensive Auth & RBAC Tests."""
from django.test import TestCase, Client
from django.urls import reverse
from apps.accounts.models import CustomUser, Organization
from apps.core.constants import UserRole, SessionStatus, AccuracyClass
from apps.instruments.models import Instrument
from apps.test_sessions.models import TestSession
from decimal import Decimal
from datetime import date


class TestAuthenticationAndPermissions(TestCase):
    def setUp(self):
        self.client = Client()
        self.org = Organization.objects.create(
            name="Apex Metrology Lab",
            accreditation_number="ACC-2026-99",
        )

        # 1. Administrator
        self.admin_user = CustomUser.objects.create_user(
            email="admin@apex.local",
            username="admin_apex",
            password="AdminPassword123!",
            role=UserRole.ADMINISTRATOR,
            organization=self.org,
            must_change_password=False,
        )

        # 2. Laboratory Operator
        self.operator_user = CustomUser.objects.create_user(
            email="operator@apex.local",
            username="operator_apex",
            password="OperatorPassword123!",
            role=UserRole.LAB_OPERATOR,
            organization=self.org,
            must_change_password=False,
        )

        # 3. Reviewer / Approver
        self.reviewer_user = CustomUser.objects.create_user(
            email="reviewer@apex.local",
            username="reviewer_apex",
            password="ReviewerPassword123!",
            role=UserRole.REVIEWER,
            organization=self.org,
            must_change_password=False,
        )

        # Sample instrument & session
        self.instrument = Instrument.objects.create(
            organization=self.org,
            serial_number="TEST-SN-001",
            manufacturer="Mettler Toledo",
            model_name="XP205",
            accuracy_class=AccuracyClass.CLASS_I,
            max_capacity=Decimal("220.0000"),
            min_capacity=Decimal("0.0010"),
            scale_interval=Decimal("0.00001"),
            actual_scale_interval=Decimal("0.001"),
            created_by=self.admin_user,
        )

        self.session = TestSession.objects.create(
            organization=self.org,
            instrument=self.instrument,
            session_number="TS-TEST-0001",
            test_date=date.today(),
            technician=self.operator_user,
            status=SessionStatus.PENDING_REVIEW,
            created_by=self.operator_user,
        )

    # ── Authentication Tests ───────────────────────────────────────────────────

    def test_login_success(self):
        """User can sign in with valid email and password."""
        response = self.client.post(reverse("accounts:login"), {
            "username": "operator@apex.local",
            "password": "OperatorPassword123!",
        })
        self.assertEqual(response.status_code, 302)
        self.assertTrue("_auth_user_id" in self.client.session)

    def test_login_failure_invalid_credentials(self):
        """Invalid credentials display an error."""
        response = self.client.post(reverse("accounts:login"), {
            "username": "operator@apex.local",
            "password": "WrongPassword!",
        })
        self.assertEqual(response.status_code, 200)
        self.assertFalse("_auth_user_id" in self.client.session)

    def test_logout(self):
        """Authenticated user can sign out."""
        self.client.login(username="operator@apex.local", password="OperatorPassword123!")
        response = self.client.post(reverse("accounts:logout"))
        self.assertEqual(response.status_code, 302)
        self.assertFalse("_auth_user_id" in self.client.session)

    def test_password_reset_page_accessible(self):
        """Password reset request page renders properly."""
        response = self.client.get(reverse("accounts:password_reset"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Reset Password")

    def test_profile_view_and_update(self):
        """Authenticated user can view and edit their profile."""
        self.client.login(username="operator@apex.local", password="OperatorPassword123!")
        response = self.client.get(reverse("accounts:profile"))
        self.assertEqual(response.status_code, 200)

        # Update profile
        update_resp = self.client.post(reverse("accounts:profile"), {
            "first_name": "Updated",
            "last_name": "Operator",
            "job_title": "Senior Metrologist",
            "phone": "+1-555-4321",
        })
        self.assertEqual(update_resp.status_code, 302)
        self.operator_user.refresh_from_db()
        self.assertEqual(self.operator_user.first_name, "Updated")
        self.assertEqual(self.operator_user.job_title, "Senior Metrologist")

    # ── Role-Based Access Control (RBAC) Enforcement Tests ─────────────────────

    def test_unauthenticated_user_redirected_to_login(self):
        """Anonymous user trying to access protected views is redirected to login."""
        protected_urls = [
            reverse("instruments:list"),
            reverse("test_sessions:list"),
            reverse("accounts:user_list"),
        ]
        for url in protected_urls:
            response = self.client.get(url)
            self.assertEqual(response.status_code, 302)
            self.assertIn("/accounts/login/", response.url)

    def test_administrator_permissions(self):
        """Administrator has access to user management, organizations, instruments, and sessions."""
        self.client.login(username="admin@apex.local", password="AdminPassword123!")

        # User management
        resp = self.client.get(reverse("accounts:user_list"))
        self.assertEqual(resp.status_code, 200)

        # Create user
        resp_create = self.client.get(reverse("accounts:user_create"))
        self.assertEqual(resp_create.status_code, 200)

        # Organizations
        resp_org = self.client.get(reverse("accounts:org_list"))
        self.assertEqual(resp_org.status_code, 200)

        # Instruments & Sessions
        self.assertEqual(self.client.get(reverse("instruments:list")).status_code, 200)
        self.assertEqual(self.client.get(reverse("test_sessions:list")).status_code, 200)

    def test_operator_blocked_from_admin_urls(self):
        """Laboratory Operator is denied access (HTTP 403) when manually accessing user management."""
        self.client.login(username="operator@apex.local", password="OperatorPassword123!")

        # User list
        resp = self.client.get(reverse("accounts:user_list"))
        self.assertEqual(resp.status_code, 403)

        # User create
        resp_create = self.client.get(reverse("accounts:user_create"))
        self.assertEqual(resp_create.status_code, 403)

        # Organization list
        resp_org = self.client.get(reverse("accounts:org_list"))
        self.assertEqual(resp_org.status_code, 403)

        # But Operator CAN access Instruments and Test Sessions
        self.assertEqual(self.client.get(reverse("instruments:list")).status_code, 200)
        self.assertEqual(self.client.get(reverse("test_sessions:list")).status_code, 200)

    def test_reviewer_blocked_from_admin_urls_and_can_review(self):
        """Reviewer is blocked from user administration but can access test sessions for approval."""
        self.client.login(username="reviewer@apex.local", password="ReviewerPassword123!")

        # Blocked from user management
        resp = self.client.get(reverse("accounts:user_list"))
        self.assertEqual(resp.status_code, 403)

        # Allowed to access session detail
        session_resp = self.client.get(reverse("test_sessions:detail", kwargs={"pk": self.session.pk}))
        self.assertEqual(session_resp.status_code, 200)

        # Configure session so it is complete and eligible for approval under OIML R 76 rules
        self.session.proc_zero_setting = False
        self.session.proc_weighing = False
        self.session.proc_repeatability = False
        self.session.proc_eccentricity = False
        self.session.proc_discrimination = False
        self.session.proc_tare = False
        self.session.proc_initial_examination = True
        self.session.initial_examination_passed = True
        self.session.save()

        # Reviewer can approve session
        approve_resp = self.client.post(reverse("test_sessions:approve", kwargs={"pk": self.session.pk}))
        self.assertEqual(approve_resp.status_code, 302)
        self.session.refresh_from_db()
        self.assertEqual(self.session.status, SessionStatus.APPROVED)
        self.assertTrue(self.session.is_locked)

    def test_operator_cannot_approve_session(self):
        """Laboratory Operator cannot approve test sessions (HTTP 403)."""
        self.client.login(username="operator@apex.local", password="OperatorPassword123!")
        resp = self.client.post(reverse("test_sessions:approve", kwargs={"pk": self.session.pk}))
        self.assertEqual(resp.status_code, 403)

