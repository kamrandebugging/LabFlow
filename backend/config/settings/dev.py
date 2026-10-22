"""
Local development settings for LabFlow.
Used for local testing and health checks.
"""

import os

from .base import *

DEBUG = True

# Development fallback for local verification if env var is not set
SECRET_KEY = os.environ.get(
    "DJANGO_SECRET_KEY",
    "django-insecure-dev-only-secret-key-for-local-scaffold-boot",
)

ALLOWED_HOSTS = ["*"]

# Default database for local scaffolding check
# (Switched to PostgreSQL / django-tenants in LAB-5)
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
    }
}
