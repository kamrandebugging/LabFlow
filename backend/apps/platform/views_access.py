"""Phase 2 Platform Tenant Access Control views.

Covers:
- GET /api/v1/platform/access/<tenant_id>
- PUT /api/v1/platform/access/<tenant_id> (TOTP-gated write, audit)
"""

import logging
import uuid
from typing import Any

from django.db import DatabaseError, connection, transaction
from django_tenants.utils import schema_context
from rest_framework import status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import Role, StaffUser
from apps.accounts.role_config import (
    ROLE_LABELS,
    normalize_role,
    normalize_role_list,
)
from apps.core.models import (
    Subscription,
    TenantFeatureFlag,
)
from apps.platform.views import (
    IsAuthenticatedPlatformUser,
    PlatformJWTAuthentication,
    problem_response,
)
from apps.platform.views_admin import (
    _get_platform_user,
    _get_tenant_or_404,
    _require_totp,
    _unauthorized,
    _write_platform_audit,
)

logger = logging.getLogger(__name__)


def _active_staff_counts(tenant: Any) -> dict[str, int] | None:
    """Active staff per role for a tenant schema (D-D confirmation data).

    A registry row whose schema was never provisioned has no staff table;
    counts are then unknown rather than fatal. Real tenant schemas always
    answer, so the disable guard remains effective.
    """
    if not tenant or not getattr(tenant, "schema_name", None):
        return None
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT 1 FROM information_schema.schemata WHERE schema_name = %s",
            [tenant.schema_name],
        )
        schema_exists = cursor.fetchone() is not None
        cursor.execute(
            "SELECT 1 FROM information_schema.tables "
            "WHERE table_schema = %s AND table_name = 'staff_user'",
            [tenant.schema_name],
        )
        staff_table_exists = cursor.fetchone() is not None
    if not schema_exists or not staff_table_exists:
        logger.warning(
            "staff_role_counts_unavailable: schema %s has no staff table",
            tenant.schema_name,
        )
        return None
    try:
        with schema_context(tenant.schema_name):
            rows = StaffUser.objects.filter(is_active=True).values("role")
            counts: dict[str, int] = {}
            for row in rows:
                counts[row["role"]] = counts.get(row["role"], 0) + 1
            return counts
    except DatabaseError:
        logger.warning(
            "staff_role_counts_unavailable: schema %s has no staff table",
            tenant.schema_name,
        )
        return {}


def _role_rows(tenant: Any) -> list[dict[str, Any]]:
    # Fail closed: an empty list means Owner only. D-G defaults are written by
    # provisioning, never inferred from a missing configuration.
    enabled = normalize_role_list(list(tenant.enabled_roles or []))
    counts = _active_staff_counts(tenant) or {}
    updated_at = tenant.updated_at.isoformat() if tenant.updated_at else None
    rows: list[dict[str, Any]] = []
    for role in (Role.OWNER, *(role for role in ROLE_LABELS if role != Role.OWNER)):
        rows.append(
            {
                "role": role,
                "label": ROLE_LABELS.get(role, role),
                "enabled": role == Role.OWNER or role in enabled,
                "immutable": role == Role.OWNER,
                "active_staff_count": counts.get(role, 0),
                "updated_by": None,
                "updated_at": updated_at,
            }
        )
    return rows


class PlatformAccessControlView(APIView):
    """GET / PUT /api/v1/platform/access/<tenant_id>."""

    authentication_classes = [PlatformJWTAuthentication]
    permission_classes = [IsAuthenticatedPlatformUser]

    def get(self, request: Request, tenant_id: uuid.UUID) -> Response:
        user = _get_platform_user(request)
        if not user:
            return _unauthorized()

        tenant, err = _get_tenant_or_404(str(tenant_id))
        if err or not tenant:
            return err or problem_response(
                code="not_found",
                title="Not found",
                detail="Tenant not found.",
                status_code=404,
            )

        sub = (
            Subscription.objects.select_related("plan")
            .filter(tenant=tenant, status=Subscription.Status.ACTIVE)
            .first()
        )
        plan = sub.plan if sub else None

        flags_qs = TenantFeatureFlag.objects.filter(tenant=tenant)
        flags_dict = {f.flag_key: f.enabled for f in flags_qs}
        # Standard default flags
        default_keys = [
            "referral_partners",
            "settlements",
            "advanced_analytics",
            "automated_whatsapp",
        ]
        for k in default_keys:
            if k not in flags_dict:
                flags_dict[k] = False

        roles = _role_rows(tenant)
        return Response(
            {
                "tenant_id": str(tenant.id),
                "tenant_name": tenant.name,
                "tenant_slug": tenant.slug,
                "plan_name": plan.name if plan else "None",
                "plan_max_branches": plan.max_branches if plan else None,
                "plan_max_staff": plan.max_staff if plan else None,
                "max_branches": plan.max_branches if plan else None,
                "max_staff": plan.max_staff if plan else None,
                "branch_limit": tenant.branch_count,
                "staff_limit": tenant.staff_seats_limit,
                "enabled_roles": [row["role"] for row in roles if row["enabled"]],
                "roles": roles,
                "feature_flags": flags_dict,
            },
            status=status.HTTP_200_OK,
        )

    @transaction.atomic
    def put(self, request: Request, tenant_id: uuid.UUID) -> Response:
        user = _get_platform_user(request)
        if not user:
            return _unauthorized()

        totp_err = _require_totp(user)
        if totp_err:
            return totp_err

        tenant, err = _get_tenant_or_404(str(tenant_id))
        if err or not tenant:
            return err or problem_response(
                code="not_found",
                title="Not found",
                detail="Tenant not found.",
                status_code=404,
            )

        sub = (
            Subscription.objects.select_related("plan")
            .filter(tenant=tenant, status=Subscription.Status.ACTIVE)
            .first()
        )
        plan = sub.plan if sub else None

        data = request.data if isinstance(request.data, dict) else {}
        staff_limit = data.get("staff_limit")
        branch_limit = data.get("branch_limit")
        feature_flags = data.get("feature_flags", {})

        current_enabled = normalize_role_list(list(tenant.enabled_roles or []))
        if not tenant.enabled_roles:
            from apps.accounts.role_config import DEFAULT_ENABLED_ROLES

            current_enabled = normalize_role_list(list(DEFAULT_ENABLED_ROLES))

        raw_roles = data.get("roles")
        explicit_enabled = data.get("enabled_roles")

        requested_enabled: list[str] | None = None
        if isinstance(raw_roles, list):
            # Delta semantics: absent roles keep their current state. A
            # partial client payload must never disable every omitted role.
            requested_enabled = [role for role in current_enabled if role != Role.OWNER]
            for item in raw_roles:
                if not isinstance(item, dict):
                    return problem_response(
                        code="validation_error",
                        title="Validation error",
                        detail="roles must be a list of {role, enabled} objects.",
                        status_code=422,
                    )
                role = normalize_role(item.get("role"))
                if role is None or role == Role.OWNER:
                    return problem_response(
                        code="owner_role_immutable"
                        if role == Role.OWNER
                        else "validation_error",
                        title="Invalid role",
                        detail="Unknown role or the immutable Owner role.",
                        status_code=422,
                    )
                if bool(item.get("enabled")):
                    if role not in requested_enabled:
                        requested_enabled.append(role)
                elif role in requested_enabled:
                    requested_enabled.remove(role)
        elif isinstance(explicit_enabled, list):
            normalised = normalize_role_list(list(explicit_enabled))
            if "owner" not in [normalize_role(r) for r in explicit_enabled]:
                return problem_response(
                    code="owner_role_immutable",
                    title="Owner role is immutable",
                    detail="The Owner role is required and cannot be disabled.",
                    status_code=422,
                )
            requested_enabled = [r for r in normalised if r != Role.OWNER]
        elif explicit_enabled is not None:
            return problem_response(
                code="validation_error",
                title="Validation error",
                detail="enabled_roles must be a list of role names.",
                status_code=422,
            )

        # D-D: disabling a role with active staff is blocked until those staff
        # are deactivated. Never leave active staff under a disabled role.
        if requested_enabled is not None:
            requested_set = set(requested_enabled)
            active_counts = _active_staff_counts(tenant)
            disabling = [
                role
                for role in current_enabled
                if role != Role.OWNER and role not in requested_set
            ]
            if disabling and active_counts is None:
                return problem_response(
                    code="role_state_unknown",
                    title="Cannot verify active staff",
                    detail=(
                        "The tenant staff table could not be read, so no role "
                        "may be disabled safely. Try again after provisioning "
                        "completes."
                    ),
                    status_code=422,
                )
            assert active_counts is not None
            for role in current_enabled:
                if role == Role.OWNER or role in requested_set:
                    continue
                if active_counts.get(role, 0) == 0:
                    continue
                with schema_context(tenant.schema_name):
                    blockers = list(
                        StaffUser.objects.filter(role=role, is_active=True).values(
                            "id", "email", "display_name"
                        )[:50]
                    )
                if blockers:
                    return problem_response(
                        code="role_has_active_staff",
                        title="Role has active staff",
                        detail=(
                            f"{ROLE_LABELS.get(role, role)} still has "
                            f"{len(blockers)} active staff member(s). "
                            "Deactivate them before disabling the role."
                        ),
                        status_code=422,
                        errors={
                            "role": [role],
                            "active_staff_count": [str(len(blockers))],
                            "staff": [
                                {
                                    "id": str(row["id"]),
                                    "email": row["email"],
                                    "display_name": row["display_name"] or "",
                                }
                                for row in blockers
                            ],
                        },
                    )

        # 2. Parse and bound quotas once (no implicit ValueError -> 500).
        staff_cap: int | None = None
        branch_cap: int | None = None
        if staff_limit is not None:
            try:
                staff_cap = int(staff_limit)
            except (TypeError, ValueError):
                return problem_response(
                    code="validation_error",
                    title="Validation error",
                    detail="staff_limit must be a non-negative integer.",
                    status_code=422,
                )
            if staff_cap < 0:
                return problem_response(
                    code="validation_error",
                    title="Validation error",
                    detail="staff_limit must be a non-negative integer.",
                    status_code=422,
                )
            if plan and plan.max_staff is not None and staff_cap > plan.max_staff:
                return problem_response(
                    code="staff_limit_exceeds_plan",
                    title="Quota exceeded",
                    detail=(
                        f"Staff limit {staff_cap} exceeds plan maximum "
                        f"({plan.max_staff})."
                    ),
                    status_code=422,
                )
        if branch_limit is not None:
            try:
                branch_cap = int(branch_limit)
            except (TypeError, ValueError):
                return problem_response(
                    code="validation_error",
                    title="Validation error",
                    detail="branch_limit must be a non-negative integer.",
                    status_code=422,
                )
            if branch_cap < 0:
                return problem_response(
                    code="validation_error",
                    title="Validation error",
                    detail="branch_limit must be a non-negative integer.",
                    status_code=422,
                )
            if (
                plan
                and plan.max_branches is not None
                and branch_cap > plan.max_branches
            ):
                return problem_response(
                    code="branch_limit_exceeds_plan",
                    title="Quota exceeded",
                    detail=(
                        f"Branch limit {branch_cap} exceeds plan maximum "
                        f"({plan.max_branches})."
                    ),
                    status_code=422,
                )

        before_state: dict[str, Any] = {
            "enabled_roles": current_enabled,
            "staff_seats_limit": tenant.staff_seats_limit,
            "branch_count": tenant.branch_count,
        }

        update_fields: list[str] = ["updated_at"]
        new_roles = normalize_role_list(
            list(
                requested_enabled if requested_enabled is not None else current_enabled
            )
        )
        if new_roles != current_enabled or not tenant.enabled_roles:
            tenant.enabled_roles = new_roles
            update_fields.append("enabled_roles")
        if staff_cap is not None:
            tenant.staff_seats_limit = staff_cap
            update_fields.append("staff_seats_limit")
        if branch_cap is not None:
            tenant.branch_count = branch_cap
            update_fields.append("branch_count")
        tenant.save(update_fields=update_fields)

        # Update feature flags
        if isinstance(feature_flags, dict):
            for flag_key, val in feature_flags.items():
                TenantFeatureFlag.objects.update_or_create(
                    tenant=tenant,
                    flag_key=flag_key,
                    defaults={"enabled": bool(val)},
                )

        after_state = {
            "enabled_roles": tenant.enabled_roles,
            "staff_seats_limit": tenant.staff_seats_limit,
            "branch_count": tenant.branch_count,
            "feature_flags": feature_flags,
        }

        _write_platform_audit(
            actor_id=user.id,
            action="role.updated",
            entity_type="tenant",
            entity_id=tenant.id,
            before=before_state,
            after=after_state,
            ip=request.META.get("REMOTE_ADDR"),
            user_agent=request.META.get("HTTP_USER_AGENT"),
        )

        # FR-1/S10: one audit row per role that actually changed.
        old_set = set(before_state["enabled_roles"])
        new_set = set(tenant.enabled_roles)
        for role in sorted(old_set | new_set):
            if role in ("owner",) or (role in old_set) == (role in new_set):
                continue
            enabled = role in new_set
            _write_platform_audit(
                actor_id=user.id,
                action="role.enabled" if enabled else "role.disabled",
                entity_type="tenant",
                entity_id=tenant.id,
                before={"role": role, "enabled": not enabled},
                after={"role": role, "enabled": enabled},
                ip=request.META.get("REMOTE_ADDR"),
                user_agent=request.META.get("HTTP_USER_AGENT"),
            )

        roles = _role_rows(tenant)
        return Response(
            {
                "ok": True,
                "tenant_id": str(tenant.id),
                "enabled_roles": [row["role"] for row in roles if row["enabled"]],
                "roles": roles,
                "staff_limit": tenant.staff_seats_limit,
                "branch_limit": tenant.branch_count,
            },
            status=status.HTTP_200_OK,
        )
