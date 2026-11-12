"""Cross-cutting security middleware (LAB-49 Phase 3.1/3.2/3.6, Phase 5.7).

- :class:`PayloadLimitMiddleware` — 413 before DRF parses an oversize body.
- :class:`SecurityHeadersMiddleware` — CSP (report-only), Permissions-Policy,
  COOP/CORP and ``Cache-Control: no-store`` on API JSON responses.
- :class:`InternalPathMiddleware` — ``/internal/*`` is refused for public
  source addresses even when Caddy is bypassed.
- :class:`DocsGateMiddleware` — API docs/schema are off unless explicitly on.
- :class:`OriginCheckMiddleware` — cookie-bearing auth routes reject a
  cross-site ``Origin`` header.
"""

from __future__ import annotations

import ipaddress
from typing import Any
from urllib.parse import urlparse

from django.conf import settings
from django.http import HttpResponse, JsonResponse

_ERROR_413 = {
    "error": {
        "code": "payload_too_large",
        "message": "Request body exceeds the configured limit.",
    }
}
_ERROR_404 = {"error": {"code": "not_found", "message": "Not found."}}
_ERROR_403 = {
    "error": {"code": "forbidden", "message": "Cross-origin request refused."}
}

_CSP_REPORT_ONLY = (
    "default-src 'self'; "
    "img-src 'self' data:; "
    "style-src 'self' 'unsafe-inline'; "
    "script-src 'self'; "
    "connect-src 'self'; "
    "frame-ancestors 'none'; "
    "base-uri 'self'; "
    "form-action 'self'"
)
_PERMISSIONS_POLICY = (
    "camera=(), microphone=(), geolocation=(), payment=(), usb=(), interest-cohort=()"
)


class PayloadLimitMiddleware:
    """Reject bodies larger than ``DATA_UPLOAD_MAX_MEMORY_SIZE`` with 413."""

    def __init__(self, get_response: Any) -> None:
        self.get_response = get_response

    def __call__(self, request: Any) -> HttpResponse:
        limit = int(getattr(settings, "DATA_UPLOAD_MAX_MEMORY_SIZE", 0) or 0)
        content_length = getattr(request, "content_length", None)
        if content_length is None:
            raw_length = (getattr(request, "META", {}) or {}).get("CONTENT_LENGTH")
            try:
                content_length = int(raw_length) if raw_length else None
            except (TypeError, ValueError):
                content_length = None
        if limit and content_length is not None and content_length > limit:
            return JsonResponse(_ERROR_413, status=413)
        return self.get_response(request)


class SecurityHeadersMiddleware:
    """Headers Django does not emit by itself, plus no-store for API JSON."""

    def __init__(self, get_response: Any) -> None:
        self.get_response = get_response

    def __call__(self, request: Any) -> HttpResponse:
        response = self.get_response(request)
        response.setdefault("Content-Security-Policy-Report-Only", _CSP_REPORT_ONLY)
        response.setdefault("Permissions-Policy", _PERMISSIONS_POLICY)
        response.setdefault("Cross-Origin-Opener-Policy", "same-origin")
        response.setdefault("Cross-Origin-Resource-Policy", "same-origin")
        response.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        path = getattr(request, "path", "")
        if path.startswith("/api/"):
            response.setdefault("Cache-Control", "no-store, no-cache")
            response.setdefault("Pragma", "no-cache")
        return response


def _is_public_address(remote_addr: str | None) -> bool:
    """True only for a clearly public source address."""
    if not remote_addr:
        return True
    try:
        address = ipaddress.ip_address(remote_addr)
    except ValueError:
        return True
    return not (address.is_private or address.is_loopback or address.is_link_local)


class InternalPathMiddleware:
    """Refuse ``/internal/*`` to public clients; Caddy is not the only gate."""

    def __init__(self, get_response: Any) -> None:
        self.get_response = get_response

    def __call__(self, request: Any) -> HttpResponse:
        path = getattr(request, "path", "")
        if path.startswith("/internal/"):
            remote = (getattr(request, "META", {}) or {}).get("REMOTE_ADDR")
            if _is_public_address(str(remote) if remote else None):
                return JsonResponse(_ERROR_404, status=404)
        return self.get_response(request)


class DocsGateMiddleware:
    """Disable interactive docs/schema unless ``DOCS_ENABLED`` is true."""

    _PATHS = ("/api/schema", "/api/docs", "/api/redoc")

    def __init__(self, get_response: Any) -> None:
        self.get_response = get_response

    def __call__(self, request: Any) -> HttpResponse:
        if not getattr(settings, "DOCS_ENABLED", False):
            path = getattr(request, "path", "")
            if any(path.startswith(prefix) for prefix in self._PATHS):
                return JsonResponse(_ERROR_404, status=404)
        return self.get_response(request)


class OriginCheckMiddleware:
    """Reject cookie-bearing auth POSTs whose ``Origin`` is cross-site.

    Non-browser clients typically omit ``Origin``; that is accepted. A present
    ``Origin`` must match the request host (same scheme/host[:port]). This is
    defence in depth on top of ``SameSite=Lax`` (API2 A2-9, Phase 5.7).
    """

    _PATHS = (
        "/api/v1/auth/login",
        "/api/v1/auth/refresh",
        "/api/v1/auth/totp/verify",
    )

    def __init__(self, get_response: Any) -> None:
        self.get_response = get_response

    def __call__(self, request: Any) -> HttpResponse:
        path = getattr(request, "path", "")
        if request.method == "POST" and any(
            path == prefix or path == prefix + "/" for prefix in self._PATHS
        ):
            origin = request.META.get("HTTP_ORIGIN")
            if origin:
                parsed = urlparse(origin)
                host = request.get_host().split(":")[0]
                if parsed.hostname != host:
                    return JsonResponse(_ERROR_403, status=403)
        return self.get_response(request)
