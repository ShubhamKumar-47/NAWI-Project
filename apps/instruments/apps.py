"""apps/instruments/apps.py"""
from django.apps import AppConfig


class InstrumentsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.instruments"
    label = "instruments"
    verbose_name = "Instrument Registry"
