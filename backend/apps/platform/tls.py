"""TLS Ask Endpoint implementation (Doc 04 §6.4 & §15.3, Doc 01 §15).

Caddy calls GET /internal/tls-check?domain=<host> before issuing certs.
The apex is pre-approved; non-apex must be one label under base domain
and registered to an active/provisioning/suspended tenant. Negative answers
are cached for 60s in Redis. Miss bursts are counted and alerted (Doc 04 §17).
"""

import logging
import re
from datetime import UTC, datetime
from typing import Final

from django.conf import settings
from django.core.cache import cache
from django.http import HttpRequest, HttpResponse

from apps.core.models import Domain, Tenant

logger = logging.getLogger(__name__)

APEX_FIXED_HOST: Final[str] = "labflow.app"
MAX_DNS_LABEL_LENGTH: Final[int] = 63  # RFC 1035 §2.3.4
NEGATIVE_CACHE_PREFIX: Final[str] = "platform:tls-ask:miss:"
NEGATIVE_CACHE_TTL: Final[int] = 60  # seconds (Doc 04 §6.4)
HOURLY_MISS_PREFIX: Final[str] = "platform:tls-ask:misses:"
HOURLY_MISS_TTL: Final[int] = 7200  # 2 hours
TLS_BURST_ALERT_THRESHOLD: int = 100  # misses per hour threshold (Doc 04 §17)

LABEL_REGEX: Final[re.Pattern[str]] = re.compile(r"^[a-z0-9](?:[a-z0-9-]*[a-z0-9])?$")

AUTHORIZED_TENANT_STATUSES: Final[tuple[str, ...]] = (
    Tenant.Status.PROVISIONING,
    Tenant.Status.ACTIVE,
    Tenant.Status.SUSPENDED,
)


def get_allowed_base_domains() -> tuple[str, ...]:
    """Return sorted allowed base domains (longest suffix first)."""
    raw_base = getattr(settings, "PLATFORM_BASE_DOMAIN", None) or APEX_FIXED_HOST
    configured = str(raw_base).strip().rstrip(".").lower()
    bases = {APEX_FIXED_HOST, configured}
    return tuple(sorted(bases, key=len, reverse=True))


def get_hourly_miss_key(now: datetime | None = None) -> str:
    """Return cache key for current hour's miss counter."""
    current_time = now or datetime.now(UTC)
    hour_str = current_time.strftime("%Y%m%d%H")
    return f"{HOURLY_MISS_PREFIX}{hour_str}"


def record_miss(host: str) -> None:
    """Record negative cache entry and increment miss monitoring counter."""
    try:
        cache.set(f"{NEGATIVE_CACHE_PREFIX}{host}", "1", timeout=NEGATIVE_CACHE_TTL)
    except Exception as exc:
        logger.warning(
            "tls_ask_cache_set_failed: Could not set negative cache for %s: %s",
            host,
            exc,
        )

    hourly_key = get_hourly_miss_key()
    miss_count = 1
    try:
        miss_count = cache.incr(hourly_key)
    except ValueError:
        try:
            if not cache.add(hourly_key, 1, timeout=HOURLY_MISS_TTL):
                try:
                    miss_count = cache.incr(hourly_key)
                except (ValueError, Exception):
                    miss_count = 1
            else:
                miss_count = 1
        except Exception as exc:
            logger.warning(
                "tls_ask_cache_add_failed: Cache add failed for %s: %s",
                hourly_key,
                exc,
            )
            miss_count = 1
    except Exception as exc:
        logger.warning(
            "tls_ask_cache_incr_failed: Cache incr error during miss recording: %s",
            exc,
        )
        miss_count = 1

    # Alert on threshold boundary and periodic intervals to avoid log flooding
    if miss_count == TLS_BURST_ALERT_THRESHOLD or (
        miss_count > TLS_BURST_ALERT_THRESHOLD and miss_count % 100 == 0
    ):
        logger.warning(
            "tls_ask_miss_burst: TLS ask miss burst detected "
            "(count=%d >= threshold=%d) for host=%s",
            miss_count,
            TLS_BURST_ALERT_THRESHOLD,
            host,
        )


def get_hourly_miss_count(now: datetime | None = None) -> int:
    """Return the number of TLS ask misses recorded in the current hour."""
    hourly_key = get_hourly_miss_key(now)
    try:
        count = cache.get(hourly_key)
    except Exception as exc:
        logger.warning(
            "tls_ask_cache_get_failed: Cache get error for %s: %s",
            hourly_key,
            exc,
        )
        return 0

    if count is None:
        return 0
    try:
        return int(count)
    except (TypeError, ValueError):
        return 0


def is_valid_label(label: str) -> bool:
    """Validate RFC 1035 / RFC 1123 DNS subdomain label format."""
    if not label or len(label) > MAX_DNS_LABEL_LENGTH:
        return False
    return bool(LABEL_REGEX.match(label))


def is_apex_domain(host: str) -> bool:
    """Check if host matches fixed allow-list apex or configured platform apex."""
    return host in get_allowed_base_domains()


def extract_subdomain_label(host: str) -> str | None:
    """Extract and validate single-label subdomain under platform base domain.

    Returns the label if exactly one label under base domain, else None.
    """
    for base in get_allowed_base_domains():
        suffix = f".{base}"
        if host.endswith(suffix):
            label = host[: -len(suffix)]
            if "." not in label and is_valid_label(label):
                return label

    return None


def verify_tls_domain(host: str) -> bool:
    """Evaluate host authorization for on-demand TLS certificate issuance.

    Returns True (200) iff host is apex or one-label-under-base registered to a
    non-deleted tenant; else False (404).
    """
    # 1. Pre-approved apex allow-list (Doc 04 §6.4: constant in code)
    if is_apex_domain(host):
        return True

    # 2. Negative cache lookup (F-7: repeated scans short-circuit immediately)
    try:
        if cache.get(f"{NEGATIVE_CACHE_PREFIX}{host}") is not None:
            return False
    except Exception as exc:
        logger.warning(
            "tls_ask_cache_check_failed: Cache read error for %s: %s",
            host,
            exc,
        )

    # 3. Strict one-label subdomain structure check (F-7: no nested subdomains)
    label = extract_subdomain_label(host)
    if label is None:
        record_miss(host)
        return False

    # 4. Database lookup: Domain must exist for valid tenant status
    exists = Domain.objects.filter(
        domain=host,
        tenant__status__in=AUTHORIZED_TENANT_STATUSES,
    ).exists()

    if exists:
        return True

    # Unknown domain or deleted tenant -> record negative cache and miss counter
    record_miss(host)
    return False


def tls_check_view(request: HttpRequest) -> HttpResponse:
    """GET /internal/tls-check?domain=<host> ask endpoint for Caddy on-demand TLS."""
    if request.method != "GET":
        return HttpResponse(status=404)

    raw_domain = request.GET.get("domain", "")
    if not isinstance(raw_domain, str) or not raw_domain.strip():
        return HttpResponse(status=404)

    host = raw_domain.strip().rstrip(".").lower()
    if not host:
        return HttpResponse(status=404)

    if verify_tls_domain(host):
        return HttpResponse(status=200)

    return HttpResponse(status=404)
