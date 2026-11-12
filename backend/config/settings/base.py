"""Django base settings for LabFlow.

Architecture & Configuration per Docs 01, 02, 04, 08, 09.
"""

import os
from pathlib import Path

import environ
from celery.schedules import crontab
from django.core.exceptions import ImproperlyConfigured

BASE_DIR = Path(__file__).resolve().parent.parent.parent

env = environ.Env()
environ.Env.read_env(BASE_DIR / ".env")

# -----------------------------------------------------------------------------
# Secret hygiene (LAB-49 Phase 0.1 / OWASP API2 A2-1, API8 A8-1)
#
# Insecure defaults exist for local dev/test only. Every other settings module
# (base via gunicorn, config.settings.prod) refuses to boot unless the operator
# supplied real secrets in the environment. Explicit ``LABFLOW_LOCAL_DEV=1``
# also opts into the dev defaults.
# -----------------------------------------------------------------------------
_SETTINGS_MODULE = os.environ.get("DJANGO_SETTINGS_MODULE", "")
_IS_LOCAL_DEV = bool(
    os.environ.get("LABFLOW_LOCAL_DEV") == "1"
    or _SETTINGS_MODULE.endswith(".dev")
    or _SETTINGS_MODULE.endswith(".test")
)

_INSECURE_SECRET_DEFAULT = "django-insecure-dev-key-change-in-production"
# The Fernet key committed to the public repository. Treated as compromised:
# accepted only for local dev/test, rejected everywhere else.
_COMMITTED_TOTP_KEY = "sb_wYl5m_YtxnHje0H4_ZEZ35_8mNfguSqqV897s_ts="
_DEFAULT_DATABASE_URL = "postgres://postgres:postgres@localhost:5432/labflow"


def _require_env_secret(
    name: str,
    *,
    local_default: str | None = None,
    forbidden: frozenset[str] = frozenset(),
    must_differ_from: tuple[str, str] | None = None,
) -> str:
    """Return a required secret from the environment, failing closed.

    ``local_default`` is used only when the current settings module is dev or
    test (or ``LABFLOW_LOCAL_DEV=1``). ``must_differ_from`` is a
    ``(other_name, other_value)`` tuple enforcing key separation in prod.
    """
    value = env(name, default="")
    if not value:
        if local_default is not None and _IS_LOCAL_DEV:
            value = local_default
        else:
            raise ImproperlyConfigured(
                f"{name} must be set in the environment (no insecure default)."
            )
    if not _IS_LOCAL_DEV and value in forbidden:
        raise ImproperlyConfigured(
            f"{name} uses a known public/default value and must be rotated."
        )
    if must_differ_from is not None and not _IS_LOCAL_DEV:
        other_name, other_value = must_differ_from
        if value == other_value:
            raise ImproperlyConfigured(
                f"{name} must differ from {other_name} (key separation)."
            )
    return value


SECRET_KEY = _require_env_secret(
    "DJANGO_SECRET_KEY",
    local_default=_INSECURE_SECRET_DEFAULT,
    forbidden=frozenset({_INSECURE_SECRET_DEFAULT}),
)
DEBUG = env.bool("DJANGO_DEBUG", default=False)
ALLOWED_HOSTS = env.list(
    "DJANGO_ALLOWED_HOSTS", default=[".localhost", "127.0.0.1", "localhost"]
)

# -----------------------------------------------------------------------------
# Multi-Tenancy Architecture (Docs 01 §6, 02 §3, 04 §6)
# -----------------------------------------------------------------------------

SHARED_APPS: tuple[str, ...] = (
    "django_tenants",
    "apps.core",
    "apps.platform",
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.postgres",
    "rest_framework",
    "drf_spectacular",
)

TENANT_APPS: tuple[str, ...] = (
    "apps.branches",
    "apps.accounts",
    "apps.patients",
    "apps.catalog",
    "apps.partners",
    "apps.billing",
    "apps.samples",
    "apps.results",
    "apps.reports",
    "apps.notifications",
    "apps.automation",
)

INSTALLED_APPS: list[str] = list(SHARED_APPS) + [
    app for app in TENANT_APPS if app not in SHARED_APPS
]

TENANT_MODEL = "core.Tenant"
TENANT_DOMAIN_MODEL = "core.Domain"

PUBLIC_SCHEMA_NAME = "public"
PUBLIC_SCHEMA_URLCONF = "config.urls_public"
ROOT_URLCONF = "config.urls"

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# -----------------------------------------------------------------------------
# Middleware Configuration (Doc 01 §11, Doc 04 §6.1)
# -----------------------------------------------------------------------------

MIDDLEWARE = [
    "apps.core.middleware.PayloadLimitMiddleware",
    "django_tenants.middleware.main.TenantMainMiddleware",
    "apps.core.middleware.InternalPathMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "apps.core.middleware.SecurityHeadersMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "apps.core.middleware.OriginCheckMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    # LAB-36 (Doc 04 §11.2): subscription read-only enforcement after auth.
    "apps.platform.middleware.SubscriptionReadOnlyMiddleware",
    "apps.core.middleware.DocsGateMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

# -----------------------------------------------------------------------------
# Database Configuration (Docs 01 §6, 02 §2, 04 §6.1)
# -----------------------------------------------------------------------------

if not os.environ.get("DATABASE_URL") and not _IS_LOCAL_DEV:
    raise ImproperlyConfigured(
        "DATABASE_URL must be set in the environment (no default credentials)."
    )

DATABASES = {
    "default": env.db(
        "DATABASE_URL",
        default=_DEFAULT_DATABASE_URL,
        engine="django_tenants.postgresql_backend",
    )
}
DATABASES["default"]["ENGINE"] = "django_tenants.postgresql_backend"

DATABASE_ROUTERS = ("django_tenants.routers.TenantSyncRouter",)

# -----------------------------------------------------------------------------
# Internationalization & Regionalization (Doc 01 §5, Doc 03 §6.1, Doc 07 §9)
# -----------------------------------------------------------------------------

LANGUAGE_CODE = "en-us"
TIME_ZONE = "Asia/Karachi"
USE_I18N = True
USE_TZ = True

# -----------------------------------------------------------------------------
# Static & Media Storage (Doc 01 §15)
# -----------------------------------------------------------------------------

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "mediafiles"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

# -----------------------------------------------------------------------------
# Django REST Framework & Documentation (Doc 01 §6, Doc 03 §6.1)
# -----------------------------------------------------------------------------

REST_FRAMEWORK = {
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "apps.accounts.authentication.JWTAuthentication",
    ),
    "DEFAULT_PERMISSION_CLASSES": ("rest_framework.permissions.IsAuthenticated",),
    # LAB-49 Phase 2.1 (API4/API6): every API view is throttled by default —
    # reads per user, writes per user and writes per tenant. Public capability
    # routes keep their own stricter throttles in addition to these.
    "DEFAULT_THROTTLE_CLASSES": (
        "apps.core.throttling.ReadThrottle",
        "apps.core.throttling.WriteThrottle",
        "apps.core.throttling.TenantWriteThrottle",
    ),
    # Problem+JSON for the Layer-3 scope refusal (Doc 04 §8.5, BS-2);
    # every other exception keeps DRF's default rendering.
    "EXCEPTION_HANDLER": "apps.core.exceptions.problem_json_exception_handler",
}

# -----------------------------------------------------------------------------
# Security & Auth Engine Configuration (Doc 01 §14, Doc 08 §4, Doc 08 §10)
# -----------------------------------------------------------------------------

# Distributed Redis Cache (Doc 02 §3.4, Doc 08 §4)
REDIS_URL = env("REDIS_URL", default="redis://localhost:6379/0")

CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": REDIS_URL,
        "KEY_PREFIX": "labflow",
    }
}

# Security & Cookie Flags (Production Hardening)
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SESSION_COOKIE_SECURE = env.bool("SESSION_COOKIE_SECURE", default=not DEBUG)
CSRF_COOKIE_SECURE = env.bool("CSRF_COOKIE_SECURE", default=not DEBUG)
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SAMESITE = "Lax"
SECURE_BROWSER_XSS_FILTER = True
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"
SECURE_REFERRER_POLICY = "strict-origin-when-cross-origin"
SECURE_SSL_REDIRECT = env.bool("SECURE_SSL_REDIRECT", default=not DEBUG)
SECURE_HSTS_SECONDS = env.int("SECURE_HSTS_SECONDS", default=63072000)
SECURE_HSTS_INCLUDE_SUBDOMAINS = env.bool(
    "SECURE_HSTS_INCLUDE_SUBDOMAINS", default=True
)
SECURE_HSTS_PRELOAD = env.bool("SECURE_HSTS_PRELOAD", default=False)
CSRF_TRUSTED_ORIGINS = env.list("CSRF_TRUSTED_ORIGINS", default=[])

# API docs/schema are a ready-made attack inventory; off unless asked for
# (LAB-49 Phase 3.2). Local dev sets DOCS_ENABLED=1 in backend/.env.
DOCS_ENABLED = env.bool("DOCS_ENABLED", default=DEBUG)

# Money-movement step-up (LAB-49 Phase 2.8). Off locally/tests; prod enables it.
STEP_UP_ENABLED = env.bool("STEP_UP_ENABLED", default=False)

# Error reporting (LAB-49 Phase 3.7). Empty DSN disables Sentry entirely.
SENTRY_DSN = env("SENTRY_DSN", default="")
SENTRY_ENVIRONMENT = env("SENTRY_ENVIRONMENT", default="development")

# Breached-password screening (LAB-49 Phase 5.6). Off by default so tests and
# offline deployments never depend on the HIBP network call; prod enables it.
HIBP_ENABLED = env.bool("HIBP_ENABLED", default=False)
# Progressive lockout after repeated throttled login windows (SE-25).
ACCOUNT_LOCKOUT_THRESHOLD = env.int("ACCOUNT_LOCKOUT_THRESHOLD", default=3)
ACCOUNT_LOCKOUT_SECONDS = env.int("ACCOUNT_LOCKOUT_SECONDS", default=3600)

PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.Argon2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2SHA1PasswordHasher",
]

JWT_SIGNING_KEY = _require_env_secret(
    "JWT_SIGNING_KEY",
    local_default=SECRET_KEY,
    forbidden=frozenset({_INSECURE_SECRET_DEFAULT}),
    must_differ_from=("DJANGO_SECRET_KEY", SECRET_KEY),
)
JWT_ACCESS_TOKEN_LIFETIME_SECONDS = 900  # 15 minutes (Doc 08 §4.3)
JWT_REFRESH_TOKEN_LIFETIME_SECONDS = 7 * 86400  # 7 days (Doc 08 §4.3)
AUTH_COOKIE_NAME = "refresh_token"
AUTH_CHALLENGE_COOKIE_NAME = "auth_challenge"
LABFLOW_TOTP_ENCRYPTION_KEY = _require_env_secret(
    "LABFLOW_TOTP_ENCRYPTION_KEY",
    local_default=_COMMITTED_TOTP_KEY,
    forbidden=frozenset({_COMMITTED_TOTP_KEY}),
)

# Master dashboard Phase 1: founding-offer inventory (Doc 01 ADR-010).
# The overview endpoint reports used/total from real subscriptions plus these
# settings — the platform never hard-codes an offer size in code or UI.
PLATFORM_FOUNDING_SLOTS_TOTAL = env.int("PLATFORM_FOUNDING_SLOTS_TOTAL", default=0)
PLATFORM_FOUNDING_PLAN_NAME = env("PLATFORM_FOUNDING_PLAN_NAME", default="Founding")

# Platform base domain for on-demand TLS (Doc 04 §6.4): the TLS ask endpoint
# approves this apex plus tenant subdomains under it. Read from the
# environment — compose sets it to `localhost` locally. Without this line the
# ask only ever approved the hard-coded labflow.app apex and localhost got 404.
PLATFORM_BASE_DOMAIN = env("PLATFORM_BASE_DOMAIN", default="labflow.app")

SPECTACULAR_SETTINGS = {
    "TITLE": "LabFlow Platform API",
    "DESCRIPTION": "Diagnostic Laboratory Multi-Tenant SaaS Platform API",
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
    "COMPONENT_SPLIT_REQUEST": True,
}

# PostgreSQL supports 63-character identifiers (Doc 02 §7 & §18).
# Silence Django's 30-character Oracle compatibility check E034.
SILENCED_SYSTEM_CHECKS = ["models.E034"]

# Public report portal (KAN-156 / LAB-31): fixed-window throttle for the
# unauthenticated endpoints GET /api/v1/report-access/{token} and
# GET /api/v1/report-files/<sig>/ — requests per minute per client IP.
REPORT_ACCESS_RATE_LIMIT_PER_MINUTE = 60
REPORT_TOKEN_RATE_LIMIT_PER_10MIN = env.int(
    "REPORT_TOKEN_RATE_LIMIT_PER_10MIN", default=60
)
REPORT_INVALID_TOKEN_PER_HOUR = env.int("REPORT_INVALID_TOKEN_PER_HOUR", default=20)

# Rate-limit matrix (LAB-49 Phase 2.1, OWASP API4 G-1/G-2/G-3/G-7/G-14).
THROTTLE_READ_PER_MINUTE_USER = env.int("THROTTLE_READ_PER_MINUTE_USER", default=600)
THROTTLE_WRITE_PER_MINUTE_USER = env.int("THROTTLE_WRITE_PER_MINUTE_USER", default=300)
THROTTLE_WRITE_PER_MINUTE_TENANT = env.int(
    "THROTTLE_WRITE_PER_MINUTE_TENANT", default=3000
)
THROTTLE_TOTP_VERIFY_PER_15MIN = env.int("THROTTLE_TOTP_VERIFY_PER_15MIN", default=10)
THROTTLE_REFRESH_PER_MINUTE_IP = env.int("THROTTLE_REFRESH_PER_MINUTE_IP", default=30)
THROTTLE_DEMO_REQUEST_PER_HOUR_IP = env.int(
    "THROTTLE_DEMO_REQUEST_PER_HOUR_IP", default=5
)
THROTTLE_CALLBACK_PER_MINUTE_IP = env.int(
    "THROTTLE_CALLBACK_PER_MINUTE_IP", default=120
)
THROTTLE_EXPORT_PER_HOUR_TENANT = env.int("THROTTLE_EXPORT_PER_HOUR_TENANT", default=1)
THROTTLE_EXPORT_DOWNLOAD_PER_MINUTE_IP = env.int(
    "THROTTLE_EXPORT_DOWNLOAD_PER_MINUTE_IP", default=60
)

# Business-flow velocity caps (LAB-49 Phase 2.3, OWASP API6 A6-1/A6-2).
REFUND_MANAGER_DAILY_CAP = env("REFUND_MANAGER_DAILY_CAP", default="25000.00")
REFUND_VELOCITY_PER_INVOICE_HOUR = env.int(
    "REFUND_VELOCITY_PER_INVOICE_HOUR", default=3
)
DISCOUNT_OWNER_THRESHOLD_PKR = env("DISCOUNT_OWNER_THRESHOLD_PKR", default="10000.00")
DISCOUNT_OWNER_THRESHOLD_RATIO = env("DISCOUNT_OWNER_THRESHOLD_RATIO", default="0.25")

# Request body / array caps (LAB-49 Phase 2.4, API4 G-4/G-5).
DATA_UPLOAD_MAX_MEMORY_SIZE = env.int(
    "DATA_UPLOAD_MAX_MEMORY_SIZE", default=5 * 1024 * 1024
)
DATA_UPLOAD_MAX_NUMBER_FIELDS = env.int("DATA_UPLOAD_MAX_NUMBER_FIELDS", default=1000)
FILE_UPLOAD_MAX_MEMORY_SIZE = env.int(
    "FILE_UPLOAD_MAX_MEMORY_SIZE", default=5 * 1024 * 1024
)

# Settlement delivery via n8n (Doc 05 §9 DL-2, KAN-262 / LAB-43).
# Email delivery (LAB-49 Phase 4.5, API10 G10-6). Production refuses to boot
# without SMTP (config/settings/prod.py); tests override MAILERS with locmem.
# Django 6.1: SMTP options live in MAILERS["default"]["OPTIONS"]; the legacy
# EMAIL_HOST_* settings cannot coexist with MAILERS.
_EMAIL_HOST = env("EMAIL_HOST", default="")
MAILERS = {
    "default": {
        "BACKEND": env(
            "EMAIL_BACKEND",
            default="django.core.mail.backends.smtp.EmailBackend",
        ),
        "OPTIONS": {
            "host": _EMAIL_HOST,
            "port": env.int("EMAIL_PORT", default=587),
            "username": env("EMAIL_HOST_USER", default=""),
            "password": env("EMAIL_HOST_PASSWORD", default=""),
            "use_tls": env.bool("EMAIL_USE_TLS", default=True),
            "timeout": env.int("EMAIL_TIMEOUT", default=10),
        },
    }
}
DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL", default="no-reply@labflow.app")
FRONTEND_BASE_URL = env("FRONTEND_BASE_URL", default="")
FRONTEND_RESET_PATH = env("FRONTEND_RESET_PATH", default="/reset-password")

# N8N_WEBHOOK_URL: the n8n webhook that sends partner statement emails.
# Empty in dev/test — dispatch leaves rows PENDING until configured.
N8N_WEBHOOK_URL = env("N8N_WEBHOOK_URL", default="")
# HMAC-SHA256 secret for the signed Django -> n8n webhook protocol.
# Required (and distinct from SECRET_KEY) whenever a webhook URL is configured;
# the dev/test fallback is local-only (LAB-49 Phase 0.1).
_n8n_secret = env("N8N_WEBHOOK_SECRET", default="")
if not _n8n_secret and _IS_LOCAL_DEV:
    _n8n_secret = SECRET_KEY
if not _IS_LOCAL_DEV:
    if N8N_WEBHOOK_URL and not _n8n_secret:
        raise ImproperlyConfigured(
            "N8N_WEBHOOK_SECRET must be set when N8N_WEBHOOK_URL is configured."
        )
    if _n8n_secret and _n8n_secret == SECRET_KEY:
        raise ImproperlyConfigured(
            "N8N_WEBHOOK_SECRET must differ from DJANGO_SECRET_KEY (key separation)."
        )
N8N_WEBHOOK_SECRET = _n8n_secret
# Test/rehearsal seam: complete deliveries through the callback path
# without an n8n round-trip. Never True in production.
SETTLEMENT_DELIVERY_STUB = env.bool("SETTLEMENT_DELIVERY_STUB", default=False)

# Outbound webhook engine (Doc 06 §5; Doc 02 §8: service API keys in env only).
N8N_CALLBACK_KEY = env("N8N_CALLBACK_KEY", default="")
# Set during callback-key rotation; Django dual-accepts both keys (§5.5).
N8N_CALLBACK_KEY_NEXT = env("N8N_CALLBACK_KEY_NEXT", default="")
# Event → n8n webhook URL map (Doc 10 holds n8n configuration values).
N8N_WEBHOOK_URLS: dict[str, str] = {}
# LAB-49 Phase 4.2 (SE-43): require HMAC + timestamp on inbound callbacks.
N8N_CALLBACK_REQUIRE_SIGNATURE = env.bool(
    "N8N_CALLBACK_REQUIRE_SIGNATURE", default=False
)
# Allow http://localhost webhook targets for local dev only.
ALLOW_INSECURE_LOCAL_WEBHOOKS = env.bool(
    "ALLOW_INSECURE_LOCAL_WEBHOOKS", default=_IS_LOCAL_DEV
)

# Celery resource limits (LAB-49 Phase 2.6, API4 G-6): a hung render must not
# hold a worker slot forever, and PDF bursts must not starve delivery queues.
CELERY_TASK_TIME_LIMIT = env.int("CELERY_TASK_TIME_LIMIT", default=300)
CELERY_TASK_SOFT_TIME_LIMIT = env.int("CELERY_TASK_SOFT_TIME_LIMIT", default=240)
CELERY_TASK_ANNOTATIONS = {
    "reports.generate_pdf": {
        "time_limit": 120,
        "soft_time_limit": 110,
        "rate_limit": "30/m",
    },
    "reports.deliver": {"time_limit": 120, "rate_limit": "60/m"},
    "notifications.send_notification": {"time_limit": 60, "rate_limit": "60/m"},
    "referral_partners.deliver_settlement": {
        "time_limit": 120,
        "rate_limit": "30/m",
    },
    "tenants.export": {"time_limit": 600, "soft_time_limit": 540},
}

# Celery Beat Scheduled Tasks (Doc 02 §5.11, Doc 04 §13.2, Doc 08 §4.5)
CELERY_BEAT_SCHEDULE = {
    "accounts-cleanup-expired-tokens-daily": {
        "task": "accounts.cleanup_expired_tokens",
        "schedule": 86400.0,  # Run daily
    },
    # LAB-32 (KAN-157): retry FAILED report deliveries (Doc 02 §5.7).
    "reports-retry-failed-deliveries-15min": {
        "task": "reports.retry_failed_deliveries",
        "schedule": 900.0,  # Every 15 minutes
    },
    # LAB-41 (KAN-260): monthly settlement generation (Doc 05 §7.2 ST-1).
    # 1st of each month at 01:00 Asia/Karachi.
    "partners-generate-monthly-settlements": {
        "task": "referral_partners.generate_monthly_settlements",
        "schedule": crontab(minute=0, hour=1, day_of_month=1),
    },
    # LAB-43 (KAN-262): retry FAILED settlement deliveries (Doc 05 §9 DL-5).
    "partners-retry-failed-settlement-deliveries-15min": {
        "task": "partners.retry_failed_settlement_deliveries",
        "schedule": 900.0,  # Every 15 minutes
    },
    # LAB-44 (KAN-263): webhook retry sweep (Doc 06 §5.2, §12; Doc 10 §9).
    "webhooks-retry-pending-deliveries": {
        "task": "webhooks.retry_pending_deliveries",
        "schedule": crontab(minute="3,18,33,48"),
    },
    # LAB-45 (KAN-264): retry FAILED notification deliveries (Doc 06 §12.9).
    # Distinct from the webhook sweep; offsets per Doc 10 §9.
    "notifications-retry-pending-deliveries": {
        "task": "notifications.retry_pending_deliveries",
        "schedule": crontab(minute="11,26,41,56"),
    },
    # LAB-49 Phase 2.9: daily business-flow anomaly sweep (alert, never block).
    "security-anomaly-sweep-daily": {
        "task": "core.anomaly_sweep",
        "schedule": crontab(minute=30, hour=2),
    },
}
