"""apps/core/mixins.py — Reusable CBV mixins for permission enforcement."""
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from django.contrib import messages
from django.shortcuts import redirect
from apps.core.constants import UserRole


class RoleRequiredMixin(LoginRequiredMixin):
    """
    CBV mixin that restricts access to users with one of the allowed roles.
    Usage:
        class MyView(RoleRequiredMixin, View):
            allowed_roles = [UserRole.TECHNICIAN, UserRole.LAB_MANAGER]
    """
    allowed_roles = []

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()
        if (
            self.allowed_roles
            and request.user.role not in self.allowed_roles
            and not request.user.is_superuser
            and not (request.user.role == UserRole.ADMINISTRATOR)
        ):
            raise PermissionDenied("You do not have permission to access this page.")
        return super().dispatch(request, *args, **kwargs)


class OrganizationQuerysetMixin:
    """
    Mixin for ListView/DetailView that filters the queryset to only return
    objects belonging to the current user's organization.
    Expects the model to have an `organization` FK field.
    """
    def get_queryset(self):
        qs = super().get_queryset()
        if request_user := getattr(self.request, "user", None):
            if request_user.is_superuser or request_user.role in [UserRole.ADMINISTRATOR, UserRole.SUPERADMIN]:
                return qs
            if hasattr(request_user, "organization") and request_user.organization:
                return qs.filter(organization=request_user.organization)
        return qs.none()


class LockedSessionMixin:
    """
    Mixin that prevents modifications to approved/locked test sessions.
    Apply to any view that modifies measurement data.
    """
    def dispatch(self, request, *args, **kwargs):
        obj = self.get_object()
        session = getattr(obj, "session", obj)  # handle both session and child objects
        if getattr(session, "is_locked", False):
            messages.error(request, "This session is locked and cannot be modified.")
            return redirect("test_sessions:detail", pk=session.pk)
        return super().dispatch(request, *args, **kwargs)


class AdministratorRequiredMixin(RoleRequiredMixin):
    """Restricts access to Administrators and Superusers."""
    allowed_roles = [UserRole.ADMINISTRATOR, UserRole.SUPERADMIN]


class SuperAdminRequiredMixin(AdministratorRequiredMixin):
    pass


class LabManagerRequiredMixin(RoleRequiredMixin):
    allowed_roles = [UserRole.ADMINISTRATOR, UserRole.SUPERADMIN, UserRole.LAB_MANAGER]


class LabOperatorRequiredMixin(RoleRequiredMixin):
    """Restricts access to Laboratory Operators, Technicians, Managers, and Admins."""
    allowed_roles = [
        UserRole.ADMINISTRATOR,
        UserRole.SUPERADMIN,
        UserRole.LAB_MANAGER,
        UserRole.LAB_OPERATOR,
        UserRole.TECHNICIAN,
    ]


class TechnicianRequiredMixin(LabOperatorRequiredMixin):
    pass


class ReviewerRequiredMixin(RoleRequiredMixin):
    """Restricts access to Reviewers/Approvers, Managers, and Admins."""
    allowed_roles = [
        UserRole.ADMINISTRATOR,
        UserRole.SUPERADMIN,
        UserRole.LAB_MANAGER,
        UserRole.REVIEWER,
    ]


class LabStaffRequiredMixin(RoleRequiredMixin):
    """Allows all active laboratory roles: Administrator, Operator, and Reviewer."""
    allowed_roles = [
        UserRole.ADMINISTRATOR,
        UserRole.SUPERADMIN,
        UserRole.LAB_MANAGER,
        UserRole.LAB_OPERATOR,
        UserRole.TECHNICIAN,
        UserRole.REVIEWER,
    ]
