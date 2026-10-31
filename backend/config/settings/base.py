"""Django base settings for LabFlow.

Architecture & Configuration per Docs 01, 02, 04, 08, 09.
"""

from pathlib import Path

import environ

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
