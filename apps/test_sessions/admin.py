"""apps/test_sessions/admin.py – Django admin configuration for TestSession model."""
from django.contrib import admin
from .models import TestSession


@admin.register(TestSession)
class TestSessionAdmin(admin.ModelAdmin):
    list_display = [
        "session_number",
        "instrument",
        "lab_reference_number",
        "test_date",
        "technician",
        "reviewer",
        "status",
        "overall_result",
        "is_locked",
        "organization",
    ]
    list_filter = [
        "status",
        "is_locked",
        "overall_result",
        "oiml_edition",
        "organization",
        "test_date",
    ]
    search_fields = [
        "session_number",
        "lab_reference_number",
        "instrument__serial_number",
        "instrument__manufacturer",
        "instrument__model_name",
        "technician__email",
        "technician__username",
    ]
    readonly_fields = ["id", "created_at", "updated_at", "session_number", "is_locked"]
    ordering = ["-created_at"]

    fieldsets = (
        (
            "Test Identification",
            {
                "fields": (
                    "organization",
                    "instrument",
                    "session_number",
                    "lab_reference_number",
                    "test_date",
                    "test_location",
                    "technician",
                    "reviewer",
                    "oiml_edition",
                    "status",
                    "is_locked",
                    "overall_result",
                )
            },
        ),
        (
            "Environmental Conditions",
            {
                "fields": (
                    "temperature_start",
                    "temperature_end",
                    "humidity_start",
                    "humidity_end",
                    "reference_standards",
                )
            },
        ),
        (
            "Applicable Test Procedures",
            {
                "fields": (
                    "proc_initial_examination",
                    "proc_zero_setting",
                    "proc_weighing",
                    "proc_repeatability",
                    "proc_eccentricity",
                    "proc_discrimination",
                    "proc_tare",
                    "proc_influence_quantities",
                )
            },
        ),
        (
            "Test Observations & Review Comments",
            {
                "fields": (
                    "initial_examination_passed",
                    "initial_examination_notes",
                    "zero_test_passed",
                    "zero_test_notes",
                    "remarks",
                    "notes",
                    "rejection_reason",
                )
            },
        ),
        (
            "Audit & Metadata",
            {
                "fields": ("id", "created_at", "updated_at", "created_by"),
                "classes": ("collapse",),
            },
        ),
    )
