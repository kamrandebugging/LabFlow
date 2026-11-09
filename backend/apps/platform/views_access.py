"""Phase 2 Platform Tenant Access Control views.

Covers:
- GET /api/v1/platform/access/<tenant_id>
- PUT /api/v1/platform/access/<tenant_id> (TOTP-gated write, audit)
"""

import uuid

from rest_framework import status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

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

        return Response(
            {
                "tenant_id": str(tenant.id),
                "tenant_name": tenant.name,
                "tenant_slug": tenant.slug,
                "plan_name": plan.name if plan else "None",
                "plan_max_branches": plan.max_branches if plan else None,
                "plan_max_staff": plan.max_staff if plan else None,
                "branch_limit": tenant.branch_count,
                "staff_limit": tenant.staff_seats_limit,
                "enabled_roles": tenant.enabled_roles
                or ["owner", "manager", "receptionist", "technician", "pathologist"],
                "feature_flags": flags_dict,
            },
            status=status.HTTP_200_OK,
        )

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
        enabled_roles = data.get("enabled_roles")
        staff_limit = data.get("staff_limit")
        branch_limit = data.get("branch_limit")
        feature_flags = data.get("feature_flags", {})

        if not isinstance(enabled_roles, list):
            return problem_response(
                code="validation_error",
                title="Validation error",
                detail="enabled_roles must be a list of role names.",
                status_code=422,
            )

        # 1. Owner role is IMMUTABLE
        if "owner" not in [r.lower() for r in enabled_roles]:
            return problem_response(
                code="owner_role_immutable",
                title="Owner role is immutable",
                detail="The Owner role is required and cannot be disabled.",
                status_code=422,
            )

        # 2. Plan bounds check
        if staff_limit is not None and plan and plan.max_staff is not None:
            try:
                sl = int(staff_limit)
                if sl > plan.max_staff:
                    return problem_response(
                        code="staff_limit_exceeds_plan",
                        title="Quota exceeded",
                        detail=(
                            f"Staff limit {sl} exceeds plan maximum ({plan.max_staff})."
                        ),
                        status_code=422,
                    )
            except ValueError:
                pass

        if branch_limit is not None and plan and plan.max_branches is not None:
            try:
                bl = int(branch_limit)
                if bl > plan.max_branches:
                    return problem_response(
                        code="branch_limit_exceeds_plan",
                        title="Quota exceeded",
                        detail=(
                            f"Branch limit {bl} exceeds plan maximum "
                            f"({plan.max_branches})."
                        ),
                        status_code=422,
                    )
            except ValueError:
                pass

        before_state = {
            "enabled_roles": tenant.enabled_roles,
            "staff_seats_limit": tenant.staff_seats_limit,
            "branch_count": tenant.branch_count,
        }

        tenant.enabled_roles = [r.lower() for r in enabled_roles]
        if staff_limit is not None:
            tenant.staff_seats_limit = int(staff_limit)
        if branch_limit is not None:
            tenant.branch_count = int(branch_limit)
        tenant.save()

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

        return Response(
            {
                "ok": True,
                "tenant_id": str(tenant.id),
                "enabled_roles": tenant.enabled_roles,
                "staff_limit": tenant.staff_seats_limit,
                "branch_limit": tenant.branch_count,
            },
            status=status.HTTP_200_OK,
        )
