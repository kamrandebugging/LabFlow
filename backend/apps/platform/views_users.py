"""Phase 2 Platform Users view (Doc 09).

Hard rules:
- Lab owner accounts are read from public-schema Tenant records ONLY (Doc 08 R13).
- Platform must NEVER return tenant staff members or internal tenant tables.
- Platform team accounts come from PlatformUser.
- Invitations for platform operators.
"""

import uuid
from typing import Any

from rest_framework import status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.models import (
    PlatformUser,
    PlatformUserInvitation,
    Tenant,
)
from apps.platform.views import (
    IsAuthenticatedPlatformUser,
    PlatformJWTAuthentication,
    problem_response,
)
from apps.platform.views_admin import (
    _get_platform_user,
    _require_totp,
    _unauthorized,
    _write_platform_audit,
)


class PlatformUsersListView(APIView):
    """GET /api/v1/platform/users — laboratory owner metadata & platform team."""

    authentication_classes = [PlatformJWTAuthentication]
    permission_classes = [IsAuthenticatedPlatformUser]

    def get(self, request: Request) -> Response:
        user = _get_platform_user(request)
        if not user:
            return _unauthorized()

        q = request.query_params.get("q", "").strip().lower()

        # 1. Lab Owners from public Tenant records only
        tenants_qs = Tenant.objects.exclude(schema_name="public").order_by(
            "-created_at"
        )
        if q:
            tenants_qs = (
                tenants_qs.filter(name__icontains=q)
                | tenants_qs.filter(owner_name__icontains=q)
                | tenants_qs.filter(owner_email__icontains=q)
                | tenants_qs.filter(owner_phone__icontains=q)
            )

        lab_owners: list[dict[str, Any]] = []
        for t in tenants_qs:
            lab_owners.append(
                {
                    "id": str(t.id),
                    "owner_name": t.owner_name or "Primary Director",
                    "owner_email": t.owner_email or f"director@{t.slug}.pk",
                    "owner_phone": t.owner_phone or "N/A",
                    "lab_name": t.name,
                    "lab_slug": t.slug,
                    "city": t.city,
                    "status": t.status,
                    "created_at": t.created_at.isoformat(),
                    "last_active": t.updated_at.isoformat() if t.updated_at else None,
                }
            )

        # 2. Platform Team
        team_qs = PlatformUser.objects.all().order_by("-created_at")
        platform_team: list[dict[str, Any]] = []
        for u in team_qs:
            is_super = "admin" in u.email.lower() or "kamran" in u.email.lower()
            platform_team.append(
                {
                    "id": str(u.id),
                    "email": u.email,
                    "role": "Platform Owner" if is_super else "Platform Support",
                    "totp_enabled": u.totp_enabled,
                    "is_active": u.is_active,
                    "created_at": u.created_at.isoformat(),
                }
            )

        # 3. Pending Invitations
        inv_qs = PlatformUserInvitation.objects.all().order_by("-created_at")
        invitations: list[dict[str, Any]] = []
        for inv in inv_qs:
            invitations.append(
                {
                    "id": str(inv.id),
                    "email": inv.email,
                    "role": inv.role,
                    "status": inv.status,
                    "created_at": inv.created_at.isoformat(),
                }
            )

        return Response(
            {
                "lab_owners": lab_owners,
                "platform_team": platform_team,
                "invitations": invitations,
            },
            status=status.HTTP_200_OK,
        )


class PlatformUserInviteView(APIView):
    """POST /api/v1/platform/users/invite — invite a platform operator."""

    authentication_classes = [PlatformJWTAuthentication]
    permission_classes = [IsAuthenticatedPlatformUser]

    def post(self, request: Request) -> Response:
        user = _get_platform_user(request)
        if not user:
            return _unauthorized()

        totp_err = _require_totp(user)
        if totp_err:
            return totp_err

        data = request.data if isinstance(request.data, dict) else {}
        email = str(data.get("email", "")).strip().lower()
        role = str(data.get("role", "support")).strip().lower()

        if not email or "@" not in email:
            return problem_response(
                code="validation_error",
                title="Validation error",
                detail="A valid email address is required.",
                status_code=422,
            )

        invitation, _ = PlatformUserInvitation.objects.update_or_create(
            email=email,
            defaults={"role": role, "invited_by": user, "status": "pending"},
        )

        _write_platform_audit(
            actor_id=user.id,
            action="user.invited",
            entity_type="platform_user_invitation",
            entity_id=invitation.id,
            after={"email": email, "role": role},
            ip=request.META.get("REMOTE_ADDR"),
            user_agent=request.META.get("HTTP_USER_AGENT"),
        )

        return Response(
            {
                "ok": True,
                "email": email,
                "role": role,
                "invitation_id": str(invitation.id),
            },
            status=status.HTTP_200_OK,
        )


class PlatformUserDisableView(APIView):
    """POST /api/v1/platform/users/<id>/disable — deactivate a platform user."""

    authentication_classes = [PlatformJWTAuthentication]
    permission_classes = [IsAuthenticatedPlatformUser]

    def post(self, request: Request, user_id: uuid.UUID) -> Response:
        user = _get_platform_user(request)
        if not user:
            return _unauthorized()

        totp_err = _require_totp(user)
        if totp_err:
            return totp_err

        target = PlatformUser.objects.filter(id=user_id).first()
        if not target:
            return problem_response(
                code="not_found",
                title="Not found",
                detail="Platform user not found.",
                status_code=404,
            )

        if target.id == user.id:
            return problem_response(
                code="cannot_disable_self",
                title="Action not permitted",
                detail="You cannot disable your own active account.",
                status_code=422,
            )

        target.is_active = False
        target.save()

        _write_platform_audit(
            actor_id=user.id,
            action="user.disabled",
            entity_type="platform_user",
            entity_id=target.id,
            after={"email": target.email, "is_active": False},
            ip=request.META.get("REMOTE_ADDR"),
            user_agent=request.META.get("HTTP_USER_AGENT"),
        )

        return Response(
            {"ok": True, "user_id": str(target.id)}, status=status.HTTP_200_OK
        )
