"""Central tenant role policy — deny-by-default (LAB-49 Phase 1.3, API5 BFLA).

Every authenticated tenant route declares which roles may call it. The policy
is keyed by Django URL name (and HTTP method), not by view class, so the same
table works across the slash/no-slash route twins and can be diffed against the
live URLconf by the API-inventory command.

Enforcement lives in :class:`apps.accounts.authentication.JWTAuthentication`:
it runs for every JWT-authenticated request regardless of a view's
``permission_classes``, so a route that forgets its inline role check is still
denied. A URL name with no entry is denied (deny-by-default); public
(capability-token) routes are listed explicitly and never authenticate.

On every denial one append-only ``AuditLog`` row (``auth.access_denied``) is
written best-effort — probing leaves a trail (SE-13 second half).
"""

from __future__ import annotations

import logging
import uuid
from typing import Any, Final

logger = logging.getLogger(__name__)

ROLE_OWNER: Final[str] = "owner"
ROLE_MANAGER: Final[str] = "manager"
ROLE_RECEPTION: Final[str] = "reception"
ROLE_TECHNICIAN: Final[str] = "technician"
ROLE_PATHOLOGIST: Final[str] = "pathologist"

ALL_STAFF: frozenset[str] = frozenset(
    {ROLE_OWNER, ROLE_MANAGER, ROLE_RECEPTION, ROLE_TECHNICIAN, ROLE_PATHOLOGIST}
)
ADMIN: frozenset[str] = frozenset({ROLE_OWNER, ROLE_MANAGER})
FRONT_DESK: frozenset[str] = frozenset({ROLE_OWNER, ROLE_MANAGER, ROLE_RECEPTION})
OWNER_ONLY: frozenset[str] = frozenset({ROLE_OWNER})

#: URL name -> HTTP method -> allowed roles. Names are the canonical Django
#: names; the ``*-slash`` twin is normalised before lookup.
ROLE_POLICY: Final[dict[str, dict[str, frozenset[str]]]] = {
    # --- Session / self-service (any authenticated staff member) -------------
    "auth-logout": {"POST": ALL_STAFF},
    "auth-totp-enroll": {"POST": ALL_STAFF},
    "auth-totp-enroll-confirm": {"POST": ALL_STAFF},
    "auth-totp-disable": {"POST": ALL_STAFF},
    "auth-totp-verify": {"POST": ALL_STAFF},
    "auth-sessions-list": {"GET": ALL_STAFF},
    "auth-sessions-revoke-all": {"POST": ALL_STAFF},
    "auth-session-detail": {"DELETE": ALL_STAFF},
    "auth-password-change": {"POST": ALL_STAFF},
    "auth-tenant": {"GET": ALL_STAFF},
    # --- Patients ------------------------------------------------------------
    # Decision (Doc 03 §6.6, recorded 2026-11-12): patient reads are all-staff
    # because technicians/pathologists need patient context for samples and
    # results. PII fields are masked per role by the serializers (Phase 5.2).
    "patient-list-create": {"GET": ALL_STAFF, "POST": FRONT_DESK},
    "patient-detail": {
        "GET": ALL_STAFF,
        "PATCH": FRONT_DESK,
        "DELETE": OWNER_ONLY,
    },
    "patient-history": {"GET": ALL_STAFF},
    # --- Catalog -------------------------------------------------------------
    "test-list-create": {"GET": ALL_STAFF, "POST": OWNER_ONLY},
    "test-detail": {"GET": ALL_STAFF, "PATCH": OWNER_ONLY, "DELETE": OWNER_ONLY},
    "test-prices": {
        "GET": frozenset({ROLE_OWNER, ROLE_MANAGER, ROLE_RECEPTION, ROLE_PATHOLOGIST}),
        "POST": OWNER_ONLY,
    },
    "test-ranges": {
        "GET": ALL_STAFF,
        "POST": frozenset({ROLE_OWNER, ROLE_PATHOLOGIST}),
    },
    "test-range-detail": {
        "PATCH": frozenset({ROLE_OWNER, ROLE_PATHOLOGIST}),
    },
    "panel-list-create": {"GET": ALL_STAFF, "POST": OWNER_ONLY},
    "panel-detail": {"GET": ALL_STAFF, "PATCH": OWNER_ONLY},
    "panel-prices": {
        "GET": frozenset({ROLE_OWNER, ROLE_MANAGER, ROLE_RECEPTION, ROLE_PATHOLOGIST}),
        "POST": OWNER_ONLY,
    },
    # --- Billing -------------------------------------------------------------
    "invoice-collection": {"GET": ALL_STAFF, "POST": FRONT_DESK},
    "invoice-detail": {"GET": ALL_STAFF},
    "invoice-cancel": {"POST": FRONT_DESK},
    "payment-create": {"POST": FRONT_DESK},
    # --- Samples -------------------------------------------------------------
    "sample-collection": {"GET": ALL_STAFF, "POST": FRONT_DESK},
    "sample-detail": {"GET": ALL_STAFF},
    "sample-label": {
        "GET": frozenset({ROLE_OWNER, ROLE_MANAGER, ROLE_RECEPTION, ROLE_TECHNICIAN})
    },
    "sample-receive": {"POST": frozenset({ROLE_OWNER, ROLE_MANAGER, ROLE_TECHNICIAN})},
    "sample-reject": {
        "POST": frozenset({ROLE_OWNER, ROLE_MANAGER, ROLE_RECEPTION, ROLE_TECHNICIAN})
    },
    "sample-recollect": {"POST": frozenset({ROLE_OWNER, ROLE_MANAGER, ROLE_RECEPTION})},
    "sample-cancel": {"POST": ADMIN},
    "sample-transfer": {
        "POST": frozenset({ROLE_OWNER, ROLE_MANAGER, ROLE_RECEPTION, ROLE_TECHNICIAN})
    },
    "sample-events": {"GET": ALL_STAFF},
    "transfer-receive": {
        "POST": frozenset({ROLE_OWNER, ROLE_MANAGER, ROLE_RECEPTION, ROLE_TECHNICIAN})
    },
    "transfer-cancel": {"POST": ADMIN},
    "transfer-mark-lost": {"POST": ADMIN},
    "transfer-exceptions": {"GET": ADMIN},
    # --- Results -------------------------------------------------------------
    "result-entry": {
        "GET": ALL_STAFF,
        "POST": frozenset({ROLE_TECHNICIAN, ROLE_PATHOLOGIST, ROLE_OWNER}),
    },
    "result-list": {"GET": ALL_STAFF},
    "result-detail": {"GET": ALL_STAFF},
    "result-approve": {
        "POST": frozenset({ROLE_PATHOLOGIST, ROLE_OWNER}),
    },
    "result-withdraw": {
        "POST": frozenset({ROLE_TECHNICIAN, ROLE_PATHOLOGIST, ROLE_OWNER}),
    },
    "result-amend": {
        "POST": frozenset({ROLE_TECHNICIAN, ROLE_PATHOLOGIST, ROLE_OWNER}),
    },
    "critical-notification": {
        "POST": frozenset({ROLE_MANAGER, ROLE_PATHOLOGIST, ROLE_OWNER}),
    },
    # --- Branches ------------------------------------------------------------
    "branch-list-create": {"GET": ALL_STAFF, "POST": OWNER_ONLY},
    "branch-detail": {"PATCH": OWNER_ONLY},
    "branch-close": {"POST": OWNER_ONLY},
    "branch-reopen": {"POST": OWNER_ONLY},
    # --- Reports -------------------------------------------------------------
    "report-list": {"GET": ALL_STAFF},
    "exceptions-list": {"GET": ALL_STAFF},
    "report-detail": {"GET": ALL_STAFF},
    "report-regenerate": {
        "POST": frozenset({ROLE_OWNER, ROLE_MANAGER, ROLE_PATHOLOGIST}),
    },
    "report-deliver": {"POST": FRONT_DESK},
    "report-access-token-issue": {"POST": FRONT_DESK},
    "report-access-token-revoke": {"POST": ADMIN},
    # --- Settlements & partners ---------------------------------------------
    "settlement-list": {"GET": ADMIN},
    "settlement-detail": {"GET": ADMIN},
    "settlement-approve": {"POST": OWNER_ONLY},
    "settlement-cancel": {"POST": OWNER_ONLY},
    "settlement-mark-paid": {"POST": OWNER_ONLY},
    "settlement-send": {"POST": OWNER_ONLY},
    "settlement-exceptions": {"GET": ADMIN},
    "settlement-statement-pdf": {"GET": ADMIN},
    "partner-collection": {"GET": OWNER_ONLY, "POST": OWNER_ONLY},
    "partner-detail": {
        "GET": OWNER_ONLY,
        "PATCH": OWNER_ONLY,
        "DELETE": OWNER_ONLY,
    },
    "partner-dashboard": {"GET": OWNER_ONLY},
    "share-ledger-list": {"GET": ADMIN},
    "rule-collection": {"GET": OWNER_ONLY, "POST": OWNER_ONLY},
    "rule-detail": {"PATCH": OWNER_ONLY},
    # --- Tenant settings -----------------------------------------------------
    "settings": {"GET": ALL_STAFF, "PATCH": ADMIN},
    # --- Exports -------------------------------------------------------------
    "export-request": {"POST": OWNER_ONLY},
    "export-detail": {"GET": OWNER_ONLY},
    # --- Staff management ----------------------------------------------------
    "staff-collection": {"GET": OWNER_ONLY, "POST": OWNER_ONLY},
    "staff-detail": {"GET": OWNER_ONLY, "PATCH": OWNER_ONLY},
    "staff-deactivate": {"POST": OWNER_ONLY},
    "staff-reactivate": {"POST": OWNER_ONLY},
    "staff-reset-password": {"POST": OWNER_ONLY},
    "staff-totp-reset": {"POST": OWNER_ONLY},
    "staff-branches": {"GET": ADMIN, "PUT": OWNER_ONLY},
}

#: Routes whose credential is a capability token or a shared callback key, not
#: a staff JWT. They never reach the role policy; listed so the structural test
#: can prove the omission is deliberate.
PUBLIC_URL_NAMES: Final[frozenset[str]] = frozenset(
    {
        "auth-login",
        "auth-refresh",
        "auth-totp-verify",
        "auth-password-reset-request",
        "auth-password-reset-confirm",
        "report-access",
        "report-file-download",
        "export-download",
        "settlement-delivery-callback",
        "webhook-notification-callback",
        "webhook-report-delivery-callback",
        "webhook-settlement-delivery-callback",
        "demo-requests-capture",
        # platform (apex) and infrastructure routes
        "public-healthz",
        "public-readyz",
        "internal-tls-check",
        "schema",
        "swagger-ui",
        "redoc",
    }
)


def normalize_url_name(url_name: str | None) -> str:
    """Strip the route-twin suffix (``-slash``) from a Django URL name."""
    if not url_name:
        return ""
    return url_name[: -len("-slash")] if url_name.endswith("-slash") else url_name


def allowed_roles_for(url_name: str | None, method: str) -> frozenset[str] | None:
    """Return the allowed role set, or None when the route has no policy."""
    entry = ROLE_POLICY.get(normalize_url_name(url_name))
    if entry is None:
        return None
    return entry.get(method.upper())


def is_role_allowed(user: Any, request: Any) -> bool:
    """True when ``user`` may call this URL name + method.

    Deny-by-default: an authenticated route with no policy entry is refused.
    """
    resolver_match = getattr(request, "resolver_match", None)
    url_name = getattr(resolver_match, "url_name", None)
    allowed = allowed_roles_for(url_name, getattr(request, "method", "GET"))
    if allowed is None:
        return False
    return getattr(user, "role", None) in allowed


def _audit_denial(
    user: Any, request: Any, *, action: str = "auth.access_denied"
) -> None:
    """Best-effort append-only denial row; never block the 403 response.

    Deduplicated per (actor, route, method) for 60 seconds so a probing loop
    cannot inflate the audit table without bound (security review 2026-11-12).
    """
    try:
        from django.core.cache import cache

        resolver_match = getattr(request, "resolver_match", None)
        url_name = getattr(resolver_match, "url_name", None) or ""
        method = getattr(request, "method", "") or ""
        actor_id = getattr(user, "id", None)
        dedupe_key = f"auth:denial-audit:{action}:{actor_id}:{url_name}:{method}"
        if not cache.add(dedupe_key, "1", timeout=60):
            return
    except Exception:  # cache outage: still write the first row
        pass
    try:
        from apps.accounts.models import AuditLog

        AuditLog.objects.create(
            actor_id=actor_id,
            action=action,
            entity_type="route",
            entity_id=actor_id if actor_id else uuid.uuid4(),
            after_jsonb={
                "url_name": url_name,
                "method": method,
                "role": getattr(user, "role", None),
                "path": getattr(request, "path", ""),
            },
            ip=_client_ip(request),
            user_agent=(getattr(request, "META", {}) or {}).get("HTTP_USER_AGENT", ""),
        )
    except Exception as exc:  # pragma: no cover - audit must never mask the 403
        logger.warning("Failed to write role-denial audit row: %s", exc)


def _client_ip(request: Any) -> str | None:
    from apps.core.ip import get_client_ip

    return get_client_ip(request)


def enforce_role_policy(user: Any, request: Any) -> None:
    """Raise ``RoleDenied`` (and audit) when the role policy denies."""
    if is_role_allowed(user, request):
        return
    resolver_match = getattr(request, "resolver_match", None)
    url_name = normalize_url_name(getattr(resolver_match, "url_name", None))
    method = (getattr(request, "method", "") or "").upper()
    entry = ROLE_POLICY.get(url_name)
    action = (
        "auth.policy_missing_method"
        if entry is not None and method not in entry
        else "auth.access_denied"
    )
    _audit_denial(user, request, action=action)
    from apps.core.exceptions import RoleDenied

    raise RoleDenied()
