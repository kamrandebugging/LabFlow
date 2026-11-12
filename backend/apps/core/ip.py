"""Trusted-proxy aware client IP extraction (LAB-49 fix-up, security review).

The origin sits behind Caddy and, in production, Cloudflare. Only the
immediate peer may assert a client IP; a direct request must never have its
``X-Forwarded-For`` / ``CF-Connecting-IP`` trusted.

``TRUSTED_PROXY_CIDRS`` defaults to loopback + RFC1918 (Docker/Caddy peers).
A Cloudflare-proxied deployment MUST add Cloudflare's published ranges to this
setting (and to Caddy's ``trusted_proxies``); see docs/security/edge-hardening.md.
"""

from __future__ import annotations

import ipaddress
from functools import lru_cache
from typing import Any

from django.conf import settings

_DEFAULT_TRUSTED = "127.0.0.1/32,::1/128,10.0.0.0/8,172.16.0.0/12,192.168.0.0/16"


@lru_cache(maxsize=4)
def _networks(raw: str) -> tuple[ipaddress.IPv4Network | ipaddress.IPv6Network, ...]:
    networks = []
    for item in raw.split(","):
        value = item.strip()
        if not value:
            continue
        try:
            networks.append(ipaddress.ip_network(value, strict=False))
        except ValueError:
            continue
    return tuple(networks)


def _peer_is_trusted(remote: str, raw_cidrs: str) -> bool:
    try:
        address = ipaddress.ip_address(remote)
    except ValueError:
        return False
    return any(address in network for network in _networks(raw_cidrs))


def get_client_ip(request: Any) -> str:
    """Return the client IP, trusting forwarding headers only from a proxy."""
    meta = getattr(request, "META", {}) or {}
    remote = str(meta.get("REMOTE_ADDR") or "")
    cidrs = str(
        getattr(settings, "TRUSTED_PROXY_CIDRS", _DEFAULT_TRUSTED) or _DEFAULT_TRUSTED
    )
    if remote and _peer_is_trusted(remote, cidrs):
        cloudflare_ip = str(meta.get("HTTP_CF_CONNECTING_IP") or "").strip()
        if cloudflare_ip:
            return cloudflare_ip
        forwarded = str(meta.get("HTTP_X_FORWARDED_FOR") or "")
        if forwarded:
            # Caddy appends the immediate peer; the last hop is the trusted one.
            return forwarded.split(",")[-1].strip()
    return remote or "unknown"
