"""apps/dashboard/views.py – Comprehensive laboratory analytics dashboard."""
import json
import datetime
from django.shortcuts import render
from django.utils import timezone
from django.db.models import Count, Q
from django.db.models.functions import TruncMonth

from apps.core.constants import SessionStatus, AccuracyClass
from apps.instruments.models import Instrument
from apps.test_sessions.models import TestSession
from apps.reports.models import GeneratedReport


def home(request):
    """
    Main project homepage:
    - If user is not authenticated: displays public NTRMS landing page.
    - If user is authenticated: displays the full laboratory dashboard with
      actual ORM queries, KPI metric cards, filters, and Chart.js graphs.
    """
    if not request.user.is_authenticated:
        return render(request, "dashboard/landing.html")

    user = request.user
    org = user.organization

    # ── 1. Base Querysets Scoped to Organization ─────────────────────────────
    if user.is_administrator or user.is_superuser:
        base_instruments = Instrument.objects.filter(is_deleted=False)
        base_sessions = TestSession.objects.all()
        base_reports = GeneratedReport.objects.all()
    else:
        base_instruments = Instrument.objects.filter(organization=org, is_deleted=False)
        base_sessions = TestSession.objects.filter(organization=org)
        base_reports = GeneratedReport.objects.filter(session__organization=org)

    # ── 2. Filter Parameters ──────────────────────────────────────────────────
    status_filter = request.GET.get("status", "").strip()
    date_from = request.GET.get("date_from", "").strip()
    date_to = request.GET.get("date_to", "").strip()
    preset = request.GET.get("preset", "").strip()

    filtered_sessions = base_sessions

    # Quick preset date ranges
    today = timezone.localdate()
    if preset == "today":
        filtered_sessions = filtered_sessions.filter(test_date=today)
        date_from = str(today)
        date_to = str(today)
    elif preset == "week":
        start_week = today - datetime.timedelta(days=7)
        filtered_sessions = filtered_sessions.filter(test_date__gte=start_week, test_date__lte=today)
        date_from = str(start_week)
        date_to = str(today)
    elif preset == "month":
        start_month = today - datetime.timedelta(days=30)
        filtered_sessions = filtered_sessions.filter(test_date__gte=start_month, test_date__lte=today)
        date_from = str(start_month)
        date_to = str(today)
    elif preset == "year":
        start_year = today - datetime.timedelta(days=365)
        filtered_sessions = filtered_sessions.filter(test_date__gte=start_year, test_date__lte=today)
        date_from = str(start_year)
        date_to = str(today)
    else:
        # Custom date range
        if date_from:
            try:
                d_from = datetime.date.fromisoformat(date_from)
                filtered_sessions = filtered_sessions.filter(test_date__gte=d_from)
            except ValueError:
                date_from = ""
        if date_to:
            try:
                d_to = datetime.date.fromisoformat(date_to)
                filtered_sessions = filtered_sessions.filter(test_date__lte=d_to)
            except ValueError:
                date_to = ""

    # Status filter
    if status_filter:
        filtered_sessions = filtered_sessions.filter(status=status_filter)

    # ── 3. Optimized KPI Aggregations (Single DB Query) ───────────────────────
    kpi_aggregates = filtered_sessions.aggregate(
        total_records=Count("id"),
        in_progress=Count("id", filter=Q(status=SessionStatus.IN_PROGRESS)),
        pending_review=Count("id", filter=Q(status__in=[SessionStatus.SUBMITTED, SessionStatus.PENDING_REVIEW, SessionStatus.UNDER_REVIEW])),
        approved=Count("id", filter=Q(status__in=[SessionStatus.APPROVED, SessionStatus.REPORT_GENERATED])),
        rejected=Count("id", filter=Q(status=SessionStatus.REJECTED)),
        draft=Count("id", filter=Q(status=SessionStatus.DRAFT)),
    )

    kpi = {
        "total_instruments": base_instruments.count(),
        "total_records": kpi_aggregates["total_records"] or 0,
        "in_progress": kpi_aggregates["in_progress"] or 0,
        "pending_review": kpi_aggregates["pending_review"] or 0,
        "approved": kpi_aggregates["approved"] or 0,
        "rejected": kpi_aggregates["rejected"] or 0,
        "total_reports": base_reports.count(),
    }

    # ── 4. Recent Data Tables ─────────────────────────────────────────────────
    # Recent test records
    recent_sessions = (
        filtered_sessions
        .select_related("instrument", "technician", "reviewer")
        .order_by("-created_at")[:8]
    )

    # Recently registered instruments
    recent_instruments = (
        base_instruments
        .order_by("-created_at")[:6]
    )

    # Pending approvals (specifically requiring review action)
    pending_approvals = (
        base_sessions
        .filter(status=SessionStatus.PENDING_REVIEW)
        .select_related("instrument", "technician")
        .order_by("-test_date")[:6]
    )

    # ── 5. Monthly Test Report Statistics (Last 6 Months) ──────────────────────
    six_months_ago = today - datetime.timedelta(days=180)
    monthly_qs = (
        base_sessions
        .filter(created_at__date__gte=six_months_ago)
        .annotate(month=TruncMonth("created_at"))
        .values("month")
        .annotate(total=Count("id"))
        .order_by("month")
    )

    # Build contiguous monthly series for clean chart rendering
    month_dict = {}
    for item in monthly_qs:
        if item["month"]:
            key = item["month"].strftime("%b %Y")
            month_dict[key] = item["total"]

    # Ensure last 6 calendar months are represented
    monthly_labels = []
    monthly_data = []
    for i in range(5, -1, -1):
        ref_date = today - datetime.timedelta(days=i * 30)
        lbl = ref_date.strftime("%b %Y")
        if lbl not in monthly_labels:
            monthly_labels.append(lbl)
            monthly_data.append(month_dict.get(lbl, 0))

    # ── 6. Test Status Distribution Chart ─────────────────────────────────────
    status_chart_labels = ["Draft", "In Progress", "Pending Review", "Approved", "Rejected"]
    status_chart_data = [
        kpi_aggregates["draft"] or 0,
        kpi_aggregates["in_progress"] or 0,
        kpi_aggregates["pending_review"] or 0,
        kpi_aggregates["approved"] or 0,
        kpi_aggregates["rejected"] or 0,
    ]

    # ── 7. Accuracy Class Breakdown ───────────────────────────────────────────
    class_agg = (
        base_instruments
        .values("accuracy_class")
        .annotate(count=Count("id"))
    )
    class_dict = {item["accuracy_class"]: item["count"] for item in class_agg}
    class_labels = ["Class I", "Class II", "Class III", "Class IIII"]
    class_data = [
        class_dict.get(AccuracyClass.CLASS_I, 0),
        class_dict.get(AccuracyClass.CLASS_II, 0),
        class_dict.get(AccuracyClass.CLASS_III, 0),
        class_dict.get(AccuracyClass.CLASS_IIII, 0),
    ]

    context = {
        "page_title": "Laboratory Dashboard",
        "today": today,
        "kpi": kpi,
        "recent_sessions": recent_sessions,
        "recent_instruments": recent_instruments,
        "pending_approvals": pending_approvals,
        # Filters state
        "status_choices": SessionStatus.choices,
        "current_status": status_filter,
        "date_from": date_from,
        "date_to": date_to,
        "preset": preset,
        "is_filtered": bool(status_filter or date_from or date_to or preset),
        # Chart JSON data
        "monthly_labels_json": json.dumps(monthly_labels),
        "monthly_data_json": json.dumps(monthly_data),
        "status_labels_json": json.dumps(status_chart_labels),
        "status_data_json": json.dumps(status_chart_data),
        "class_labels_json": json.dumps(class_labels),
        "class_data_json": json.dumps(class_data),
    }
    return render(request, "dashboard/home.html", context)


from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.shortcuts import redirect

@login_required
def settings_view(request):
    """
    Enterprise Laboratory & System Settings Console:
    Allows laboratory managers and administrators to configure laboratory
    profile metadata, OIML R 76 metrological calculation baselines,
    certificate issuance templates, and user interface preferences.
    """
    user = request.user
    org = user.organization

    if request.method == "POST":
        # Process and persist user/organization laboratory settings
        lab_name = request.POST.get("lab_name", "").strip()
        accreditation_no = request.POST.get("accreditation_no", "").strip()
        default_oiml = request.POST.get("default_oiml", "R76_2006").strip()
        report_prefix = request.POST.get("report_prefix", "TR-").strip()
        temp_baseline = request.POST.get("temp_baseline", "20.0").strip()
        humidity_baseline = request.POST.get("humidity_baseline", "50.0").strip()
        compact_tables = request.POST.get("compact_tables") == "on"

        if org and (user.is_administrator or user.is_lab_manager or user.is_superuser):
            if lab_name:
                org.name = lab_name
            if accreditation_no:
                org.accreditation_number = accreditation_no
            org.save()

        # Store session/interface preferences
        request.session["compact_tables"] = compact_tables
        request.session["default_oiml"] = default_oiml
        request.session["temp_baseline"] = temp_baseline
        request.session["humidity_baseline"] = humidity_baseline

        messages.success(request, "Laboratory and system preferences successfully updated.")
        return redirect("dashboard:settings")

    context = {
        "page_title": "Laboratory & System Settings",
        "org": org,
        "default_oiml": request.session.get("default_oiml", "R76_2006"),
        "temp_baseline": request.session.get("temp_baseline", "20.0"),
        "humidity_baseline": request.session.get("humidity_baseline", "50.0"),
        "compact_tables": request.session.get("compact_tables", False),
    }
    return render(request, "dashboard/settings.html", context)

