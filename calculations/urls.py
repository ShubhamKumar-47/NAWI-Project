"""calculations/urls.py – URL routing for calculation engine results."""
from django.urls import path
from . import views

app_name = "calculations"

urlpatterns = [
    path("<uuid:session_pk>/", views.session_calculation_results, name="session_results"),
    path("<uuid:session_pk>/recalculate/", views.session_recalculate, name="session_recalculate"),
]

