"""apps/measurements/forms.py – Observation and measurement data entry forms.

Follows OIML R 76 requirements for raw observation logging, condition tracking,
input validation, and draft preservation.
"""
from decimal import Decimal
from django import forms
from django.core.exceptions import ValidationError

from .models import (
    WeighingMeasurement,
    RepeatabilityMeasurement,
    EccentricityMeasurement,
    DiscriminationMeasurement,
    TareMeasurement,
    ZeroSettingMeasurement,
)


class BaseMeasurementForm(forms.ModelForm):
    """Base class for all measurement observation forms with shared styling and validation."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field_name, field in self.fields.items():
            if isinstance(field.widget, forms.CheckboxInput):
                field.widget.attrs.update({"class": "form-check-input"})
            elif isinstance(field.widget, forms.Select):
                field.widget.attrs.update({"class": "form-select"})
            else:
                field.widget.attrs.update({"class": "form-control"})

    def clean_temperature(self):
        temp = self.cleaned_data.get("temperature")
        if temp is not None:
            if temp < Decimal("-30.0") or temp > Decimal("70.0"):
                raise ValidationError("Ambient temperature must be between -30°C and +70°C.")
        return temp


class WeighingMeasurementForm(BaseMeasurementForm):
    """Single observation entry for Weighing Performance Test."""

    class Meta:
        model = WeighingMeasurement
        fields = [
            "test_type",
            "sequence_order",
            "nominal_load",
            "indication",
            "zero_indication",
            "tare_applied",
            "temperature",
            "observations",
            "is_draft",
        ]
        widgets = {
            "sequence_order": forms.NumberInput(attrs={"min": "1", "step": "1"}),
            "nominal_load": forms.NumberInput(attrs={"step": "any", "placeholder": "e.g. 10.0000"}),
            "indication": forms.NumberInput(attrs={"step": "any", "placeholder": "e.g. 10.0010"}),
            "zero_indication": forms.NumberInput(attrs={"step": "any", "value": "0"}),
            "tare_applied": forms.NumberInput(attrs={"step": "any", "value": "0"}),
            "temperature": forms.NumberInput(attrs={"step": "0.1", "placeholder": "20.0"}),
            "observations": forms.TextInput(attrs={"placeholder": "Optional loading remarks"}),
        }

    def clean_nominal_load(self):
        load = self.cleaned_data.get("nominal_load")
        if load is not None and load < 0:
            raise ValidationError("Applied nominal load cannot be negative.")
        return load

    def clean_tare_applied(self):
        tare = self.cleaned_data.get("tare_applied")
        if tare is not None and tare < 0:
            raise ValidationError("Applied tare cannot be negative.")
        return tare


class RepeatabilityMeasurementForm(BaseMeasurementForm):
    """Single observation entry for Repeatability Test."""

    class Meta:
        model = RepeatabilityMeasurement
        fields = [
            "series_name",
            "repetition_number",
            "nominal_load",
            "zero_indication",
            "indication",
            "temperature",
            "observations",
            "is_draft",
        ]
        widgets = {
            "series_name": forms.TextInput(attrs={"placeholder": "e.g. Series 1 (~0.5 Max)"}),
            "repetition_number": forms.NumberInput(attrs={"min": "1", "step": "1"}),
            "nominal_load": forms.NumberInput(attrs={"step": "any", "placeholder": "e.g. 25.0000"}),
            "zero_indication": forms.NumberInput(attrs={"step": "any", "value": "0"}),
            "indication": forms.NumberInput(attrs={"step": "any", "placeholder": "e.g. 25.0005"}),
            "temperature": forms.NumberInput(attrs={"step": "0.1", "placeholder": "20.0"}),
            "observations": forms.TextInput(attrs={"placeholder": "Repetition remarks"}),
        }

    def clean_nominal_load(self):
        load = self.cleaned_data.get("nominal_load")
        if load is not None and load <= 0:
            raise ValidationError("Reference load must be strictly greater than zero.")
        return load

    def clean_repetition_number(self):
        rep = self.cleaned_data.get("repetition_number")
        if rep is not None and rep < 1:
            raise ValidationError("Repetition number must be at least 1.")
        return rep


class EccentricityMeasurementForm(BaseMeasurementForm):
    """Observation entry for Eccentricity (Off-Centre Loading) Test."""

    class Meta:
        model = EccentricityMeasurement
        fields = [
            "load_position",
            "nominal_load",
            "zero_indication",
            "indication",
            "temperature",
            "observations",
            "is_draft",
        ]
        widgets = {
            "nominal_load": forms.NumberInput(attrs={"step": "any", "placeholder": "e.g. 10.0000"}),
            "zero_indication": forms.NumberInput(attrs={"step": "any", "value": "0"}),
            "indication": forms.NumberInput(attrs={"step": "any", "placeholder": "e.g. 10.0002"}),
            "temperature": forms.NumberInput(attrs={"step": "0.1", "placeholder": "20.0"}),
            "observations": forms.TextInput(attrs={"placeholder": "Placement notes"}),
        }

    def clean_nominal_load(self):
        load = self.cleaned_data.get("nominal_load")
        if load is not None and load <= 0:
            raise ValidationError("Reference load must be strictly greater than zero.")
        return load


class DiscriminationMeasurementForm(BaseMeasurementForm):
    """Observation entry for Discrimination Test."""

    class Meta:
        model = DiscriminationMeasurement
        fields = [
            "test_load",
            "indication_before",
            "small_weight_added",
            "indication_after",
            "temperature",
            "observations",
            "is_draft",
        ]
        widgets = {
            "test_load": forms.NumberInput(attrs={"step": "any", "placeholder": "e.g. 50.0000"}),
            "indication_before": forms.NumberInput(attrs={"step": "any", "placeholder": "e.g. 50.0000"}),
            "small_weight_added": forms.NumberInput(attrs={"step": "any", "placeholder": "e.g. 0.0014 (≈1.4d)"}),
            "indication_after": forms.NumberInput(attrs={"step": "any", "placeholder": "e.g. 50.0010"}),
            "temperature": forms.NumberInput(attrs={"step": "0.1", "placeholder": "20.0"}),
            "observations": forms.TextInput(attrs={"placeholder": "Indicator response notes"}),
        }

    def clean_test_load(self):
        load = self.cleaned_data.get("test_load")
        if load is not None and load < 0:
            raise ValidationError("Test load cannot be negative.")
        return load

    def clean_small_weight_added(self):
        w = self.cleaned_data.get("small_weight_added")
        if w is not None and w <= 0:
            raise ValidationError("Small weight added (ΔL) must be greater than zero.")
        return w


class TareMeasurementForm(BaseMeasurementForm):
    """Observation entry for Tare Weighing Test."""

    class Meta:
        model = TareMeasurement
        fields = [
            "tare_load",
            "net_load",
            "gross_indication",
            "net_indication",
            "temperature",
            "observations",
            "is_draft",
        ]
        widgets = {
            "tare_load": forms.NumberInput(attrs={"step": "any", "placeholder": "e.g. 5.0000"}),
            "net_load": forms.NumberInput(attrs={"step": "any", "placeholder": "e.g. 10.0000"}),
            "gross_indication": forms.NumberInput(attrs={"step": "any", "placeholder": "e.g. 15.0000"}),
            "net_indication": forms.NumberInput(attrs={"step": "any", "placeholder": "e.g. 10.0005"}),
            "temperature": forms.NumberInput(attrs={"step": "0.1", "placeholder": "20.0"}),
            "observations": forms.TextInput(attrs={"placeholder": "Tare balance observations"}),
        }

    def clean_tare_load(self):
        tare = self.cleaned_data.get("tare_load")
        if tare is not None and tare < 0:
            raise ValidationError("Tare load cannot be negative.")
        return tare

    def clean_net_load(self):
        net = self.cleaned_data.get("net_load")
        if net is not None and net < 0:
            raise ValidationError("Net test load cannot be negative.")
        return net


class ZeroSettingMeasurementForm(BaseMeasurementForm):
    """Observation entry for Zero-Setting & Tracking Test."""

    class Meta:
        model = ZeroSettingMeasurement
        fields = [
            "operation_type",
            "zero_indication_before",
            "zero_indication_after",
            "small_weight_added",
            "temperature",
            "observations",
            "is_draft",
        ]
        widgets = {
            "zero_indication_before": forms.NumberInput(attrs={"step": "any", "value": "0"}),
            "zero_indication_after": forms.NumberInput(attrs={"step": "any", "value": "0"}),
            "small_weight_added": forms.NumberInput(attrs={"step": "any", "value": "0", "placeholder": "ΔL for turning point"}),
            "temperature": forms.NumberInput(attrs={"step": "0.1", "placeholder": "20.0"}),
            "observations": forms.TextInput(attrs={"placeholder": "Zero check notes"}),
        }

    def clean_small_weight_added(self):
        w = self.cleaned_data.get("small_weight_added")
        if w is not None and w < 0:
            raise ValidationError("Small weight added cannot be negative.")
        return w

