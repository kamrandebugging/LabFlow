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

