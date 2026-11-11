"""apps/audit/utils.py — Helper to create audit log entries."""
from django.contrib.contenttypes.models import ContentType
from .models import AuditLog


def log_action(user, action, obj=None, description="", old_values=None, new_values=None, request=None):
    """
    Create an audit log entry.

    Args:
        user: The CustomUser performing the action.
        action: AuditAction choice string (e.g., AuditAction.CREATE).
        obj: The Django model instance being acted upon (optional).
        description: Human-readable description of the event.
        old_values: Dict of field values before the change.
        new_values: Dict of field values after the change.
        request: Django HttpRequest — used to extract IP and user agent.
    """
    ip_address = None
    user_agent = ""
    if request:
        ip_address = get_client_ip(request)
        user_agent = request.META.get("HTTP_USER_AGENT", "")

    content_type = None
    object_id = ""
    if obj is not None:
        content_type = ContentType.objects.get_for_model(obj)
        object_id = str(obj.pk)

    AuditLog.objects.create(
        user=user,
        action=action,
        content_type=content_type,
        object_id=object_id,
        description=description,
        old_values=old_values,
        new_values=new_values,
        ip_address=ip_address,
        user_agent=user_agent,
    )


def get_client_ip(request):
    """Extract real client IP from request headers."""
    x_forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
    if x_forwarded_for:
        return x_forwarded_for.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")
