"""apps/reports/models.py – Generated report metadata, snapshots, and download audit trail."""
import hashlib
import uuid
from django.db import models
from django.conf import settings
from django.core.exceptions import PermissionDenied
from apps.core.constants import ReportType, SessionStatus


class GeneratedReport(models.Model):
    """
    Tracks an official generated PDF or DOCX report for a test session.
    The actual file is stored in media/reports/.
    Maintains cryptographic checksum, revision history, and data snapshot.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    session = models.ForeignKey(
        "test_sessions.TestSession",
        on_delete=models.CASCADE,
        related_name="reports",
    )
    report_type = models.CharField(
        max_length=10,
        choices=ReportType.choices,
        default=ReportType.PDF,
    )
    report_number = models.CharField(
        max_length=60,
        blank=True,
        help_text="Official report reference number (e.g. TR-TS-20261111-0001-R01).",
    )
    revision_number = models.PositiveIntegerField(
        default=1,
        verbose_name="Revision Number",
        help_text="Revision sequence (1 for R01, 2 for R02, etc.).",
    )
    file = models.FileField(
        upload_to="reports/",
        help_text="Generated report file (PDF or DOCX).",
    )
    checksum = models.CharField(
        max_length=64,
        blank=True,
        help_text="SHA-256 checksum of the generated file.",
    )
    data_snapshot = models.JSONField(
        default=dict,
        blank=True,
        verbose_name="Metrological Data Snapshot",
        help_text="Point-in-time snapshot of instrument, session, observations, and calculations at generation.",
    )
    generated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="generated_reports",
    )
    generated_at = models.DateTimeField(auto_now_add=True)
    is_superseded = models.BooleanField(
        default=False,
        help_text="Set True when a newer version of this report is generated.",
    )
    superseded_by = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="superseded_versions",
        verbose_name="Superseded By",
        help_text="Traceability link to the newer superseding report revision.",
    )
    revision_notes = models.TextField(
        blank=True,
        verbose_name="Revision Justification",
        help_text="Formal change-control justification or amendment summary.",
    )
    download_count = models.PositiveIntegerField(
        default=0,
        verbose_name="Download Count",
        help_text="Total number of times this report was downloaded.",
    )

    class Meta:
        ordering = ["-generated_at"]
        verbose_name = "Generated Report"
        verbose_name_plural = "Generated Reports"

    def __str__(self):
        return (
            f"{self.report_number or self.report_type} — "
            f"{self.session.session_number} (Rev #{self.revision_number})"
        )

    def compute_checksum(self):
        """Compute and store SHA-256 checksum of the report file."""
        sha256 = hashlib.sha256()
        self.file.seek(0)
        for chunk in iter(lambda: self.file.read(8192), b""):
            sha256.update(chunk)
        self.checksum = sha256.hexdigest()

    def delete(self, *args, **kwargs):
        """
        Prevent unauthorized deletion of approved, official, or superseded historical reports.
        Under ISO/IEC 17025, certified test reports are legally immutable.
        """
        if (
            self.session.status in [SessionStatus.APPROVED, SessionStatus.REPORT_GENERATED]
            or self.is_superseded
            or self.session.approval_history.filter(to_status=SessionStatus.APPROVED).exists()
        ):
            raise PermissionDenied(
                "Official metrology reports cannot be deleted once approved. "
                "Under ISO/IEC 17025 and legal metrology standards, historical test reports must be preserved."
            )
        super().delete(*args, **kwargs)

    def log_download(self, user, request=None, fmt="PDF"):
        """Record an immutable audit log entry for this report download."""
        from apps.audit.utils import get_client_ip, log_action
        from apps.core.constants import AuditAction

        ip = get_client_ip(request) if request else None
        ua = request.META.get("HTTP_USER_AGENT", "") if request else ""

        ReportDownloadLog.objects.create(
            report=self,
            user=user if user and user.is_authenticated else None,
            ip_address=ip,
            user_agent=ua,
            download_format=fmt.upper(),
        )

        GeneratedReport.objects.filter(pk=self.pk).update(
            download_count=models.F("download_count") + 1
        )

        log_action(
            user=user if user and user.is_authenticated else None,
            action=AuditAction.DOWNLOAD,
            obj=self,
            description=f"Downloaded {fmt.upper()} report {self.report_number} (Rev #{self.revision_number}).",
            request=request,
        )


class ReportDownloadLog(models.Model):
    """
    Audit log for tracking report file downloads and previews.
    Records timestamp, downloading user, IP address, user-agent, and format.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    report = models.ForeignKey(
        GeneratedReport,
        on_delete=models.CASCADE,
        related_name="download_logs",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="report_downloads",
    )
    downloaded_at = models.DateTimeField(auto_now_add=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True)
    download_format = models.CharField(max_length=10, blank=True)

    class Meta:
        ordering = ["-downloaded_at"]
        verbose_name = "Report Download Log"
        verbose_name_plural = "Report Download Logs"

    def __str__(self):
        return f"[{self.downloaded_at:%Y-%m-%d %H:%M}] {self.report.report_number} ({self.download_format}) by {self.user}"
