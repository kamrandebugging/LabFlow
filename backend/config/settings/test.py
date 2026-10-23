"""Test settings for LabFlow backend (Doc 09 §9.1).

Runs exclusively against real PostgreSQL 16 and Redis 7 service containers.
Hard-bans SQLite at initialization.
"""

import os
from typing import Any
from urllib.parse import urlparse

from config.settings.base import *  # noqa: F403

# Hard-ban SQLite before any database connection attempt
_db_url = os.environ.get("DATABASE_URL", "")
if _db_url:
    _scheme = urlparse(_db_url).scheme
    if "sqlite" in _scheme:
        msg = (
            "SQLite is strictly prohibited per Doc 09 §9.1. PostgreSQL 16 is required."
        )
        raise RuntimeError(msg)

DEBUG = False

# Ensure django_tenants postgresql engine is configured
DATABASES: dict[str, dict[str, Any]] = {
    "default": {
        "ENGINE": "django_tenants.postgresql_backend",
        "NAME": os.environ.get("POSTGRES_DB", "labflow_test"),
        "USER": os.environ.get("POSTGRES_USER", "labflow"),
        "PASSWORD": os.environ.get("POSTGRES_PASSWORD", "labflow_test_password"),
        "HOST": os.environ.get("POSTGRES_HOST", "localhost"),
        "PORT": os.environ.get("POSTGRES_PORT", "5432"),
    }
}

# If DATABASE_URL is explicitly set, parse and update connection params
if _db_url:
    _parsed = urlparse(_db_url)
    DATABASES["default"]["NAME"] = _parsed.path.lstrip("/") or "labflow_test"
    DATABASES["default"]["USER"] = _parsed.username or "labflow"
    DATABASES["default"]["PASSWORD"] = _parsed.password or "labflow_test_password"
    DATABASES["default"]["HOST"] = _parsed.hostname or "localhost"
    DATABASES["default"]["PORT"] = str(_parsed.port or 5432)

# Verify engine is never downgraded to SQLite
if "sqlite" in str(DATABASES["default"]["ENGINE"]):
    msg = (
        "SQLite database engine detected in DATABASES['default']. "
        "Aborting per Doc 09 §9.1."
    )
    raise RuntimeError(msg)

# Password hashing speedup for tests
PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.MD5PasswordHasher",
]

# Redis test cache configuration
REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
CACHES: dict[str, dict[str, Any]] = {
    "default": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": REDIS_URL,
        "KEY_PREFIX": "labflow_test",
    }
}

# Celery eager mode during tests
CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True
CELERY_BROKER_URL = REDIS_URL

# Disable Sentry in test environment
SENTRY_DSN = ""
