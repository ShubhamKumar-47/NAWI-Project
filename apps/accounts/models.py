"""apps/accounts/models.py — Custom user, organization, and profile models."""
import uuid
from django.db import models
from django.contrib.auth.models import AbstractUser
from apps.core.constants import UserRole


class Organization(models.Model):
    """
    Represents a laboratory or testing organization.
    All data is scoped under an Organization for multi-tenancy.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255)
    accreditation_number = models.CharField(max_length=100, blank=True)
    address = models.TextField(blank=True)
    phone = models.CharField(max_length=30, blank=True)
    email = models.EmailField(blank=True)
    website = models.URLField(blank=True)
    logo = models.ImageField(upload_to="org_logos/", null=True, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]
        verbose_name = "Organization"
        verbose_name_plural = "Organizations"

    def __str__(self):
        return self.name


class CustomUser(AbstractUser):
    """
    Extended user model with role-based access control and organization membership.
    Email is used as the primary identifier (username kept for Django compat).
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    email = models.EmailField(unique=True)
    role = models.CharField(
        max_length=20,
        choices=UserRole.choices,
        default=UserRole.VIEWER,
    )
    organization = models.ForeignKey(
        Organization,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="users",
    )
    job_title = models.CharField(max_length=120, blank=True)
    phone = models.CharField(max_length=30, blank=True)
    signature_image = models.ImageField(
        upload_to="signatures/", null=True, blank=True,
        help_text="Digital signature image used in test reports."
    )
    must_change_password = models.BooleanField(
        default=True,
        help_text="Force password change on first login."
    )

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["username", "first_name", "last_name"]

    class Meta:
        ordering = ["last_name", "first_name"]
        verbose_name = "User"
        verbose_name_plural = "Users"

    def __str__(self):
        return f"{self.get_full_name()} ({self.email})"

    @property
    def full_name(self):
        return self.get_full_name() or self.email

    # ─── Role convenience properties ─────────────────────────────────────────
    @property
    def is_administrator(self):
        """Administrator: manages all users, instrument records, system settings, views all reports."""
        return self.role in [UserRole.ADMINISTRATOR, UserRole.SUPERADMIN] or self.is_superuser

    @property
    def is_operator(self):
        """Laboratory Operator: registers instruments, creates sessions, enters observations."""
        return self.role in [UserRole.LAB_OPERATOR, UserRole.TECHNICIAN]

    @property
    def is_reviewer(self):
        """Reviewer / Approver: reviews observations, verifies calculations, approves/rejects reports."""
        return self.role in [UserRole.REVIEWER]

    @property
    def is_superadmin(self):
        return self.is_administrator

    @property
    def is_lab_manager(self):
        return self.role in [UserRole.LAB_MANAGER, UserRole.ADMINISTRATOR, UserRole.SUPERADMIN]

    @property
    def is_technician(self):
        return self.is_operator

    @property
    def can_manage_users(self):
        return self.is_administrator or self.role == UserRole.LAB_MANAGER

    @property
    def can_edit_measurements(self):
        """Returns True if the user is allowed to enter measurement data."""
        return self.is_administrator or self.role == UserRole.LAB_MANAGER or self.is_operator

    @property
    def can_approve_sessions(self):
        """Returns True if the user is allowed to approve/reject sessions."""
        return self.is_administrator or self.role == UserRole.LAB_MANAGER or self.is_reviewer

    @property
    def can_generate_reports(self):
        """Returns True if the user is allowed to generate reports."""
        return True
