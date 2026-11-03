"""Read-only mode enforcement middleware (Doc 04 §11.2).

Placed after AuthenticationMiddleware. For tenant-scoped requests, computes
`tenant_access_mode(tenant)`; when "read_only", every write (POST/PUT/PATCH/
DELETE) returns 403 subscription_read_only with three exemptions:

1. Patient report-access (TP-8) — public report portal links keep working.
2. The Owner's data export — a tenant that cannot pay must still leave
   with its data.
3. Platform actions — platform endpoints are not tenant writes.
"""

import re
from collections.abc import Callable
from typing import Any

from django.http import HttpRequest, JsonResponse

from apps.platform.access import tenant_access_mode

# Paths exempt from the read-only write gate (Doc 04 §11.2).
_EXEMPT_PATH_PATTERNS: tuple[re.Pattern[str], ...] = (
    # 1. Patient report-access (TP-8): public portal, signed links.
    re.compile(r"^/api/v1/reports/access/"),
    re.compile(r"^/api/v1/public/reports/"),
    # 2. Owner data export: leaving with your data is not a tenant write.
    re.compile(r"^/api/v1/exports"),
    # 3. Platform actions: apex-host platform API, not tenant writes.
    re.compile(r"^/api/v1/platform/"),
    re.compile(r"^/platform/"),
)

_WRITE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})

_PROBLEM_JSON = "application/problem+json"


def _is_exempt(path: str) -> bool:
    return any(p.match(path) for p in _EXEMPT_PATH_PATTERNS)


class SubscriptionReadOnlyMiddleware:
    """Block tenant writes when the subscription is in read-only mode."""

    def __init__(self, get_response: Callable[[HttpRequest], Any]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> Any:
        tenant = getattr(request, "tenant", None)
        if (
            tenant is not None
            and request.method in _WRITE_METHODS
            and not _is_exempt(request.path)
        ):
            try:
                mode = tenant_access_mode(tenant)
            except Exception:
                mode = "read_only"
            if mode == "read_only":
                return JsonResponse(
                    {
                        "type": "https://labflow.example/problems/subscription-read-only",
                        "title": "Subscription read-only",
                        "status": 403,
                        "detail": (
                            "This tenant's subscription is past due. "
                            "Writes are disabled until the subscription "
                            "is reactivated."
                        ),
                        "code": "subscription_read_only",
                        "errors": {},
                    },
                    status=403,
                    content_type=_PROBLEM_JSON,
                )
        return self.get_response(request)
