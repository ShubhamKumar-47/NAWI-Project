"""apps/test_sessions/urls.py – URL routing for test sessions module."""
from django.urls import path
from . import views

app_name = "test_sessions"

urlpatterns = [
    path("", views.TestSessionListView.as_view(), name="list"),
    path("reviewer-dashboard/", views.ReviewerDashboardView.as_view(), name="reviewer_dashboard"),
    path("create/", views.TestSessionCreateView.as_view(), name="create"),
    path("<uuid:pk>/", views.TestSessionDetailView.as_view(), name="detail"),
    path("<uuid:pk>/edit/", views.TestSessionUpdateView.as_view(), name="edit"),
    path("<uuid:pk>/procedures/", views.TestSessionProcedureConfigView.as_view(), name="procedure_config"),
    path("<uuid:pk>/results/", views.TestSessionResultsView.as_view(), name="results"),
    path("<uuid:pk>/results/print/", views.TestSessionResultsPrintView.as_view(), name="results_print"),
    path("<uuid:pk>/results/validate-drafts/", views.validate_session_drafts, name="validate_drafts"),
    path("<uuid:pk>/review/", views.TestSessionReviewView.as_view(), name="review"),
    path("<uuid:pk>/start-review/", views.start_session_review, name="start_review"),
    path("<uuid:pk>/submit/", views.submit_for_review, name="submit"),
    path("<uuid:pk>/approve/", views.approve_session, name="approve"),
    path("<uuid:pk>/reject/", views.reject_session, name="reject"),
    path("<uuid:pk>/revise/", views.initiate_session_revision, name="initiate_revision"),
]
