"""apps/test_sessions/tests.py – Unit and integration tests for the Test Management module."""
import datetime
from decimal import Decimal
from django.test import TestCase, Client
from django.urls import reverse
from django.utils import timezone
from apps.accounts.models import CustomUser, Organization
from apps.core.constants import UserRole, AccuracyClass, SessionStatus, InstrumentStatus
from apps.instruments.models import Instrument
from apps.test_sessions.models import TestSession, OIMLEdition, generate_session_number
from apps.test_sessions.forms import TestSessionWizardForm, ProcedureSelectionForm
from apps.test_sessions.services import SessionService


class TestSessionModelAndFormTests(TestCase):
    """Unit tests for TestSession model logic, defaults, and form validations."""

    def setUp(self):
        self.org = Organization.objects.create(name="National Metrology Centre")
        self.operator = CustomUser.objects.create_user(
            email="tech@nmc.local",
            username="tech_nmc",
            password="Password123!",
            role=UserRole.LAB_OPERATOR,
            organization=self.org,
        )
        self.reviewer = CustomUser.objects.create_user(
            email="reviewer@nmc.local",
            username="reviewer_nmc",
            password="Password123!",
            role=UserRole.REVIEWER,
            organization=self.org,
        )
        self.instrument = Instrument.objects.create(
            organization=self.org,
            instrument_name="Precision Bench Scale",
            serial_number="SN-TEST-88",
            manufacturer="Mettler Toledo",
            model_name="PB3002-S",
            accuracy_class=AccuracyClass.CLASS_II,
            max_capacity=Decimal("3000.0000"),
            min_capacity=Decimal("0.5000"),
            scale_interval=Decimal("0.0100"),
            actual_scale_interval=Decimal("0.1000"),
            unit_of_measurement="g",
        )

    def test_session_number_generation_and_defaults(self):
        """Auto-generated unique Test ID format and default properties."""
        sn = generate_session_number()
        self.assertTrue(sn.startswith("TS-"))

        session = TestSession.objects.create(
            organization=self.org,
            instrument=self.instrument,
            technician=self.operator,
        )
        self.assertIsNotNone(session.session_number)
        self.assertEqual(session.status, SessionStatus.DRAFT)
        self.assertFalse(session.is_locked)
        self.assertEqual(session.oiml_edition, OIMLEdition.R76_2006)
        self.assertTrue(session.proc_weighing)
        self.assertTrue(session.proc_repeatability)
        self.assertTrue(session.proc_eccentricity)
        self.assertTrue(session.proc_discrimination)
        self.assertTrue(session.active_procedures_count >= 6)

    def test_environmental_ranges_and_remarks_sync(self):
        """Formatted environmental ranges and remarks/notes sync."""
        session = TestSession.objects.create(
            organization=self.org,
            instrument=self.instrument,
            technician=self.operator,
            temperature_start=Decimal("20.1"),
            temperature_end=Decimal("20.5"),
            humidity_start=Decimal("50.0"),
            humidity_end=Decimal("52.0"),
            remarks="Lab environment stable; draft shield operating smoothly.",
        )
        self.assertEqual(session.temperature_range, "20.1°C – 20.5°C")
        self.assertEqual(session.humidity_range, "50.0% – 52.0% RH")
        self.assertEqual(session.notes, session.remarks)

    def test_form_requires_at_least_one_procedure(self):
        """Form rejects submission if all procedures are deselected."""
        form = TestSessionWizardForm(
            data={
                "instrument": self.instrument.pk,
                "session_number": "TS-MANUAL-001",
                "test_date": timezone.now().date(),
                "technician": self.operator.pk,
                "oiml_edition": OIMLEdition.R76_2006,
                # All procedures deselected
                "proc_initial_examination": False,
                "proc_zero_setting": False,
                "proc_weighing": False,
                "proc_repeatability": False,
                "proc_eccentricity": False,
                "proc_discrimination": False,
                "proc_tare": False,
                "proc_influence_quantities": False,
            },
            organization=self.org,
            current_user=self.operator,
        )
        self.assertFalse(form.is_valid())
        self.assertIn("__all__", form.errors)

    def test_form_validates_relative_humidity_bounds(self):
        """Form rejects relative humidity outside 0-100%."""
        form = TestSessionWizardForm(
            data={
                "instrument": self.instrument.pk,
                "session_number": "TS-MANUAL-002",
                "test_date": timezone.now().date(),
                "technician": self.operator.pk,
                "oiml_edition": OIMLEdition.R76_2006,
                "humidity_start": "120.0",  # invalid
                "proc_weighing": True,
            },
            organization=self.org,
            current_user=self.operator,
        )
        self.assertFalse(form.is_valid())
        self.assertIn("humidity_start", form.errors)


class TestSessionViewsAndWorkflowTests(TestCase):
    """Integration tests for Test Management views, wizard, procedure config, and lifecycle."""

    def setUp(self):
        self.client = Client()
        self.org = Organization.objects.create(name="Regional Calibration Laboratory")

        self.operator = CustomUser.objects.create_user(
            email="tech@rcl.local",
            username="tech_rcl",
            password="TechPassword123!",
            role=UserRole.LAB_OPERATOR,
            organization=self.org,
        )
        self.reviewer = CustomUser.objects.create_user(
            email="reviewer@rcl.local",
            username="reviewer_rcl",
            password="ReviewerPassword123!",
            role=UserRole.REVIEWER,
            organization=self.org,
        )
        self.admin = CustomUser.objects.create_user(
            email="admin@rcl.local",
            username="admin_rcl",
            password="AdminPassword123!",
            role=UserRole.ADMINISTRATOR,
            organization=self.org,
        )

        self.instrument = Instrument.objects.create(
            organization=self.org,
            instrument_name="Top-Loading Balance",
            serial_number="SN-RCL-001",
            manufacturer="Kern",
            model_name="PCB 2500-2",
            accuracy_class=AccuracyClass.CLASS_II,
            max_capacity=Decimal("2500.0000"),
            min_capacity=Decimal("0.5000"),
            scale_interval=Decimal("0.0100"),
            actual_scale_interval=Decimal("0.1000"),
            unit_of_measurement="g",
            status=InstrumentStatus.IN_LAB,
        )

        self.session = TestSession.objects.create(
            organization=self.org,
            instrument=self.instrument,
            session_number="TS-RCL-2026-001",
            lab_reference_number="LAB-CAL-001",
            test_date=timezone.now().date(),
            technician=self.operator,
            status=SessionStatus.IN_PROGRESS,
            created_by=self.operator,
        )

    def test_session_list_view_accessible_by_all_staff(self):
        """Technician, Reviewer, and Admin can view the session registry."""
        for user in [self.operator, self.reviewer, self.admin]:
            self.client.force_login(user)
            response = self.client.get(reverse("test_sessions:list"))
            self.assertEqual(response.status_code, 200)
            self.assertContains(response, "Test Sessions &amp; Records")
            self.assertContains(response, "TS-RCL-2026-001")

    def test_session_list_search_and_filter(self):
        """Search by Test ID and filter by status."""
        self.client.force_login(self.operator)
        # Search by Test ID
        response = self.client.get(reverse("test_sessions:list") + "?q=RCL-2026-001")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "TS-RCL-2026-001")

        # Filter by status
        response = self.client.get(reverse("test_sessions:list") + "?status=IN_PROGRESS")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "TS-RCL-2026-001")

        # Filter by different status
        response = self.client.get(reverse("test_sessions:list") + "?status=APPROVED")
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "TS-RCL-2026-001")

    def test_session_detail_view_shows_all_12_items(self):
        """Detail view displays all 12 required test record components."""
        self.client.force_login(self.operator)
        response = self.client.get(reverse("test_sessions:detail", kwargs={"pk": self.session.pk}))
        self.assertEqual(response.status_code, 200)
        # 1. Unique Test ID
        self.assertContains(response, "TS-RCL-2026-001")
        # 2. Linked instrument
        self.assertContains(response, "Top-Loading Balance")
        self.assertContains(response, "SN-RCL-001")
        # 3. Lab reference number
        self.assertContains(response, "LAB-CAL-001")
        # 4. Test date
        self.assertContains(response, self.session.test_date.strftime("%d %B %Y"))
        # 5. Location
        self.assertContains(response, "Test Location")
        # 6. Operator name
        self.assertContains(response, "tech_rcl")
        # 7 & 8. Environmental Temperature & Humidity
        self.assertContains(response, "Environmental Conditions")
        # 9. OIML R 76 edition
        self.assertContains(response, "OIML R 76-1:2006")
        # 10. Test procedure selection
        self.assertContains(response, "Applicable Test Procedures")
        self.assertContains(response, "Weighing Performance Tests")
        # 11. Test status
        self.assertContains(response, "In Progress")
        # 12. Remarks
        self.assertContains(response, "Remarks")

    def test_create_session_wizard_save_as_draft(self):
        """Wizard creates incomplete session with DRAFT status."""
        self.client.force_login(self.operator)
        data = {
            "action_intent": "draft",
            "instrument": self.instrument.pk,
            "session_number": "TS-DRAFT-99",
            "lab_reference_number": "LAB-DRAFT-01",
            "test_date": "2026-11-11",
            "test_location": "Cleanroom Lab 2",
            "technician": self.operator.pk,
            "oiml_edition": OIMLEdition.R76_2006,
            "temperature_start": "21.5",
            "temperature_end": "21.8",
            "humidity_start": "48.0",
            "humidity_end": "49.0",
            "proc_initial_examination": True,
            "proc_zero_setting": True,
            "proc_weighing": True,
            "proc_repeatability": True,
            "proc_eccentricity": True,
            "proc_discrimination": True,
            "proc_tare": False,
            "proc_influence_quantities": False,
            "initial_examination_passed": True,
            "zero_test_passed": True,
            "remarks": "Draft session initiated.",
        }
        response = self.client.post(reverse("test_sessions:create"), data=data)
        self.assertEqual(response.status_code, 302)

        created = TestSession.objects.get(session_number="TS-DRAFT-99")
        self.assertEqual(created.status, SessionStatus.DRAFT)
        self.assertEqual(created.lab_reference_number, "LAB-DRAFT-01")

    def test_create_session_wizard_save_and_proceed(self):
        """Wizard creates active session with IN_PROGRESS status."""
        self.client.force_login(self.operator)
        data = {
            "action_intent": "in_progress",
            "instrument": self.instrument.pk,
            "session_number": "TS-ACTIVE-101",
            "test_date": "2026-11-11",
            "technician": self.operator.pk,
            "oiml_edition": OIMLEdition.R76_2006,
            "proc_weighing": True,
            "proc_repeatability": True,
            "proc_eccentricity": True,
            "proc_discrimination": True,
        }
        response = self.client.post(reverse("test_sessions:create"), data=data)
        self.assertEqual(response.status_code, 302)

        created = TestSession.objects.get(session_number="TS-ACTIVE-101")
        self.assertEqual(created.status, SessionStatus.IN_PROGRESS)

    def test_reviewer_cannot_create_session(self):
        """Reviewers have read-only access to session creation."""
        self.client.force_login(self.reviewer)
        response = self.client.get(reverse("test_sessions:create"))
        self.assertEqual(response.status_code, 403)

    def test_procedure_configuration_view(self):
        """Operator can toggle applicable test procedures."""
        self.client.force_login(self.operator)
        self.assertFalse(self.session.proc_tare)

        data = {
            "proc_initial_examination": True,
            "proc_zero_setting": True,
            "proc_weighing": True,
            "proc_repeatability": True,
            "proc_eccentricity": True,
            "proc_discrimination": True,
            "proc_tare": True,  # activate tare test
            "proc_influence_quantities": False,
        }
        response = self.client.post(
            reverse("test_sessions:procedure_config", kwargs={"pk": self.session.pk}),
            data=data,
        )
        self.assertEqual(response.status_code, 302)
        self.session.refresh_from_db()
        self.assertTrue(self.session.proc_tare)

    def test_lifecycle_submit_and_approve(self):
        """Complete workflow: IN_PROGRESS → PENDING_REVIEW → APPROVED (and locked)."""
        # Configure session so only initial examination is active (and passed) so it meets submission criteria
        self.session.proc_zero_setting = False
        self.session.proc_weighing = False
        self.session.proc_repeatability = False
        self.session.proc_eccentricity = False
        self.session.proc_discrimination = False
        self.session.proc_tare = False
        self.session.proc_initial_examination = True
        self.session.initial_examination_passed = True
        self.session.save()

        # 1. Operator submits for review
        self.client.force_login(self.operator)
        response = self.client.post(reverse("test_sessions:submit", kwargs={"pk": self.session.pk}))
        self.assertEqual(response.status_code, 302)
        self.session.refresh_from_db()
        self.assertIn(self.session.status, [SessionStatus.SUBMITTED, SessionStatus.PENDING_REVIEW])

        # 2. Reviewer approves
        self.client.force_login(self.reviewer)
        response = self.client.post(reverse("test_sessions:approve", kwargs={"pk": self.session.pk}))
        self.assertEqual(response.status_code, 302)
        self.session.refresh_from_db()
        self.assertEqual(self.session.status, SessionStatus.APPROVED)
        self.assertTrue(self.session.is_locked)

        # Instrument status updated to TESTED
        self.instrument.refresh_from_db()
        self.assertEqual(self.instrument.status, InstrumentStatus.TESTED)

    def test_prevent_modification_of_approved_tests(self):
        """Locked/approved sessions cannot be edited."""
        self.session.status = SessionStatus.APPROVED
        self.session.is_locked = True
        self.session.save()

        self.client.force_login(self.operator)

        # Attempt to access edit view -> redirected with error
        response = self.client.get(reverse("test_sessions:edit", kwargs={"pk": self.session.pk}))
        self.assertEqual(response.status_code, 302)

        # Attempt to modify procedures -> redirected with error
        response = self.client.get(reverse("test_sessions:procedure_config", kwargs={"pk": self.session.pk}))
        self.assertEqual(response.status_code, 302)

    def test_reviewer_rejection_workflow(self):
        """Reviewer returns session with technical comments."""
        self.session.status = SessionStatus.PENDING_REVIEW
        self.session.save()

        self.client.force_login(self.reviewer)
        data = {"reason": "Eccentricity load point at position RIGHT exceeds MPE limit; please re-verify."}
        response = self.client.post(
            reverse("test_sessions:reject", kwargs={"pk": self.session.pk}),
            data=data,
        )
        self.assertEqual(response.status_code, 302)
        self.session.refresh_from_db()
        self.assertEqual(self.session.status, SessionStatus.REJECTED)
        self.assertIn("Eccentricity load point", self.session.rejection_reason)


class TestSessionResultsAndValidationTests(TestCase):
    """
    Unit and integration tests for the Test Results and Validation Module.
    Tests OIML R 76 result evaluation, missing data warnings, draft workflows,
    print view, and non-delegable compliance safeguards.
    """

    def setUp(self):
        self.org = Organization.objects.create(name="Precision Metrology Standards Lab")
        self.operator = CustomUser.objects.create_user(
            email="metrologist@nawi.local",
            username="metrologist_01",
            password="Password123!",
            role=UserRole.LAB_OPERATOR,
            organization=self.org,
        )
        self.reviewer = CustomUser.objects.create_user(
            email="signatory@nawi.local",
            username="signatory_01",
            password="Password123!",
            role=UserRole.REVIEWER,
            organization=self.org,
        )
        self.instrument = Instrument.objects.create(
            organization=self.org,
            instrument_name="High-Precision Laboratory Balance",
            serial_number="BAL-2026-VAL",
            manufacturer="Sartorius",
            model_name="Cubis II",
            accuracy_class=AccuracyClass.CLASS_II,
            max_capacity=Decimal("1000.0000"),
            min_capacity=Decimal("0.5000"),
            scale_interval=Decimal("0.0100"),
            actual_scale_interval=Decimal("0.1000"),
            unit_of_measurement="g",
        )
        self.session = TestSession.objects.create(
            organization=self.org,
            instrument=self.instrument,
            session_number="TS-VAL-2026-001",
            lab_reference_number="REF-VAL-001",
            test_date=timezone.now().date(),
            technician=self.operator,
            status=SessionStatus.IN_PROGRESS,
            proc_initial_examination=True,
            proc_weighing=True,
            proc_repeatability=True,
            proc_eccentricity=True,
            proc_zero_setting=False,
            proc_discrimination=False,
            proc_tare=False,
            initial_examination_passed=True,
            created_by=self.operator,
        )

    def test_results_view_renders_for_operator(self):
        """Laboratory results view displays instrument, procedures, and actions."""
        self.client.force_login(self.operator)
        url = reverse("test_sessions:results", kwargs={"pk": self.session.pk})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Laboratory Test Results &amp; Validation")
        self.assertContains(response, "High-Precision Laboratory Balance")
        self.assertContains(response, "TS-VAL-2026-001")
        self.assertContains(response, "OIML R 76-1:2006")
        self.assertIn("report", response.context)
        self.assertIn("initial_examination", response.context["report"].procedure_summaries)

    def test_results_print_view_renders_for_authorized_staff(self):
        """Print-friendly results view includes signatures and ISO 17025 conformity structure."""
        self.client.force_login(self.operator)
        url = reverse("test_sessions:results_print", kwargs={"pk": self.session.pk})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Non-Automatic Weighing Instrument Test Results Report")
        self.assertContains(response, "Print This Test Report")
        self.assertContains(response, "Metrology Technician / Operator")
        self.assertContains(response, "Authorized Technical Reviewer")

    def test_incomplete_procedure_blocks_pass_and_generates_warnings(self):
        """
        Normative Requirement: A report must NOT receive an overall PASS status if
        required tests are incomplete or observation count < required minimum.
        """
        from apps.measurements.models import RepeatabilityMeasurement
        from apps.test_sessions.results_validation import ResultsValidationService

        # Only 2 repetitions added for repeatability (minimum 3 required)
        RepeatabilityMeasurement.objects.create(
            session=self.session,
            series_name="Series 1 (~0.5 Max)",
            nominal_load=Decimal("500.0000"),
            repetition_number=1,
            indication=Decimal("500.0100"),
            is_draft=False,
        )
        RepeatabilityMeasurement.objects.create(
            session=self.session,
            series_name="Series 1 (~0.5 Max)",
            nominal_load=Decimal("500.0000"),
            repetition_number=2,
            indication=Decimal("500.0150"),
            is_draft=False,
        )

        report = ResultsValidationService.validate_session(self.session)
        # Repeatability has < 3 observations -> INCOMPLETE
        self.assertEqual(report.procedure_summaries["repeatability"].status, "INCOMPLETE")
        self.assertFalse(report.is_pass_eligible)
        self.assertNotEqual(report.overall_status, "PASS")
        self.assertTrue(any("Minimum 3 repetitions required" in w for w in report.missing_data_warnings))

    def test_draft_observations_warning_and_bulk_confirmation(self):
        """Draft observations trigger warnings and can be confirmed in bulk."""
        from apps.measurements.models import WeighingMeasurement
        from apps.test_sessions.results_validation import ResultsValidationService

        wm = WeighingMeasurement.objects.create(
            session=self.session,
            sequence_order=1,
            nominal_load=Decimal("100.0000"),
            indication=Decimal("100.0100"),
            is_draft=True,
        )

        report = ResultsValidationService.validate_session(self.session)
        self.assertGreater(report.total_drafts, 0)
        self.assertFalse(report.is_submittable)

        # Operator confirms drafts via POST to validate_drafts
        self.client.force_login(self.operator)
        url = reverse("test_sessions:validate_drafts", kwargs={"pk": self.session.pk})
        response = self.client.post(url)
        self.assertEqual(response.status_code, 302)

        wm.refresh_from_db()
        self.assertFalse(wm.is_draft)

    def test_missing_eccentricity_positions_warning(self):
        """Eccentricity test with missing standard positions triggers missing data warnings."""
        from apps.measurements.models import EccentricityMeasurement
        from apps.test_sessions.results_validation import ResultsValidationService

        # Add only CENTRE position
        EccentricityMeasurement.objects.create(
            session=self.session,
            load_position="CENTRE",
            nominal_load=Decimal("300.0000"),
            indication=Decimal("300.0000"),
            is_draft=False,
        )

        report = ResultsValidationService.validate_session(self.session)
        self.assertTrue(any("Missing standard receptor position" in w for w in report.missing_data_warnings))

    def test_submission_blocked_when_session_is_incomplete(self):
        """Session with incomplete active procedures cannot be submitted."""
        from django.core.exceptions import ValidationError
        from apps.test_sessions.services import SessionService

        with self.assertRaises(ValidationError) as ctx:
            SessionService.submit_for_review(self.session, self.operator)
        self.assertIn("Cannot submit test session", str(ctx.exception))

    def test_approval_blocked_when_overall_pass_ineligible(self):
        """Reviewer cannot approve overall PASS if test rules are not verified or tests incomplete."""
        from django.core.exceptions import ValidationError
        from apps.test_sessions.services import SessionService

        # Manually put in PENDING_REVIEW with overall_result="PASS"
        self.session.status = SessionStatus.PENDING_REVIEW
        self.session.overall_result = "PASS"
        self.session.save()

        with self.assertRaises(ValidationError) as ctx:
            SessionService.approve(self.session, self.reviewer)
        self.assertIn("Session cannot receive an overall PASS approval", str(ctx.exception))


class TestReviewAndApprovalWorkflowTests(TestCase):
    """
    Unit and integration tests for the Complete Test Review & Approval Workflow:
    DRAFT → SUBMITTED → UNDER REVIEW → APPROVED / REJECTED → REPORT GENERATED
    with controlled revisions and complete immutable audit history.
    """

    def setUp(self):
        self.org = Organization.objects.create(name="National Standards & Metrology Institute")
        self.operator = CustomUser.objects.create_user(
            email="operator@metrology.gov",
            username="metrology_operator",
            password="Password123!",
            role=UserRole.LAB_OPERATOR,
            organization=self.org,
            first_name="Alice",
            last_name="Operator",
        )
        self.reviewer = CustomUser.objects.create_user(
            email="reviewer@metrology.gov",
            username="metrology_reviewer",
            password="Password123!",
            role=UserRole.REVIEWER,
            organization=self.org,
            first_name="Dr. Robert",
            last_name="Reviewer",
        )
        self.admin = CustomUser.objects.create_user(
            email="admin@metrology.gov",
            username="metrology_admin",
            password="Password123!",
            role=UserRole.ADMINISTRATOR,
            organization=self.org,
            first_name="Carol",
            last_name="Admin",
        )
        self.instrument = Instrument.objects.create(
            organization=self.org,
            instrument_name="Precision Metrology Balance",
            serial_number="MET-2026-X1",
            manufacturer="Radwag",
            model_name="XA 220.4Y",
            accuracy_class=AccuracyClass.CLASS_I,
            max_capacity=Decimal("220.0000"),
            min_capacity=Decimal("0.0010"),
            scale_interval=Decimal("0.0001"),
            actual_scale_interval=Decimal("0.0010"),
            unit_of_measurement="g",
            status=InstrumentStatus.IN_LAB,
        )
        # Create a valid complete session configured for submission
        self.session = TestSession.objects.create(
            organization=self.org,
            instrument=self.instrument,
            session_number="TS-WF-2026-001",
            lab_reference_number="LAB-WF-001",
            test_date=timezone.now().date(),
            technician=self.operator,
            status=SessionStatus.DRAFT,
            proc_initial_examination=True,
            initial_examination_passed=True,
            proc_weighing=False,
            proc_repeatability=False,
            proc_eccentricity=False,
            proc_zero_setting=False,
            proc_discrimination=False,
            proc_tare=False,
            created_by=self.operator,
        )

    def test_reviewer_dashboard_renders_for_reviewer(self):
        """Reviewer dashboard displays metric counters, tabs, and pending queue."""
        self.client.force_login(self.reviewer)
        url = reverse("test_sessions:reviewer_dashboard")
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Reviewer &amp; Approvals Dashboard")
        self.assertContains(response, "Pending Queue")
        self.assertContains(response, "Under Review")
        self.assertContains(response, "Approved &amp; Certified")
        self.assertContains(response, "Returned / Rejected")

    def test_reviewer_dashboard_forbidden_for_operators(self):
        """Laboratory operators cannot access the reviewer dashboard (HTTP 403)."""
        self.client.force_login(self.operator)
        url = reverse("test_sessions:reviewer_dashboard")
        response = self.client.get(url)
        self.assertEqual(response.status_code, 403)

    def test_complete_workflow_lifecycle_and_history_audit_trail(self):
        """
        Tests the complete workflow state progression:
        DRAFT → SUBMITTED → UNDER REVIEW → REJECTED → RESUBMITTED → UNDER REVIEW → APPROVED → REPORT GENERATED
        and verifies all timestamps, reviewer identity, and immutable audit history.
        """
        from apps.test_sessions.models import ApprovalHistory, ApprovalAction

        # ── Step 1: Operator submits completed test ──
        self.client.force_login(self.operator)
        submit_url = reverse("test_sessions:submit", kwargs={"pk": self.session.pk})
        resp = self.client.post(submit_url, {"comments": "All observations validated; ready for review."})
        self.assertEqual(resp.status_code, 302)
        self.session.refresh_from_db()
        self.assertEqual(self.session.status, SessionStatus.SUBMITTED)
        self.assertIsNotNone(self.session.submitted_at)
        self.assertEqual(self.session.submitted_by, self.operator)

        # Check history entry 1
        h1 = self.session.approval_history.first()
        self.assertEqual(h1.action, ApprovalAction.SUBMIT)
        self.assertEqual(h1.from_status, SessionStatus.DRAFT)
        self.assertEqual(h1.to_status, SessionStatus.SUBMITTED)
        self.assertEqual(h1.actor, self.operator)
        self.assertIn("All observations validated", h1.comments)

        # ── Step 2: Reviewer starts review ──
        self.client.force_login(self.reviewer)
        start_url = reverse("test_sessions:start_review", kwargs={"pk": self.session.pk})
        resp = self.client.post(start_url)
        self.assertEqual(resp.status_code, 302)
        self.session.refresh_from_db()
        self.assertEqual(self.session.status, SessionStatus.UNDER_REVIEW)
        self.assertIsNotNone(self.session.review_started_at)
        self.assertEqual(self.session.reviewer, self.reviewer)

        # Check history entry 2
        h2 = self.session.approval_history.first()
        self.assertEqual(h2.action, ApprovalAction.START_REVIEW)
        self.assertEqual(h2.to_status, SessionStatus.UNDER_REVIEW)
        self.assertEqual(h2.actor, self.reviewer)

        # ── Step 3: Reviewer rejects with mandatory comments ──
        reject_url = reverse("test_sessions:reject", kwargs={"pk": self.session.pk})
        rejection_reason = "Tare test load is missing verification notes. Please re-check."
        resp = self.client.post(reject_url, {"reason": rejection_reason})
        self.assertEqual(resp.status_code, 302)
        self.session.refresh_from_db()
        self.assertEqual(self.session.status, SessionStatus.REJECTED)
        self.assertFalse(self.session.is_locked)
        self.assertIsNotNone(self.session.rejected_at)
        self.assertEqual(self.session.rejection_reason, rejection_reason)

        # Check history entry 3
        h3 = self.session.approval_history.first()
        self.assertEqual(h3.action, ApprovalAction.REJECT)
        self.assertEqual(h3.to_status, SessionStatus.REJECTED)
        self.assertEqual(h3.comments, rejection_reason)

        # ── Step 4: Operator corrects and resubmits ──
        self.client.force_login(self.operator)
        resp = self.client.post(submit_url, {"comments": "Remediation complete per reviewer instructions."})
        self.assertEqual(resp.status_code, 302)
        self.session.refresh_from_db()
        self.assertEqual(self.session.status, SessionStatus.SUBMITTED)

        # Check history entry 4 (RESUBMIT)
        h4 = self.session.approval_history.first()
        self.assertEqual(h4.action, ApprovalAction.RESUBMIT)
        self.assertEqual(h4.from_status, SessionStatus.REJECTED)
        self.assertEqual(h4.to_status, SessionStatus.SUBMITTED)

        # ── Step 5: Reviewer starts review again and approves ──
        self.client.force_login(self.reviewer)
        self.client.post(start_url)
        self.session.refresh_from_db()
        self.assertEqual(self.session.status, SessionStatus.UNDER_REVIEW)

        approve_url = reverse("test_sessions:approve", kwargs={"pk": self.session.pk})
        approval_notes = "Verified and certified under OIML R 76-1:2006."
        resp = self.client.post(approve_url, {"comments": approval_notes})
        self.assertEqual(resp.status_code, 302)
        self.session.refresh_from_db()
        self.assertEqual(self.session.status, SessionStatus.APPROVED)
        self.assertTrue(self.session.is_locked)
        self.assertIsNotNone(self.session.approved_at)
        self.assertEqual(self.session.reviewer, self.reviewer)

        # Instrument status updated to TESTED
        self.instrument.refresh_from_db()
        self.assertEqual(self.instrument.status, InstrumentStatus.TESTED)

        # Check history entry 5 (APPROVE)
        h5 = self.session.approval_history.first()
        self.assertEqual(h5.action, ApprovalAction.APPROVE)
        self.assertEqual(h5.to_status, SessionStatus.APPROVED)
        self.assertIn("Verified and certified", h5.comments)

        # ── Step 6: Generate Report transition ──
        SessionService.generate_report(self.session, self.reviewer)
        self.session.refresh_from_db()
        self.assertEqual(self.session.status, SessionStatus.REPORT_GENERATED)
        self.assertIsNotNone(self.session.report_generated_at)
        self.assertEqual(self.session.report_generated_by, self.reviewer)

        # Check history count (Total 7 distinct workflow audit steps)
        self.assertEqual(self.session.approval_history.count(), 7)

    def test_rejection_requires_mandatory_comments(self):
        """Reviewer cannot reject a session without providing a technical reason (min 10 chars)."""
        self.session.status = SessionStatus.SUBMITTED
        self.session.save()

        self.client.force_login(self.reviewer)
        reject_url = reverse("test_sessions:reject", kwargs={"pk": self.session.pk})

        # Empty reason
        resp = self.client.post(reject_url, {"reason": ""})
        self.session.refresh_from_db()
        self.assertNotEqual(self.session.status, SessionStatus.REJECTED)

        # Short reason (< 10 chars)
        resp = self.client.post(reject_url, {"reason": "Short"})
        self.session.refresh_from_db()
        self.assertNotEqual(self.session.status, SessionStatus.REJECTED)

    def test_unauthorized_approval_attempt_blocked(self):
        """Technician / Operator cannot approve a session (HTTP 403)."""
        self.session.status = SessionStatus.SUBMITTED
        self.session.save()

        self.client.force_login(self.operator)
        approve_url = reverse("test_sessions:approve", kwargs={"pk": self.session.pk})
        resp = self.client.post(approve_url)
        self.assertEqual(resp.status_code, 403)
        self.session.refresh_from_db()
        self.assertNotEqual(self.session.status, SessionStatus.APPROVED)

    def test_immutability_of_approved_records_and_controlled_revision(self):
        """
        Approved records are immutable: editing is prohibited.
        Controlled revision requires authorized reviewer/admin and change-control reason.
        """
        from apps.test_sessions.models import ApprovalAction

        # Set session to APPROVED & locked
        self.session.status = SessionStatus.APPROVED
        self.session.is_locked = True
        self.session.save()

        # Operator attempts to edit -> blocked/redirected
        self.client.force_login(self.operator)
        edit_url = reverse("test_sessions:edit", kwargs={"pk": self.session.pk})
        resp = self.client.get(edit_url)
        self.assertEqual(resp.status_code, 302)

        # Reviewer initiates controlled revision with change-control justification
        self.client.force_login(self.reviewer)
        revise_url = reverse("test_sessions:initiate_revision", kwargs={"pk": self.session.pk})
        justification = "Typographical correction on certificate client address per Customer Request #CR-2026-88."
        resp = self.client.post(revise_url, {"revision_reason": justification})
        self.assertEqual(resp.status_code, 302)

        self.session.refresh_from_db()
        self.assertEqual(self.session.revision_number, 2)
        self.assertEqual(self.session.status, SessionStatus.UNDER_REVIEW)
        self.assertFalse(self.session.is_locked)
        self.assertEqual(self.session.revision_reason, justification)

        # Check revision logged in ApprovalHistory
        rev_history = self.session.approval_history.first()
        self.assertEqual(rev_history.action, ApprovalAction.REVISE)
        self.assertIn("CR-2026-88", rev_history.comments)

    def test_review_inspection_console_view(self):
        """Reviewer inspection console displays all 6 inspection sections and action modals."""
        self.session.status = SessionStatus.SUBMITTED
        self.session.save()

        self.client.force_login(self.reviewer)
        review_url = reverse("test_sessions:review", kwargs={"pk": self.session.pk})
        response = self.client.get(review_url)
        self.assertEqual(response.status_code, 200)

        # Section 1: Instrument details
        self.assertContains(response, "Instrument Metrological Identification")
        self.assertContains(response, "Precision Metrology Balance")
        self.assertContains(response, "MET-2026-X1")

        # Section 2: Procedures
        self.assertContains(response, "Applicable Test Procedures &amp; Acceptance Status")

        # Section 3: Original observations & calculations
        self.assertContains(response, "Detailed Measurement Observations, Calculated Errors")

        # Section 4: Decisions & exceptions
        self.assertContains(response, "Overall: PASS")

        # Section 5: Approval history
        self.assertContains(response, "Complete Review &amp; Approval History")

        # Review actions & modals
        self.assertContains(response, "Start Technical Review")
        self.assertContains(response, "Approve &amp; Certify")
        self.assertContains(response, "Return for Correction")


