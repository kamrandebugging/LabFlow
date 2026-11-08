import base64
import binascii
import uuid
from datetime import datetime
from typing import Any

from django.db.models import Q
from django.utils.dateparse import parse_datetime
from rest_framework.authentication import BaseAuthentication
from rest_framework.permissions import BasePermission
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.models import PlatformUser
from apps.platform.auth_service import (
    is_access_token_revoked,
    token_is_stale_for_user,
)
from apps.platform.platform_jwt import platform_decode_jwt
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
    """Resolve a PlatformUser from a Bearer platform access token.

    Rejects, in order: non-access token types (a refresh token presented as an
    access token fails on ``typ`` alone), tenant-scoped tokens (they carry a
    ``tenant`` claim that platform tokens never do), denylisted/revoked jtis,
    tokens issued before the user's revocation marker, and inactive accounts.
    """
    if not isinstance(auth_header, str) or not auth_header.startswith("Bearer "):
        return None
    token = auth_header[7:].strip()
    try:
        decoded = platform_decode_jwt(token, expected_type="access")
    except ValueError:
        return None

    jti = decoded.get("jti")
    if not jti:
        return None
    sid = decoded.get("sid")
    if is_access_token_revoked(str(jti), str(sid) if sid else None):
        return None

    sub = decoded.get("sub") or decoded.get("user_id")
    if not sub:
        return None
    try:
        user_uuid = uuid.UUID(str(sub))
    except ValueError:
        return None

    if token_is_stale_for_user(user_uuid, int(decoded.get("iat", 0) or 0)):
        return None

    role = decoded.get("role")
    if role not in (None, "super_admin", "platform_admin", "platform"):
        return None

    return PlatformUser.objects.filter(id=user_uuid, is_active=True).first()


def _encode_cursor(created_at: datetime, tenant_id: uuid.UUID) -> str:
    """Opaque keyset cursor for the tenant registry (created_at DESC, id DESC)."""
    raw = f"{created_at.isoformat()}|{tenant_id}"
    return base64.urlsafe_b64encode(raw.encode()).decode().rstrip("=")


def _decode_cursor(cursor: str) -> tuple[datetime, uuid.UUID] | None:
    """Decode a cursor, returning None for anything malformed."""
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        raw = base64.urlsafe_b64decode(padded.encode()).decode()
        stamp, _, identifier = raw.partition("|")
        parsed = parse_datetime(stamp)
        if parsed is None:
            return None
        return parsed, uuid.UUID(identifier)
    except (ValueError, binascii.Error, UnicodeDecodeError):
        return None


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

    def get(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        """GET /api/v1/platform/tenants — registry list (Doc 04 §15.1, LAB-37).

        Filters: ``status``, ``q`` (slug/name substring), ``limit`` (1–100,
        default 50) and the opaque ``cursor`` returned by the previous page.
        Read-only and metadata-only — no tenant row content ever leaves here.
        """
        from apps.core.models import Tenant as _Tenant

        user = getattr(request, "user", None)
        if not isinstance(user, PlatformUser) or not user.is_active:
            return problem_response(
                code="unauthorized",
                title="Authentication required",
                detail="Valid platform super-admin credentials are required.",
                status_code=401,
            )

        status_filter = request.query_params.get("status")
        query = (request.query_params.get("q") or "").strip()
        raw_limit = request.query_params.get("limit") or "50"
        try:
            limit = max(1, min(int(raw_limit), 100))
        except (TypeError, ValueError):
            return problem_response(
                code="validation_error",
                title="Invalid limit",
                detail="limit must be an integer between 1 and 100.",
                status_code=422,
            )

        qs = _Tenant.objects.exclude(schema_name="public").order_by(
            "-created_at", "-id"
        )
        if status_filter:
            valid = {c.value for c in _Tenant.Status}
            if status_filter not in valid:
                return problem_response(
                    code="validation_error",
                    title="Invalid status filter",
                    detail=f"status must be one of: {sorted(valid)}",
                    status_code=422,
                )
            qs = qs.filter(status=status_filter)

        if query:
            qs = qs.filter(Q(slug__icontains=query) | Q(name__icontains=query))

        raw_cursor = request.query_params.get("cursor")
        if raw_cursor:
            decoded = _decode_cursor(raw_cursor)
            if decoded is None:
                return problem_response(
                    code="validation_error",
                    title="Invalid cursor",
                    detail="The pagination cursor is malformed or expired.",
                    status_code=422,
                )
            cursor_created_at, cursor_id = decoded
            qs = qs.filter(
                Q(created_at__lt=cursor_created_at)
                | Q(created_at=cursor_created_at, id__lt=cursor_id)
            )

        rows = list(qs[: limit + 1])
        has_more = len(rows) > limit
        page = rows[:limit]
        next_cursor = (
            _encode_cursor(page[-1].created_at, page[-1].id)
            if has_more and page
            else None
        )

        tenant_ids = [t.id for t in page]
        from apps.core.models import Subscription as SubModel

        from .plan_snapshot import tenant_plan_snapshot

        # Same helper the Lab Detail screen uses, so list and detail can never
        # disagree on plan name or price.
        snapshots = tenant_plan_snapshot(tenant_ids)

        tenants_data = []
        for t in page:
            snapshot = snapshots.get(t.id)
            plan_name = snapshot["name"] if snapshot else "Starter"
            plan_price = snapshot["price"] if snapshot else "0.00"
            mrr_contribution = (
                plan_price
                if snapshot and snapshot["status"] == SubModel.Status.ACTIVE
                else "0.00"
            )
            tenants_data.append(
                {
                    "id": str(t.id),
                    "slug": t.slug,
                    "name": t.name,
                    "schema_name": t.schema_name,
                    "status": t.status,
                    "city": t.city or "Lahore",
                    "province": t.province or "Punjab",
                    "branch_count": t.branch_count,
                    "staff_count": t.staff_count,
                    "plan_name": plan_name,
                    "plan_price": plan_price,
                    "plan_status": snapshot["status"] if snapshot else None,
                    "is_demo": bool(snapshot and snapshot.get("is_demo")),
                    "mrr_contribution": mrr_contribution,
                    "created_at": t.created_at.isoformat(),
                    "updated_at": t.updated_at.isoformat(),
                }
            )

        return Response(
            {
                "tenants": tenants_data,
                "next_cursor": next_cursor,
            },
            status=200,
        )

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
                city=validated.get("city", ""),
                province=validated.get("province", ""),
                owner_phone=validated.get("resolved_owner_phone", ""),
                staff_seats=validated.get("staff_seats"),
                branch_count=validated.get("branch_count", 1),
                enabled_roles=validated.get("enabled_roles", []),
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
                "temp_password": result.temp_password,
                "created_at": result.tenant.created_at.isoformat(),
            },
            status=202,
        )


class _PlatformBaseView(APIView):
    """Shared auth + error handling for platform endpoints."""

    authentication_classes = [PlatformJWTAuthentication]
    permission_classes = [IsAuthenticatedPlatformUser]

    def handle_exception(self, exc: Exception) -> Response:
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

    def _require_totp(self, user: PlatformUser) -> Response | None:
        if not user.totp_enabled:
            return problem_response(
                code="totp_required",
                title="TOTP 2FA enrolment required",
                detail="Super Admin accounts must enable TOTP before writes.",
                status_code=403,
            )
        return None


def _plan_to_dict(plan: Any) -> dict[str, Any]:
    return {
        "id": str(plan.id),
        "name": plan.name,
        "price": str(plan.price),
        "max_branches": plan.max_branches,
        "max_staff": getattr(plan, "max_staff", None),
        "is_active": plan.is_active,
        "created_at": plan.created_at.isoformat(),
        "updated_at": plan.updated_at.isoformat(),
    }


class PlatformPlanListCreateView(_PlatformBaseView):
    """GET/POST /api/v1/platform/plans (Doc 04 §11.1, §15.1)."""

    def get(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        from apps.core.models import Plan as PlanModel

        include_inactive = request.query_params.get("include_inactive", "").lower() in (
            "1",
            "true",
            "yes",
        )
        if include_inactive:
            plans = PlanModel.objects.all().order_by("name")
        else:
            # Retired plans (e.g. the old Standard Lab tier) stay in the table for
            # historical subscriptions but are never offered for selection.
            plans = PlanModel.objects.filter(is_active=True).order_by("price")
        return Response({"plans": [_plan_to_dict(p) for p in plans]}, status=200)

    def post(self, request: Request, *args: Any, **kwargs: Any) -> Response:

        from django.db import IntegrityError, transaction

        from apps.core.models import Plan as PlanModel
        from apps.core.models import PlatformAudit
        from apps.platform.serializers import PlanCreateSerializer

        user = request.user
        assert isinstance(user, PlatformUser)
        totp_resp = self._require_totp(user)
        if totp_resp is not None:
            return totp_resp

        # BL-V1: money must be a Decimal string, not a JSON number.
        raw_price = request.data.get("price")
        if raw_price is not None and not isinstance(raw_price, str):
            return problem_response(
                code="money_must_be_string",
                title="Validation error",
                detail='Price must be a Decimal string, e.g. "5000.00".',
                status_code=422,
                errors={"price": ["money_must_be_string"]},
            )

        serializer = PlanCreateSerializer(data=request.data)
        if not serializer.is_valid():
            field_errors: dict[str, list[str]] = {
                str(k): [str(m) for m in v]
                for k, v in serializer.errors.items()
                if isinstance(v, list)
            }
            code = "validation_error"
            for msgs in field_errors.values():
                if "money_must_be_string" in msgs:
                    code = "money_must_be_string"
                    break
            return problem_response(
                code=code,
                title="Validation error",
                detail="Plan creation failed validation.",
                status_code=422,
                errors=field_errors,
            )

        validated = serializer.validated_data
        try:
            with transaction.atomic():
                plan = PlanModel.objects.create(
                    name=validated["name"],
                    price=validated["price"],
                    max_branches=validated.get("max_branches"),
                    is_active=True,
                )
                PlatformAudit.objects.create(
                    actor_id=user.id,
                    action="plan.created",
                    entity_type="plan",
                    entity_id=plan.id,
                    after_jsonb={"name": plan.name, "price": str(plan.price)},
                )
        except IntegrityError:
            return problem_response(
                code="duplicate_plan_name",
                title="Duplicate plan name",
                detail=f"A plan named '{validated['name']}' already exists.",
                status_code=422,
            )
        return Response(_plan_to_dict(plan), status=201)


class PlatformPlanRetireView(_PlatformBaseView):
    """POST /api/v1/platform/plans/{id}/retire (Doc 04 §11.1, §15.1)."""

    def post(
        self, request: Request, plan_id: uuid.UUID, *args: Any, **kwargs: Any
    ) -> Response:
        from django.db import transaction

        from apps.core.models import Plan as PlanModel
        from apps.core.models import PlatformAudit
        from apps.core.models import Subscription as SubscriptionModel

        user = request.user
        assert isinstance(user, PlatformUser)
        totp_resp = self._require_totp(user)
        if totp_resp is not None:
            return totp_resp

        plan = PlanModel.objects.filter(id=plan_id).first()
        if plan is None:
            return problem_response(
                code="not_found",
                title="Not found",
                detail="Plan not found.",
                status_code=404,
            )

        # Referenced plans cannot be retired — 409 plan_in_use (Doc 04 §11.1).
        if SubscriptionModel.objects.filter(plan=plan).exists():
            return problem_response(
                code="plan_in_use",
                title="Plan in use",
                detail=(
                    "This plan is referenced by one or more subscriptions "
                    "and cannot be retired."
                ),
                status_code=409,
            )

        with transaction.atomic():
            plan.is_active = False
            plan.save(update_fields=["is_active", "updated_at"])
            PlatformAudit.objects.create(
                actor_id=user.id,
                action="plan.retired",
                entity_type="plan",
                entity_id=plan.id,
                after_jsonb={"name": plan.name, "is_active": False},
            )
        return Response(_plan_to_dict(plan), status=200)


class PlatformTenantSubscriptionView(_PlatformBaseView):
    """POST /api/v1/platform/tenants/{id}/subscription (Doc 04 §15.1).

    Creates the new subscription row; the previous active row is closed in
    the same transaction. Invalidates the cached access mode at once.
    """

    def post(
        self, request: Request, tenant_id: uuid.UUID, *args: Any, **kwargs: Any
    ) -> Response:
        from django.db import transaction
        from django.utils import timezone as dj_timezone

        from apps.core.models import Plan as PlanModel
        from apps.core.models import PlatformAudit
        from apps.core.models import Subscription as SubscriptionModel
        from apps.core.models import Tenant as TenantModel
        from apps.platform.access import invalidate_access_mode_cache
        from apps.platform.serializers import SubscriptionChangeSerializer

        user = request.user
        assert isinstance(user, PlatformUser)
        totp_resp = self._require_totp(user)
        if totp_resp is not None:
            return totp_resp

        tenant = TenantModel.objects.filter(id=tenant_id).first()
        if tenant is None:
            return problem_response(
                code="not_found",
                title="Not found",
                detail="Tenant not found.",
                status_code=404,
            )

        serializer = SubscriptionChangeSerializer(data=request.data)
        if not serializer.is_valid():
            field_errors: dict[str, list[str]] = {
                str(k): [str(m) for m in v]
                for k, v in serializer.errors.items()
                if isinstance(v, list)
            }
            return problem_response(
                code="validation_error",
                title="Validation error",
                detail="Subscription change failed validation.",
                status_code=422,
                errors=field_errors,
            )
        validated = serializer.validated_data

        plan = PlanModel.objects.filter(id=validated["plan_id"]).first()
        if plan is None:
            return problem_response(
                code="not_found",
                title="Not found",
                detail="Plan not found.",
                status_code=404,
            )
        if not plan.is_active:
            return problem_response(
                code="plan_inactive",
                title="Plan inactive",
                detail="Cannot subscribe a tenant to a retired plan.",
                status_code=422,
            )

        now = dj_timezone.now()
        with transaction.atomic():
            previous = (
                SubscriptionModel.objects.filter(
                    tenant=tenant, status=SubscriptionModel.Status.ACTIVE
                )
                .order_by("-created_at")
                .first()
            )
            before_plan_id = str(previous.plan_id) if previous else None
            if previous is not None:
                previous.status = SubscriptionModel.Status.CANCELLED
                previous.ends_at = now
                previous.save(update_fields=["status", "ends_at", "updated_at"])

            new_sub = SubscriptionModel.objects.create(
                tenant=tenant,
                plan=plan,
                status=validated["status"],
                starts_at=now,
                ends_at=validated.get("ends_at"),
            )
            PlatformAudit.objects.create(
                actor_id=user.id,
                action="subscription.changed",
                entity_type="subscription",
                entity_id=new_sub.id,
                before_jsonb={
                    "tenant_id": str(tenant.id),
                    "plan_id": before_plan_id,
                },
                after_jsonb={
                    "tenant_id": str(tenant.id),
                    "tenant_slug": tenant.slug,
                    "plan_id": str(plan.id),
                    "status": validated["status"],
                },
            )

        # Invalidate cached access mode at once (Doc 04 §11.2).
        invalidate_access_mode_cache(tenant.slug)

        return Response(
            {
                "id": str(new_sub.id),
                "tenant_id": str(tenant.id),
                "plan_id": str(plan.id),
                "status": new_sub.status,
                "starts_at": new_sub.starts_at.isoformat(),
                "ends_at": (new_sub.ends_at.isoformat() if new_sub.ends_at else None),
            },
            status=201,
        )
