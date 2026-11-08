"""Django base settings for LabFlow.

Architecture & Configuration per Docs 01, 02, 04, 08, 09.
"""

from pathlib import Path

import environ
from celery.schedules import crontab

BASE_DIR = Path(__file__).resolve().parent.parent.parent

env = environ.Env()
environ.Env.read_env(BASE_DIR / ".env")

SECRET_KEY = env(
    "DJANGO_SECRET_KEY", default="django-insecure-dev-key-change-in-production"
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
    "django_tenants.middleware.main.TenantMainMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    # LAB-36 (Doc 04 §11.2): subscription read-only enforcement after auth.
    "apps.platform.middleware.SubscriptionReadOnlyMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

# -----------------------------------------------------------------------------
# Database Configuration (Docs 01 §6, 02 §2, 04 §6.1)
# -----------------------------------------------------------------------------

DATABASES = {
    "default": env.db(
        "DATABASE_URL",
        default="postgres://postgres:postgres@localhost:5432/labflow",
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
        "rest_framework.authentication.SessionAuthentication",
    ),
    "DEFAULT_PERMISSION_CLASSES": ("rest_framework.permissions.IsAuthenticated",),
    # Problem+JSON for the Layer-3 scope refusal (Doc 04 §8.5, BS-2);
    # every other exception keeps DRF's default rendering.
    "EXCEPTION_HANDLER": "apps.core.exceptions.problem_json_exception_handler",
}

# -----------------------------------------------------------------------------
# Security & Auth Engine Configuration (Doc 01 §14, Doc 08 §4, Doc 08 §10)
# -----------------------------------------------------------------------------

PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.Argon2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2SHA1PasswordHasher",
]

JWT_SIGNING_KEY = env("JWT_SIGNING_KEY", default=SECRET_KEY)
JWT_ACCESS_TOKEN_LIFETIME_SECONDS = 900  # 15 minutes (Doc 08 §4.3)
JWT_REFRESH_TOKEN_LIFETIME_SECONDS = 7 * 86400  # 7 days (Doc 08 §4.3)
AUTH_COOKIE_NAME = "refresh_token"
AUTH_CHALLENGE_COOKIE_NAME = "auth_challenge"
LABFLOW_TOTP_ENCRYPTION_KEY = env(
    "LABFLOW_TOTP_ENCRYPTION_KEY",
    default="sb_wYl5m_YtxnHje0H4_ZEZ35_8mNfguSqqV897s_ts=",
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

# Settlement delivery via n8n (Doc 05 §9 DL-2, KAN-262 / LAB-43).
# N8N_WEBHOOK_URL: the n8n webhook that sends partner statement emails.
# Empty in dev/test — dispatch leaves rows PENDING until configured.
N8N_WEBHOOK_URL = env("N8N_WEBHOOK_URL", default="")
# HMAC-SHA256 secret for the signed Django -> n8n webhook protocol.
N8N_WEBHOOK_SECRET = env("N8N_WEBHOOK_SECRET", default=SECRET_KEY)
# Test/rehearsal seam: complete deliveries through the callback path
# without an n8n round-trip. Never True in production.
SETTLEMENT_DELIVERY_STUB = env.bool("SETTLEMENT_DELIVERY_STUB", default=False)

# Outbound webhook engine (Doc 06 §5; Doc 02 §8: service API keys in env only).
N8N_CALLBACK_KEY = env("N8N_CALLBACK_KEY", default="")
# Set during callback-key rotation; Django dual-accepts both keys (§5.5).
N8N_CALLBACK_KEY_NEXT = env("N8N_CALLBACK_KEY_NEXT", default="")
# Event → n8n webhook URL map (Doc 10 holds n8n configuration values).
N8N_WEBHOOK_URLS: dict[str, str] = {}

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
}
