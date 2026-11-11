"""apps/reports/urls.py"""
from django.urls import path
from . import views

app_name = "reports"

urlpatterns = [
    path("", views.report_list, name="list"),
    path("generate/<uuid:session_pk>/", views.generate_report, name="generate"),
    path("<uuid:pk>/detail/", views.report_detail, name="detail"),
    path("<uuid:pk>/preview/", views.preview_report, name="preview"),
    path("<uuid:pk>/download/", views.download_report, name="download"),
    path("session/<uuid:session_pk>/download/<str:fmt>/", views.session_download_report, name="session_download"),
    path("session/<uuid:session_pk>/revise/", views.initiate_revision, name="initiate_revision"),
    path("preview-session/<uuid:session_pk>/", views.session_pdf_preview, name="session_preview"),
]
