"""apps/reports/tests.py – Unit and integration tests for PDF Report Generation."""
import os
import hashlib
from decimal import Decimal
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from django.core.files.base import ContentFile

from apps.accounts.models import CustomUser, Organization
from apps.core.constants import AccuracyClass, SessionStatus, UserRole, ReportType, InstrumentStatus
from apps.instruments.models import Instrument
from apps.test_sessions.models import TestSession, OIMLEdition, ApprovalAction
from apps.measurements.models import (
    WeighingMeasurement,
    RepeatabilityMeasurement,
    EccentricityMeasurement,
    DiscriminationMeasurement,
    TareMeasurement,
)
from apps.reports.models import GeneratedReport, ReportDownloadLog
from apps.audit.models import AuditLog
from apps.test_sessions.services import SessionService
from django.core.exceptions import PermissionDenied
from apps.reports.builders.pdf_builder import build_pdf_report
from apps.reports.builders.docx_builder import (
    build_docx_report,
    add_document_heading,
    add_paragraph,
    create_table,
    add_kv_table,
    add_data_table,
    setup_report_header,
    setup_report_footer,
    add_signature_block,
)
import docx


class PDFReportGenerationTests(TestCase):
    """
    Test suite for Python ReportLab PDF Test Report generation,
    versioning, security, preview, and download endpoints.
    """

    def setUp(self):
        self.org = Organization.objects.create(
            name="National Metrology Standards Laboratory",
            accreditation_number="NMC-ISO-17025-2026",
            address="Building 4, Science & Technology Park",
            phone="+44 20 7946 0991",
            email="reports@metrology.gov",
        )
        self.other_org = Organization.objects.create(
            name="Private Calibrations Ltd",
            accreditation_number="PRIV-CAL-99",
        )

        self.operator = CustomUser.objects.create_user(
            email="operator@metrology.gov",
            username="op_user",
            password="Password123!",
            role=UserRole.LAB_OPERATOR,
            organization=self.org,
            first_name="David",
            last_name="Technician",
        )
        self.reviewer = CustomUser.objects.create_user(
            email="reviewer@metrology.gov",
            username="rev_user",
            password="Password123!",
            role=UserRole.REVIEWER,
            organization=self.org,
            first_name="Dr. Eleanor",
            last_name="Reviewer",
        )
        self.other_user = CustomUser.objects.create_user(
            email="intruder@private.com",
            username="intruder_user",
            password="Password123!",
            role=UserRole.REVIEWER,
            organization=self.other_org,
        )

        self.instrument = Instrument.objects.create(
            organization=self.org,
            instrument_name="Ultra-Micro Analytical Balance",
            serial_number="BAL-RPT-001",
            manufacturer="Mettler Toledo",
            model_name="XPR2U",
            accuracy_class=AccuracyClass.CLASS_I,
            max_capacity=Decimal("2.1000"),
            min_capacity=Decimal("0.0001"),
            scale_interval=Decimal("0.000001"),
            actual_scale_interval=Decimal("0.0001"),
            unit_of_measurement="g",
            status=InstrumentStatus.TESTED,
            customer_name="Pharmaceutical Quality Centre",
            location="Cleanroom Bay Alpha",
        )

        self.session = TestSession.objects.create(
            organization=self.org,
            instrument=self.instrument,
            session_number="TS-RPT-2026-001",
            lab_reference_number="LAB-RPT-CAL-01",
            test_date=timezone.now().date(),
            technician=self.operator,
            reviewer=self.reviewer,
            status=SessionStatus.APPROVED,
            is_locked=True,
            overall_result="PASS",
            approved_at=timezone.now(),
            oiml_edition=OIMLEdition.R76_2006,
            temperature_start=Decimal("20.1"),
            temperature_end=Decimal("20.3"),
            humidity_start=Decimal("49.5"),
            humidity_end=Decimal("50.2"),
            reference_standards="E2 Stainless Steel Mass Set #STD-99; Cert #CAL-2026",
            remarks="Instrument stable; environment controlled within ISO 17025 tolerances.",
            proc_initial_examination=True,
            initial_examination_passed=True,
            proc_weighing=True,
            proc_repeatability=True,
            proc_eccentricity=True,
            proc_discrimination=True,
            proc_tare=True,
            created_by=self.operator,
        )

        # Seed measurements for rich multi-page reporting
        WeighingMeasurement.objects.create(
            session=self.session,
            sequence_order=1,
            nominal_load=Decimal("0.5000"),
            indication=Decimal("0.5000"),
            error=Decimal("0.0000"),
            mpe=Decimal("0.0001"),
            pass_fail="PASS",
            is_draft=False,
        )
        WeighingMeasurement.objects.create(
            session=self.session,
            sequence_order=2,
            nominal_load=Decimal("1.0000"),
            indication=Decimal("1.0001"),
            error=Decimal("0.0001"),
            mpe=Decimal("0.0001"),
            pass_fail="PASS",
            is_draft=False,
        )
        WeighingMeasurement.objects.create(
            session=self.session,
            sequence_order=3,
            nominal_load=Decimal("2.0000"),
            indication=Decimal("2.0000"),
            error=Decimal("0.0000"),
            mpe=Decimal("0.0002"),
            pass_fail="PASS",
            is_draft=False,
        )

        for rep in range(1, 4):
            RepeatabilityMeasurement.objects.create(
                session=self.session,
                series_name="Series 1 (~1.0g)",
                nominal_load=Decimal("1.0000"),
                repetition_number=rep,
                indication=Decimal("1.0000"),
                error=Decimal("0.0000"),
                mpe=Decimal("0.0001"),
                pass_fail="PASS",
                is_draft=False,
            )

        for pos in ["CENTRE", "FRONT_LEFT", "BACK_LEFT", "BACK_RIGHT", "FRONT_RIGHT"]:
            EccentricityMeasurement.objects.create(
                session=self.session,
                load_position=pos,
                nominal_load=Decimal("0.7000"),
                indication=Decimal("0.7000"),
                error=Decimal("0.0000"),
                mpe=Decimal("0.0001"),
                pass_fail="PASS",
                is_draft=False,
            )

        DiscriminationMeasurement.objects.create(
            session=self.session,
            test_load=Decimal("1.0000"),
            indication_before=Decimal("1.0000"),
            small_weight_added=Decimal("0.0000014"),
            indication_after=Decimal("1.000001"),
            change=Decimal("0.000001"),
            pass_fail="PASS",
            is_draft=False,
        )

        TareMeasurement.objects.create(
            session=self.session,
            tare_load=Decimal("0.5000"),
            net_load=Decimal("1.0000"),
            gross_indication=Decimal("1.5000"),
            net_indication=Decimal("1.0000"),
            error=Decimal("0.0000"),
            mpe=Decimal("0.0001"),
            pass_fail="PASS",
            is_draft=False,
        )

    def test_pdf_builder_creates_valid_pdf_buffer(self):
        """ReportLab builder compiles a valid, non-empty PDF binary buffer with header/footer."""
        pdf_buf = build_pdf_report(self.session, report_number="TR-TS-RPT-2026-001-R01")
        self.assertIsNotNone(pdf_buf)
        pdf_bytes = pdf_buf.getvalue()

        # Valid PDF header
        self.assertTrue(pdf_bytes.startswith(b"%PDF-"))
        # Non-trivial size (4-page report)
        self.assertGreater(len(pdf_bytes), 5000)

    def test_report_generation_for_approved_session(self):
        """Generating report creates a GeneratedReport model, computes SHA-256, and links to session."""
        self.client.force_login(self.reviewer)
        gen_url = reverse("reports:generate", kwargs={"session_pk": self.session.pk})

        resp = self.client.post(gen_url, {"report_type": ReportType.PDF})
        self.assertEqual(resp.status_code, 302)

        # Report model created
        report = GeneratedReport.objects.filter(session=self.session).first()
        self.assertIsNotNone(report)
        self.assertEqual(report.report_type, ReportType.PDF)
        self.assertTrue(report.report_number.startswith("TR-TS-RPT-2026-001"))
        self.assertFalse(report.is_superseded)
        self.assertEqual(report.generated_by, self.reviewer)

        # Cryptographic checksum verified
        self.assertIsNotNone(report.checksum)
        self.assertEqual(len(report.checksum), 64)

        # Session status moved to REPORT_GENERATED
        self.session.refresh_from_db()
        self.assertEqual(self.session.status, SessionStatus.REPORT_GENERATED)

        # Audit log and ApprovalHistory recorded
        h = self.session.approval_history.first()
        self.assertEqual(h.action, ApprovalAction.GENERATE_REPORT)

    def test_unapproved_session_blocked_from_generating_report(self):
        """Security: Draft / In-Progress sessions are blocked from generating reports."""
        unapproved_session = TestSession.objects.create(
            organization=self.org,
            instrument=self.instrument,
            session_number="TS-DRAFT-REPORT",
            test_date=timezone.now().date(),
            technician=self.operator,
            status=SessionStatus.DRAFT,
            is_locked=False,
        )

        self.client.force_login(self.reviewer)
        gen_url = reverse("reports:generate", kwargs={"session_pk": unapproved_session.pk})
        resp = self.client.post(gen_url, {"report_type": ReportType.PDF})

        # Redirected with error message
        self.assertEqual(resp.status_code, 302)
        # No report created
        self.assertFalse(GeneratedReport.objects.filter(session=unapproved_session).exists())

    def test_superseded_report_versioning_preserves_history(self):
        """Generating a revised report marks the older report as superseded without deleting file."""
        self.client.force_login(self.reviewer)
        gen_url = reverse("reports:generate", kwargs={"session_pk": self.session.pk})

        # Generate Report Version 1
        self.client.post(gen_url, {"report_type": ReportType.PDF})
        r1 = GeneratedReport.objects.get(session=self.session, is_superseded=False)
        self.assertIn("-R01", r1.report_number)

        # Generate Report Version 2
        self.client.post(gen_url, {"report_type": ReportType.PDF})

        r1.refresh_from_db()
        r2 = GeneratedReport.objects.get(session=self.session, is_superseded=False)

        # Version 1 is preserved and marked superseded
        self.assertTrue(r1.is_superseded)
        self.assertFalse(r2.is_superseded)
        self.assertIn("-R02", r2.report_number)
        self.assertNotEqual(r1.pk, r2.pk)

    def test_preview_and_download_views(self):
        """PDF preview serves inline, download serves attachment."""
        self.client.force_login(self.reviewer)
        gen_url = reverse("reports:generate", kwargs={"session_pk": self.session.pk})
        self.client.post(gen_url, {"report_type": ReportType.PDF})
        report = GeneratedReport.objects.filter(session=self.session).first()

        # Preview endpoint
        preview_url = reverse("reports:preview", kwargs={"pk": report.pk})
        prev_resp = self.client.get(preview_url)
        self.assertEqual(prev_resp.status_code, 200)
        self.assertEqual(prev_resp["Content-Type"], "application/pdf")
        self.assertIn("inline", prev_resp["Content-Disposition"])

        # Download endpoint
        download_url = reverse("reports:download", kwargs={"pk": report.pk})
        down_resp = self.client.get(download_url)
        self.assertEqual(down_resp.status_code, 200)
        self.assertEqual(down_resp["Content-Type"], "application/pdf")
        self.assertIn("attachment", down_resp["Content-Disposition"])

    def test_cross_organization_security_blocks_unauthorized_download(self):
        """User from Organization B cannot download or preview Organization A's report (HTTP 404)."""
        self.client.force_login(self.reviewer)
        gen_url = reverse("reports:generate", kwargs={"session_pk": self.session.pk})
        self.client.post(gen_url, {"report_type": ReportType.PDF})
        report = GeneratedReport.objects.filter(session=self.session).first()

        # Switch to intruder user
        self.client.force_login(self.other_user)
        preview_url = reverse("reports:preview", kwargs={"pk": report.pk})
        resp = self.client.get(preview_url)
        self.assertEqual(resp.status_code, 404)

        download_url = reverse("reports:download", kwargs={"pk": report.pk})
        resp_down = self.client.get(download_url)
        self.assertEqual(resp_down.status_code, 404)

    def test_session_pdf_preview_endpoint(self):
        """Session-level preview serves PDF for approved sessions."""
        self.client.force_login(self.reviewer)
        preview_url = reverse("reports:session_preview", kwargs={"session_pk": self.session.pk})
        resp = self.client.get(preview_url)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp["Content-Type"], "application/pdf")


class WordReportGenerationTests(TestCase):
    """
    Test suite for python-docx Word Document Test Report generation,
    reusable components, large datasets, multi-page tables, and downloads.
    """

    def setUp(self):
        self.org = Organization.objects.create(
            name="National Metrology Standards Laboratory",
            accreditation_number="NMC-ISO-17025-2026",
            address="Building 4, Science & Technology Park",
            phone="+44 20 7946 0991",
            email="reports@metrology.gov",
        )
        self.operator = CustomUser.objects.create_user(
            email="operator@metrology.gov",
            username="op_user_docx",
            password="Password123!",
            role=UserRole.LAB_OPERATOR,
            organization=self.org,
            first_name="David",
            last_name="Technician",
        )
        self.reviewer = CustomUser.objects.create_user(
            email="reviewer@metrology.gov",
            username="rev_user_docx",
            password="Password123!",
            role=UserRole.REVIEWER,
            organization=self.org,
            first_name="Dr. Eleanor",
            last_name="Reviewer",
        )

        self.instrument = Instrument.objects.create(
            organization=self.org,
            instrument_name="Precision Industrial Floor Scale",
            serial_number="IND-DOCX-2026",
            manufacturer="Avery Weigh-Tronix",
            model_name="ProFloor-3000",
            accuracy_class=AccuracyClass.CLASS_III,
            max_capacity=Decimal("3000.0"),
            min_capacity=Decimal("20.0"),
            scale_interval=Decimal("1.0"),
            actual_scale_interval=Decimal("1.0"),
            unit_of_measurement="kg",
            status=InstrumentStatus.TESTED,
            customer_name="Global Logistics Hub",
            location="Terminal 4 Loading Bay",
        )

        self.session = TestSession.objects.create(
            organization=self.org,
            instrument=self.instrument,
            session_number="TS-DOCX-2026-001",
            lab_reference_number="LAB-DOCX-CAL-01",
            test_date=timezone.now().date(),
            technician=self.operator,
            reviewer=self.reviewer,
            status=SessionStatus.APPROVED,
            is_locked=True,
            overall_result="PASS",
            approved_at=timezone.now(),
            oiml_edition=OIMLEdition.R76_2006,
            temperature_start=Decimal("21.5"),
            temperature_end=Decimal("22.0"),
            humidity_start=Decimal("48.0"),
            humidity_end=Decimal("51.0"),
            test_location="Terminal 4 Metrology Bay",
            reference_standards="M1 Working Standard Weights (Cert: NMC-2026-M1)",
            initial_examination_passed=True,
            zero_test_passed=True,
            proc_weighing=True,
            proc_repeatability=True,
            proc_eccentricity=True,
            proc_discrimination=True,
            proc_tare=True,
            remarks="Instrument fully compliant with Class III MPE requirements.",
        )

        # Baseline measurement observations
        WeighingMeasurement.objects.create(
            session=self.session,
            sequence_order=1,
            nominal_load=Decimal("500.0"),
            indication=Decimal("500.0"),
            error=Decimal("0.0"),
            mpe=Decimal("1.0"),
            pass_fail="PASS",
        )
        WeighingMeasurement.objects.create(
            session=self.session,
            sequence_order=2,
            nominal_load=Decimal("1500.0"),
            indication=Decimal("1500.5"),
            error=Decimal("0.5"),
            mpe=Decimal("1.5"),
            pass_fail="PASS",
        )
        RepeatabilityMeasurement.objects.create(
            session=self.session,
            series_name="Series 1 (Max)",
            repetition_number=1,
            nominal_load=Decimal("1500.0"),
            indication=Decimal("1500.0"),
            error=Decimal("0.0"),
            mpe=Decimal("1.5"),
            pass_fail="PASS",
        )
        EccentricityMeasurement.objects.create(
            session=self.session,
            load_position="CENTRE",
            nominal_load=Decimal("1000.0"),
            indication=Decimal("1000.0"),
            error=Decimal("0.0"),
            mpe=Decimal("1.0"),
            pass_fail="PASS",
        )

    def test_docx_builder_creates_valid_docx_buffer(self):
        """Word builder outputs a valid, openable DOCX document with expected sections and metadata."""
        buf = build_docx_report(self.session)
        self.assertIsNotNone(buf)
        buf.seek(0)
        content_bytes = buf.getvalue()
        self.assertGreater(len(content_bytes), 1000)

        # Re-open with python-docx to verify document structure
        doc = docx.Document(buf)
        self.assertGreater(len(doc.paragraphs), 5)
        self.assertGreater(len(doc.tables), 3)

        # Verify key metadata in paragraphs and tables
        full_text = " ".join([p.text for p in doc.paragraphs] + [
            cell.text for tbl in doc.tables for row in tbl.rows for cell in row.cells
        ])
        self.assertIn("METROLOGICAL TEST REPORT", full_text)
        self.assertIn("IND-DOCX-2026", full_text)
        self.assertIn("TS-DOCX-2026-001", full_text)
        self.assertIn("Avery Weigh-Tronix", full_text)
        self.assertIn("COMPLIANT / PASS", full_text)

    def test_docx_reusable_functions(self):
        """Directly verify reusable helper functions for headings, tables, paragraphs, and signatures."""
        doc = docx.Document()
        section = doc.sections[0]

        # 1. Reusable Heading
        h1 = add_document_heading(doc, "1. Major Section", level=1)
        self.assertIn("1. Major Section", h1.text)
        h2 = add_document_heading(doc, "1.1 Sub Section", level=2)
        self.assertIn("1.1 Sub Section", h2.text)

        # 2. Reusable Paragraph
        p = add_paragraph(doc, "Test body with <strong>bold text</strong>", bold=False)
        self.assertIn("Test body with bold text", p.text)

        # 3. Reusable KV Table
        kv_table = add_kv_table(doc, [("Key 1", "Value 1"), ("Key 2", "Value 2")])
        self.assertEqual(len(kv_table.rows), 2)
        self.assertEqual(kv_table.rows[0].cells[0].text, "Key 1")
        self.assertEqual(kv_table.rows[0].cells[1].text, "Value 1")

        # 4. Reusable Data Table
        data_table = add_data_table(doc, ["Col A", "Col B", "Status"], [["Val 1", "Val 2", "PASS"], ["Val 3", "Val 4", "FAIL"]])
        self.assertEqual(len(data_table.rows), 3)

        # 5. Header and Footer
        setup_report_header(section, "Test Lab", "TR-TEST-001")
        setup_report_footer(section, "NAWI Test System")
        self.assertIn("TEST LAB", section.header.paragraphs[0].text)
        self.assertIn("NAWI Test System", section.footer.paragraphs[0].text)

        # 6. Signature Block
        sig_tbl = add_signature_block(doc, self.operator, self.reviewer, "2026-11-11", "2026-11-11 12:00")
        self.assertEqual(len(sig_tbl.rows), 1)
        self.assertIn("David Technician", sig_tbl.rows[0].cells[0].text)
        self.assertIn("Dr. Eleanor Reviewer", sig_tbl.rows[0].cells[1].text)

    def test_report_generation_creates_both_pdf_and_docx_reports(self):
        """Submitting report generation with 'BOTH' creates matching PDF and Word reports under same revision."""
        self.client.force_login(self.reviewer)
        gen_url = reverse("reports:generate", kwargs={"session_pk": self.session.pk})

        resp = self.client.post(gen_url, {"report_type": "BOTH"})
        self.assertEqual(resp.status_code, 302)

        reports = GeneratedReport.objects.filter(session=self.session, is_superseded=False)
        self.assertEqual(reports.count(), 2)

        pdf_rep = reports.get(report_type=ReportType.PDF)
        docx_rep = reports.get(report_type=ReportType.DOCX)

        # Both have identical report number and revision
        self.assertEqual(pdf_rep.report_number, docx_rep.report_number)
        self.assertIn("-R01", pdf_rep.report_number)

        # Both have SHA-256 checksums
        self.assertEqual(len(pdf_rep.checksum), 64)
        self.assertEqual(len(docx_rep.checksum), 64)
        self.assertNotEqual(pdf_rep.checksum, docx_rep.checksum)

        # Both files exist on disk
        self.assertTrue(pdf_rep.file.name.endswith(".pdf"))
        self.assertTrue(docx_rep.file.name.endswith(".docx"))

        # Session status updated to REPORT_GENERATED
        self.session.refresh_from_db()
        self.assertEqual(self.session.status, SessionStatus.REPORT_GENERATED)

    def test_download_docx_report_endpoint(self):
        """Word document download returns proper MIME type and attachment header."""
        self.client.force_login(self.reviewer)
        gen_url = reverse("reports:generate", kwargs={"session_pk": self.session.pk})
        self.client.post(gen_url, {"report_type": "DOCX"})

        docx_rep = GeneratedReport.objects.get(session=self.session, report_type=ReportType.DOCX)
        download_url = reverse("reports:download", kwargs={"pk": docx_rep.pk})

        resp = self.client.get(download_url)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(
            resp["Content-Type"],
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        )
        self.assertIn(".docx", resp["Content-Disposition"])
        self.assertIn("attachment", resp["Content-Disposition"])

    def test_session_direct_download_endpoints(self):
        """Testing direct session download buttons for 'pdf' and 'docx'."""
        self.client.force_login(self.reviewer)

        # 1. Download PDF button
        pdf_url = reverse("reports:session_download", kwargs={"session_pk": self.session.pk, "fmt": "pdf"})
        resp_pdf = self.client.get(pdf_url)
        self.assertEqual(resp_pdf.status_code, 200)
        self.assertEqual(resp_pdf["Content-Type"], "application/pdf")
        self.assertIn("attachment", resp_pdf["Content-Disposition"])

        # 2. Download Word button
        docx_url = reverse("reports:session_download", kwargs={"session_pk": self.session.pk, "fmt": "docx"})
        resp_docx = self.client.get(docx_url)
        self.assertEqual(resp_docx.status_code, 200)
        self.assertEqual(
            resp_docx["Content-Type"],
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        )
        self.assertIn(".docx", resp_docx["Content-Disposition"])
        self.assertIn("attachment", resp_docx["Content-Disposition"])

    def test_docx_with_large_dataset_and_multi_page_tables(self):
        """
        Test document generation with a large dataset (40+ measurement rows across multiple cycles)
        verifying repeating headers (<w:tblHeader/>) and anti-split rows (<w:cantSplit/>).
        """
        # Create 40 additional weighing measurements across increasing and decreasing directions
        for i in range(3, 45):
            load = Decimal(str(i * 50))
            is_increasing = (i % 2 != 0)
            WeighingMeasurement.objects.create(
                session=self.session,
                sequence_order=i,
                test_type="INCREASING" if is_increasing else "DECREASING",
                nominal_load=load,
                indication=load + Decimal("0.5"),
                error=Decimal("0.5"),
                mpe=Decimal("1.5"),
                pass_fail="PASS",
            )

        # Generate Word document with large dataset
        buf = build_docx_report(self.session)
        self.assertIsNotNone(buf)
        buf.seek(0)

        # Inspect resulting document
        doc = docx.Document(buf)
        # Find the weighing performance table
        weighing_table = None
        for tbl in doc.tables:
            if len(tbl.rows) >= 40:
                weighing_table = tbl
                break

        self.assertIsNotNone(weighing_table, "Large weighing results table must be present in document.")
        self.assertEqual(len(weighing_table.rows), 45)  # 1 header + 2 baseline + 42 added data rows

        # Verify <w:tblHeader/> on header row
        h_tr = weighing_table.rows[0]._tr
        tblHeader_elements = h_tr.xpath(".//w:tblHeader")
        self.assertGreaterEqual(len(tblHeader_elements), 1, "Table header row must contain <w:tblHeader/> for multi-page repeat.")

        # Verify <w:cantSplit/> on data rows
        row_5 = weighing_table.rows[5]._tr
        cantSplit_elements = row_5.xpath(".//w:cantSplit")
        self.assertGreaterEqual(len(cantSplit_elements), 1, "Data rows must contain <w:cantSplit/> to avoid page splits.")

    def test_consistent_revision_and_data_between_pdf_and_docx(self):
        """Ensures revisions generated across multiple cycles retain identical report numbers and flags."""
        self.client.force_login(self.reviewer)
        gen_url = reverse("reports:generate", kwargs={"session_pk": self.session.pk})

        # Cycle 1: Generate Both
        self.client.post(gen_url, {"report_type": "BOTH"})
        r1_pdf = GeneratedReport.objects.get(session=self.session, report_type=ReportType.PDF, is_superseded=False)
        r1_docx = GeneratedReport.objects.get(session=self.session, report_type=ReportType.DOCX, is_superseded=False)

        self.assertEqual(r1_pdf.report_number, r1_docx.report_number)
        self.assertIn("-R01", r1_pdf.report_number)

        # Cycle 2: Regenerate Both
        self.client.post(gen_url, {"report_type": "BOTH"})
        r1_pdf.refresh_from_db()
        r1_docx.refresh_from_db()
        r2_pdf = GeneratedReport.objects.get(session=self.session, report_type=ReportType.PDF, is_superseded=False)
        r2_docx = GeneratedReport.objects.get(session=self.session, report_type=ReportType.DOCX, is_superseded=False)

        # Prior versions marked superseded
        self.assertTrue(r1_pdf.is_superseded)
        self.assertTrue(r1_docx.is_superseded)

        # New versions have matching -R02 reference
        self.assertFalse(r2_pdf.is_superseded)
        self.assertFalse(r2_docx.is_superseded)
        self.assertEqual(r2_pdf.report_number, r2_docx.report_number)
        self.assertIn("-R02", r2_pdf.report_number)


class ReportHistoryAndAuditTrailTests(TestCase):
    """
    Test suite for Report History and Audit Trail:
    - Unique report IDs, revisions, generation timestamp, generating user
    - Audit logging of approval history, downloads, draft observations & instruments
    - Prevent unauthorized deletion of approved reports
    - Multi-criteria searchable report history with all 8 filters
    - Controlled revision mechanism with point-in-time data snapshots
    """

    def setUp(self):
        self.org = Organization.objects.create(
            name="Federal Metrology Service",
            accreditation_number="FMS-ISO-17025",
            address="Metrology Complex, Central District",
        )
        self.operator = CustomUser.objects.create_user(
            email="tech_audit@fms.gov",
            username="tech_audit",
            password="Password123!",
            role=UserRole.LAB_OPERATOR,
            organization=self.org,
            first_name="Marcus",
            last_name="Technician",
        )
        self.reviewer = CustomUser.objects.create_user(
            email="rev_audit@fms.gov",
            username="rev_audit",
            password="Password123!",
            role=UserRole.REVIEWER,
            organization=self.org,
            first_name="Dr. Sarah",
            last_name="Reviewer",
        )

        self.instrument_1 = Instrument.objects.create(
            organization=self.org,
            instrument_name="High-Capacity Platform Scale",
            serial_number="HPS-2026-X1",
            manufacturer="Sartorius",
            model_name="Combics 3",
            accuracy_class=AccuracyClass.CLASS_III,
            max_capacity=Decimal("1500.0"),
            min_capacity=Decimal("10.0"),
            scale_interval=Decimal("0.5"),
            actual_scale_interval=Decimal("0.5"),
            unit_of_measurement="kg",
            status=InstrumentStatus.TESTED,
            customer_name="AgriCorp Logistics",
            location="Grain Terminal 1",
        )

        self.session_1 = TestSession.objects.create(
            organization=self.org,
            instrument=self.instrument_1,
            session_number="TS-HIST-001",
            lab_reference_number="LAB-HIST-01",
            test_date=timezone.now().date(),
            technician=self.operator,
            reviewer=self.reviewer,
            status=SessionStatus.APPROVED,
            is_locked=True,
            overall_result="PASS",
            approved_at=timezone.now(),
            oiml_edition=OIMLEdition.R76_2006,
            temperature_start=Decimal("20.0"),
            temperature_end=Decimal("20.5"),
            humidity_start=Decimal("50.0"),
            humidity_end=Decimal("52.0"),
            reference_standards="M1 Working Weights",
            proc_initial_examination=True,
            initial_examination_passed=True,
            proc_weighing=True,
            proc_repeatability=False,
            proc_eccentricity=False,
            proc_discrimination=False,
            proc_tare=False,
            proc_zero_setting=False,
        )

        loads = [Decimal("100.0"), Decimal("300.0"), Decimal("600.0"), Decimal("1000.0"), Decimal("1500.0")]
        for seq, load in enumerate(loads, start=1):
            WeighingMeasurement.objects.create(
                session=self.session_1,
                sequence_order=seq,
                nominal_load=load,
                indication=load,
                error=Decimal("0.0"),
                mpe=Decimal("1.0"),
                pass_fail="PASS",
            )

    def test_generated_report_metadata_and_unique_ids(self):
        """Report generation stores unique UUID, revision number, generation date, and data snapshot."""
        self.client.force_login(self.reviewer)
        gen_url = reverse("reports:generate", kwargs={"session_pk": self.session_1.pk})

        resp = self.client.post(gen_url, {"report_type": ReportType.PDF})
        self.assertEqual(resp.status_code, 302)

        report = GeneratedReport.objects.get(session=self.session_1, report_type=ReportType.PDF)
        self.assertIsNotNone(report.id)
        self.assertEqual(report.revision_number, 1)
        self.assertEqual(report.generated_by, self.reviewer)
        self.assertIsNotNone(report.generated_at)
        self.assertIn("-R01", report.report_number)

        # Point-in-time data snapshot verification
        self.assertIn("instrument", report.data_snapshot)
        self.assertIn("session", report.data_snapshot)
        self.assertIn("observations", report.data_snapshot)
        self.assertEqual(report.data_snapshot["instrument"]["serial_number"], "HPS-2026-X1")
        self.assertEqual(report.data_snapshot["session"]["session_number"], "TS-HIST-001")
        self.assertEqual(len(report.data_snapshot["observations"]["weighing"]), 5)

    def test_prevent_unauthorized_deletion_of_approved_reports(self):
        """Approved legal metrology test reports cannot be deleted from the database."""
        self.client.force_login(self.reviewer)
        gen_url = reverse("reports:generate", kwargs={"session_pk": self.session_1.pk})
        self.client.post(gen_url, {"report_type": ReportType.PDF})

        report = GeneratedReport.objects.get(session=self.session_1, report_type=ReportType.PDF)

        # Attempting to delete raises PermissionDenied
        with self.assertRaises(PermissionDenied):
            report.delete()

        # Report still exists in database
        self.assertTrue(GeneratedReport.objects.filter(pk=report.pk).exists())

    def test_track_report_downloads(self):
        """Downloading reports records a ReportDownloadLog entry, increments download_count, and logs to AuditLog."""
        self.client.force_login(self.reviewer)
        gen_url = reverse("reports:generate", kwargs={"session_pk": self.session_1.pk})
        self.client.post(gen_url, {"report_type": ReportType.PDF})

        report = GeneratedReport.objects.get(session=self.session_1, report_type=ReportType.PDF)
        self.assertEqual(report.download_count, 0)
        self.assertEqual(ReportDownloadLog.objects.filter(report=report).count(), 0)

        # Perform download
        download_url = reverse("reports:download", kwargs={"pk": report.pk})
        resp = self.client.get(download_url)
        self.assertEqual(resp.status_code, 200)

        report.refresh_from_db()
        self.assertEqual(report.download_count, 1)

        # Download log created
        log_entry = ReportDownloadLog.objects.filter(report=report).first()
        self.assertIsNotNone(log_entry)
        self.assertEqual(log_entry.user, self.reviewer)
        self.assertEqual(log_entry.download_format, "PDF")

        # AuditLog entry created
        audit_entry = AuditLog.objects.filter(action="DOWNLOAD", object_id=str(report.pk)).first()
        self.assertIsNotNone(audit_entry)
        self.assertIn(report.report_number, audit_entry.description)

    def test_searchable_report_history_filters(self):
        """Test all 8 searchable report history filters."""
        self.client.force_login(self.reviewer)

        # Report 1 (Session 1)
        gen_url_1 = reverse("reports:generate", kwargs={"session_pk": self.session_1.pk})
        self.client.post(gen_url_1, {"report_type": ReportType.PDF})
        r1 = GeneratedReport.objects.get(session=self.session_1, report_type=ReportType.PDF)

        # Second instrument & session for contrast
        instrument_2 = Instrument.objects.create(
            organization=self.org,
            instrument_name="Analytical Microbalance",
            serial_number="MICRO-999-Z",
            manufacturer="Mettler Toledo",
            accuracy_class=AccuracyClass.CLASS_I,
            max_capacity=Decimal("100.0"),
            min_capacity=Decimal("0.001"),
            scale_interval=Decimal("0.0001"),
            actual_scale_interval=Decimal("0.0001"),
            unit_of_measurement="g",
            customer_name="PharmaLab International",
        )
        session_2 = TestSession.objects.create(
            organization=self.org,
            instrument=instrument_2,
            session_number="TS-HIST-002",
            test_date=timezone.now().date() - timezone.timedelta(days=10),
            technician=self.operator,
            reviewer=self.reviewer,
            status=SessionStatus.APPROVED,
            overall_result="PASS",
            approved_at=timezone.now(),
            oiml_edition=OIMLEdition.R76_2006,
        )
        WeighingMeasurement.objects.create(
            session=session_2,
            sequence_order=1,
            nominal_load=Decimal("50.0"),
            indication=Decimal("50.0"),
            error=Decimal("0.0"),
            mpe=Decimal("0.0005"),
            pass_fail="PASS",
        )
        gen_url_2 = reverse("reports:generate", kwargs={"session_pk": session_2.pk})
        self.client.post(gen_url_2, {"report_type": ReportType.DOCX})
        r2 = GeneratedReport.objects.get(session=session_2, report_type=ReportType.DOCX)

        list_url = reverse("reports:list")
        # Consume any redirect flash messages so assertions check table rows cleanly
        self.client.get(list_url)

        # 1. Filter by Report Number
        resp = self.client.get(list_url, {"report_number": r1.report_number})
        self.assertContains(resp, r1.report_number)
        self.assertNotContains(resp, r2.report_number)

        # 2. Filter by Test ID
        resp = self.client.get(list_url, {"test_id": "TS-HIST-002"})
        self.assertContains(resp, r2.report_number)
        self.assertNotContains(resp, r1.report_number)

        # 3. Filter by Instrument Serial Number
        resp = self.client.get(list_url, {"serial_number": "MICRO-999-Z"})
        self.assertContains(resp, r2.report_number)
        self.assertNotContains(resp, r1.report_number)

        # 4. Filter by Client
        resp = self.client.get(list_url, {"client": "AgriCorp"})
        self.assertContains(resp, r1.report_number)
        self.assertNotContains(resp, r2.report_number)

        # 5. Filter by Test Date range
        recent_date = timezone.now().date().strftime("%Y-%m-%d")
        resp = self.client.get(list_url, {"date_from": recent_date})
        self.assertContains(resp, r1.report_number)
        self.assertNotContains(resp, r2.report_number)

        # 6. Filter by Operator
        resp = self.client.get(list_url, {"operator": "Marcus"})
        self.assertContains(resp, r1.report_number)
        self.assertContains(resp, r2.report_number)

        # 7. Filter by Reviewer
        resp = self.client.get(list_url, {"reviewer": "Sarah"})
        self.assertContains(resp, r1.report_number)
        self.assertContains(resp, r2.report_number)

        # 8. Filter by Status (Current)
        resp = self.client.get(list_url, {"status": "CURRENT"})
        self.assertContains(resp, r1.report_number)
        self.assertContains(resp, r2.report_number)

    def test_controlled_revision_mechanism(self):
        """
        Controlled Revision Workflow:
        1. Approved session has report R01.
        2. Authorized reviewer initiates controlled revision with mandatory justification.
        3. R01 report is marked superseded, retaining original file and data snapshot.
        4. Session is unlocked for technical observation adjustments, revision_number increments to 2.
        5. Session is re-approved and report R02 is generated.
        6. R01 points to R02 via superseded_by; both historical data and revised data remain fully traceable.
        """
        self.client.force_login(self.reviewer)

        # Step 1: Generate initial report R01
        gen_url = reverse("reports:generate", kwargs={"session_pk": self.session_1.pk})
        self.client.post(gen_url, {"report_type": ReportType.PDF})
        r01 = GeneratedReport.objects.get(session=self.session_1, report_type=ReportType.PDF)
        self.assertEqual(r01.revision_number, 1)
        self.assertFalse(r01.is_superseded)
        self.assertEqual(r01.data_snapshot["counts"]["weighing_points"], 5)

        # Step 2: Initiate controlled revision
        revise_url = reverse("reports:initiate_revision", kwargs={"session_pk": self.session_1.pk})
        revision_reason = "Metrological re-verification requested due to temperature fluctuation in calibration bay."
        resp = self.client.post(revise_url, {"revision_reason": revision_reason})
        self.assertEqual(resp.status_code, 302)

        # Step 3: Check session state
        self.session_1.refresh_from_db()
        self.assertEqual(self.session_1.revision_number, 2)
        self.assertEqual(self.session_1.status, SessionStatus.UNDER_REVIEW)
        self.assertFalse(self.session_1.is_locked)
        self.assertEqual(self.session_1.revision_reason, revision_reason)

        # Step 4: Check R01 report is marked superseded and retains original snapshot
        r01.refresh_from_db()
        self.assertTrue(r01.is_superseded)
        self.assertEqual(r01.revision_notes, revision_reason)
        self.assertEqual(r01.data_snapshot["counts"]["weighing_points"], 5)

        # Step 5: Technician enters updated observation in unlocked session
        WeighingMeasurement.objects.create(
            session=self.session_1,
            sequence_order=6,
            nominal_load=Decimal("1200.0"),
            indication=Decimal("1200.0"),
            error=Decimal("0.0"),
            mpe=Decimal("1.5"),
            pass_fail="PASS",
        )

        # Step 6: Reviewer re-approves session
        SessionService.approve(self.session_1, self.reviewer, comments="Re-verification satisfactory under revised conditions.")
        self.session_1.refresh_from_db()
        self.assertEqual(self.session_1.status, SessionStatus.APPROVED)
        self.assertTrue(self.session_1.is_locked)

        # Step 7: Generate revised report R02
        self.client.post(gen_url, {"report_type": ReportType.PDF})
        r02 = GeneratedReport.objects.get(session=self.session_1, report_type=ReportType.PDF, is_superseded=False)
        self.assertEqual(r02.revision_number, 2)
        self.assertIn("-R02", r02.report_number)

        # Traceability link: R01 points to R02 via superseded_by
        r01.refresh_from_db()
        self.assertEqual(r01.superseded_by, r02)

        # Snapshot integrity: R01 retained 5 observation points, R02 captures 6 observation points
        self.assertEqual(r01.data_snapshot["counts"]["weighing_points"], 5)
        self.assertEqual(r02.data_snapshot["counts"]["weighing_points"], 6)

    def test_report_detail_and_audit_view(self):
        """Report detail endpoint shows snapshot, approval history, and download audit trail."""
        self.client.force_login(self.reviewer)
        gen_url = reverse("reports:generate", kwargs={"session_pk": self.session_1.pk})
        self.client.post(gen_url, {"report_type": ReportType.PDF})
        report = GeneratedReport.objects.get(session=self.session_1, report_type=ReportType.PDF)

        detail_url = reverse("reports:detail", kwargs={"pk": report.pk})
        resp = self.client.get(detail_url)
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, report.report_number)
        self.assertContains(resp, "Point-in-Time Metrological Data Snapshot")
        self.assertContains(resp, "Approval &amp; Workflow Audit Ledger")
        self.assertContains(resp, "Download Access Audit Log")


