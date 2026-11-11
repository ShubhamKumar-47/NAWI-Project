"""apps/test_sessions/apps.py"""
from django.apps import AppConfig


class TestSessionsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.test_sessions"
    verbose_name = "Test Sessions"
