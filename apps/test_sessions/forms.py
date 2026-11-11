"""apps/test_sessions/forms.py – Forms for test session wizard, procedure selection, and review."""
from django import forms
from django.core.exceptions import ValidationError
from django.utils import timezone
from crispy_forms.helper import FormHelper
from crispy_forms.layout import Layout, Row, Column, Submit, Fieldset, HTML, Div
from apps.accounts.models import CustomUser
from apps.instruments.models import Instrument
from apps.core.constants import SessionStatus, UserRole
from .models import TestSession, OIMLEdition, generate_session_number


class TestSessionWizardForm(forms.ModelForm):
    """
    Comprehensive multi-step form / wizard for creating and editing test records.
    Covers Steps 1 through 5:
      Step 1: Instrument selection
      Step 2: Test information & identification
      Step 3: Environmental conditions
      Step 4: Test procedure selection (configurable applicability)
      Step 5: Test observations & initial checks
    """

    # Hidden field to capture wizard submission intent: 'draft' or 'in_progress'
    action_intent = forms.CharField(
        widget=forms.HiddenInput(),
        required=False,
        initial="in_progress",
    )

    class Meta:
        model = TestSession
        fields = [
            # Step 1: Instrument
            "instrument",
            # Step 2: Test Information
            "session_number",
            "lab_reference_number",
            "test_date",
            "test_location",
            "technician",
            "oiml_edition",
            # Step 3: Environmental Conditions
            "temperature_start",
            "temperature_end",
            "humidity_start",
            "humidity_end",
            "reference_standards",
            # Step 4: Procedure Selection
            "proc_initial_examination",
            "proc_zero_setting",
            "proc_weighing",
            "proc_repeatability",
            "proc_eccentricity",
            "proc_discrimination",
            "proc_tare",
            "proc_influence_quantities",
            # Step 5: Test Observations & Remarks
            "initial_examination_passed",
            "initial_examination_notes",
            "zero_test_passed",
            "zero_test_notes",
            "remarks",
        ]
        widgets = {
            "instrument": forms.Select(attrs={"class": "form-select", "id": "id_instrument"}),
            "session_number": forms.TextInput(attrs={"class": "form-control font-monospace", "id": "id_session_number"}),
            "lab_reference_number": forms.TextInput(attrs={"class": "form-control font-monospace", "placeholder": "e.g. LAB-TR-2026-0042"}),
            "test_date": forms.DateInput(attrs={"type": "date", "class": "form-control"}),
            "test_location": forms.TextInput(attrs={"class": "form-control", "placeholder": "e.g. Metrology Bay 1"}),
            "technician": forms.Select(attrs={"class": "form-select"}),
            "oiml_edition": forms.Select(attrs={"class": "form-select"}),
            "temperature_start": forms.NumberInput(attrs={"class": "form-control", "step": "0.1", "placeholder": "°C"}),
            "temperature_end": forms.NumberInput(attrs={"class": "form-control", "step": "0.1", "placeholder": "°C"}),
            "humidity_start": forms.NumberInput(attrs={"class": "form-control", "step": "0.5", "placeholder": "%RH"}),
            "humidity_end": forms.NumberInput(attrs={"class": "form-control", "step": "0.5", "placeholder": "%RH"}),
            "reference_standards": forms.Textarea(attrs={"class": "form-control", "rows": 2, "placeholder": "e.g. Standard Weights Set F1, S/N: W-10294, Cal Cert: CC-2026-88"}),
            "initial_examination_notes": forms.Textarea(attrs={"class": "form-control", "rows": 2, "placeholder": "Observations on plate markings, levelling bubble, and physical condition"}),
            "zero_test_notes": forms.Textarea(attrs={"class": "form-control", "rows": 2, "placeholder": "Observations on non-automatic zero-setting accuracy (within ±0.25e)"}),
            "remarks": forms.Textarea(attrs={"class": "form-control", "rows": 3, "placeholder": "General technician remarks, instrument behavior, or unusual lab occurrences"}),
        }

    def __init__(self, *args, **kwargs):
        self.organization = kwargs.pop("organization", None)
        self.current_user = kwargs.pop("current_user", None)
        initial_instrument = kwargs.pop("initial_instrument", None)
        super().__init__(*args, **kwargs)

        # Restrict instruments to active instruments in the user's organisation
        if self.organization:
            self.fields["instrument"].queryset = (
                Instrument.objects.filter(organization=self.organization, is_deleted=False)
                .order_by("manufacturer", "model_name")
            )
            # Restrict technician to organisation users
            self.fields["technician"].queryset = (
                CustomUser.objects.filter(organization=self.organization, is_active=True)
                .exclude(role=UserRole.VIEWER)
                .order_by("first_name", "last_name", "username")
            )

        # Set defaults for new sessions
        if not self.instance.pk:
            if not self.initial.get("session_number"):
                self.initial["session_number"] = generate_session_number()
            if not self.initial.get("test_date"):
                self.initial["test_date"] = timezone.now().date()
            if self.current_user and not self.initial.get("technician"):
                self.initial["technician"] = self.current_user

        if initial_instrument:
            self.fields["instrument"].initial = initial_instrument

    def clean_session_number(self):
        """Enforce unique session reference number per organisation."""
        sn = self.cleaned_data.get("session_number", "").strip()
        if not sn:
            raise ValidationError("A unique Test ID is required.")

        qs = TestSession.objects.filter(session_number__iexact=sn)
        if self.organization:
            qs = qs.filter(organization=self.organization)
        if self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)

        if qs.exists():
            raise ValidationError(
                f"A test record with Test ID '{sn}' already exists in your laboratory."
            )
        return sn

    def clean_humidity_start(self):
        rh = self.cleaned_data.get("humidity_start")
        if rh is not None and (rh < 0 or rh > 100):
            raise ValidationError("Relative humidity must be between 0% and 100%.")
        return rh

    def clean_humidity_end(self):
        rh = self.cleaned_data.get("humidity_end")
        if rh is not None and (rh < 0 or rh > 100):
            raise ValidationError("Relative humidity must be between 0% and 100%.")
        return rh

    def clean(self):
        cleaned = super().clean()
        # Verify at least one test procedure is selected
        procedures = [
            cleaned.get("proc_initial_examination"),
            cleaned.get("proc_zero_setting"),
            cleaned.get("proc_weighing"),
            cleaned.get("proc_repeatability"),
            cleaned.get("proc_eccentricity"),
            cleaned.get("proc_discrimination"),
            cleaned.get("proc_tare"),
            cleaned.get("proc_influence_quantities"),
        ]
        if not any(procedures):
            raise ValidationError(
                "At least one test procedure must be selected for verification testing."
            )

        # Check temperature variation
        t_start = cleaned.get("temperature_start")
        t_end = cleaned.get("temperature_end")
        if t_start is not None and t_end is not None:
            diff = abs(t_end - t_start)
            if diff > 10:
                # Flag huge temperature swings
                self.add_error(
                    "temperature_end",
                    f"Temperature shift of {diff}°C during test exceeds standard lab stability limits."
                )
        return cleaned


# Backward-compatible alias
TestSessionForm = TestSessionWizardForm



class ProcedureSelectionForm(forms.ModelForm):
    """
    Dedicated form for adding and removing applicable test procedures
    on an existing test session.
    """

    class Meta:
        model = TestSession
        fields = [
            "proc_initial_examination",
            "proc_zero_setting",
            "proc_weighing",
            "proc_repeatability",
            "proc_eccentricity",
            "proc_discrimination",
            "proc_tare",
            "proc_influence_quantities",
        ]


class SessionRejectionForm(forms.Form):
    """Form for rejecting a session with a mandatory reason."""

    reason = forms.CharField(
        widget=forms.Textarea(attrs={"rows": 4, "class": "form-control"}),
        label="Rejection Reason & Required Remediation",
        help_text="Provide a detailed technical reason for rejection. Minimum 10 characters.",
        min_length=10,
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.helper = FormHelper()
        self.helper.form_tag = False
        self.helper.layout = Layout("reason")


class SessionApprovalForm(forms.Form):
    """Form for approving a session with optional technical verification notes."""

    comments = forms.CharField(
        widget=forms.Textarea(attrs={
            "rows": 3,
            "class": "form-control",
            "placeholder": "Enter optional technical approval notes, conformity verification remarks, or special conditions...",
        }),
        label="Reviewer Approval Notes (Optional)",
        required=False,
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.helper = FormHelper()
        self.helper.form_tag = False
        self.helper.layout = Layout("comments")


class SessionRevisionForm(forms.Form):
    """Form for initiating a controlled revision on an approved record."""

    revision_reason = forms.CharField(
        widget=forms.Textarea(attrs={
            "rows": 4,
            "class": "form-control",
            "placeholder": "Explain the change control justification, reference change order, or typographical correction required...",
        }),
        label="Change Control Justification",
        help_text="Mandatory reason for revising an approved record (minimum 15 characters).",
        min_length=15,
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.helper = FormHelper()
        self.helper.form_tag = False
        self.helper.layout = Layout("revision_reason")
