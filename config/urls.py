"""config/urls.py — Root URL configuration."""
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", include("apps.dashboard.urls", namespace="dashboard")),
    path("accounts/", include("apps.accounts.urls", namespace="accounts")),
    path("instruments/", include("apps.instruments.urls", namespace="instruments")),
    path("sessions/", include("apps.test_sessions.urls", namespace="test_sessions")),
    path("measurements/", include("apps.measurements.urls", namespace="measurements")),
    path("calculations/", include("calculations.urls", namespace="calculations")),
    path("reports/", include("apps.reports.urls", namespace="reports")),
    path("audit/", include("apps.audit.urls", namespace="audit")),
]

# Custom HTTP error handlers
handler403 = "apps.accounts.views.unauthorized_view"

# Serve static and media files during development
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
    import debug_toolbar
    urlpatterns = [path("__debug__/", include(debug_toolbar.urls))] + urlpatterns
