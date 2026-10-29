"""Test settings for LabFlow backend (Doc 09 §9.1).

Runs exclusively against real PostgreSQL 16 and Redis 7 service containers.
Hard-bans SQLite at initialization.
"""

import os
import socket
from typing import Any
from urllib.parse import urlparse

from config.settings.base import *  # noqa: F403

if not os.environ.get("DJANGO_SECRET_KEY"):
    SECRET_KEY = "ci-test-secret-key-32-chars-minimum-length-for-testing"

# Hard-ban SQLite before any database connection attempt
_db_url = os.environ.get("DATABASE_URL", "")
if _db_url:
    _scheme = urlparse(_db_url).scheme
    if "sqlite" in _scheme:
        msg = (
            "SQLite is strictly prohibited per Doc 09 §9.1. PostgreSQL 16 is required."
        )
        raise RuntimeError(msg)


def _resolve_default_db_port() -> str:
    if "POSTGRES_PORT" in os.environ:
        return os.environ["POSTGRES_PORT"]
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(0.2)
    try:
        if sock.connect_ex(("127.0.0.1", 5433)) == 0:
            return "5433"
    except Exception:
        pass
    finally:
        sock.close()
    return "5432"


def _resolve_default_db_host() -> str:
    if "POSTGRES_HOST" in os.environ:
        return os.environ["POSTGRES_HOST"]
    if _resolve_default_db_port() == "5433":
        return "127.0.0.1"
    return "localhost"


def _resolve_default_redis_url() -> str:
    if "REDIS_URL" in os.environ:
        return os.environ["REDIS_URL"]
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(0.2)
    try:
        if sock.connect_ex(("127.0.0.1", 6380)) == 0:
            return "redis://127.0.0.1:6380/0"
    except Exception:
        pass
    finally:
        sock.close()
    return "redis://localhost:6379/0"


DEBUG = False

# Ensure django_tenants postgresql engine is configured
_db_user = os.environ.get("POSTGRES_USER", "labflow")
_db_pass = os.environ.get("POSTGRES_PASSWORD", "labflow_test_password")
_db_name = os.environ.get("POSTGRES_DB", "labflow_test")
_db_host = _resolve_default_db_host()
_db_port = _resolve_default_db_port()

DATABASES: dict[str, dict[str, Any]] = {  # type: ignore[no-redef]  # overrides base.py DATABASES (LAB-5)
    "default": {
        "ENGINE": "django_tenants.postgresql_backend",
        "NAME": _db_name,
        "USER": _db_user,
        "PASSWORD": _db_pass,
        "HOST": _db_host,
        "PORT": _db_port,
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
else:
    # Ensure DATABASE_URL is set in environment for child processes and assertions
    os.environ.setdefault(
        "DATABASE_URL",
        f"postgresql://{_db_user}:{_db_pass}@{_db_host}:{_db_port}/{_db_name}",
    )

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
REDIS_URL = _resolve_default_redis_url()
os.environ.setdefault("REDIS_URL", REDIS_URL)

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

# Django 6.1+: MAILERS replaces EMAIL_BACKEND (RemovedInDjango2028Warning).
# Without MAILERS, send_mail() emits "Django 2028 will not have a default
# mailer", which pytest's filterwarnings=error turns into an exception and
# silently breaks owner activation emails. Locmem keeps mail.outbox working.
MAILERS = {
    "default": {
        "BACKEND": "django.core.mail.backends.locmem.EmailBackend",
    }
}
