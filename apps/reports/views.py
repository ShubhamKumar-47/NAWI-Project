"""apps/reports/views.py – Searchable report history, audit trail, versioning & downloads."""
import hashlib
import os
from io import BytesIO

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.core.files.base import ContentFile
from django.core.paginator import Paginator
from django.db import models
from django.db.models import Q, Sum
from django.http import FileResponse, Http404, HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.dateparse import parse_date

from apps.core.constants import AuditAction, ReportType, SessionStatus
from apps.audit.utils import log_action
from apps.test_sessions.models import TestSession
from .models import GeneratedReport, ReportDownloadLog
from .snapshot import create_session_snapshot
from .builders.pdf_builder import build_pdf_report
from .builders.docx_builder import build_docx_report


@login_required
def report_list(request):
    """
    Searchable Report History with comprehensive metrological filters:
    1. Report Number
    2. Test ID (Session Number)
    3. Instrument Serial Number
    4. Client / Owner Name
    5. Test Date Range (from / to)
    6. Report Status (Current vs Superseded vs All)
    7. Operator (Technician)
    8. Reviewer
    Plus general text search and document format filter (PDF / Word).
    """
    org = request.user.organization
    if request.user.is_superadmin:
        base_qs = GeneratedReport.objects.select_related(
            "session", "session__instrument", "session__technician",
            "session__reviewer", "generated_by"
        )
    else:
        base_qs = GeneratedReport.objects.filter(
            session__organization=org
        ).select_related(
            "session", "session__instrument", "session__technician",
            "session__reviewer", "generated_by"
        )

    # Summary metrics before filtering
    total_count = base_qs.count()
    current_count = base_qs.filter(is_superseded=False).count()
    superseded_count = base_qs.filter(is_superseded=True).count()
    total_downloads = base_qs.aggregate(Sum("download_count"))["download_count__sum"] or 0

    reports = base_qs.order_by("-generated_at")

    # ── 1. General search keyword ──
    q = request.GET.get("q", "").strip()
    if q:
        reports = reports.filter(
            Q(report_number__icontains=q)
            | Q(session__session_number__icontains=q)
            | Q(session__instrument__serial_number__icontains=q)
            | Q(session__instrument__instrument_name__icontains=q)
            | Q(session__instrument__customer_name__icontains=q)
        )

    # ── 2. Report Number Filter ──
    report_number = request.GET.get("report_number", "").strip()
    if report_number:
        reports = reports.filter(report_number__icontains=report_number)

    # ── 3. Test ID (Session Number) Filter ──
    test_id = request.GET.get("test_id", "").strip()
    if test_id:
        reports = reports.filter(session__session_number__icontains=test_id)

    # ── 4. Instrument Serial Number Filter ──
    serial_number = request.GET.get("serial_number", "").strip()
    if serial_number:
        reports = reports.filter(session__instrument__serial_number__icontains=serial_number)

    # ── 5. Client / Customer Filter ──
    client = request.GET.get("client", "").strip()
    if client:
        reports = reports.filter(
            Q(session__instrument__customer_name__icontains=client)
            | Q(session__organization__name__icontains=client)
        )

    # ── 6. Test Date Range Filter ──
    date_from = request.GET.get("date_from", "").strip()
    date_to = request.GET.get("date_to", "").strip()
    if date_from:
        d_from = parse_date(date_from)
        if d_from:
            reports = reports.filter(session__test_date__gte=d_from)
    if date_to:
        d_to = parse_date(date_to)
        if d_to:
            reports = reports.filter(session__test_date__lte=d_to)

    # ── 7. Report Status (Current vs Superseded) ──
    status = request.GET.get("status", "ALL").upper().strip()
    if status == "CURRENT":
        reports = reports.filter(is_superseded=False)
    elif status == "SUPERSEDED":
        reports = reports.filter(is_superseded=True)

    # ── 8. Operator (Technician) Filter ──
    operator = request.GET.get("operator", "").strip()
    if operator:
        reports = reports.filter(
            Q(session__technician__first_name__icontains=operator)
            | Q(session__technician__last_name__icontains=operator)
            | Q(session__technician__username__icontains=operator)
            | Q(session__technician__email__icontains=operator)
        )

    # ── 9. Reviewer Filter ──
    reviewer = request.GET.get("reviewer", "").strip()
    if reviewer:
        reports = reports.filter(
            Q(session__reviewer__first_name__icontains=reviewer)
            | Q(session__reviewer__last_name__icontains=reviewer)
            | Q(session__reviewer__username__icontains=reviewer)
            | Q(session__reviewer__email__icontains=reviewer)
        )

    # ── 10. Format Filter (PDF vs DOCX) ──
    fmt = request.GET.get("format", "ALL").upper().strip()
    if fmt in [ReportType.PDF, ReportType.DOCX]:
        reports = reports.filter(report_type=fmt)

    # Pagination (15 reports per page)
    paginator = Paginator(reports, 15)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    # Build query string preserving active filters for pagination links
    params = request.GET.copy()
    params.pop("page", None)
    query_string = params.urlencode()
    has_active_filters = bool(params)

    return render(request, "reports/report_list.html", {
        "page_obj": page_obj,
        "reports": page_obj.object_list,
        "total_count": total_count,
        "current_count": current_count,
        "superseded_count": superseded_count,
        "total_downloads": total_downloads,
        "filtered_count": reports.count(),
        "query_string": query_string,
        "has_active_filters": has_active_filters,
        # Preserve filter field values
        "filter_q": q,
        "filter_report_number": report_number,
        "filter_test_id": test_id,
        "filter_serial_number": serial_number,
        "filter_client": client,
        "filter_date_from": date_from,
        "filter_date_to": date_to,
        "filter_status": status,
        "filter_operator": operator,
        "filter_reviewer": reviewer,
        "filter_format": fmt,
    })


@login_required
def report_detail(request, pk):
    """
    Detailed Report Audit Trail & Data Snapshot Viewer:
    - Cryptographic integrity (SHA-256)
    - Full point-in-time metrological data snapshot
    - Version genealogy (earlier superseded reports & superseding report)
    - Approval workflow timeline for linked test session
    - File download access log
    - Controlled revision actions
    """
    report = get_object_or_404(
        GeneratedReport.objects.select_related(
            "session", "session__instrument", "session__technician",
            "session__reviewer", "session__organization",
            "generated_by", "superseded_by"
        ),
        pk=pk,
    )

    # Scoped authorization
    if not request.user.is_superadmin:
        if report.session.organization != request.user.organization:
            raise Http404("Report not found.")

    download_logs = report.download_logs.select_related("user").order_by("-downloaded_at")[:50]
    approval_history = report.session.approval_history.select_related("actor").order_by("created_at")
    superseded_versions = report.superseded_versions.all().order_by("-revision_number")

    can_revise = (
        report.session.status in [SessionStatus.APPROVED, SessionStatus.REPORT_GENERATED]
        and (
            request.user.is_superadmin
            or request.user.can_approve_sessions
            or request.user.is_administrator
        )
    )

    return render(request, "reports/report_detail.html", {
        "report": report,
        "session": report.session,
        "instrument": report.session.instrument,
        "snapshot": report.data_snapshot,
        "download_logs": download_logs,
        "approval_history": approval_history,
        "superseded_versions": superseded_versions,
        "can_revise": can_revise,
    })


@login_required
def initiate_revision(request, session_pk):
    """
    Controlled Revision Workflow:
    Approved/Report Generated records can only be revised through this formal
    change-control procedure. Requires an authorized reviewer or administrator
    and a mandatory revision justification (minimum 15 characters).
    Unlocks the record for technical adjustments and increments revision_number,
    while permanently preserving all historical reports, files, and data snapshots.
    """
    session = get_object_or_404(
        TestSession.objects.select_related("instrument", "organization"),
        pk=session_pk,
        organization=request.user.organization,
    )

    # Security check: Only reviewers or administrators can initiate a controlled revision
    if not (
        request.user.is_superadmin
        or request.user.can_approve_sessions
        or request.user.is_administrator
    ):
        raise PermissionDenied("Only authorized reviewers or laboratory administrators can initiate revisions.")

    if session.status not in [SessionStatus.APPROVED, SessionStatus.REPORT_GENERATED]:
        messages.warning(
            request,
            f"Controlled revision is only applicable to Approved records (current: '{session.get_status_display()}')."
        )
        return redirect("test_sessions:detail", pk=session_pk)

    if request.method == "POST":
        justification = request.POST.get("revision_reason", "").strip()
        if len(justification) < 15:
            messages.error(
                request,
                "A formal change-control justification is mandatory (minimum 15 characters)."
            )
            return render(request, "reports/revise.html", {
                "session": session,
                "active_reports": session.reports.filter(is_superseded=False),
            })

        try:
            # 1. Capture snapshot of the current state for any active report missing a snapshot
            snapshot = create_session_snapshot(session)
            GeneratedReport.objects.filter(session=session, is_superseded=False).filter(
                data_snapshot={}
            ).update(data_snapshot=snapshot)

            # 2. Mark active reports as superseded with the revision notes
            GeneratedReport.objects.filter(
                session=session, is_superseded=False
            ).update(is_superseded=True, revision_notes=justification)

            # 3. Call SessionService to execute controlled revision transition
            from apps.test_sessions.services import SessionService
            SessionService.initiate_revision(
                session=session,
                user=request.user,
                revision_reason=justification,
                request=request,
            )

            messages.success(
                request,
                f"Controlled Revision #{session.revision_number} successfully initiated for {session.session_number}. "
                "The test record is now open for technical adjustments and observation revision."
            )
            return redirect("test_sessions:detail", pk=session_pk)

        except Exception as exc:
            messages.error(request, f"Failed to initiate revision: {exc}")
            return redirect("test_sessions:detail", pk=session_pk)

    return render(request, "reports/revise.html", {
        "session": session,
        "active_reports": session.reports.filter(is_superseded=False),
    })


@login_required
def generate_report(request, session_pk):
    """
    Generate an official, immutable test report (PDF and/or DOCX) from an approved TestSession.
    Captures point-in-time data snapshot and links previous superseded revisions.
    Security:
    - Only authorized users with report generation permission.
    - Only approved records (APPROVED or REPORT_GENERATED) can generate final reports.
    - Historical versions are preserved and marked as superseded (never silently overwritten).
    """
    session = get_object_or_404(
        TestSession,
        pk=session_pk,
        organization=request.user.organization,
    )

    # Security rule: Only approved test records can generate final reports
    if session.status not in [SessionStatus.APPROVED, SessionStatus.REPORT_GENERATED]:
        messages.error(
            request,
            f"Cannot generate an official test report for session '{session.session_number}' in '{session.get_status_display()}' status. "
            "The record must first complete review and receive formal Approval."
        )
        return redirect("test_sessions:detail", pk=session_pk)

    if not request.user.can_generate_reports:
        return HttpResponseForbidden("You do not have authorization to generate test reports.")

    if request.method == "POST":
        selected_type = request.POST.get("report_type", "BOTH")

        try:
            # Calculate report revision number based on existing distinct report runs
            existing_revisions = set(
                GeneratedReport.objects.filter(session=session)
                .values_list("report_number", flat=True)
            )
            rev_idx = len(existing_revisions) + 1
            revision_num = session.revision_number or rev_idx
            report_number = f"TR-{session.session_number}-R{rev_idx:02d}"

            # Capture complete metrological data snapshot at this generation instant
            snapshot = create_session_snapshot(session)
            created_reports = []

            # ── 1. Generate PDF ReportLab Certificate ──
            if selected_type in [ReportType.PDF, "BOTH", "ALL"]:
                pdf_buffer = build_pdf_report(session, report_number=report_number)
                pdf_filename = f"Report_{session.session_number}_R{rev_idx:02d}.pdf"
                pdf_content = ContentFile(pdf_buffer.getvalue(), name=pdf_filename)
                pdf_sha256 = hashlib.sha256(pdf_buffer.getvalue()).hexdigest()

                pdf_report = GeneratedReport.objects.create(
                    session=session,
                    report_type=ReportType.PDF,
                    file=pdf_content,
                    report_number=report_number,
                    revision_number=revision_num,
                    checksum=pdf_sha256,
                    data_snapshot=snapshot,
                    revision_notes=session.revision_reason or "",
                    generated_by=request.user,
                )
                # Mark older PDF versions as superseded and link parent traceability
                GeneratedReport.objects.filter(
                    session=session, report_type=ReportType.PDF
                ).exclude(pk=pdf_report.pk).filter(
                    superseded_by__isnull=True
                ).update(
                    is_superseded=True, superseded_by=pdf_report
                )
                created_reports.append(pdf_report)

            # ── 2. Generate Editable Word (.docx) Report ──
            if selected_type in [ReportType.DOCX, "BOTH", "ALL"]:
                docx_buffer = build_docx_report(session, report_number=report_number)
                docx_filename = f"Report_{session.session_number}_R{rev_idx:02d}.docx"
                docx_content = ContentFile(docx_buffer.getvalue(), name=docx_filename)
                docx_sha256 = hashlib.sha256(docx_buffer.getvalue()).hexdigest()

                docx_report = GeneratedReport.objects.create(
                    session=session,
                    report_type=ReportType.DOCX,
                    file=docx_content,
                    report_number=report_number,
                    revision_number=revision_num,
                    checksum=docx_sha256,
                    data_snapshot=snapshot,
                    revision_notes=session.revision_reason or "",
                    generated_by=request.user,
                )
                # Mark older DOCX versions as superseded and link parent traceability
                GeneratedReport.objects.filter(
                    session=session, report_type=ReportType.DOCX
                ).exclude(pk=docx_report.pk).filter(
                    superseded_by__isnull=True
                ).update(
                    is_superseded=True, superseded_by=docx_report
                )
                created_reports.append(docx_report)

            # Advance session workflow to REPORT_GENERATED & update approval history
            from apps.test_sessions.services import SessionService
            SessionService.generate_report(session, request.user, request=request)

            format_names = ", ".join([r.get_report_type_display() for r in created_reports])
            log_action(
                user=request.user,
                action=AuditAction.GENERATE,
                obj=session,
                description=f"Generated official test reports ({format_names}) under reference {report_number} (Rev #{revision_num}).",
                request=request,
            )
            messages.success(
                request,
                f"Official Test Report '{report_number}' ({format_names}) generated and cryptographically signed successfully."
            )

            # Primary redirect
            pdf_rep = next((r for r in created_reports if r.report_type == ReportType.PDF), None)
            if pdf_rep:
                return redirect("reports:preview", pk=pdf_rep.pk)
            elif created_reports:
                return redirect("reports:download", pk=created_reports[0].pk)
            else:
                return redirect("reports:list")

        except Exception as exc:
            messages.error(request, f"Report generation failed: {exc}")
            return redirect("test_sessions:detail", pk=session_pk)

    return render(request, "reports/generate.html", {
        "session": session,
        "report_type_choices": ReportType.choices,
    })


@login_required
def preview_report(request, pk):
    """
    Serve a generated PDF test report for inline browser preview.
    If DOCX is requested for preview, redirect to file download.
    Tracks preview in AuditLog.
    """
    report = get_object_or_404(GeneratedReport, pk=pk)

    # Scoped authorization
    if not request.user.is_superadmin:
        if report.session.organization != request.user.organization:
            raise Http404("Report not found.")

    if report.report_type == ReportType.DOCX:
        return redirect("reports:download", pk=report.pk)

    try:
        file_handle = report.file.open("rb")
        response = FileResponse(file_handle, content_type="application/pdf")
        clean_filename = f"{report.report_number or 'Test_Report'}.pdf"
        response["Content-Disposition"] = f'inline; filename="{clean_filename}"'

        # Record viewing in audit log
        log_action(
            user=request.user,
            action=AuditAction.VIEW,
            obj=report,
            description=f"Previewed PDF report {report.report_number} (Rev #{report.revision_number}).",
            request=request,
        )
        return response
    except (FileNotFoundError, ValueError):
        messages.error(request, "The requested report file could not be located on disk.")
        return redirect("reports:list")


@login_required
def download_report(request, pk):
    """
    Serve a generated report file for direct file download as an attachment.
    Tracks download count, IP address, user agent, and logs to AuditLog and ReportDownloadLog.
    """
    report = get_object_or_404(GeneratedReport, pk=pk)

    # Scoped authorization
    if not request.user.is_superadmin:
        if report.session.organization != request.user.organization:
            raise Http404("Report not found.")

    try:
        file_handle = report.file.open("rb")
        if report.report_type == ReportType.DOCX:
            mime = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            ext = "docx"
        else:
            mime = "application/pdf"
            ext = "pdf"

        response = FileResponse(file_handle, content_type=mime)
        clean_filename = f"{report.report_number or 'Test_Report'}.{ext}"
        response["Content-Disposition"] = f'attachment; filename="{clean_filename}"'

        # Record download audit tracking
        report.log_download(user=request.user, request=request, fmt=ext)
        return response
    except (FileNotFoundError, ValueError):
        messages.error(request, "The requested report file could not be located on disk.")
        return redirect("reports:list")


@login_required
def session_download_report(request, session_pk, fmt):
    """
    Direct download endpoint for session reports by format ('pdf' or 'docx').
    If report already exists, downloads the active version and logs audit trail.
    If session is approved but file not yet compiled, compiles it on the fly.
    """
    session = get_object_or_404(
        TestSession,
        pk=session_pk,
        organization=request.user.organization,
    )

    fmt_upper = fmt.upper()
    if fmt_upper not in [ReportType.PDF, ReportType.DOCX]:
        raise Http404(f"Unsupported report format '{fmt}'.")

    # Find active non-superseded report of requested format
    report = GeneratedReport.objects.filter(
        session=session, report_type=fmt_upper, is_superseded=False
    ).first()

    if report:
        return download_report(request, report.pk)

    # If approved but report record not yet persisted, compile and serve
    if session.status in [SessionStatus.APPROVED, SessionStatus.REPORT_GENERATED]:
        existing_revisions = set(
            GeneratedReport.objects.filter(session=session)
            .values_list("report_number", flat=True)
        )
        rev_idx = len(existing_revisions) + 1
        report_number = f"TR-{session.session_number}-R{rev_idx:02d}"

        if fmt_upper == ReportType.DOCX:
            buf = build_docx_report(session, report_number=report_number)
            mime = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            ext = "docx"
        else:
            buf = build_pdf_report(session, report_number=report_number)
            mime = "application/pdf"
            ext = "pdf"

        # Log action for on-the-fly download
        log_action(
            user=request.user,
            action=AuditAction.DOWNLOAD,
            obj=session,
            description=f"Downloaded on-the-fly {fmt_upper} report for session {session.session_number}.",
            request=request,
        )

        response = FileResponse(buf, content_type=mime)
        response["Content-Disposition"] = f'attachment; filename="{report_number}.{ext}"'
        return response

    messages.warning(request, "Test record must be Approved before downloading official reports.")
    return redirect("test_sessions:detail", pk=session_pk)


@login_required
def session_pdf_preview(request, session_pk):
    """
    Convenience view: Opens the latest generated report preview for a session,
    or generates an on-the-fly preview if already approved.
    """
    session = get_object_or_404(
        TestSession,
        pk=session_pk,
        organization=request.user.organization,
    )

    latest_report = GeneratedReport.objects.filter(
        session=session, report_type=ReportType.PDF, is_superseded=False
    ).first()
    if latest_report:
        return redirect("reports:preview", pk=latest_report.pk)

    if session.status in [SessionStatus.APPROVED, SessionStatus.REPORT_GENERATED]:
        pdf_buffer = build_pdf_report(session)
        response = FileResponse(pdf_buffer, content_type="application/pdf")
        response["Content-Disposition"] = f'inline; filename="Preview_{session.session_number}.pdf"'
        return response

    messages.warning(request, "Test record must be Approved before viewing official report preview.")
    return redirect("test_sessions:detail", pk=session_pk)
