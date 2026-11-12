"""Shared fixed-window throttles (LAB-49 Phase 2.1, OWASP API4 / API6).

All counters live in the configured Django cache (Redis in production), so the
limit is shared across workers. Keys include the tenant schema so one tenant's
burst never consumes another's budget.

Every throttle answers ``429`` through DRF's ``Throttled`` exception, which the
project exception handler renders with a ``Retry-After`` header and the stable
``rate_limited`` error code.
"""

from __future__ import annotations

import hashlib
import time
from typing import Any

from django.conf import settings
from django.core.cache import cache
from rest_framework.throttling import BaseThrottle

SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})
_WINDOW_SECONDS = 60


def _tenant_key() -> str:
    from django.db import connection

    return str(getattr(connection, "schema_name", "") or "public")


def _client_ip(request: Any) -> str:
    meta = getattr(request, "META", {}) or {}
    # Caddy appends the real peer; the last hop is the trusted one.
    forwarded = meta.get("HTTP_X_FORWARDED_FOR", "")
    if forwarded:
        return forwarded.split(",")[-1].strip() or "unknown"
    return meta.get("REMOTE_ADDR") or "unknown"


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:24]


class FixedWindowThrottle(BaseThrottle):
    """One cache counter per ``(scope, ident, window bucket)``.

    ``rate_setting`` names a settings attribute holding requests-per-window;
    ``window_seconds`` defaults to one minute. ``ident`` may be overridden.
    """

    scope: str = "default"
    rate_setting: str = "THROTTLE_READ_PER_MINUTE_USER"
    window_seconds: int = _WINDOW_SECONDS
    methods: frozenset[str] | None = None

    def get_ident(self, request: Any) -> str:
        user = getattr(request, "user", None)
        user_id = (
            getattr(user, "id", None)
            if getattr(user, "is_authenticated", False)
            else None
        )
        if user_id:
            return f"user:{user_id}"
        return f"ip:{_client_ip(request)}"

    def get_limit(self) -> int:
        return int(getattr(settings, self.rate_setting, 0) or 0)

    def allow_request(self, request: Any, view: Any) -> bool:
        if self.methods is not None and request.method not in self.methods:
            return True
        limit = self.get_limit()
        if limit <= 0:
            return True

        now = time.time()
        bucket = int(now // self.window_seconds)
        self.retry_after = max(
            1, int(self.window_seconds - (now % self.window_seconds))
        )
        key = (
            f"throttle:{self.scope}:{_tenant_key()}:{self.get_ident(request)}:{bucket}"
        )
        try:
            if cache.add(key, 1, timeout=self.window_seconds + 1):
                count = 1
            else:
                count = int(cache.incr(key))
        except Exception:
            # Fail closed: a cache outage must not remove the limit entirely.
            count = limit + 1
        return count <= limit

    def wait(self) -> int | None:
        return getattr(self, "retry_after", None)


class ReadThrottle(FixedWindowThrottle):
    """600 reads/min/user (tenant-configurable) — API4 G-1."""

    scope = "read_user"
    rate_setting = "THROTTLE_READ_PER_MINUTE_USER"
    methods = frozenset({"GET", "HEAD"})


class WriteThrottle(FixedWindowThrottle):
    """300 writes/min/user — API4 G-1."""

    scope = "write_user"
    rate_setting = "THROTTLE_WRITE_PER_MINUTE_USER"
    methods = frozenset({"POST", "PUT", "PATCH", "DELETE"})


class TenantWriteThrottle(FixedWindowThrottle):
    """3,000 writes/min for the whole tenant — bounds a compromised tenant."""

    scope = "write_tenant"
    rate_setting = "THROTTLE_WRITE_PER_MINUTE_TENANT"
    methods = frozenset({"POST", "PUT", "PATCH", "DELETE"})

    def get_ident(self, request: Any) -> str:
        return _tenant_key()


class TotpVerifyThrottle(FixedWindowThrottle):
    """10 TOTP verifications / 15 min / account, independent of challenges.

    Keyed on the submitted email (or challenge token when the email is not
    supplied) so a fresh login cannot reset the counter (API4 G-2).
    """

    scope = "totp_verify"
    rate_setting = "THROTTLE_TOTP_VERIFY_PER_15MIN"
    window_seconds = 15 * 60

    def get_ident(self, request: Any) -> str:
        data = getattr(request, "data", {}) or {}
        email = data.get("email") or getattr(request, "query_params", {}).get("email")
        if not email:
            challenge = (getattr(request, "COOKIES", {}) or {}).get(
                "auth_challenge"
            ) or ""
            email = f"challenge:{challenge}"
        return f"email:{_digest(str(email).strip().lower())}"


class RefreshThrottle(FixedWindowThrottle):
    """30 refresh attempts/min/IP (API2 A2-6)."""

    scope = "auth_refresh"
    rate_setting = "THROTTLE_REFRESH_PER_MINUTE_IP"
    window_seconds = 60

    def get_ident(self, request: Any) -> str:
        return f"ip:{_client_ip(request)}"


class DemoRequestThrottle(FixedWindowThrottle):
    """5 public demo-request submissions/hour/IP (API6 A6-5)."""

    scope = "demo_request"
    rate_setting = "THROTTLE_DEMO_REQUEST_PER_HOUR_IP"
    window_seconds = 60 * 60

    def get_ident(self, request: Any) -> str:
        return f"ip:{_client_ip(request)}"


class CallbackThrottle(FixedWindowThrottle):
    """120 callback requests/min/IP — unthrottled key guessing (API7 G-14)."""

    scope = "callback"
    rate_setting = "THROTTLE_CALLBACK_PER_MINUTE_IP"
    window_seconds = 60

    def get_ident(self, request: Any) -> str:
        return f"ip:{_client_ip(request)}"


class ExportThrottle(FixedWindowThrottle):
    """1 export request/hour/tenant (API4 G-3)."""

    scope = "export_request"
    rate_setting = "THROTTLE_EXPORT_PER_HOUR_TENANT"
    window_seconds = 60 * 60

    def get_ident(self, request: Any) -> str:
        return _tenant_key()


class ExportDownloadThrottle(FixedWindowThrottle):
    """60 signed-export downloads/min/IP (API4 G-3)."""

    scope = "export_download"
    rate_setting = "THROTTLE_EXPORT_DOWNLOAD_PER_MINUTE_IP"
    window_seconds = 60

    def get_ident(self, request: Any) -> str:
        return f"ip:{_client_ip(request)}"
