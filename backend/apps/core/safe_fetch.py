"""One safe outbound HTTP client (LAB-49 Phase 4.1/4.7, OWASP API7/API10).

Every server-side POST the application makes goes through :func:`post`:

- scheme allow-list: HTTPS only (plain HTTP only for an explicitly allowed
  local development webhook),
- the hostname is resolved and **every** resolved address must be globally
  routable (``ipaddress.is_global``) — loopback, RFC1918, link-local,
  CGNAT, documentation and multicast ranges are rejected before connecting,
- redirects are never followed,
- the response body is capped (default 1 MB) and timeouts are mandatory,
- upstream responses are never returned to an end user.

Residual risk (documented, not hidden): this is a v1 pin-at-validation
implementation. A determined DNS-rebinding attacker can still win the
resolution race between validation and connect; the egress firewall backstop
and the fixed n8n host allowlist are the second layer. There is no
caller-supplied URL fetch anywhere in LabFlow today, so this is a loaded-gun
guard, not a live vulnerability fix.
"""

from __future__ import annotations

import ipaddress
import socket
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

import requests
from django.conf import settings

MAX_RESPONSE_BYTES = 1024 * 1024
ALLOWED_SCHEMES = frozenset({"https"})


class UnsafeURLError(ValueError):
    """The destination violated the outbound allow-list."""


class SafeFetchError(RuntimeError):
    """The outbound call failed at the transport layer."""


@dataclass
class SafeResponse:
    status_code: int
    content: bytes

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise SafeFetchError(f"upstream returned HTTP {self.status_code}")


def _local_dev_hosts() -> set[str]:
    if not getattr(settings, "ALLOW_INSECURE_LOCAL_WEBHOOKS", False):
        return set()
    return {"localhost", "127.0.0.1", "::1"}


def validate_url(url: str, *, resolve: bool = True) -> str:
    """Validate scheme (+ resolved destination when ``resolve`` is true)."""
    parsed = urlparse(url or "")
    if not parsed.scheme or not parsed.hostname:
        raise UnsafeURLError("webhook URL is not an absolute URL.")

    host = parsed.hostname.lower()
    local_ok = host in _local_dev_hosts()
    if parsed.scheme not in ALLOWED_SCHEMES and not (
        local_ok and parsed.scheme == "http"
    ):
        raise UnsafeURLError(f"scheme {parsed.scheme!r} is not allowed.")

    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    if not resolve:
        return url
    try:
        infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise UnsafeURLError(f"cannot resolve {host!r}: {exc}") from exc

    addresses = {info[4][0] for info in infos}
    if not addresses:
        raise UnsafeURLError(f"{host!r} resolved to no addresses.")
    for raw in addresses:
        address = ipaddress.ip_address(raw)
        if local_ok and (address.is_loopback or address.is_private):
            continue
        if not address.is_global:
            raise UnsafeURLError(f"{host!r} resolves to non-public address {raw!r}.")
    return url


def post(
    url: str,
    *,
    data: bytes | str | None = None,
    json_body: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    timeout: int = 15,
) -> SafeResponse:
    """POST to a validated destination; never follow redirects."""
    validate_url(url)
    try:
        response = requests.post(
            url,
            data=data,
            json=json_body,
            headers=headers,
            timeout=timeout,
            allow_redirects=False,
            stream=True,
        )
    except requests.RequestException as exc:
        raise SafeFetchError(str(exc)) from exc

    body = b""
    try:
        for chunk in response.iter_content(chunk_size=64 * 1024):
            body += chunk
            if len(body) > MAX_RESPONSE_BYTES:
                raise SafeFetchError("upstream response exceeded the 1 MB cap.")
    except requests.RequestException as exc:
        raise SafeFetchError(str(exc)) from exc
    finally:
        response.close()
    return SafeResponse(status_code=response.status_code, content=body)


def validate_configured_webhooks(*, resolve: bool = True) -> None:
    """Fail loudly on a misconfigured webhook URL (startup check)."""
    candidates = []
    single = str(getattr(settings, "N8N_WEBHOOK_URL", "") or "")
    if single:
        candidates.append(single)
    for url in (getattr(settings, "N8N_WEBHOOK_URLS", None) or {}).values():
        if url:
            candidates.append(str(url))
    for candidate in candidates:
        validate_url(candidate, resolve=resolve)
