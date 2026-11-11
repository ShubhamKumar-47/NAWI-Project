"""apps/test_sessions/views.py – Test session lifecycle, wizard, procedure configuration, and review views."""
import datetime
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import models
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse_lazy, reverse
from django.views.generic import ListView, DetailView, CreateView, UpdateView, TemplateView

from apps.core.mixins import (
    TechnicianRequiredMixin,
    ReviewerRequiredMixin,
    LabOperatorRequiredMixin,
    LabStaffRequiredMixin,
    OrganizationQuerysetMixin,
    LockedSessionMixin,
)
from apps.audit.utils import log_action
from apps.core.constants import AuditAction, SessionStatus, UserRole
from apps.instruments.models import Instrument
from .models import TestSession, OIMLEdition, ApprovalHistory, ApprovalAction
from .forms import (
    TestSessionWizardForm,
    ProcedureSelectionForm,
    SessionRejectionForm,
    SessionApprovalForm,
    SessionRevisionForm,
)
from .services import SessionService
from .results_validation import ResultsValidationService


class TestSessionListView(LabStaffRequiredMixin, OrganizationQuerysetMixin, ListView):
    """
    Displays a paginated, searchable, and filterable list of test records
    scoped to the current user's organisation.
    """

    model = TestSession
    template_name = "test_sessions/session_list.html"
    context_object_name = "sessions"
    paginate_by = 12

    def get_queryset(self):
        qs = (
            super()
            .get_queryset()
            .select_related("instrument", "technician", "reviewer", "organization")
            .order_by("-test_date", "-created_at")
        )

        # ── Search (Test ID, S/N, Manufacturer, Model, Client, Lab ref, Operator) ──
        q = self.request.GET.get("q", "").strip()
        if q:
            qs = qs.filter(
                models.Q(session_number__icontains=q)
                | models.Q(lab_reference_number__icontains=q)
                | models.Q(instrument__serial_number__icontains=q)
                | models.Q(instrument__manufacturer__icontains=q)
                | models.Q(instrument__model_name__icontains=q)
                | models.Q(instrument__customer_name__icontains=q)
                | models.Q(technician__first_name__icontains=q)
                | models.Q(technician__last_name__icontains=q)
                | models.Q(technician__username__icontains=q)
            )

        # ── Filter by Status ──
        status_filter = self.request.GET.get("status", "").strip()
        if status_filter:
            qs = qs.filter(status=status_filter)

        # ── Filter by OIML Edition ──
        edition_filter = self.request.GET.get("oiml_edition", "").strip()
        if edition_filter:
            qs = qs.filter(oiml_edition=edition_filter)

        # ── Filter by Date Range ──
        date_from = self.request.GET.get("date_from", "").strip()
        if date_from:
            qs = qs.filter(test_date__gte=date_from)
        date_to = self.request.GET.get("date_to", "").strip()
        if date_to:
            qs = qs.filter(test_date__lte=date_to)

        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        base_qs = super().get_queryset()

        ctx["status_choices"] = SessionStatus.choices
        ctx["oiml_editions"] = OIMLEdition.choices
        ctx["current_status"] = self.request.GET.get("status", "").strip()
        ctx["current_edition"] = self.request.GET.get("oiml_edition", "").strip()
        ctx["search_query"] = self.request.GET.get("q", "").strip()
        ctx["date_from"] = self.request.GET.get("date_from", "").strip()
        ctx["date_to"] = self.request.GET.get("date_to", "").strip()

        # Summary statistics
        ctx["total_sessions"] = base_qs.count()
        ctx["draft_count"] = base_qs.filter(status=SessionStatus.DRAFT).count()
        ctx["in_progress_count"] = base_qs.filter(status=SessionStatus.IN_PROGRESS).count()
        ctx["pending_count"] = base_qs.filter(status=SessionStatus.PENDING_REVIEW).count()
        ctx["approved_count"] = base_qs.filter(status=SessionStatus.APPROVED).count()
        ctx["rejected_count"] = base_qs.filter(status=SessionStatus.REJECTED).count()

        # Build clean query string for pagination
        params = self.request.GET.copy()
        params.pop("page", None)
        ctx["query_string"] = params.urlencode()
        ctx["is_filtered"] = bool(params)

        return ctx


class TestSessionDetailView(LabStaffRequiredMixin, OrganizationQuerysetMixin, DetailView):
    """
    Displays full details of a test record, including linked instrument specs,
    environmental conditions, active test procedures, observations, and audit trail.
    """

    model = TestSession
    template_name = "test_sessions/session_detail.html"
    context_object_name = "session"

    def get_queryset(self):
        return super().get_queryset().select_related(
            "instrument", "technician", "reviewer", "organization"
        )

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        session = self.object

        ctx["rejection_form"] = SessionRejectionForm()
        ctx["selected_procedures"] = session.selected_procedures
        ctx["active_procedures_count"] = session.active_procedures_count

        # Permissions helpers
        user = self.request.user
        ctx["can_edit_session"] = (
            not session.is_locked
            and (user.is_superuser or user.is_administrator or user.is_operator)
        )
        ctx["can_submit_session"] = session.can_be_submitted and not session.is_locked
        ctx["can_approve_session"] = (
            session.can_be_approved
            and (user.is_superuser or user.can_approve_sessions)
        )

        return ctx


class TestSessionCreateView(LabOperatorRequiredMixin, CreateView):
    """
    Multi-step wizard view for creating a new test record.
    Supports saving incomplete tests as Drafts or proceeding directly to In Progress.
    """

    model = TestSession
    form_class = TestSessionWizardForm
    template_name = "test_sessions/session_form.html"

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["organization"] = self.request.user.organization
        kwargs["current_user"] = self.request.user

        inst_pk = self.request.GET.get("instrument")
        if inst_pk:
            kwargs["initial_instrument"] = inst_pk
        return kwargs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        # Pass JSON-serializable instrument data for dynamic wizard preview
        instruments = Instrument.objects.filter(
            organization=self.request.user.organization,
            is_deleted=False,
        ).order_by("manufacturer", "model_name")

        instrument_dict = {}
        for inst in instruments:
            instrument_dict[str(inst.pk)] = {
                "name": inst.display_name,
                "manufacturer": inst.manufacturer,
                "model": inst.model_name,
                "serial_number": inst.serial_number,
                "accuracy_class": inst.get_accuracy_class_display(),
                "max_capacity": str(inst.max_capacity),
                "min_capacity": str(inst.min_capacity),
                "scale_interval": str(inst.scale_interval),
                "actual_scale_interval": str(inst.actual_scale_interval),
                "n_max": str(inst.n_max or "—"),
                "unit": inst.unit_of_measurement,
                "customer_name": inst.customer_name or "—",
                "lab_reference_number": inst.lab_reference_number or "—",
            }
        ctx["instruments_json"] = instrument_dict
        ctx["is_create"] = True
        return ctx

    def form_valid(self, form):
        form.instance.organization = self.request.user.organization
        form.instance.created_by = self.request.user

        # Set status based on action intent
        action_intent = form.cleaned_data.get("action_intent", "in_progress")
        if action_intent == "draft":
            form.instance.status = SessionStatus.DRAFT
        else:
            form.instance.status = SessionStatus.IN_PROGRESS

        response = super().form_valid(form)

        log_action(
            user=self.request.user,
            action=AuditAction.CREATE,
            obj=self.object,
            description=f"Created test record {self.object.session_number} ({self.object.get_status_display()}).",
            request=self.request,
        )

        status_label = "draft" if form.instance.status == SessionStatus.DRAFT else "in progress"
        messages.success(
            self.request,
            f"Test record '{self.object.session_number}' created successfully as {status_label}."
        )
        return response

    def get_success_url(self):
        return reverse("test_sessions:detail", kwargs={"pk": self.object.pk})


class TestSessionUpdateView(LabOperatorRequiredMixin, OrganizationQuerysetMixin, UpdateView):
    """
    Edit an existing test record.
    Prevents unauthorized modification of locked or approved tests.
    """

    model = TestSession
    form_class = TestSessionWizardForm
    template_name = "test_sessions/session_form.html"

    def dispatch(self, request, *args, **kwargs):
        obj = self.get_object()
        if obj.is_locked:
            messages.error(
                request,
                "This test session has been approved and locked. Modifications are prohibited under OIML R 76 audit rules."
            )
            return redirect("test_sessions:detail", pk=obj.pk)
        return super().dispatch(request, *args, **kwargs)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["organization"] = self.request.user.organization
        kwargs["current_user"] = self.request.user
        return kwargs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["is_create"] = False
        ctx["session"] = self.object
        return ctx

    def form_valid(self, form):
        # Allow updating draft to in_progress
        action_intent = form.cleaned_data.get("action_intent")
        if action_intent == "in_progress" and form.instance.status == SessionStatus.DRAFT:
            form.instance.status = SessionStatus.IN_PROGRESS

        response = super().form_valid(form)
        log_action(
            user=self.request.user,
            action=AuditAction.UPDATE,
            obj=self.object,
            description=f"Updated test record {self.object.session_number}.",
            request=self.request,
        )
        messages.success(
            self.request,
            f"Test record '{self.object.session_number}' updated successfully."
        )
        return response

    def get_success_url(self):
        return reverse("test_sessions:detail", kwargs={"pk": self.object.pk})


class TestSessionProcedureConfigView(LabOperatorRequiredMixin, OrganizationQuerysetMixin, UpdateView):
    """
    Dedicated view to quickly add or remove applicable test procedures on an active test session.
    """

    model = TestSession
    form_class = ProcedureSelectionForm
    template_name = "test_sessions/session_procedure_config.html"

    def dispatch(self, request, *args, **kwargs):
        obj = self.get_object()
        if obj.is_locked:
            messages.error(request, "This session is locked and test procedures cannot be modified.")
            return redirect("test_sessions:detail", pk=obj.pk)
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        response = super().form_valid(form)
        log_action(
            user=self.request.user,
            action=AuditAction.UPDATE,
            obj=self.object,
            description=f"Updated test procedures for session {self.object.session_number}.",
            request=self.request,
        )
        messages.success(self.request, "Test procedures configuration updated.")
        return response

    def get_success_url(self):
        return reverse("test_sessions:detail", kwargs={"pk": self.object.pk})


@login_required
def submit_for_review(request, pk):
    """POST-only: submit a completed test session for technical reviewer verification."""
    session = get_object_or_404(TestSession, pk=pk, organization=request.user.organization)
    if request.method == "POST":
        comments = request.POST.get("comments", "").strip()
        try:
            SessionService.submit_for_review(session, request.user, request, comments=comments)
            messages.success(request, f"Test record '{session.session_number}' submitted for technical review.")
        except (ValidationError, PermissionDenied) as exc:
            messages.error(request, str(exc))
    return redirect("test_sessions:detail", pk=pk)


@login_required
def start_session_review(request, pk):
    """POST-only: reviewer commences active evaluation (moves to UNDER_REVIEW)."""
    session = get_object_or_404(TestSession, pk=pk, organization=request.user.organization)
    if not request.user.can_approve_sessions:
        raise PermissionDenied("You do not have permission to review test sessions.")
    if request.method == "POST":
        comments = request.POST.get("comments", "").strip()
        try:
            SessionService.start_review(session, request.user, request, comments=comments)
            messages.info(request, f"Review commenced for test record '{session.session_number}'. Status set to Under Review.")
        except (ValidationError, PermissionDenied) as exc:
            messages.error(request, str(exc))
    return redirect("test_sessions:review", pk=pk)


@login_required
def approve_session(request, pk):
    """POST-only: approve a session, verify compliance, and lock permanently."""
    session = get_object_or_404(TestSession, pk=pk, organization=request.user.organization)
    if not request.user.can_approve_sessions:
        raise PermissionDenied("You do not have permission to approve test sessions.")
    if request.method == "POST":
        form = SessionApprovalForm(request.POST)
        comments = form.cleaned_data.get("comments", "") if form.is_valid() else request.POST.get("comments", "")
        try:
            SessionService.approve(session, request.user, comments=comments, request=request)
            messages.success(
                request,
                f"Test record '{session.session_number}' approved and metrologically certified. Record is locked."
            )
        except (ValidationError, PermissionDenied) as exc:
            messages.error(request, str(exc))
    return redirect("test_sessions:detail", pk=pk)


@login_required
def reject_session(request, pk):
    """POST-only: reject a test session with a mandatory technical remediation reason."""
    session = get_object_or_404(TestSession, pk=pk, organization=request.user.organization)
    if not request.user.can_approve_sessions:
        raise PermissionDenied("You do not have permission to reject test sessions.")
    if request.method == "POST":
        form = SessionRejectionForm(request.POST)
        if form.is_valid():
            try:
                SessionService.reject(
                    session,
                    request.user,
                    form.cleaned_data["reason"],
                    request,
                )
                messages.warning(request, f"Test record '{session.session_number}' returned to operator for remediation.")
            except (ValidationError, PermissionDenied) as exc:
                messages.error(request, str(exc))
        else:
            messages.error(request, "Please provide a valid technical rejection reason (minimum 10 characters).")
    return redirect("test_sessions:detail", pk=pk)


@login_required
def initiate_session_revision(request, pk):
    """
    POST-only: controlled revision process for approved records.
    Requires reviewer or administrator privileges and mandatory change-control justification.
    """
    session = get_object_or_404(TestSession, pk=pk, organization=request.user.organization)
    if not request.user.can_approve_sessions:
        raise PermissionDenied("Only authorized reviewers or administrators can initiate a controlled revision.")
    if request.method == "POST":
        form = SessionRevisionForm(request.POST)
        if form.is_valid():
            try:
                SessionService.initiate_revision(
                    session,
                    request.user,
                    form.cleaned_data["revision_reason"],
                    request,
                )
                messages.warning(
                    request,
                    f"Controlled Revision #{session.revision_number} initiated for '{session.session_number}'. "
                    "Record unlocked for technical correction."
                )
            except (ValidationError, PermissionDenied) as exc:
                messages.error(request, str(exc))
        else:
            messages.error(request, "A formal change control justification is required (minimum 15 characters).")
    return redirect("test_sessions:review", pk=pk)


# ─────────────────────────────────────────────────────────────────────────────
# Test Results and Validation Module Views
# ─────────────────────────────────────────────────────────────────────────────

from .results_validation import ResultsValidationService
from calculations.services.coordinator import SessionCalculationCoordinator


class TestSessionResultsView(LabStaffRequiredMixin, OrganizationQuerysetMixin, DetailView):
    """
    Detailed laboratory results and validation interface.
    Presents test-wise result summaries, calculated error tables, MPE limits,
    pass/fail/unevaluated statuses, missing data warnings, and draft correction tools.
    """
    model = TestSession
    template_name = "test_sessions/session_results.html"
    context_object_name = "session"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        session = self.object
        report = ResultsValidationService.validate_session(session)
        user = self.request.user

        ctx["instrument"] = session.instrument
        ctx["report"] = report
        ctx["can_edit"] = (
            not session.is_locked
            and session.status != SessionStatus.APPROVED
            and (user.is_superuser or user.is_administrator or user.is_operator)
        )
        ctx["can_submit"] = (
            report.is_submittable
            and not session.is_locked
            and session.status in [SessionStatus.DRAFT, SessionStatus.IN_PROGRESS, SessionStatus.REJECTED]
            and (user.is_superuser or user.is_administrator or user.is_operator)
        )
        ctx["can_recalculate"] = (
            not session.is_locked
            and session.status != SessionStatus.APPROVED
            and (user.is_superuser or user.is_administrator or user.is_operator)
        )
        ctx["can_validate_drafts"] = (
            report.total_drafts > 0
            and not session.is_locked
            and (user.is_superuser or user.is_administrator or user.is_operator)
        )
        return ctx


class TestSessionResultsPrintView(LabStaffRequiredMixin, OrganizationQuerysetMixin, DetailView):
    """
    Print-friendly laboratory test results report conforming to metrology standards.
    Features optimized print layout, ISO 17025 compliant headers, and signature lines.
    """
    model = TestSession
    template_name = "test_sessions/session_results_print.html"
    context_object_name = "session"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        session = self.object
        report = ResultsValidationService.validate_session(session)
        ctx["instrument"] = session.instrument
        ctx["report"] = report
        return ctx


@login_required
def validate_session_drafts(request, pk):
    """
    Operator action: Convert all draft observations in the session into confirmed observations
    and re-evaluate the calculation engine.
    """
    session = get_object_or_404(TestSession, pk=pk, organization=request.user.organization)
    if session.is_locked or session.status == SessionStatus.APPROVED:
        messages.error(request, "Cannot modify observations in an approved or locked session.")
        return redirect("test_sessions:results", pk=pk)

    if request.method == "POST":
        # Confirm all draft measurements across all 6 models
        w_count = session.weighing_measurements.filter(is_draft=True).update(is_draft=False)
        r_count = session.repeatability_measurements.filter(is_draft=True).update(is_draft=False)
        e_count = session.eccentricity_measurements.filter(is_draft=True).update(is_draft=False)
        d_count = session.discrimination_measurements.filter(is_draft=True).update(is_draft=False)
        t_count = session.tare_measurements.filter(is_draft=True).update(is_draft=False)
        z_count = session.zero_setting_measurements.filter(is_draft=True).update(is_draft=False)

        total_confirmed = w_count + r_count + e_count + d_count + t_count + z_count

        # Recalculate results
        SessionCalculationCoordinator.evaluate_session(session, calculated_by=request.user)

        log_action(
            user=request.user,
            action=AuditAction.UPDATE,
            obj=session,
            description=f"Confirmed {total_confirmed} draft observation(s) on session {session.session_number}.",
            request=request,
        )
        messages.success(request, f"Successfully confirmed {total_confirmed} draft observation(s) and re-evaluated calculations.")

    return redirect("test_sessions:results", pk=pk)


# ─────────────────────────────────────────────────────────────────────────────
# Test Review & Approval Workflow Views
# ─────────────────────────────────────────────────────────────────────────────

class ReviewerDashboardView(ReviewerRequiredMixin, TemplateView):
    """
    Reviewer Dashboard showing pending approvals, approved tests, and rejected tests
    with KPI summary cards, quick filters, and direct links to the review console.
    """
    template_name = "test_sessions/reviewer_dashboard.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        user = self.request.user
        org = user.organization

        if user.is_administrator or user.is_superuser:
            qs = TestSession.objects.all().select_related("instrument", "technician", "reviewer", "organization")
        else:
            qs = TestSession.objects.filter(organization=org).select_related(
                "instrument", "technician", "reviewer", "organization"
            )

        # Search filter
        q = self.request.GET.get("q", "").strip()
        if q:
            qs = qs.filter(
                models.Q(session_number__icontains=q)
                | models.Q(lab_reference_number__icontains=q)
                | models.Q(instrument__serial_number__icontains=q)
                | models.Q(instrument__instrument_name__icontains=q)
                | models.Q(instrument__manufacturer__icontains=q)
                | models.Q(technician__first_name__icontains=q)
                | models.Q(technician__last_name__icontains=q)
                | models.Q(technician__username__icontains=q)
            )

        # Date range filter
        date_from = self.request.GET.get("date_from", "").strip()
        date_to = self.request.GET.get("date_to", "").strip()
        if date_from:
            try:
                qs = qs.filter(test_date__gte=datetime.date.fromisoformat(date_from))
            except ValueError:
                pass
        if date_to:
            try:
                qs = qs.filter(test_date__lte=datetime.date.fromisoformat(date_to))
            except ValueError:
                pass

        # Split into status streams
        pending_statuses = [SessionStatus.SUBMITTED, SessionStatus.PENDING_REVIEW, SessionStatus.UNDER_REVIEW]
        approved_statuses = [SessionStatus.APPROVED, SessionStatus.REPORT_GENERATED]
        rejected_statuses = [SessionStatus.REJECTED]

        pending_sessions = qs.filter(status__in=pending_statuses).order_by("-submitted_at", "-created_at")
        approved_sessions = qs.filter(status__in=approved_statuses).order_by("-approved_at", "-updated_at")
        rejected_sessions = qs.filter(status__in=rejected_statuses).order_by("-rejected_at", "-updated_at")

        active_tab = self.request.GET.get("tab", "pending").lower()
        if active_tab not in ["pending", "approved", "rejected"]:
            active_tab = "pending"

        ctx["pending_sessions"] = pending_sessions
        ctx["approved_sessions"] = approved_sessions
        ctx["rejected_sessions"] = rejected_sessions

        ctx["pending_count"] = pending_sessions.count()
        ctx["under_review_count"] = qs.filter(status=SessionStatus.UNDER_REVIEW).count()
        ctx["approved_count"] = approved_sessions.count()
        ctx["rejected_count"] = rejected_sessions.count()
        ctx["total_count"] = qs.count()

        ctx["active_tab"] = active_tab
        ctx["q"] = q
        ctx["date_from"] = date_from
        ctx["date_to"] = date_to
        return ctx


class TestSessionReviewView(ReviewerRequiredMixin, DetailView):
    """
    Comprehensive Review & Inspection Console for Authorized Reviewers and Approvers.
    Inspects:
    1. Instrument identification and metrological parameters (Max, Min, e, d, Class)
    2. Applicable test procedures and completeness status
    3. Original observations & turning-point measurements
    4. Automated calculations and error evaluation
    5. OIML R 76 acceptance criteria & MPE tolerances
    6. Exceptions, draft warnings, and missing data warnings
    7. Full immutable Approval History ledger
    8. Review controls: Start Review, Approve, Reject, Revise, Generate Report
    """
    model = TestSession
    template_name = "test_sessions/session_review.html"
    context_object_name = "session"

    def get_queryset(self):
        user = self.request.user
        if user.is_administrator or user.is_superuser:
            return TestSession.objects.all().select_related("instrument", "technician", "reviewer", "organization")
        return TestSession.objects.filter(organization=user.organization).select_related(
            "instrument", "technician", "reviewer", "organization"
        )

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        session = self.object
        report = ResultsValidationService.validate_session(session)

        ctx["instrument"] = session.instrument
        ctx["report"] = report
        ctx["summaries"] = report.procedure_summaries
        ctx["approval_history"] = session.approval_history.select_related("actor").order_by("-created_at")

        ctx["approval_form"] = SessionApprovalForm()
        ctx["rejection_form"] = SessionRejectionForm(initial={"reason": session.rejection_reason})
        ctx["revision_form"] = SessionRevisionForm()

        ctx["can_start_review"] = session.can_be_reviewed
        ctx["can_approve"] = session.can_be_approved and report.is_pass_eligible
        ctx["can_reject"] = session.can_be_approved
        ctx["can_revise"] = session.can_be_revised
        ctx["can_generate_report"] = session.status in [SessionStatus.APPROVED, SessionStatus.REPORT_GENERATED]
        return ctx
