"""apps/core/context_processors.py — Global template context variables."""
from django.conf import settings


def site_settings(request):
    """Inject site-wide settings into every template context."""
    return {
        "SITE_NAME": getattr(settings, "SITE_NAME", "NAWI TRMS"),
        "SITE_SHORT_NAME": getattr(settings, "SITE_SHORT_NAME", "NTRMS"),
        "SITE_VERSION": getattr(settings, "SITE_VERSION", "1.0.0"),
    }
