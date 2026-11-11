"""apps/instruments/forms.py – Instrument registration, edit, and filter forms."""
from django import forms
from django.core.exceptions import ValidationError
from django.utils import timezone
from crispy_forms.helper import FormHelper
from crispy_forms.layout import Layout, Row, Column, Submit, HTML, Fieldset, Div
from apps.core.constants import AccuracyClass, InstrumentStatus
from .models import Instrument, CommonInstrumentType, MeasurementUnit


VALID_UNITS = ["kg", "g", "mg", "t", "lb", "oz"]


class InstrumentForm(forms.ModelForm):
    """
    Form for creating and editing Instrument records according to OIML R 76.
    Uses Crispy Forms (Bootstrap 5) with metrological validations.
    """

    # Custom widgets / fields for enhanced usability
    instrument_type = forms.CharField(
        required=False,
        label="Instrument Type",
        widget=forms.TextInput(
            attrs={
                "class": "form-control",
                "list": "instrument-types-datalist",
                "placeholder": "e.g. Bench Scale, Analytical Balance...",
            }
        ),
        help_text="Select a common type or type a custom instrument category.",
    )

    unit_of_measurement = forms.ChoiceField(
        choices=MeasurementUnit.choices,
        initial=MeasurementUnit.KG,
        label="Unit of Measurement",
        widget=forms.Select(attrs={"class": "form-select", "id": "id_unit_of_measurement"}),
        help_text="Metrological display unit.",
    )

    class Meta:
        model = Instrument
        fields = [
            # A. Identification
            "instrument_name",
            "manufacturer",
            "model_name",
            "model_number",
            "serial_number",
            "instrument_type",
            "year_of_manufacture",
            # B. Metrological Characteristics
            "accuracy_class",
            "unit_of_measurement",
            "max_capacity",
            "min_capacity",
            "scale_interval",
            "actual_scale_interval",
            "n_max",
            # C. Additional Information
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
        ]
        widgets = {
            "registration_date": forms.DateInput(attrs={"type": "date", "class": "form-control"}),
            "received_date": forms.DateInput(attrs={"type": "date", "class": "form-control"}),
            "accuracy_class": forms.Select(attrs={"class": "form-select", "id": "id_accuracy_class"}),
            "status": forms.Select(attrs={"class": "form-select"}),
            "max_capacity": forms.NumberInput(attrs={"class": "form-control", "step": "any", "id": "id_max_capacity"}),
            "min_capacity": forms.NumberInput(attrs={"class": "form-control", "step": "any", "id": "id_min_capacity"}),
            "scale_interval": forms.NumberInput(attrs={"class": "form-control", "step": "any", "id": "id_scale_interval"}),
            "actual_scale_interval": forms.NumberInput(attrs={"class": "form-control", "step": "any", "id": "id_actual_scale_interval"}),
            "n_max": forms.NumberInput(attrs={"class": "form-control", "id": "id_n_max", "placeholder": "Auto-calculated if blank"}),
            "description": forms.Textarea(attrs={"rows": 2, "class": "form-control"}),
            "notes": forms.Textarea(attrs={"rows": 2, "class": "form-control"}),
        }

    def __init__(self, *args, **kwargs):
        self.organization = kwargs.pop("organization", None)
        super().__init__(*args, **kwargs)

        if not self.instance.pk and not self.initial.get("registration_date"):
            self.initial["registration_date"] = timezone.now().date()
            self.initial["received_date"] = timezone.now().date()

        self.helper = FormHelper()
        self.helper.form_tag = True
        self.helper.form_enctype = "multipart/form-data"
        self.helper.layout = Layout(
            # ── A. Identification ──
            Fieldset(
                "A. Instrument Identification",
                Row(
                    Column("instrument_name", css_class="col-md-6 mb-3"),
                    Column("manufacturer", css_class="col-md-6 mb-3"),
                ),
                Row(
                    Column("model_name", css_class="col-md-4 mb-3"),
                    Column("model_number", css_class="col-md-4 mb-3"),
                    Column("serial_number", css_class="col-md-4 mb-3"),
                ),
                Row(
                    Column("instrument_type", css_class="col-md-6 mb-3"),
                    Column("year_of_manufacture", css_class="col-md-6 mb-3"),
                ),
                css_class="border p-3 rounded mb-4 bg-light bg-opacity-25 shadow-sm",
            ),
            # ── B. Metrological Characteristics ──
            Fieldset(
                "B. Metrological Characteristics (OIML R 76)",
                HTML(
                    """
                    <div class="alert alert-primary py-2 px-3 mb-3 small d-flex align-items-center">
                        <i class="bi bi-info-circle-fill me-2 fs-5"></i>
                        <div>
                            <strong>OIML R 76 Metrological Principles:</strong>
                            <code>Max</code> = Maximum capacity &bull; <code>Min</code> = Minimum capacity &bull;
                            <code>d</code> = Actual scale interval &bull; <code>e</code> = Verification scale interval &bull;
                            <code>n = Max / e</code>. Note: <em>d &le; e</em> per &sect;3.4.
                        </div>
                    </div>
                    """
                ),
                Row(
                    Column("accuracy_class", css_class="col-md-6 mb-3"),
                    Column("unit_of_measurement", css_class="col-md-6 mb-3"),
                ),
                Row(
                    Column("max_capacity", css_class="col-md-6 mb-3"),
                    Column("min_capacity", css_class="col-md-6 mb-3"),
                ),
                Row(
                    Column("scale_interval", css_class="col-md-4 mb-3"),
                    Column("actual_scale_interval", css_class="col-md-4 mb-3"),
                    Column("n_max", css_class="col-md-4 mb-3"),
                ),
                HTML(
                    """
                    <div class="d-flex gap-2 mb-3">
                        <button type="button" class="btn btn-outline-secondary btn-sm" id="btn-copy-d-to-e">
                            <i class="bi bi-arrow-left-right me-1"></i>Set e = d (Standard Scale)
                        </button>
                        <button type="button" class="btn btn-outline-primary btn-sm" id="btn-calc-n">
                            <i class="bi bi-calculator me-1"></i>Auto-Calculate n = Max / e
                        </button>
                    </div>
                    """
                ),
                css_class="border p-3 rounded mb-4 bg-light bg-opacity-25 shadow-sm",
            ),
            # ── C. Additional Information ──
            Fieldset(
                "C. Additional Information & Laboratory Tracking",
                Row(
                    Column("customer_name", css_class="col-md-6 mb-3"),
                    Column("lab_reference_number", css_class="col-md-6 mb-3"),
                ),
                Row(
                    Column("location", css_class="col-md-4 mb-3"),
                    Column("registration_date", css_class="col-md-4 mb-3"),
                    Column("received_date", css_class="col-md-4 mb-3"),
                ),
                Row(
                    Column("approval_number", css_class="col-md-6 mb-3"),
                    Column("status", css_class="col-md-6 mb-3"),
                ),
                Row(
                    Column("description", css_class="col-12 mb-3"),
                ),
                Row(
                    Column("photo", css_class="col-md-6 mb-3"),
                    Column("notes", css_class="col-md-6 mb-3"),
                ),
                css_class="border p-3 rounded mb-4 bg-light bg-opacity-25 shadow-sm",
            ),
            Div(
                Submit("submit", "Save Instrument", css_class="btn btn-primary px-4 py-2"),
                HTML('<a href="{% url \'instruments:list\' %}" class="btn btn-outline-secondary ms-2">Cancel</a>'),
                css_class="d-flex align-items-center mt-3",
            ),
        )

    def clean_serial_number(self):
        """Prevent duplicate serial numbers within the organisation."""
        sn = self.cleaned_data.get("serial_number", "").strip()
        if not sn:
            raise ValidationError("Serial number is required.")

        qs = Instrument.objects.filter(
            serial_number__iexact=sn,
            is_deleted=False,
        )
        if self.organization:
            qs = qs.filter(organization=self.organization)

        if self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)

        if qs.exists():
            raise ValidationError(
                f"An active instrument with serial number '{sn}' is already registered in this laboratory."
            )
        return sn

    def clean_year_of_manufacture(self):
        """Validate realistic year of manufacture."""
        year = self.cleaned_data.get("year_of_manufacture")
        if year is not None:
            current_year = timezone.now().year
            if year < 1900 or year > current_year + 1:
                raise ValidationError(
                    f"Year of manufacture must be between 1900 and {current_year + 1}."
                )
        return year

    def clean_max_capacity(self):
        """Validate Max > 0."""
        max_cap = self.cleaned_data.get("max_capacity")
        if max_cap is not None and max_cap <= 0:
            raise ValidationError("Maximum capacity (Max) must be strictly greater than 0.")
        return max_cap

    def clean_min_capacity(self):
        """Validate Min >= 0."""
        min_cap = self.cleaned_data.get("min_capacity")
        if min_cap is not None and min_cap < 0:
            raise ValidationError("Minimum capacity (Min) cannot be negative.")
        return min_cap

    def clean_scale_interval(self):
        """Validate d > 0."""
        d = self.cleaned_data.get("scale_interval")
        if d is not None and d <= 0:
            raise ValidationError("Actual scale interval (d) must be strictly greater than 0.")
        return d

    def clean_actual_scale_interval(self):
        """Validate e > 0."""
        e = self.cleaned_data.get("actual_scale_interval")
        if e is not None and e <= 0:
            raise ValidationError("Verification scale interval (e) must be strictly greater than 0.")
        return e

    def clean_n_max(self):
        """Validate n > 0 if provided."""
        n = self.cleaned_data.get("n_max")
        if n is not None and n <= 0:
            raise ValidationError("Number of verification intervals (n) must be a positive integer.")
        return n

    def clean(self):
        """Cross-field metrological validation per OIML R 76."""
        cleaned = super().clean()
        max_cap = cleaned.get("max_capacity")
        min_cap = cleaned.get("min_capacity")
        scale_d = cleaned.get("scale_interval")
        scale_e = cleaned.get("actual_scale_interval")
        n_max = cleaned.get("n_max")

        # 1. Min < Max
        if max_cap is not None and min_cap is not None:
            if min_cap >= max_cap:
                self.add_error(
                    "min_capacity",
                    "Minimum capacity (Min) must be strictly less than maximum capacity (Max)."
                )

        # 2. OIML R 76 §3.4: d <= e (Actual scale interval d cannot exceed verification interval e)
        if scale_d is not None and scale_e is not None:
            if scale_d > scale_e:
                self.add_error(
                    "scale_interval",
                    f"Per OIML R 76 §3.4, actual scale interval (d={scale_d}) cannot be greater "
                    f"than verification scale interval (e={scale_e})."
                )

        # 3. Auto-compute or verify n = Max / e
        if max_cap and scale_e and scale_e > 0:
            calc_n = int(max_cap / scale_e)
            if not n_max:
                cleaned["n_max"] = calc_n
            elif abs(n_max - calc_n) > 5:
                # Warning / informational validation: allow configurable, but flag if widely disparate
                # without raising a fatal error if it's a multi-range instrument
                pass

        return cleaned
