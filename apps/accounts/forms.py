"""apps/accounts/forms.py — Authentication and user management forms."""
from django import forms
from django.contrib.auth.forms import (
    AuthenticationForm,
    UserCreationForm,
    PasswordChangeForm,
    PasswordResetForm,
    SetPasswordForm,
)
from django.core.exceptions import ValidationError
from crispy_forms.helper import FormHelper
from crispy_forms.layout import Layout, Row, Column, Submit, HTML
from .models import CustomUser, Organization
from apps.core.constants import UserRole


class LoginForm(AuthenticationForm):
    """Custom login form using email as the username field with Bootstrap 5 styling."""
    username = forms.EmailField(
        label="Email Address",
        widget=forms.EmailInput(
            attrs={
                "class": "form-control form-control-lg",
                "autofocus": True,
                "placeholder": "name@metrology-lab.com",
            }
        ),
    )
    password = forms.CharField(
        label="Password",
        widget=forms.PasswordInput(
            attrs={
                "class": "form-control form-control-lg",
                "placeholder": "••••••••••••",
            }
        ),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.helper = FormHelper()
        self.helper.form_id = "login-form"
        self.helper.layout = Layout(
            "username",
            "password",
            HTML(
                '<div class="d-flex justify-content-between align-items-center mb-3">'
                '  <div class="form-check">'
                '    <input class="form-check-input" type="checkbox" id="rememberMe">'
                '    <label class="form-check-label small text-muted" for="rememberMe">Remember me</label>'
                '  </div>'
                '  <a href="/accounts/password/reset/" class="small text-decoration-none">Forgot password?</a>'
                '</div>'
            ),
            Submit("submit", "Sign In", css_class="btn btn-primary btn-lg w-100 shadow-sm fw-semibold"),
        )


class UserCreateForm(UserCreationForm):
    """Form for creating new users (Administrator and Lab Manager only)."""

    class Meta:
        model = CustomUser
        fields = [
            "first_name",
            "last_name",
            "email",
            "username",
            "role",
            "organization",
            "job_title",
            "phone",
        ]
        widgets = {
            "role": forms.Select(attrs={"class": "form-select"}),
            "organization": forms.Select(attrs={"class": "form-select"}),
        }

    def __init__(self, *args, **kwargs):
        self.requesting_user = kwargs.pop("requesting_user", None)
        super().__init__(*args, **kwargs)

        # Scoping based on requester role
        if self.requesting_user and not self.requesting_user.is_administrator:
            # Lab managers can only assign users to their own organization
            if self.requesting_user.organization_id:
                self.fields["organization"].queryset = Organization.objects.filter(
                    pk=self.requesting_user.organization_id
                )
            # Lab managers cannot create Administrators
            self.fields["role"].choices = [
                c for c in UserRole.choices
                if c[0] not in [UserRole.ADMINISTRATOR, UserRole.SUPERADMIN]
            ]

        self.helper = FormHelper()
        self.helper.form_id = "user-create-form"
        self.helper.layout = Layout(
            Row(Column("first_name"), Column("last_name")),
            Row(Column("email"), Column("username")),
            Row(Column("role"), Column("organization")),
            Row(Column("job_title"), Column("phone")),
            Row(Column("password1"), Column("password2")),
            Submit("submit", "Create User", css_class="btn btn-primary mt-2"),
        )

    def save(self, commit=True):
        user = super().save(commit=False)
        user.must_change_password = True
        if commit:
            user.save()
        return user


class UserProfileForm(forms.ModelForm):
    """Form for users to update their own profile and signature."""

    class Meta:
        model = CustomUser
        fields = ["first_name", "last_name", "job_title", "phone", "signature_image"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.helper = FormHelper()
        self.helper.form_id = "profile-form"
        self.helper.layout = Layout(
            Row(Column("first_name"), Column("last_name")),
            Row(Column("job_title"), Column("phone")),
            "signature_image",
            Submit("submit", "Save Changes", css_class="btn btn-primary mt-3"),
        )


class OrganizationForm(forms.ModelForm):
    """Form for creating and editing organizations."""

    class Meta:
        model = Organization
        fields = ["name", "accreditation_number", "address", "phone", "email", "website", "logo"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.helper = FormHelper()
        self.helper.form_id = "org-form"
        self.helper.layout = Layout(
            "name",
            Row(Column("accreditation_number"), Column("phone")),
            Row(Column("email"), Column("website")),
            "address",
            "logo",
            Submit("submit", "Save Organization", css_class="btn btn-primary mt-3"),
        )


class CustomPasswordResetForm(PasswordResetForm):
    """Custom password reset form using Crispy Forms styling."""
    email = forms.EmailField(
        label="Email Address",
        widget=forms.EmailInput(
            attrs={"class": "form-control form-control-lg", "placeholder": "registered@laboratory.com"}
        ),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.helper = FormHelper()
        self.helper.layout = Layout(
            "email",
            Submit("submit", "Send Reset Link", css_class="btn btn-primary btn-lg w-100 mt-3"),
        )
