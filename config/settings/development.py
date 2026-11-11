"""config/settings/development.py — Development overrides."""
from .base import *  # noqa

DEBUG = True
ALLOWED_HOSTS = ["*"]

# ─── Database (SQLite for dev) ───────────────────────────────────────────────
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
    }
}

# ─── Debug Toolbar ───────────────────────────────────────────────────────────
INSTALLED_APPS += ["debug_toolbar"]  # noqa
MIDDLEWARE.insert(0, "debug_toolbar.middleware.DebugToolbarMiddleware")  # noqa
INTERNAL_IPS = ["127.0.0.1"]

# ─── Email (console backend for dev) ─────────────────────────────────────────
EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"

# ─── Axes relaxed for development ────────────────────────────────────────────
AXES_ENABLED = False

# ─── Static files served by Django in dev ────────────────────────────────────
STATICFILES_STORAGE = "django.contrib.staticfiles.storage.StaticFilesStorage"
