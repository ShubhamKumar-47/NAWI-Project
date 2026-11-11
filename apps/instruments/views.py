"""apps/instruments/views.py – Instrument registry CRUD, search, filter, and history views."""
from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.db import models
from django.shortcuts import redirect, get_object_or_404
from django.urls import reverse_lazy, reverse
from django.views.generic import (
    ListView,
    DetailView,
    CreateView,
    UpdateView,
    DeleteView,
)

from apps.core.mixins import (
    LabStaffRequiredMixin,
    LabOperatorRequiredMixin,
    AdministratorRequiredMixin,
    OrganizationQuerysetMixin,
)
from apps.audit.utils import log_action
from apps.core.constants import AuditAction, AccuracyClass, InstrumentStatus, SessionStatus
from .models import Instrument, CommonInstrumentType
from .forms import InstrumentForm


class InstrumentListView(LabStaffRequiredMixin, OrganizationQuerysetMixin, ListView):
    """
    Displays a paginated, searchable, and filterable list of weighing instruments
    scoped to the current user's organisation.
    """

    model = Instrument
    template_name = "instruments/instrument_list.html"
    context_object_name = "instruments"
    paginate_by = 12

    def get_queryset(self):
        qs = (
            super()
            .get_queryset()
            .filter(is_deleted=False)
            .select_related("organization", "created_by")
            .annotate(test_session_count=models.Count("test_sessions"))
            .order_by("-created_at")
        )

        # ── Search (Serial number, name, manufacturer, model, client, lab reference) ──
        q = self.request.GET.get("q", "").strip()
        if q:
            qs = qs.filter(
                models.Q(serial_number__icontains=q)
                | models.Q(instrument_name__icontains=q)
                | models.Q(manufacturer__icontains=q)
                | models.Q(model_name__icontains=q)
                | models.Q(model_number__icontains=q)
                | models.Q(customer_name__icontains=q)
                | models.Q(lab_reference_number__icontains=q)
            )

        # ── Filter by Manufacturer ──
        manufacturer = self.request.GET.get("manufacturer", "").strip()
        if manufacturer:
            qs = qs.filter(manufacturer__iexact=manufacturer)

        # ── Filter by Accuracy Class ──
        accuracy_class = self.request.GET.get("accuracy_class", "").strip()
        if accuracy_class:
            qs = qs.filter(accuracy_class=accuracy_class)

        # ── Filter by Status ──
        status = self.request.GET.get("status", "").strip()
        if status:
            qs = qs.filter(status=status)

        # ── Filter by Instrument Type ──
        instrument_type = self.request.GET.get("instrument_type", "").strip()
        if instrument_type:
            qs = qs.filter(instrument_type__icontains=instrument_type)

        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        base_qs = super().get_queryset().filter(is_deleted=False)

        # Distinct manufacturers in this organization for filter dropdown
        manufacturers = (
            base_qs.exclude(manufacturer="")
            .values_list("manufacturer", flat=True)
            .distinct()
            .order_by("manufacturer")
        )

        # Filter parameter values
        ctx["search_query"] = self.request.GET.get("q", "").strip()
        ctx["current_manufacturer"] = self.request.GET.get("manufacturer", "").strip()
        ctx["current_class"] = self.request.GET.get("accuracy_class", "").strip()
        ctx["current_status"] = self.request.GET.get("status", "").strip()
        ctx["current_type"] = self.request.GET.get("instrument_type", "").strip()

        ctx["available_manufacturers"] = list(manufacturers)
        ctx["accuracy_classes"] = AccuracyClass.choices
        ctx["status_choices"] = InstrumentStatus.choices
        ctx["instrument_types"] = CommonInstrumentType.choices

        # Quick stats for header metric pills
        ctx["total_count"] = base_qs.count()
        ctx["in_lab_count"] = base_qs.filter(status=InstrumentStatus.IN_LAB).count()
        ctx["in_progress_count"] = base_qs.filter(status=InstrumentStatus.IN_PROGRESS).count()
        ctx["tested_count"] = base_qs.filter(status=InstrumentStatus.TESTED).count()

        # Build clean query string for pagination links (excluding &page=)
        params = self.request.GET.copy()
        params.pop("page", None)
        ctx["query_string"] = params.urlencode()
        ctx["is_filtered"] = bool(params)

        return ctx


class InstrumentDetailView(LabStaffRequiredMixin, OrganizationQuerysetMixin, DetailView):
    """
    Displays complete instrument details, metrological characteristics,
    and associated test records & audit history.
    """

    model = Instrument
    template_name = "instruments/instrument_detail.html"
    context_object_name = "instrument"

    def get_queryset(self):
        return (
            super()
            .get_queryset()
            .filter(is_deleted=False)
            .select_related("organization", "created_by")
        )

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        instrument = self.object

        # Associated test sessions and history
        test_sessions = (
            instrument.test_sessions.select_related("technician", "reviewer", "organization")
            .order_by("-test_date", "-created_at")
        )

        ctx["test_sessions"] = test_sessions
        ctx["total_sessions"] = test_sessions.count()
        ctx["approved_sessions_count"] = test_sessions.filter(status=SessionStatus.APPROVED).count()
        ctx["pending_sessions_count"] = test_sessions.filter(status=SessionStatus.PENDING_REVIEW).count()
        ctx["has_approved_tests"] = instrument.has_approved_tests

        # Permission helper for delete button in template
        user = self.request.user
        ctx["can_delete_instrument"] = (
            user.is_superuser or user.is_administrator
        )
        ctx["can_edit_instrument"] = (
            user.is_superuser or user.is_administrator or user.is_operator
        )

        return ctx


class InstrumentCreateView(LabOperatorRequiredMixin, CreateView):
    """Register a new weighing instrument under the user's organisation."""

    model = Instrument
    form_class = InstrumentForm
    template_name = "instruments/instrument_form.html"
    success_url = reverse_lazy("instruments:list")

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["organization"] = self.request.user.organization
        return kwargs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["is_create"] = True
        return ctx

    def form_valid(self, form):
        form.instance.organization = self.request.user.organization
        form.instance.created_by = self.request.user
        response = super().form_valid(form)

        log_action(
            user=self.request.user,
            action=AuditAction.CREATE,
            obj=self.object,
            description=f"Registered instrument: {self.object.display_name} (S/N: {self.object.serial_number})",
            request=self.request,
        )
        messages.success(
            self.request,
            f"Instrument '{self.object.display_name}' (S/N: {self.object.serial_number}) registered successfully."
        )
        return response


class InstrumentUpdateView(LabOperatorRequiredMixin, OrganizationQuerysetMixin, UpdateView):
    """Edit an existing instrument record."""

    model = Instrument
    form_class = InstrumentForm
    template_name = "instruments/instrument_form.html"

    def get_queryset(self):
        return super().get_queryset().filter(is_deleted=False)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["organization"] = self.request.user.organization
        return kwargs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["is_create"] = False
        return ctx

    def get_success_url(self):
        return reverse("instruments:detail", kwargs={"pk": self.object.pk})

    def form_valid(self, form):
        response = super().form_valid(form)
        log_action(
            user=self.request.user,
            action=AuditAction.UPDATE,
            obj=self.object,
            description=f"Updated instrument: {self.object.display_name} (S/N: {self.object.serial_number})",
            request=self.request,
        )
        messages.success(
            self.request,
            f"Instrument '{self.object.display_name}' updated successfully."
        )
        return response


class InstrumentDeleteView(AdministratorRequiredMixin, OrganizationQuerysetMixin, DeleteView):
    """
    Safely delete (soft-delete) an instrument record.
    Enforces authorization: Only Administrators can delete instruments.
    Prevents deletion if certified approved test sessions exist.
    """

    model = Instrument
    template_name = "instruments/instrument_confirm_delete.html"
    context_object_name = "instrument"
    success_url = reverse_lazy("instruments:list")

    def get_queryset(self):
        return super().get_queryset().filter(is_deleted=False)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        instrument = self.object
        associated_sessions = instrument.test_sessions.all()

        ctx["associated_sessions"] = associated_sessions
        ctx["has_approved_sessions"] = associated_sessions.filter(status=SessionStatus.APPROVED).exists()
        ctx["total_sessions"] = associated_sessions.count()
        return ctx

    def post(self, request, *args, **kwargs):
        self.object = self.get_object()

        # Check for certified/approved test records: prevent deletion
        if self.object.has_approved_tests:
            messages.error(
                request,
                f"Cannot delete instrument '{self.object.display_name}': it has certified approved "
                f"OIML R 76 test records that must be retained for metrological audit compliance."
            )
            return redirect("instruments:detail", pk=self.object.pk)

        # Perform soft-delete
        obj_name = str(self.object)
        self.object.soft_delete(user=request.user)

        log_action(
            user=request.user,
            action=AuditAction.DELETE,
            obj=self.object,
            description=f"Soft-deleted instrument: {obj_name}",
            request=request,
        )
        messages.success(request, f"Instrument '{obj_name}' was successfully removed from active registry.")
        return redirect(self.success_url)
