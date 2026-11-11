"""apps/reports/admin.py – Legal metrology report repository and download audit administration."""
from django.contrib import admin
from .models import GeneratedReport, ReportDownloadLog


@admin.register(GeneratedReport)
class GeneratedReportAdmin(admin.ModelAdmin):
    list_display = [
        "report_number", "revision_number", "session", "report_type",
        "generated_by", "generated_at", "is_superseded", "download_count", "checksum",
    ]
    list_filter = ["report_type", "is_superseded", "revision_number", "generated_at"]
    search_fields = [
        "report_number", "session__session_number",
        "session__instrument__serial_number", "session__instrument__customer_name",
    ]
    readonly_fields = [
        "id", "report_number", "revision_number", "session", "report_type",
        "file", "checksum", "data_snapshot", "generated_by", "generated_at",
        "is_superseded", "superseded_by", "revision_notes", "download_count",
    ]
    ordering = ["-generated_at"]

    def has_delete_permission(self, request, obj=None):
        # Prevent deletion of approved/official reports from admin
        return False

    def has_add_permission(self, request):
        # Reports must only be generated via official test session workflows
        return False


@admin.register(ReportDownloadLog)
class ReportDownloadLogAdmin(admin.ModelAdmin):
    list_display = ["report", "download_format", "user", "ip_address", "downloaded_at"]
    list_filter = ["download_format", "downloaded_at"]
    search_fields = ["report__report_number", "user__email", "user__username", "ip_address"]
    readonly_fields = ["id", "report", "user", "download_format", "ip_address", "user_agent", "downloaded_at"]
    ordering = ["-downloaded_at"]

    def has_delete_permission(self, request, obj=None):
        return False

    def has_add_permission(self, request):
        return False
