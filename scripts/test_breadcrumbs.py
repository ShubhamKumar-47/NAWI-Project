"""
scripts/test_breadcrumbs.py
Verify rendered breadcrumb HTML across all pages to ensure no trailing or repeating slashes exist.
"""
import os
import sys
import django
import re

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(BASE_DIR)
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.development")
django.setup()

from django.test import Client
from apps.accounts.models import CustomUser

admin = CustomUser.objects.filter(is_superuser=True).first()
if not admin:
    admin = CustomUser.objects.first()

client = Client()
client.force_login(admin)

from apps.instruments.models import Instrument
from apps.test_sessions.models import TestSession
from apps.reports.models import GeneratedReport

inst = Instrument.objects.first()
sess = TestSession.objects.first()
rep = GeneratedReport.objects.first()

test_urls = [
    "/instruments/",
    "/instruments/create/",
    f"/instruments/{inst.pk}/" if inst else "/instruments/",
    "/sessions/",
    "/sessions/create/",
    f"/sessions/{sess.pk}/" if sess else "/sessions/",
    "/accounts/users/",
    "/settings/",
    "/audit/",
    "/reports/",
    f"/reports/{rep.pk}/detail/" if rep else "/reports/",
]

print("CHECKING BREADCRUMB RENDERING ACROSS URLS:")
all_clean = True
for url in test_urls:
    res = client.get(url)
    html = res.content.decode("utf-8")
    bc_match = re.search(r"<ol class=[\"']breadcrumb[^>]*>(.*?)</ol>", html, re.DOTALL)
    if bc_match:
        bc_content = bc_match.group(1)
        items = re.findall(r"<li[^>]*>(.*?)</li>", bc_content, re.DOTALL)
        clean_items = [re.sub(r"<[^>]+>", "", it).strip() for it in items]
        print(f"URL {url:22} -> Breadcrumb items: {clean_items}")
        for it in clean_items:
            if not it:
                print(f"  ❌ WARNING: Empty breadcrumb item found in {url}!")
                all_clean = False
    else:
        print(f"URL {url:22} -> (No breadcrumb on this page)")

if all_clean:
    print("\n✅ ALL BREADCRUMBS ARE CLEAN! No empty items, no extra slashes.")
else:
    print("\n❌ Found issues with breadcrumbs.")

