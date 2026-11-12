"""Production settings (LAB-49 Phase 3.4, OWASP API8 A8-6).

Compose and gunicorn point at this module. Importing it asserts the hardened
posture: DEBUG off, no local-only hosts, real secrets present and separated,
HTTPS redirect + HSTS on, docs off, step-up on.
"""

from __future__ import annotations

import ipaddress

from django.core.exceptions import ImproperlyConfigured

from .base import *  # noqa: F403

DEBUG = False
DOCS_ENABLED = False
STEP_UP_ENABLED = True
N8N_CALLBACK_REQUIRE_SIGNATURE = True
ALLOW_INSECURE_LOCAL_WEBHOOKS = False
HIBP_ENABLED = True
# Force the transport posture regardless of a stray local .env.
SECURE_SSL_REDIRECT = True
SECURE_HSTS_SECONDS = 63072000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True

# Local-only hostnames must never appear in a production allowlist.
_ALLOWED = {"localhost", "127.0.0.1", ".localhost", "testserver", "*"}
for _host in ALLOWED_HOSTS:  # noqa: F405
    if str(_host).strip() in _ALLOWED:
        raise ImproperlyConfigured(f"DJANGO_ALLOWED_HOSTS contains {_host!r}.")

if not ALLOWED_HOSTS:  # noqa: F405
    raise ImproperlyConfigured("DJANGO_ALLOWED_HOSTS must be set in production.")

if JWT_SIGNING_KEY == SECRET_KEY:  # noqa: F405
    raise ImproperlyConfigured("JWT_SIGNING_KEY must differ from DJANGO_SECRET_KEY.")

try:
    from cryptography.fernet import Fernet

    Fernet(LABFLOW_TOTP_ENCRYPTION_KEY.encode())  # noqa: F405
except Exception as exc:  # noqa: BLE001
    raise ImproperlyConfigured(
        "LABFLOW_TOTP_ENCRYPTION_KEY must be a valid Fernet key."
    ) from exc

if not SECURE_SSL_REDIRECT or SECURE_HSTS_SECONDS < 31536000:  # noqa: F405
    raise ImproperlyConfigured(
        "Production requires SECURE_SSL_REDIRECT and HSTS >= 1 year."
    )

if N8N_CALLBACK_REQUIRE_SIGNATURE and not N8N_CALLBACK_HMAC_SECRET:  # noqa: F405
    raise ImproperlyConfigured(
        "N8N_CALLBACK_HMAC_SECRET must be set when callback signatures are required."
    )

if not MAILERS["default"]["OPTIONS"].get("host"):  # noqa: F405
    raise ImproperlyConfigured(
        "EMAIL_HOST must be configured: password reset and activation mail "
        "are security controls (API10 G10-6)."
    )

# Optional explicit assertion that DB hosts are not loopback.
_db_host = str(DATABASES["default"].get("HOST") or "")  # noqa: F405
if _db_host:
    try:
        if ipaddress.ip_address(_db_host).is_loopback:
            raise ImproperlyConfigured("DATABASE_URL points at loopback in prod.")
    except ValueError:
        if _db_host in {"localhost", "127.0.0.1"}:
            raise ImproperlyConfigured(
                "DATABASE_URL points at localhost in prod."
            ) from None
