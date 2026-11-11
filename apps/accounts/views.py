"""apps/accounts/views.py — Authentication, password reset, and user management views."""
from django.contrib.auth import login, logout, update_session_auth_hash
from django.contrib.auth.forms import PasswordChangeForm, SetPasswordForm
from django.contrib.auth.views import (
    PasswordResetView,
    PasswordResetDoneView,
    PasswordResetConfirmView,
    PasswordResetCompleteView,
)
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.shortcuts import render, redirect, get_object_or_404
from django.views.generic import ListView, CreateView, UpdateView, DetailView
from django.urls import reverse_lazy

from apps.core.mixins import (
    AdministratorRequiredMixin,
    LabManagerRequiredMixin,
    SuperAdminRequiredMixin,
)
from apps.audit.utils import log_action
from apps.core.constants import AuditAction
from .models import CustomUser, Organization
from .forms import (
    LoginForm,
    UserCreateForm,
    UserProfileForm,
    OrganizationForm,
    CustomPasswordResetForm,
)


def login_view(request):
    """Custom login view using email-based LoginForm."""
    if request.user.is_authenticated:
        return redirect("dashboard:home")

    form = LoginForm(request, data=request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = form.get_user()
        login(request, user)
        log_action(
            user=user,
            action=AuditAction.LOGIN,
            description=f"User {user.email} signed in.",
            request=request,
        )
        if user.must_change_password:
            messages.warning(request, "You must change your password before continuing.")
            return redirect("accounts:password_change")
        messages.success(request, f"Welcome back, {user.first_name}!")
        return redirect(request.GET.get("next", "dashboard:home"))

    return render(request, "accounts/login.html", {"form": form})


def logout_view(request):
    """Logout view supporting both POST and GET with proper audit logging."""
    if request.user.is_authenticated:
        user = request.user
        log_action(
            user=user,
            action=AuditAction.LOGOUT,
            description=f"User {user.email} signed out.",
            request=request,
        )
        logout(request)
        messages.info(request, "You have been successfully signed out.")
    return redirect("accounts:login")


@login_required
def profile_view(request):
    """View and update own user profile."""
    form = UserProfileForm(request.POST or None, request.FILES or None, instance=request.user)
    if request.method == "POST" and form.is_valid():
        form.save()
        log_action(
            user=request.user,
            action=AuditAction.UPDATE,
            obj=request.user,
            description=f"User {request.user.email} updated profile.",
            request=request,
        )
        messages.success(request, "Profile updated successfully.")
        return redirect("accounts:profile")
    return render(request, "accounts/profile.html", {"form": form})


@login_required
def password_change_view(request):
    """Change password with session refresh to keep user logged in."""
    form = PasswordChangeForm(request.user, request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = form.save()
        user.must_change_password = False
        user.save(update_fields=["must_change_password"])
        update_session_auth_hash(request, user)
        log_action(
            user=user,
            action=AuditAction.UPDATE,
            obj=user,
            description=f"User {user.email} changed password.",
            request=request,
        )
        messages.success(request, "Password changed successfully.")
        return redirect("dashboard:home")
    return render(request, "accounts/password_change.html", {"form": form})


# ─── Password Reset Flow ───────────────────────────────────────────────────────

class CustomPasswordResetView(PasswordResetView):
    template_name = "accounts/password_reset_form.html"
    email_template_name = "accounts/password_reset_email.html"
    subject_template_name = "accounts/password_reset_subject.txt"
    form_class = CustomPasswordResetForm
    success_url = reverse_lazy("accounts:password_reset_done")


class CustomPasswordResetDoneView(PasswordResetDoneView):
    template_name = "accounts/password_reset_done.html"


class CustomPasswordResetConfirmView(PasswordResetConfirmView):
    template_name = "accounts/password_reset_confirm.html"
    success_url = reverse_lazy("accounts:password_reset_complete")


class CustomPasswordResetCompleteView(PasswordResetCompleteView):
    template_name = "accounts/password_reset_complete.html"


# ─── User Management (Administrator & Lab Manager) ───────────────────────────

class UserListView(LabManagerRequiredMixin, ListView):
    model = CustomUser
    template_name = "accounts/user_list.html"
    context_object_name = "users"
    paginate_by = 25

    def get_queryset(self):
        qs = super().get_queryset()
        if not self.request.user.is_administrator:
            qs = qs.filter(organization=self.request.user.organization)
        return qs.select_related("organization").order_by("last_name")


class UserCreateView(LabManagerRequiredMixin, CreateView):
    model = CustomUser
    form_class = UserCreateForm
    template_name = "accounts/user_form.html"
    success_url = reverse_lazy("accounts:user_list")

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["requesting_user"] = self.request.user
        return kwargs

    def form_valid(self, form):
        response = super().form_valid(form)
        log_action(
            user=self.request.user,
            action=AuditAction.CREATE,
            obj=self.object,
            description=f"Created user account for {self.object.email} (Role: {self.object.get_role_display()}).",
            request=self.request,
        )
        messages.success(self.request, f"User '{form.instance.email}' created successfully.")
        return response


class UserDetailView(LabManagerRequiredMixin, DetailView):
    model = CustomUser
    template_name = "accounts/user_detail.html"
    context_object_name = "target_user"


# ─── Organization Management ──────────────────────────────────────────────────

class OrganizationListView(SuperAdminRequiredMixin, ListView):
    model = Organization
    template_name = "accounts/org_list.html"
    context_object_name = "organizations"


class OrganizationCreateView(SuperAdminRequiredMixin, CreateView):
    model = Organization
    form_class = OrganizationForm
    template_name = "accounts/org_form.html"
    success_url = reverse_lazy("accounts:org_list")

    def form_valid(self, form):
        response = super().form_valid(form)
        log_action(
            user=self.request.user,
            action=AuditAction.CREATE,
            obj=self.object,
            description=f"Created organization: {self.object.name}.",
            request=self.request,
        )
        messages.success(self.request, f"Organization '{form.instance.name}' created.")
        return response


class OrganizationUpdateView(SuperAdminRequiredMixin, UpdateView):
    model = Organization
    form_class = OrganizationForm
    template_name = "accounts/org_form.html"
    success_url = reverse_lazy("accounts:org_list")

    def form_valid(self, form):
        response = super().form_valid(form)
        log_action(
            user=self.request.user,
            action=AuditAction.UPDATE,
            obj=self.object,
            description=f"Updated organization: {self.object.name}.",
            request=self.request,
        )
        messages.success(self.request, f"Organization '{self.object.name}' updated.")
        return response


# ─── Security Pages ────────────────────────────────────────────────────────────

def lockout_view(request, *args, **kwargs):
    """Displayed when django-axes locks an account after failed login attempts."""
    return render(request, "accounts/lockout.html", status=403)


def unauthorized_view(request, *args, **kwargs):
    """Custom unauthorized access (403 Forbidden) page."""
    return render(request, "accounts/unauthorized.html", status=403)
