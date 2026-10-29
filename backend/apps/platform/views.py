import uuid
from typing import Any

import jwt
from django.conf import settings
from rest_framework.authentication import BaseAuthentication
from rest_framework.permissions import BasePermission
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.models import PlatformUser
from apps.platform.provisioning import (
    ProvisioningError,
    ProvisionTenantInput,
    create_tenant_provisioning,
)
from apps.platform.serializers import TenantProvisionRequestSerializer

PROBLEM_JSON_CONTENT_TYPE = "application/problem+json"


def problem_response(
    *,
    code: str,
    title: str,
    detail: str,
    status_code: int,
    errors: dict[str, list[str]] | None = None,
) -> Response:
    slug_type = code.replace("_", "-")
    payload: dict[str, Any] = {
        "type": f"https://labflow.example/problems/{slug_type}",
        "title": title,
        "status": status_code,
        "detail": detail,
        "code": code,
        "errors": errors or {},
    }
    return Response(
        payload,
        status=status_code,
        content_type=PROBLEM_JSON_CONTENT_TYPE,
    )


def _authenticate_jwt_header(auth_header: str) -> PlatformUser | None:
    """Resolve PlatformUser from Bearer JWT header."""
    if not isinstance(auth_header, str) or not auth_header.startswith("Bearer "):
        return None
    token = auth_header[7:].strip()
    signing_key = getattr(
        settings,
        "JWT_SIGNING_KEY",
        getattr(settings, "SECRET_KEY", "test-secret"),
    )
    try:
        decoded = jwt.decode(token, str(signing_key), algorithms=["HS256"])
    except jwt.PyJWTError:
        return None

    if decoded.get("typ", "access") != "access":
        return None

    # Reject tenant tokens
    if decoded.get("tenant") is not None:
        return None
    role = decoded.get("role")
    if role not in (None, "super_admin", "platform_admin", "platform"):
        return None

    sub = decoded.get("sub") or decoded.get("user_id")
    if not sub:
        return None
    try:
        user_uuid = uuid.UUID(str(sub))
    except ValueError:
        return None

    return PlatformUser.objects.filter(id=user_uuid, is_active=True).first()


class PlatformJWTAuthentication(BaseAuthentication):
    """Authenticate PlatformUser via Bearer JWT (Doc 04 §12.1)."""

    def authenticate(self, request: Any) -> tuple[PlatformUser, None] | None:
        auth_header = request.META.get("HTTP_AUTHORIZATION", "")
        platform_user = _authenticate_jwt_header(auth_header)
        if platform_user is not None:
            return (platform_user, None)
        return None

    def authenticate_header(self, request: Any) -> str:
        return "Bearer"


class IsAuthenticatedPlatformUser(BasePermission):
    """Allow access only to active PlatformUser accounts (Doc 04 §12.1)."""

    def has_permission(self, request: Request, view: Any) -> bool:
        user = getattr(request, "user", None)
        return isinstance(user, PlatformUser) and user.is_active


class PlatformTenantCreateView(APIView):
    """POST /api/v1/platform/tenants — Provision a tenant (Doc 04 §15.1)."""

    authentication_classes = [PlatformJWTAuthentication]
    permission_classes = [IsAuthenticatedPlatformUser]

    def handle_exception(self, exc: Exception) -> Response:
        if isinstance(exc, ProvisioningError):
            return problem_response(
                code=exc.code,
                title=exc.title,
                detail=exc.detail,
                status_code=exc.status_code,
                errors=exc.errors,
            )
        response = super().handle_exception(exc)
        if response.status_code in (401, 403):
            return problem_response(
                code="unauthorized" if response.status_code == 401 else "forbidden",
                title=(
                    "Authentication required"
                    if response.status_code == 401
                    else "Forbidden"
                ),
                detail="Valid platform super-admin credentials are required.",
                status_code=response.status_code,
            )
        return response

    def post(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        user = getattr(request, "user", None)
        if not isinstance(user, PlatformUser) or not user.is_active:
            return problem_response(
                code="unauthorized",
                title="Authentication required",
                detail="Valid platform super-admin credentials are required.",
                status_code=401,
            )
        platform_user = user

        if not platform_user.totp_enabled:
            return problem_response(
                code="totp_required",
                title="TOTP 2FA enrolment required",
                detail="Super Admin accounts must enable TOTP before writes.",
                status_code=403,
            )

        serializer = TenantProvisionRequestSerializer(data=request.data)
        if not serializer.is_valid():
            field_errors: dict[str, list[str]] = {
                str(k): [str(msg) for msg in v]
                for k, v in serializer.errors.items()
                if isinstance(v, list)
            }
            if "slug" in field_errors and "slug" in request.data:
                return problem_response(
                    code="slug_invalid",
                    title="Invalid tenant slug",
                    detail="Slug must be a valid lowercase alphanumeric string.",
                    status_code=422,
                    errors=field_errors,
                )
            return problem_response(
                code="validation_error",
                title="Validation error",
                detail="Request validation failed.",
                status_code=422,
                errors=field_errors,
            )

        validated = serializer.validated_data
        idempotency_key = request.META.get("HTTP_IDEMPOTENCY_KEY")
        if isinstance(idempotency_key, str):
            idempotency_key = idempotency_key.strip() or None
        else:
            idempotency_key = None

        ip_addr = request.META.get("REMOTE_ADDR")
        user_agent = str(request.META.get("HTTP_USER_AGENT", ""))

        result = create_tenant_provisioning(
            ProvisionTenantInput(
                name=validated["name"],
                slug=validated["slug"],
                plan_id=validated["plan_id"],
                owner_email=validated["resolved_owner_email"],
                owner_name=validated["resolved_owner_name"],
                actor_id=platform_user.id,
                idempotency_key=idempotency_key,
                ip_address=ip_addr if isinstance(ip_addr, str) else None,
                user_agent=user_agent,
            )
        )

        return Response(
            {
                "id": str(result.tenant.id),
                "slug": result.tenant.slug,
                "name": result.tenant.name,
                "schema_name": result.tenant.schema_name,
                "status": result.tenant.status,
                "domain": result.domain.domain,
                "plan_id": str(result.subscription.plan_id),
                "subscription_id": str(result.subscription.id),
                "owner_email": result.owner_email,
                "owner_name": result.owner_name,
                "created_at": result.tenant.created_at.isoformat(),
            },
            status=202,
        )
