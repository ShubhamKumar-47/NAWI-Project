"""
scripts/check_all_routes.py
Probe every single URL pattern in the project with Django test Client to detect any 500 errors.
"""
import os
import sys
import django

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(BASE_DIR)
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.development")
django.setup()

from django.test import Client
from apps.accounts.models import CustomUser
from apps.instruments.models import Instrument
from apps.test_sessions.models import TestSession
from apps.reports.models import GeneratedReport

user = CustomUser.objects.filter(is_superuser=True).first()
if not user:
    user = CustomUser.objects.first()

client = Client()
client.force_login(user)

inst = Instrument.objects.first()
sess = TestSession.objects.first()
rep = GeneratedReport.objects.first()

routes = [
    ("/", "Dashboard Landing"),
    ("/instruments/", "Instruments List"),
    ("/instruments/create/", "Instrument Create"),
    (f"/instruments/{inst.pk}/" if inst else "/instruments/", "Instrument Detail"),
    (f"/instruments/{inst.pk}/edit/" if inst else "/instruments/", "Instrument Edit"),
    ("/sessions/", "Test Sessions List"),
    ("/sessions/create/", "Test Session Create"),
    (f"/sessions/{sess.pk}/" if sess else "/sessions/", "Test Session Detail"),
    (f"/sessions/{sess.pk}/edit/" if sess else "/sessions/", "Test Session Edit"),
    (f"/sessions/{sess.pk}/procedures/" if sess else "/sessions/", "Test Session Procedures"),
    (f"/sessions/{sess.pk}/review/" if sess else "/sessions/", "Test Session Review"),
    (f"/sessions/{sess.pk}/results/" if sess else "/sessions/", "Test Session Results"),
    (f"/sessions/{sess.pk}/results/print/" if sess else "/sessions/", "Test Session Print"),
    ("/sessions/reviewer-dashboard/", "Reviewer Dashboard"),
    ("/reports/", "Reports List"),
    (f"/reports/generate/{sess.pk}/" if sess else "/reports/", "Report Generate"),
    (f"/reports/{rep.pk}/detail/" if rep else "/reports/", "Report Detail"),
    (f"/reports/{rep.pk}/preview/" if rep else "/reports/", "Report Preview"),
    ("/accounts/users/", "Users List"),
    ("/accounts/profile/", "User Profile"),
    ("/settings/", "Settings Page"),
    ("/audit/", "Audit Log List"),
]

print("PROBING ALL SYSTEM ROUTES:")
errors_found = 0
for path, name in routes:
    try:
        resp = client.get(path)
        status = resp.status_code
        if status in [500, 404, 403]:
            print(f"❌ [{status}] {name:25} -> {path}")
            errors_found += 1
        else:
            print(f"✔ [{status}] {name:25} -> {path}")
    except Exception as e:
        print(f"💥 [EXCEPTION] {name:25} -> {path}: {e}")
        errors_found += 1

print(f"\nTotal errors / unexpected statuses: {errors_found}")

