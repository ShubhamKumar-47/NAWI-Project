"""apps/measurements/admin.py"""
from django.contrib import admin
from .models import (
    WeighingMeasurement,
    RepeatabilityMeasurement,
    EccentricityMeasurement,
    DiscriminationMeasurement,
    TareMeasurement,
)


@admin.register(WeighingMeasurement)
class WeighingMeasurementAdmin(admin.ModelAdmin):
    list_display = ["session", "test_type", "nominal_load", "indication", "error", "mpe", "pass_fail"]
    list_filter = ["test_type", "pass_fail"]
    search_fields = ["session__session_number"]


@admin.register(RepeatabilityMeasurement)
class RepeatabilityAdmin(admin.ModelAdmin):
    list_display = ["session", "nominal_load", "repetition_number", "indication", "error", "pass_fail"]
    list_filter = ["pass_fail"]


@admin.register(EccentricityMeasurement)
class EccentricityAdmin(admin.ModelAdmin):
    list_display = ["session", "load_position", "nominal_load", "indication", "error", "pass_fail"]
    list_filter = ["load_position", "pass_fail"]


@admin.register(DiscriminationMeasurement)
class DiscriminationAdmin(admin.ModelAdmin):
    list_display = ["session", "test_load", "indication_before", "indication_after", "change", "pass_fail"]


@admin.register(TareMeasurement)
class TareMeasurementAdmin(admin.ModelAdmin):
    list_display = ["session", "tare_load", "gross_indication", "net_indication", "error", "pass_fail"]
