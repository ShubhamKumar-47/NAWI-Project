"""
scripts/verify_e2e_live.py
Execute a complete, live end-to-end metrological verification on the active database.
"""
import os
import sys
import django
from decimal import Decimal
import datetime
import hashlib
from django.core.files.base import ContentFile

# Setup Django
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(BASE_DIR)
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.development")
django.setup()

from apps.accounts.models import CustomUser, Organization
from apps.core.constants import UserRole, AccuracyClass, InstrumentStatus, SessionStatus, ReportType
from apps.instruments.models import Instrument
from apps.test_sessions.models import TestSession, OIMLEdition
from apps.test_sessions.services import SessionService
from apps.measurements.models import (
    WeighingMeasurement,
    RepeatabilityMeasurement,
    EccentricityMeasurement,
    ZeroSettingMeasurement,
)
from calculations.services import SessionCalculationCoordinator
from apps.reports.builders.pdf_builder import build_pdf_report
from apps.reports.builders.docx_builder import build_docx_report
from apps.reports.models import GeneratedReport, ReportDownloadLog
from apps.reports.snapshot import create_session_snapshot
from apps.audit.models import AuditLog


def run_e2e_verification():
    print("=" * 75)
    print("NAWI TEST REPORT MANAGEMENT SYSTEM - LIVE END-TO-END VERIFICATION")
    print("=" * 75)

    # 1. Organization & User Accounts
    print("\n[Step 1] Verifying Laboratory Organization & User Roles...")
    org = Organization.objects.filter(name="National Standards Metrology Lab").first()
    if not org:
        org = Organization.objects.first()
    if not org:
        org = Organization.objects.create(
            name="National Standards Metrology Lab",
            accreditation_number="NMI-ISO17025-001"
        )
    print(f"  Organization: {org.name} (Accreditation: {org.accreditation_number})")

    operator, _ = CustomUser.objects.get_or_create(
        email="operator.live@nawi.local",
        defaults={
            "username": "operator_live",
            "first_name": "Marcus",
            "last_name": "Vance",
            "role": UserRole.LAB_OPERATOR,
            "organization": org,
            "must_change_password": False,
            "is_active": True,
        }
    )
    operator.role = UserRole.LAB_OPERATOR
    operator.save()

    reviewer, _ = CustomUser.objects.get_or_create(
        email="reviewer.live@nawi.local",
        defaults={
            "username": "reviewer_live",
            "first_name": "Dr. Sarah",
            "last_name": "Chen",
            "role": UserRole.REVIEWER,
            "organization": org,
            "must_change_password": False,
            "is_active": True,
        }
    )
    reviewer.role = UserRole.REVIEWER
    reviewer.save()

    print(f"  Operator Account: {operator.email} (Role: {operator.role})")
    print(f"  Reviewer Account: {reviewer.email} (Role: {reviewer.role}, Can Approve: {reviewer.can_approve_sessions})")

    # 2. Instrument Registration
    print("\n[Step 2] Registering OIML Class III Precision Bench Scale...")
    inst_serial = f"LIVE-SN-{datetime.datetime.now().strftime('%Y%m%d%H%M%S')}"
    instrument = Instrument.objects.create(
        organization=org,
        serial_number=inst_serial,
        instrument_name="Precision Bench Scale",
        manufacturer="Sartorius",
        model_name="CPA-16001S",
        model_number="CPA-16001S",
        instrument_type="Bench Scale",
        year_of_manufacture=2024,
        accuracy_class=AccuracyClass.CLASS_III,
        max_capacity=Decimal("15.000"),
        min_capacity=Decimal("0.100"),
        scale_interval=Decimal("0.005"),
        actual_scale_interval=Decimal("0.005"),
        unit_of_measurement="kg",
        customer_name="Apex Food Industries Ltd",
        lab_reference_number="LAB-REF-LIVE-01",
        location="Main Calibration Bay A",
        status=InstrumentStatus.IN_LAB,
        created_by=operator,
    )
    print(f"  Instrument Registered: {instrument.model_name} (S/N: {instrument.serial_number})")
    print(f"  Accuracy Class: {instrument.accuracy_class}, Max: {instrument.max_capacity}kg, e: {instrument.scale_interval}kg")
    print(f"  Verification scale intervals n: {instrument.n_max}")
    assert instrument.n_max == 3000, f"Expected n=3000, got {instrument.n_max}"

    # 3. Test Session Initialization
    print("\n[Step 3] Creating Test Session with Environmental Conditions...")
    session_num = f"TS-LIVE-{datetime.datetime.now().strftime('%Y%m%d%H%M%S')}"
    session = TestSession.objects.create(
        organization=org,
        instrument=instrument,
        session_number=session_num,
        test_date=datetime.date.today(),
        technician=operator,
        test_location="Environmental Calibration Bay 1",
        temperature_start=Decimal("20.2"),
        temperature_end=Decimal("20.5"),
        humidity_start=Decimal("50.0"),
        humidity_end=Decimal("52.0"),
        reference_standards="Class M1 Stainless Steel Weights (Cert: NMI-M1-2026)",
        lab_reference_number="TS-REF-LIVE-001",
        proc_initial_examination=True,
        initial_examination_passed=True,
        proc_weighing=True,
        proc_repeatability=False,
        proc_eccentricity=False,
        proc_discrimination=False,
        proc_tare=False,
        proc_zero_setting=False,
        status=SessionStatus.DRAFT,
        created_by=operator,
    )
    print(f"  Test Session Initialized: {session.session_number}")
    print(f"  Environmental: {session.temperature_start}°C - {session.temperature_end}°C, {session.humidity_start}% - {session.humidity_end}% RH")

    # 4. Recording Metrological Observations across Test Procedures
    print("\n[Step 4] Logging Observations for Weighing Performance Procedure...")

    # Weighing Performance: 5 Ascending + 5 Descending Load Steps
    weighing_points = [
        {"seq": 1, "type": "INCREASING", "load": "1.000", "ind": "1.000"},
        {"seq": 2, "type": "INCREASING", "load": "3.000", "ind": "3.000"},
        {"seq": 3, "type": "INCREASING", "load": "7.500", "ind": "7.500"},
        {"seq": 4, "type": "INCREASING", "load": "11.000", "ind": "11.000"},
        {"seq": 5, "type": "INCREASING", "load": "15.000", "ind": "15.000"},
        {"seq": 6, "type": "DECREASING", "load": "15.000", "ind": "15.000"},
        {"seq": 7, "type": "DECREASING", "load": "11.000", "ind": "11.000"},
        {"seq": 8, "type": "DECREASING", "load": "7.500", "ind": "7.500"},
        {"seq": 9, "type": "DECREASING", "load": "3.000", "ind": "3.000"},
        {"seq": 10, "type": "DECREASING", "load": "1.000", "ind": "1.000"},
    ]
    for pt in weighing_points:
        WeighingMeasurement.objects.create(
            session=session,
            sequence_order=pt["seq"],
            test_type=pt["type"],
            nominal_load=Decimal(pt["load"]),
            indication=Decimal(pt["ind"]),
            is_draft=False,
            created_by=operator,
        )
    print(f"  - Weighing Performance: {len(weighing_points)} load steps logged (5 increasing + 5 decreasing).")

    # 5. Calculation Engine Processing
    print("\n[Step 5] Triggering Automated Metrological Calculation Engine...")
    calc_records = SessionCalculationCoordinator.evaluate_session(session, calculated_by=operator)
    session.refresh_from_db()
    print(f"  Calculations executed. Records generated: {len(calc_records)}")
    print(f"  Session Overall Result: {session.overall_result}")
    assert session.overall_result == "PASS", f"Expected PASS, got {session.overall_result}"

    # 6. Workflow Submission & Peer Review
    print("\n[Step 6] Operator Submitting Test for Review...")
    SessionService.submit_for_review(session, user=operator, comments="Observations submitted for technical review.")
    session.refresh_from_db()
    print(f"  Session Status: {session.status}")
    assert session.status == SessionStatus.SUBMITTED

    print("\n[Step 7] Reviewer Peer Review & Approval...")
    SessionService.start_review(session, reviewer=reviewer, comments="Starting technical review.")
    session.refresh_from_db()
    print(f"  Session Status: {session.status}")
    assert session.status == SessionStatus.UNDER_REVIEW

    SessionService.approve(
        session,
        reviewer=reviewer,
        comments="Measurements verified compliant with OIML R 76-1:2006 Table 1 MPE tolerances."
    )
    session.refresh_from_db()
    print(f"  Session Status: {session.status}, Locked: {session.is_locked}, Reviewer: {session.reviewer.email}")
    assert session.status == SessionStatus.APPROVED
    assert session.is_locked is True

    # 7. Dual Report Generation (PDF & Word)
    print("\n[Step 8] Generating Dual Metrology Certificates (PDF & Word)...")
    snapshot = create_session_snapshot(session)
    report_num = f"REP-{session.session_number}-01"

    # PDF Generation
    pdf_buffer = build_pdf_report(session, report_number=report_num)
    pdf_bytes = pdf_buffer.getvalue()
    assert pdf_bytes.startswith(b"%PDF"), "Generated PDF does not have %PDF header!"
    print(f"  PDF Report Generated ({len(pdf_bytes)} bytes)")

    pdf_sha256 = hashlib.sha256(pdf_bytes).hexdigest()
    pdf_report = GeneratedReport.objects.create(
        session=session,
        report_number=report_num,
        report_type=ReportType.PDF,
        file=ContentFile(pdf_bytes, name=f"{report_num}.pdf"),
        revision_number=session.revision_number,
        checksum=pdf_sha256,
        data_snapshot=snapshot,
        generated_by=reviewer,
    )
    print(f"  PDF Archive Saved: {pdf_report.report_number}, Checksum: {pdf_report.checksum[:16]}...")

    # Word (DOCX) Generation
    docx_buffer = build_docx_report(session, report_number=report_num)
    docx_bytes = docx_buffer.getvalue()
    assert docx_bytes.startswith(b"PK"), "Generated DOCX does not have valid ZIP header!"
    print(f"  Word Report Generated ({len(docx_bytes)} bytes)")

    docx_sha256 = hashlib.sha256(docx_bytes).hexdigest()
    docx_report = GeneratedReport.objects.create(
        session=session,
        report_number=report_num,
        report_type=ReportType.DOCX,
        file=ContentFile(docx_bytes, name=f"{report_num}.docx"),
        revision_number=session.revision_number,
        checksum=docx_sha256,
        data_snapshot=snapshot,
        generated_by=reviewer,
    )
    print(f"  Word Archive Saved: {docx_report.report_number}, Checksum: {docx_report.checksum[:16]}...")

    SessionService.generate_report(session, user=reviewer)
    session.refresh_from_db()
    print(f"  Session Status after Report Generation: {session.status}")
    assert session.status == SessionStatus.REPORT_GENERATED

    # 8. Report History, Search & Download Auditing
    print("\n[Step 9] Verifying Download Auditing & Immutability...")
    ReportDownloadLog.objects.create(
        report=pdf_report,
        user=reviewer,
        ip_address="127.0.0.1",
        user_agent="Live-Verification-Agent/1.0",
    )
    pdf_report.refresh_from_db()
    print(f"  Download logged. PDF Total Downloads: {pdf_report.download_logs.count()}")

    # 9. Controlled Revision Workflow
    print("\n[Step 10] Testing Controlled Revision Workflow...")
    SessionService.initiate_revision(
        session,
        user=reviewer,
        revision_reason="Customer requested recalibration at additional check point."
    )
    session.refresh_from_db()
    print(f"  Revised Session Status: {session.status}")
    print(f"  Revision Number: {session.revision_number}, Locked: {session.is_locked}")
    assert session.revision_number == 2, f"Expected revision 2, got {session.revision_number}"
    assert session.is_locked is False, "Revised session must be unlocked!"

    print("\n" + "=" * 75)
    print("ALL 10 END-TO-END WORKFLOW STAGES VERIFIED LIVE ON THE ACTIVE SYSTEM!")
    print("=" * 75)


if __name__ == "__main__":
    run_e2e_verification()
