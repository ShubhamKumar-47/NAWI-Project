"""apps/instruments/admin.py – Django admin registration for Instrument model."""
from django.contrib import admin
from .models import Instrument


@admin.register(Instrument)
class InstrumentAdmin(admin.ModelAdmin):
    list_display = [
        "serial_number",
        "instrument_name",
        "manufacturer",
        "model_name",
        "accuracy_class",
        "max_capacity",
        "unit_of_measurement",
        "customer_name",
        "status",
        "organization",
        "registration_date",
    ]
    list_filter = ["accuracy_class", "status", "organization", "instrument_type", "is_deleted"]
    search_fields = [
        "serial_number",
        "instrument_name",
        "manufacturer",
        "model_name",
        "model_number",
        "customer_name",
        "lab_reference_number",
        "approval_number",
    ]
    ordering = ["-created_at"]
    readonly_fields = ["id", "created_at", "updated_at", "created_by", "n_max"]

    fieldsets = (
        (
            "Identification",
            {
                "fields": (
                    "organization",
                    "instrument_name",
                    "manufacturer",
                    "model_name",
                    "model_number",
                    "serial_number",
                    "instrument_type",
                    "year_of_manufacture",
                )
            },
        ),
        (
            "Metrological Characteristics (OIML R 76)",
            {
                "fields": (
                    "accuracy_class",
                    "unit_of_measurement",
                    "max_capacity",
                    "min_capacity",
                    "scale_interval",
                    "actual_scale_interval",
                    "n_max",
                )
            },
        ),
        (
            "Additional Information & Lab Tracking",
            {
                "fields": (
                    "customer_name",
                    "lab_reference_number",
                    "location",
                    "registration_date",
                    "received_date",
                    "approval_number",
                    "status",
                    "description",
                    "photo",
                    "notes",
                )
            },
        ),
        (
            "Audit & System",
            {
                "fields": (
                    "id",
                    "created_at",
                    "updated_at",
                    "created_by",
                    "is_deleted",
                    "deleted_at",
                    "deleted_by",
                ),
                "classes": ("collapse",),
            },
        ),
    )
