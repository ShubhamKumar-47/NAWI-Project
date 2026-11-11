"""apps/instruments/urls.py – URL configuration for the instruments app."""
from django.urls import path
from . import views

app_name = "instruments"

urlpatterns = [
    path("", views.InstrumentListView.as_view(), name="list"),
    path("create/", views.InstrumentCreateView.as_view(), name="create"),
    path("<uuid:pk>/", views.InstrumentDetailView.as_view(), name="detail"),
    path("<uuid:pk>/edit/", views.InstrumentUpdateView.as_view(), name="edit"),
    path("<uuid:pk>/delete/", views.InstrumentDeleteView.as_view(), name="delete"),
]
