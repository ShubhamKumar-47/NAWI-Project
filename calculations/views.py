"""calculations/views.py – Views for viewing and recalculating OIML R 76 compliance results."""
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from apps.core.constants import AuditAction, UserRole
from apps.audit.utils import log_action
from apps.test_sessions.models import TestSession
from calculations.models import CalculationCompliance, CalculationProcedureType, CalculationRecord
from calculations.services.coordinator import SessionCalculationCoordinator


def _get_session_or_404(request, session_pk):
    """Retrieve TestSession scoped to the authenticated user's organization."""
    return get_object_or_404(
        TestSession.objects.select_related("instrument", "technician", "reviewer"),
        pk=session_pk,
        organization=request.user.organization,
    )


@login_required
def session_calculation_results(request, session_pk):
    """
    Calculation Results Page.
    Displays:
    - Reference load
    - Indicated reading
    - Calculated error
    - Applicable permissible error (MPE)
    - Comparison result
    - PASS / FAIL / NOT EVALUATED badge
    - Step-by-step mathematical and regulatory explanation
    """
    session = _get_session_or_404(request, session_pk)

    # Automatically generate calculation records if none exist yet and measurements exist
    records = CalculationRecord.objects.filter(session=session)
    if not records.exists() and (
        session.weighing_measurements.exists()
        or session.repeatability_measurements.exists()
        or session.eccentricity_measurements.exists()
        or session.discrimination_measurements.exists()
        or session.tare_measurements.exists()
        or session.zero_setting_measurements.exists()
    ):
        SessionCalculationCoordinator.evaluate_session(session, calculated_by=request.user)
        records = CalculationRecord.objects.filter(session=session)

    # Group records by procedure type
    grouped_records = {}
    for proc_choice in CalculationProcedureType.choices:
        proc_code, proc_label = proc_choice
        proc_recs = records.filter(procedure_type=proc_code)
        if proc_recs.exists():
            grouped_records[proc_label] = proc_recs

    # Summary statistics
    total_count = records.count()
    pass_count = records.filter(comparison_result=CalculationCompliance.PASS).count()
    fail_count = records.filter(comparison_result=CalculationCompliance.FAIL).count()
    not_eval_count = records.filter(comparison_result=CalculationCompliance.NOT_EVALUATED).count()

    can_recalculate = (
        not session.is_locked
        and session.status != "APPROVED"
        and (request.user.is_superuser or request.user.is_administrator or request.user.is_operator)
    )

    return render(request, "calculations/calculation_results.html", {
        "session": session,
        "instrument": session.instrument,
        "records": records,
        "grouped_records": grouped_records,
        "total_count": total_count,
        "pass_count": pass_count,
        "fail_count": fail_count,
        "not_eval_count": not_eval_count,
        "can_recalculate": can_recalculate,
    })


@login_required
@require_POST
def session_recalculate(request, session_pk):
    """Re-run the calculation engine across all session observations."""
    session = _get_session_or_404(request, session_pk)

    if session.is_locked or session.status == "APPROVED":
        messages.error(request, "Cannot recalculate an approved or locked test session.")
        return redirect("calculations:session_results", session_pk=session_pk)

    try:
        records = SessionCalculationCoordinator.evaluate_session(session, calculated_by=request.user)
        log_action(
            user=request.user,
            action=AuditAction.UPDATE,
            obj=session,
            description=f"Recalculated OIML R 76 compliance engine for session {session.session_number} ({len(records)} points evaluated).",
            request=request,
        )
        messages.success(request, f"Calculation engine successfully evaluated {len(records)} test observations.")
    except Exception as exc:
        messages.error(request, f"Calculation engine error: {exc}")

    return redirect("calculations:session_results", session_pk=session_pk)
