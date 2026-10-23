"""
Test settings for LabFlow.
Enforces real PostgreSQL 16 and Redis 7 per Doc 09 §9.1. SQLite is strictly banned.
"""

from __future__ import annotations

import os
from urllib.parse import urlparse

from config.settings.base import *  # noqa: F403

DEBUG = False
TESTING = True

# Security / Auth speedups for testing
# (argon2 kept available, fast hasher for runner speed)
PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.MD5PasswordHasher",
]

# Database configuration: read DATABASE_URL or individual POSTGRES_* environment vars
DATABASE_URL = os.environ.get("DATABASE_URL")

if DATABASE_URL:
    parsed_db = urlparse(DATABASE_URL)
    engine = "django.db.backends.postgresql"
    # When django_tenants is installed in INSTALLED_APPS, use tenant backend
    if "django_tenants" in globals().get("INSTALLED_APPS", []):
        engine = "django_tenants.postgresql_backend"

    DATABASES = {
        "default": {
            "ENGINE": engine,
            "NAME": parsed_db.path.lstrip("/") or "labflow_test",
            "USER": parsed_db.username or "labflow",
            "PASSWORD": parsed_db.password or "labflow",
            "HOST": parsed_db.hostname or "localhost",
            "PORT": parsed_db.port or 5432,
            "TEST": {
                "NAME": (
                    f"test_{parsed_db.path.lstrip('/')}"
                    if parsed_db.path
                    else "test_labflow"
                ),
            },
        }
    }
else:
    pg_db = os.environ.get("POSTGRES_DB", "labflow_test")
    pg_user = os.environ.get("POSTGRES_USER", "labflow")
    pg_password = os.environ.get("POSTGRES_PASSWORD", "labflow")
    pg_host = os.environ.get("POSTGRES_HOST", "localhost")
    pg_port = int(os.environ.get("POSTGRES_PORT", "5432"))

    engine = "django.db.backends.postgresql"
    if "django_tenants" in globals().get("INSTALLED_APPS", []):
        engine = "django_tenants.postgresql_backend"

    DATABASES = {
        "default": {
            "ENGINE": engine,
            "NAME": pg_db,
            "USER": pg_user,
            "PASSWORD": pg_password,
            "HOST": pg_host,
            "PORT": pg_port,
            "TEST": {
                "NAME": f"test_{pg_db}",
            },
        }
    }

# Explicitly disallow any fallback or sqlite engine
if "sqlite" in str(DATABASES["default"]["ENGINE"]).lower():
    raise RuntimeError(
        "SQLite is not allowed — tests must run against PostgreSQL (Doc 09 §9.1)."
    )

# Redis / Cache configuration
REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/1")

CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": REDIS_URL,
        "KEY_PREFIX": "labflow_test",
        "TIMEOUT": 300,
    }
}

# Celery in test mode
CELERY_BROKER_URL = REDIS_URL
CELERY_RESULT_BACKEND = REDIS_URL
CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True

# Disable Sentry in test runs
SENTRY_DSN = ""
