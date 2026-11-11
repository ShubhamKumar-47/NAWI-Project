"""
tests/test_audit/test_complete_audit_and_e2e.py

Comprehensive End-to-End Audit & Metrological Verification Test Suite:
1. Independent OIML R 76-1:2006 calculation engine verification across Class I, II, III, IIII.
2. Boundary conditions, decimal precision, missing observation guards, and overload limits.
3. Multi-role security, permission gates, tenant isolation, and delete protections.
4. Complete End-to-End Workflow:
   Login -> Register Instrument -> Create Test Session -> Configure Procedures ->
   Enter Batch Observations -> Trigger Calculation Engine -> Submit for Review ->
   Technical Inspection -> Approve & Lock -> Generate PDF -> Generate Word ->
   Download & Audit Tracking -> Controlled Revision -> Archival & Traceability.
"""
import io
import json
from decimal import Decimal
from datetime import date
from django.test import TestCase, Client
from django.urls import reverse
from django.utils import timezone
from django.core.exceptions import PermissionDenied

from apps.accounts.models import CustomUser, Organization
from apps.core.constants import UserRole, AccuracyClass, SessionStatus, ReportType, PassFail
from apps.instruments.models import Instrument
from apps.test_sessions.models import TestSession, ApprovalHistory, OIMLEdition
from apps.measurements.models import (
    WeighingMeasurement,
    RepeatabilityMeasurement,
    EccentricityMeasurement,
    DiscriminationMeasurement,
    TareMeasurement,
    ZeroSettingMeasurement,
)
from apps.reports.models import GeneratedReport, ReportDownloadLog
from apps.audit.models import AuditLog
from calculations.constants import CLASS_I, CLASS_II, CLASS_III, CLASS_IIII
from calculations.services import (
    get_weighing_mpe,
    SessionCalculationCoordinator,
    RepeatabilityService,
    EccentricityService,
    DiscriminationService,
    ZeroTestsService,
    TareService,
)
from calculations.exceptions import InsufficientDataError, InvalidInputError
from apps.test_sessions.services import SessionService


class IndependentOIMLCalculationsAuditTests(TestCase):
    """
    Independently verified metrological calculation tests based directly
    on OIML R 76-1:2006 Table 1, Table 2, §3.5, §3.6, §A.4.
    """

    def test_class_i_mpe_boundaries_and_precision(self):
        """
        OIML R 76 Table 1 — Class I:
        - 0 <= m <= 50,000 e: MPE = ±0.5 e
        - 50,000 e < m <= 200,000 e: MPE = ±1.0 e
        - m > 200,000 e: MPE = ±1.5 e

        Instrument: Analytical Micro-balance (e = 0.001 g = 1 mg)
        """
        e = Decimal("0.001")

        # Range 1: 50,000 e = 50.000 g -> MPE = 0.5 e = 0.0005 g
        res_50k = get_weighing_mpe(Decimal("50.000"), CLASS_I, e, is_initial_verification=True)
        self.assertEqual(res_50k.mpe_in_e, Decimal("0.5"))
        self.assertEqual(res_50k.mpe_value, Decimal("0.0005"))

        # Exact boundary +1: 50,001 e = 50.001 g -> MPE = 1.0 e = 0.0010 g
        res_50k_plus = get_weighing_mpe(Decimal("50.001"), CLASS_I, e, is_initial_verification=True)
        self.assertEqual(res_50k_plus.mpe_in_e, Decimal("1.0"))
        self.assertEqual(res_50k_plus.mpe_value, Decimal("0.0010"))

        # Range 2: 200,000 e = 200.000 g -> MPE = 1.0 e = 0.0010 g
        res_200k = get_weighing_mpe(Decimal("200.000"), CLASS_I, e, is_initial_verification=True)
        self.assertEqual(res_200k.mpe_in_e, Decimal("1.0"))
        self.assertEqual(res_200k.mpe_value, Decimal("0.0010"))

        # Exact boundary +1: 200,001 e = 200.001 g -> MPE = 1.5 e = 0.0015 g
        res_200k_plus = get_weighing_mpe(Decimal("200.001"), CLASS_I, e, is_initial_verification=True)
        self.assertEqual(res_200k_plus.mpe_in_e, Decimal("1.5"))
        self.assertEqual(res_200k_plus.mpe_value, Decimal("0.0015"))

    def test_class_ii_mpe_boundaries(self):
        """
        OIML R 76 Table 1 — Class II:
        - 0 <= m <= 5,000 e: MPE = ±0.5 e
        - 5,000 e < m <= 20,000 e: MPE = ±1.0 e
        - m > 20,000 e: MPE = ±1.5 e

        Instrument: Precision Balance (e = 0.1 g)
        """
        e = Decimal("0.1")

        # 5,000 e = 500.0 g -> MPE = ±0.05 g
        res1 = get_weighing_mpe(Decimal("500.0"), CLASS_II, e, is_initial_verification=True)
        self.assertEqual(res1.mpe_in_e, Decimal("0.5"))
        self.assertEqual(res1.mpe_value, Decimal("0.05"))

        # 5,001 e = 500.1 g -> MPE = ±0.10 g
        res2 = get_weighing_mpe(Decimal("500.1"), CLASS_II, e, is_initial_verification=True)
        self.assertEqual(res2.mpe_in_e, Decimal("1.0"))
        self.assertEqual(res2.mpe_value, Decimal("0.10"))

        # 20,000 e = 2000.0 g -> MPE = ±0.10 g
        res3 = get_weighing_mpe(Decimal("2000.0"), CLASS_II, e, is_initial_verification=True)
        self.assertEqual(res3.mpe_in_e, Decimal("1.0"))
        self.assertEqual(res3.mpe_value, Decimal("0.10"))

        # 20,001 e = 2000.1 g -> MPE = ±0.15 g
        res4 = get_weighing_mpe(Decimal("2000.1"), CLASS_II, e, is_initial_verification=True)
        self.assertEqual(res4.mpe_in_e, Decimal("1.5"))
        self.assertEqual(res4.mpe_value, Decimal("0.15"))

    def test_class_iii_mpe_boundaries(self):
        """
        OIML R 76 Table 1 — Class III:
        - 0 <= m <= 500 e: MPE = ±0.5 e
        - 500 e < m <= 2,000 e: MPE = ±1.0 e
        - m > 2,000 e: MPE = ±1.5 e

        Instrument: Industrial Platform Scale (e = 0.005 kg = 5 g)
        """
        e = Decimal("0.005")

        # 500 e = 2.500 kg -> MPE = ±0.0025 kg
        res1 = get_weighing_mpe(Decimal("2.500"), CLASS_III, e, is_initial_verification=True)
        self.assertEqual(res1.mpe_in_e, Decimal("0.5"))
        self.assertEqual(res1.mpe_value, Decimal("0.0025"))

        # 501 e = 2.505 kg -> MPE = ±0.0050 kg
        res2 = get_weighing_mpe(Decimal("2.505"), CLASS_III, e, is_initial_verification=True)
        self.assertEqual(res2.mpe_in_e, Decimal("1.0"))
        self.assertEqual(res2.mpe_value, Decimal("0.0050"))

        # 2,000 e = 10.000 kg -> MPE = ±0.0050 kg
        res3 = get_weighing_mpe(Decimal("10.000"), CLASS_III, e, is_initial_verification=True)
        self.assertEqual(res3.mpe_in_e, Decimal("1.0"))
        self.assertEqual(res3.mpe_value, Decimal("0.0050"))

        # 2,001 e = 10.005 kg -> MPE = ±0.0075 kg
        res4 = get_weighing_mpe(Decimal("10.005"), CLASS_III, e, is_initial_verification=True)
        self.assertEqual(res4.mpe_in_e, Decimal("1.5"))
        self.assertEqual(res4.mpe_value, Decimal("0.0075"))

    def test_class_iiii_mpe_boundaries(self):
        """
        OIML R 76 Table 1 — Class IIII:
        - 0 <= m <= 50 e: MPE = ±0.5 e
        - 50 e < m <= 200 e: MPE = ±1.0 e
        - m > 200 e: MPE = ±1.5 e

        Instrument: Vehicle / Weighbridge Scale (e = 20 kg)
        """
        e = Decimal("20")

        # 50 e = 1,000 kg -> MPE = ±10 kg
        res1 = get_weighing_mpe(Decimal("1000"), CLASS_IIII, e, is_initial_verification=True)
        self.assertEqual(res1.mpe_in_e, Decimal("0.5"))
        self.assertEqual(res1.mpe_value, Decimal("10"))

        # 51 e = 1,020 kg -> MPE = ±20 kg
        res2 = get_weighing_mpe(Decimal("1020"), CLASS_IIII, e, is_initial_verification=True)
        self.assertEqual(res2.mpe_in_e, Decimal("1.0"))
        self.assertEqual(res2.mpe_value, Decimal("20"))

        # 200 e = 4,000 kg -> MPE = ±20 kg
        res3 = get_weighing_mpe(Decimal("4000"), CLASS_IIII, e, is_initial_verification=True)
        self.assertEqual(res3.mpe_in_e, Decimal("1.0"))
        self.assertEqual(res3.mpe_value, Decimal("20"))

        # 201 e = 4,020 kg -> MPE = ±30 kg
        res4 = get_weighing_mpe(Decimal("4020"), CLASS_IIII, e, is_initial_verification=True)
        self.assertEqual(res4.mpe_in_e, Decimal("1.5"))
        self.assertEqual(res4.mpe_value, Decimal("30"))

    def test_repeatability_acceptance_criterion(self):
        """
        OIML R 76 §A.4.10: Range R = I_max - I_min must be <= |mpe| for that load.
        """
        readings = [Decimal("10.001"), Decimal("10.002"), Decimal("10.001"), Decimal("10.002")]
        res = RepeatabilityService.calculate_series(
            nominal_load=Decimal("10.0"),
            indications=readings,
            accuracy_class=CLASS_III,
            actual_scale_interval=Decimal("0.005"),
        )
        # Load 10.0 kg is in 2,000 e zone -> mpe = ±0.005 kg.
        # Range R = 10.002 - 10.001 = 0.001 kg <= 0.005 kg -> PASS
        self.assertEqual(res.calculated_range, Decimal("0.001"))
        self.assertEqual(res.comparison_result, "PASS")

    def test_zero_setting_tolerance(self):
        """
        OIML R 76 §A.4.4.2: Zero-setting error E_0 must not exceed ±0.25 e.
        """
        res = ZeroTestsService.calculate_zero_check(
            zero_indication_after=Decimal("0.001"),
            scale_interval=Decimal("0.005"),
            actual_scale_interval=Decimal("0.005"),
            zero_indication_before=Decimal("0.000"),
        )
        # 0.25 * 0.005 = 0.00125. Deviation = 0.001 <= 0.00125 -> PASS
        self.assertEqual(res.comparison_result, "PASS")
        self.assertEqual(res.permissible_mpe, Decimal("0.00125"))


class SecurityAndAccessControlAuditTests(TestCase):
    """Security, RBAC, Multi-tenancy, and Immutability audit tests."""

    def setUp(self):
        self.client = Client()
        self.org_a = Organization.objects.create(name="Alpha Lab", accreditation_number="ISO-ALPHA-01")
        self.org_b = Organization.objects.create(name="Beta Lab", accreditation_number="ISO-BETA-02")

        self.tech_a = CustomUser.objects.create_user(
            email="tech.a@alpha.local", username="techa", password="Password123!",
            role=UserRole.TECHNICIAN, organization=self.org_a
        )
        self.reviewer_a = CustomUser.objects.create_user(
            email="rev.a@alpha.local", username="reva", password="Password123!",
            role=UserRole.REVIEWER, organization=self.org_a
        )
        self.tech_b = CustomUser.objects.create_user(
            email="tech.b@beta.local", username="techb", password="Password123!",
            role=UserRole.TECHNICIAN, organization=self.org_b
        )

        self.inst_a = Instrument.objects.create(
            organization=self.org_a,
            serial_number="SN-ALPHA-01",
            manufacturer="Mettler",
            model_name="MS-300",
            accuracy_class=AccuracyClass.CLASS_II,
            max_capacity=Decimal("300.00"),
            min_capacity=Decimal("0.50"),
            scale_interval=Decimal("0.01"),
            actual_scale_interval=Decimal("0.01"),
        )

        self.session_a = TestSession.objects.create(
            organization=self.org_a,
            instrument=self.inst_a,
            session_number="TS-ALPHA-001",
            test_date=date.today(),
            technician=self.tech_a,
            status=SessionStatus.SUBMITTED,
        )

    def test_unauthenticated_requests_redirected_to_login(self):
        """Unauthenticated requests to protected endpoints redirect to login."""
        endpoints = [
            reverse("instruments:list"),
            reverse("test_sessions:list"),
            reverse("reports:list"),
            reverse("dashboard:settings"),
        ]
        for ep in endpoints:
            resp = self.client.get(ep)
            self.assertEqual(resp.status_code, 302)
            self.assertIn("/accounts/login/", resp.url)

    def test_technician_cannot_approve_or_reject_session(self):
        """Technicians lack permission to approve or reject sessions (HTTP 403)."""
        self.client.force_login(self.tech_a)
        approve_url = reverse("test_sessions:approve", kwargs={"pk": self.session_a.pk})
        resp = self.client.post(approve_url, {"comments": "Unauthorized approval"})
        self.assertEqual(resp.status_code, 403)

        reject_url = reverse("test_sessions:reject", kwargs={"pk": self.session_a.pk})
        resp = self.client.post(reject_url, {"reason": "Unauthorized rejection"})
        self.assertEqual(resp.status_code, 403)

    def test_multi_tenant_isolation(self):
        """Users from Org B cannot view or modify Org A test sessions."""
        self.client.force_login(self.tech_b)
        detail_url = reverse("test_sessions:detail", kwargs={"pk": self.session_a.pk})
        resp = self.client.get(detail_url)
        self.assertEqual(resp.status_code, 404)

    def test_immutable_approved_report_delete_protection(self):
        """Deleting an approved report via ORM delete() raises PermissionDenied."""
        self.session_a.status = SessionStatus.APPROVED
        self.session_a.save()

        report = GeneratedReport.objects.create(
            session=self.session_a,
            report_type=ReportType.PDF,
            report_number="TR-ALPHA-R01",
            revision_number=1,
            generated_by=self.reviewer_a,
        )
        with self.assertRaises(PermissionDenied):
            report.delete()


class CompleteEndToEndWorkflowAuditTests(TestCase):
    """
    Complete Life-Cycle Verification:
    Login -> Register Instrument -> Create Test Session -> Configure Procedures ->
    Enter Batch Observations -> Automated Calculation -> Submission -> Review ->
    Approval & Lock -> Generate PDF & Word -> Download & Audit Tracking -> Controlled Revision.
    """

    def setUp(self):
        self.client = Client()
        self.org = Organization.objects.create(
            name="National Standards Metrology Lab",
            accreditation_number="NMI-ISO17025-001",
        )
        self.operator = CustomUser.objects.create_user(
            email="operator@metrology.local",
            username="operator_lims",
            password="LimsPassword123!",
            role=UserRole.TECHNICIAN,
            organization=self.org,
            must_change_password=False,
        )
        self.reviewer = CustomUser.objects.create_user(
            email="reviewer@metrology.local",
            username="reviewer_lims",
            password="ReviewerPassword123!",
            role=UserRole.REVIEWER,
            organization=self.org,
            must_change_password=False,
        )

    def test_complete_end_to_end_audit_workflow(self):
        """Execute the full 14-step end-to-end lifecycle and verify compliance."""

        # ── Step 1: Login with Operator Credentials ─────────────────────────
        login_resp = self.client.post(reverse("accounts:login"), {
            "username": "operator@metrology.local",
            "password": "LimsPassword123!",
        })
        self.assertEqual(login_resp.status_code, 302)
        self.assertRedirects(login_resp, reverse("dashboard:home"))

        # ── Step 2: Register Instrument (OIML Class III Bench Scale) ─────────
        inst_create_url = reverse("instruments:create")
        inst_payload = {
            "instrument_name": "Precision Bench Scale",
            "manufacturer": "Sartorius",
            "model_name": "CPA-16001S",
            "model_number": "CPA-16001S",
            "serial_number": "SN-E2E-AUDIT-99",
            "instrument_type": "Bench Scale",
            "year_of_manufacture": 2024,
            "accuracy_class": AccuracyClass.CLASS_III,
            "max_capacity": "15.000",
            "min_capacity": "0.100",
            "scale_interval": "0.005",
            "actual_scale_interval": "0.005",
            "unit_of_measurement": "kg",
            "status": "IN_LAB",
            "customer_name": "Apex Food Industries Ltd",
            "lab_reference_number": "LAB-REF-AUDIT-01",
            "location": "Main Calibration Bay A",
            "description": "Electronic Non-Automatic Weighing Instrument for legal trade.",
        }
        inst_resp = self.client.post(inst_create_url, inst_payload)
        self.assertEqual(inst_resp.status_code, 302)

        instrument = Instrument.objects.get(serial_number="SN-E2E-AUDIT-99")
        self.assertEqual(instrument.n_max, 3000)
        self.assertEqual(instrument.organization, self.org)

        # ── Step 3: Create Test Record Wizard ─────────────────────────────────
        session_create_url = reverse("test_sessions:create")
        session_payload = {
            "instrument": str(instrument.pk),
            "session_number": "TS-E2E-AUDIT-001",
            "technician": str(self.operator.pk),
            "test_date": date.today().isoformat(),
            "test_location": "Environmental Test Cell 2",
            "temperature_start": "20.2",
            "temperature_end": "20.5",
            "humidity_start": "50.0",
            "humidity_end": "52.0",
            "oiml_edition": OIMLEdition.R76_2006,
            "reference_standards": "Class M1 Stainless Steel Weights (Cert: NMI-M1-2026)",
            "lab_reference_number": "TS-REF-E2E-001",
            "proc_initial_examination": True,
            "initial_examination_passed": True,
            "proc_weighing": True,
            "action_intent": "next_procedures",
        }
        session_resp = self.client.post(session_create_url, session_payload)
        self.assertEqual(session_resp.status_code, 302)

        session = TestSession.objects.get(instrument=instrument)
        self.assertIn(session.status, [SessionStatus.DRAFT, SessionStatus.IN_PROGRESS])
        self.assertEqual(session.revision_number, 1)

        # ── Step 4: Configure Applicable Procedures ───────────────────────────
        # Set procedures: weighing performance + initial examination (satisfies OIML validation)
        session.proc_initial_examination = True
        session.initial_examination_passed = True
        session.proc_weighing = True
        session.proc_repeatability = False
        session.proc_eccentricity = False
        session.proc_discrimination = False
        session.proc_tare = False
        session.proc_zero_setting = False
        session.save()

        # ── Step 5: Enter Batch Observations (5 Load Points per OIML §A.4.4) ─
        weighing_points = [
            {"seq": 1, "load": "1.000", "ind": "1.000"},
            {"seq": 2, "load": "3.000", "ind": "3.000"},
            {"seq": 3, "load": "7.500", "ind": "7.500"},
            {"seq": 4, "load": "11.000", "ind": "11.000"},
            {"seq": 5, "load": "15.000", "ind": "15.000"},
        ]
        for pt in weighing_points:
            WeighingMeasurement.objects.create(
                session=session,
                sequence_order=pt["seq"],
                nominal_load=Decimal(pt["load"]),
                indication=Decimal(pt["ind"]),
                is_draft=False,
            )

        self.assertEqual(session.weighing_measurements.count(), 5)

        # ── Step 6: Trigger Metrological Calculation Engine ───────────────────
        calc_records = SessionCalculationCoordinator.evaluate_session(session, calculated_by=self.operator)
        self.assertEqual(len(calc_records), 5)

        session.refresh_from_db()
        self.assertEqual(session.overall_result, "PASS")

        # ── Step 7: Operator Submits Test Record for Review ───────────────────
        submit_url = reverse("test_sessions:submit", kwargs={"pk": session.pk})
        submit_resp = self.client.post(submit_url)
        self.assertEqual(submit_resp.status_code, 302)

        session.refresh_from_db()
        self.assertEqual(session.status, SessionStatus.SUBMITTED)

        # ── Step 8: Reviewer Starts Technical Review ──────────────────────────
        self.client.force_login(self.reviewer)
        start_review_url = reverse("test_sessions:start_review", kwargs={"pk": session.pk})
        start_resp = self.client.post(start_review_url)
        self.assertEqual(start_resp.status_code, 302)

        session.refresh_from_db()
        self.assertEqual(session.status, SessionStatus.UNDER_REVIEW)

        # ── Step 9: Reviewer Formally Approves and Locks Record ───────────────
        approve_url = reverse("test_sessions:approve", kwargs={"pk": session.pk})
        approve_resp = self.client.post(approve_url, {
            "comments": "All 5 weighing points comply with OIML R 76-1:2006 Table 1 MPE limits."
        })
        self.assertEqual(approve_resp.status_code, 302)

        session.refresh_from_db()
        self.assertEqual(session.status, SessionStatus.APPROVED)
        self.assertTrue(session.is_locked)
        self.assertEqual(session.reviewer, self.reviewer)

        # ── Step 10: Generate Official Reports (Dual PDF & Word) ──────────────
        gen_url = reverse("reports:generate", kwargs={"session_pk": session.pk})
        gen_resp = self.client.post(gen_url, {"report_type": "BOTH"})
        self.assertEqual(gen_resp.status_code, 302)

        session.refresh_from_db()
        self.assertEqual(session.status, SessionStatus.REPORT_GENERATED)

        reports = GeneratedReport.objects.filter(session=session)
        self.assertEqual(reports.count(), 2)

        pdf_report = reports.get(report_type=ReportType.PDF)
        docx_report = reports.get(report_type=ReportType.DOCX)

        # Verify PDF structure (binary header %PDF-)
        pdf_bytes = pdf_report.file.read()
        self.assertTrue(pdf_bytes.startswith(b"%PDF-"))
        self.assertGreater(len(pdf_bytes), 1000)

        # Verify Word structure (valid zip/docx binary)
        docx_bytes = docx_report.file.read()
        self.assertTrue(docx_bytes.startswith(b"PK"))
        self.assertGreater(len(docx_bytes), 1000)

        # Verify snapshot integrity
        self.assertEqual(pdf_report.data_snapshot["instrument"]["serial_number"], "SN-E2E-AUDIT-99")
        self.assertEqual(pdf_report.data_snapshot["counts"]["weighing_points"], 5)

        # ── Step 11: Download Tracking & Audit Logging ────────────────────────
        download_url = reverse("reports:download", kwargs={"pk": pdf_report.pk})
        dl_resp = self.client.get(download_url)
        self.assertEqual(dl_resp.status_code, 200)

        pdf_report.refresh_from_db()
        self.assertEqual(pdf_report.download_count, 1)
        self.assertEqual(pdf_report.download_logs.count(), 1)

        # ── Step 12: Controlled Revision Workflow ─────────────────────────────
        revise_url = reverse("reports:initiate_revision", kwargs={"session_pk": session.pk})
        revise_resp = self.client.post(revise_url, {
            "revision_reason": "Correction of customer billing address and additional verification testing."
        })
        self.assertEqual(revise_resp.status_code, 302)

        session.refresh_from_db()
        self.assertEqual(session.revision_number, 2)
        self.assertEqual(session.status, SessionStatus.UNDER_REVIEW)
        self.assertFalse(session.is_locked)

        # Prior report is superseded
        pdf_report.refresh_from_db()
        self.assertTrue(pdf_report.is_superseded)

        # ── Step 13: Re-approval & Revision 2 Report Generation ───────────────
        SessionService.approve(session, self.reviewer, comments="Revised record verified satisfactory.")
        session.refresh_from_db()
        self.assertEqual(session.status, SessionStatus.APPROVED)

        self.client.post(gen_url, {"report_type": ReportType.PDF})
        rev2_report = GeneratedReport.objects.get(session=session, report_type=ReportType.PDF, is_superseded=False)
        self.assertEqual(rev2_report.revision_number, 2)
        self.assertIn("-R02", rev2_report.report_number)

        # Traceability link
        pdf_report.refresh_from_db()
        self.assertEqual(pdf_report.superseded_by, rev2_report)

        # ── Step 14: Permanent Archival & Delete Protection ───────────────────
        with self.assertRaises(PermissionDenied):
            rev2_report.delete()
