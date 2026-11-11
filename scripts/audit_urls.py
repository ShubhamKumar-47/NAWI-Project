import os
import sys
import re
import glob
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.append(str(BASE_DIR))

import django
from django.urls import reverse, NoReverseMatch

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.development")
django.setup()

url_pattern = re.compile(r'{%\s*url\s+[\'"]([^\'" ]+)[\'"]')
all_tags = set()
broken = []

for t in glob.glob("templates/**/*.html", recursive=True):
    with open(t, "r", encoding="utf-8", errors="ignore") as f:
        content = f.read()
    for match in url_pattern.finditer(content):
        url_name = match.group(1)
        all_tags.add((url_name, t))

dummy_uuid = "00000000-0000-0000-0000-000000000000"
test_kwargs_list = [
    {},
    {"pk": 1},
    {"session_pk": 1},
    {"pk": dummy_uuid},
    {"session_pk": dummy_uuid},
    {"session_pk": dummy_uuid, "fmt": "pdf"},
    {"session_pk": dummy_uuid, "pk": 1},
    {"uidb64": "MQ", "token": "token"},
    {"step": "instrument"},
    {"step": 1},
]

for url_name, template_path in sorted(all_tags):
    resolved = False
    for kw in test_kwargs_list:
        try:
            reverse(url_name, kwargs=kw)
            resolved = True
            break
        except NoReverseMatch:
            pass
        except Exception:
            pass
    if not resolved:
        try:
            reverse(url_name, args=[1])
            resolved = True
        except NoReverseMatch:
            pass
    if not resolved:
        broken.append((url_name, template_path))

if broken:
    print(f"BROKEN URLS ({len(broken)}):")
    for b in broken:
        print(f"  '{b[0]}' in {b[1]}")
else:
    print(f"AUDIT SUCCESS: All {len(all_tags)} distinct template URL references resolved cleanly!")
