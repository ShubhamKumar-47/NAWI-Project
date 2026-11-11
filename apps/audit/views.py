"""apps/audit/views.py — Audit log list view with multi-parameter filtering."""
from django.db import models
from django.views.generic import ListView
from apps.core.constants import AuditAction
from apps.core.mixins import LabManagerRequiredMixin
from .models import AuditLog


class AuditLogListView(LabManagerRequiredMixin, ListView):
    model = AuditLog
    template_name = "audit/log_list.html"
    context_object_name = "logs"
    paginate_by = 50

    def get_queryset(self):
        qs = AuditLog.objects.select_related("user", "content_type").order_by("-timestamp")
        if not self.request.user.is_superadmin:
            qs = qs.filter(user__organization=self.request.user.organization)

        action = self.request.GET.get("action", "").strip()
        if action:
            qs = qs.filter(action=action)

        user_q = self.request.GET.get("user", "").strip()
        if user_q:
            qs = qs.filter(
                models.Q(user__first_name__icontains=user_q)
                | models.Q(user__last_name__icontains=user_q)
                | models.Q(user__email__icontains=user_q)
                | models.Q(user__username__icontains=user_q)
            )

        q = self.request.GET.get("q", "").strip()
        if q:
            qs = qs.filter(
                models.Q(description__icontains=q)
                | models.Q(object_id__icontains=q)
                | models.Q(ip_address__icontains=q)
            )

        date_from = self.request.GET.get("date_from", "").strip()
        if date_from:
            qs = qs.filter(timestamp__date__gte=date_from)

        date_to = self.request.GET.get("date_to", "").strip()
        if date_to:
            qs = qs.filter(timestamp__date__lte=date_to)

        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["actions"] = AuditAction.choices
        ctx["filter_action"] = self.request.GET.get("action", "")
        ctx["filter_user"] = self.request.GET.get("user", "")
        ctx["filter_q"] = self.request.GET.get("q", "")
        ctx["filter_date_from"] = self.request.GET.get("date_from", "")
        ctx["filter_date_to"] = self.request.GET.get("date_to", "")
        params = self.request.GET.copy()
        params.pop("page", None)
        ctx["query_string"] = params.urlencode()
        ctx["has_active_filters"] = bool(params)
        return ctx
