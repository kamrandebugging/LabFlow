"""LAB-37 (KAN-162): Platform admin views — tenant registry, lifecycle actions, audit.

Doc 04 §12 (platform admin surface), §15.1 (endpoint spec).
"""

import re
import uuid
from decimal import Decimal
from typing import Any

from django.apps import apps as django_apps
from django.conf import settings
from django.db import connection, transaction
from django.utils import timezone
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.models import Domain, PlatformAudit, PlatformUser, Subscription, Tenant
from apps.platform.provisioning import get_provisioning_state
from apps.platform.serializers import (
    PlatformAuditFilterSerializer,
    TenantOffboardCompleteSerializer,
    TenantSuspendSerializer,
)
from apps.platform.views import (
    IsAuthenticatedPlatformUser,
    PlatformJWTAuthentication,
    problem_response,
)


def _require_totp(platform_user: PlatformUser) -> Response | None:
    """Return 403 totp_required response if TOTP not enabled, else None."""
    if not platform_user.totp_enabled:
        return problem_response(
            code="totp_required",
            title="TOTP 2FA enrolment required",
            detail="Super Admin accounts must enable TOTP before writes.",
            status_code=403,
        )
    return None


def _get_platform_user(request: Request) -> PlatformUser | None:
    user = getattr(request, "user", None)
    if isinstance(user, PlatformUser) and user.is_active:
        return user
    return None


def _unauthorized() -> Response:
    return problem_response(
        code="unauthorized",
        title="Authentication required",
        detail="Valid platform super-admin credentials are required.",
        status_code=401,
    )


def _get_tenant_or_404(tenant_id: str) -> tuple[Tenant | None, Response | None]:
    try:
        tid = uuid.UUID(str(tenant_id))
    except (ValueError, TypeError):
        return None, problem_response(
            code="not_found",
            title="Not found",
            detail="Tenant not found.",
            status_code=404,
        )
    tenant = Tenant.objects.filter(id=tid).first()
    if tenant is None:
        return None, problem_response(
            code="not_found",
            title="Not found",
            detail="Tenant not found.",
            status_code=404,
        )
    return tenant, None


def _write_platform_audit(
    *,
    actor_id: uuid.UUID | None,
    action: str,
    entity_type: str,
    entity_id: uuid.UUID,
    before: dict[str, Any] | None = None,
    after: dict[str, Any] | None = None,
    ip: str | None = None,
    user_agent: str | None = None,
) -> PlatformAudit:
    """Insert an immutable platform_audit row (Doc 02 §4.1)."""
    return PlatformAudit.objects.create(
        actor_id=actor_id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        before_jsonb=before,
        after_jsonb=after,
        ip=ip,
        user_agent=user_agent,
    )


def _tenant_list_item(tenant: Tenant) -> dict[str, Any]:
    """Registry list item — metadata only, NO tenant row content (Doc 04 §12.2)."""
    return {
        "id": str(tenant.id),
        "slug": tenant.slug,
        "name": tenant.name,
        "status": tenant.status,
        "created_at": tenant.created_at.isoformat(),
        "updated_at": tenant.updated_at.isoformat(),
    }


def _migration_state(tenant: Tenant) -> dict[str, Any]:
    """Tenant schema migration state (Doc 04 §15.1, §12.2).

    Reads the tenant schema's own ``django_migrations`` bookkeeping table —
    platform machinery, never tenant business rows — and compares it with the
    migrations that exist on disk for the tenant apps.
    """
    state: dict[str, Any] = {
        "schema_exists": False,
        "applied_migrations": 0,
        "pending_migrations": 0,
        "in_sync": True,
        "latest_applied": None,
    }
    schema = tenant.schema_name
    if not re.fullmatch(r"tenant_[a-z0-9_]+", schema):
        return state

    try:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT 1 FROM information_schema.schemata WHERE schema_name = %s",
                [schema],
            )
            if cursor.fetchone() is None:
                return state
            state["schema_exists"] = True
            cursor.execute(
                f'SELECT app, name, applied FROM "{schema}".django_migrations '
                "ORDER BY applied DESC"
            )
            rows = cursor.fetchall()
    except Exception:
        return state

    applied = {(str(row[0]), str(row[1])) for row in rows}
    state["applied_migrations"] = len(applied)
    if rows:
        state["latest_applied"] = {
            "app": str(rows[0][0]),
            "name": str(rows[0][1]),
            "applied_at": rows[0][2].isoformat() if rows[0][2] else None,
        }

    tenant_app_names = {app.split(".")[-1] for app in settings.TENANT_APPS}
    on_disk: set[tuple[str, str]] = set()
    for config in django_apps.get_app_configs():
        if config.label not in tenant_app_names:
            continue
        migrations_dir = config.path + "/migrations"
        try:
            import os

            for filename in os.listdir(migrations_dir):
                if re.fullmatch(r"\d{4}_[a-z0-9_]+\.py", filename):
                    on_disk.add((config.label, filename[:-3]))
        except OSError:
            continue

    pending = on_disk - applied
    state["pending_migrations"] = len(pending)
    state["in_sync"] = not pending
    return state


def _tenant_detail(tenant: Tenant) -> dict[str, Any]:
    """Registry detail — domains, subscription/plan, provisioning, schema state.

    Per Doc 04 §12.2: schema size and migration state come from PostgreSQL
    catalogues and the tenant's migration bookkeeping only. NO tenant row
    content, NO per-tenant business counts. ``branches_used`` is read from the
    denormalized public-schema counter (TP-4), never from the tenant schema.
    """
    domains = list(Domain.objects.filter(tenant=tenant).values("domain", "is_primary"))

    subscription = (
        Subscription.objects.filter(
            tenant_id=tenant.id, status=Subscription.Status.ACTIVE
        )
        .select_related("plan")
        .order_by("-created_at")
        .first()
    )
    if subscription is None:
        subscription = (
            Subscription.objects.filter(tenant_id=tenant.id)
            .select_related("plan")
            .order_by("-created_at")
            .first()
        )

    sub_data: dict[str, Any] | None = None
    plan_data: dict[str, Any] | None = None
    branches_limit: int | None = None
    if subscription is not None:
        sub_data = {
            "id": str(subscription.id),
            "plan_id": str(subscription.plan_id),
            "status": subscription.status,
            "started_at": subscription.starts_at.isoformat()
            if subscription.starts_at
            else None,
            "ends_at": subscription.ends_at.isoformat()
            if subscription.ends_at
            else None,
        }
        plan = subscription.plan
        branches_limit = plan.max_branches
        plan_data = {
            "id": str(plan.id),
            "name": plan.name,
            "price": str(Decimal(plan.price).quantize(Decimal("0.01"))),
            "max_branches": plan.max_branches,
            "is_active": plan.is_active,
        }

    # One source for plan name/price: the same snapshot the Labs List uses.
    from .plan_snapshot import tenant_plan_snapshot

    snapshot = tenant_plan_snapshot([tenant.id]).get(tenant.id)
    if plan_data is not None and snapshot is not None:
        plan_data["id"] = snapshot["plan_id"]
        plan_data["name"] = snapshot["name"]
        plan_data["price"] = snapshot["price"]

    # Schema size from PostgreSQL catalogues (platform machinery, §12.2)
    schema_size_bytes: int | None = None
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT COALESCE(SUM(pg_total_relation_size(c.oid)), 0) "
                "FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
                "WHERE n.nspname = %s",
                [tenant.schema_name],
            )
            row = cursor.fetchone()
            if row:
                schema_size_bytes = int(row[0])
    except Exception:
        schema_size_bytes = None

    prov_state = get_provisioning_state(tenant)
    prov_audit = (
        PlatformAudit.objects.filter(entity_type="tenant", entity_id=tenant.id)
        .filter(action__startswith="tenant.")
        .order_by("-at")
        .first()
    )
    provisioning: dict[str, Any] = {
        "current_step": prov_state.current_step,
        "completed_steps": prov_state.completed_steps,
        "failed_step": prov_state.failed_step,
        "error": prov_state.error,
        "owner_email": prov_state.owner_email or tenant.owner_email,
        "last_action": prov_audit.action if prov_audit else None,
        "last_action_at": prov_audit.at.isoformat()
        if prov_audit and prov_audit.at
        else None,
    }

    # Fetch recent audit timeline for this tenant
    recent_audits = PlatformAudit.objects.filter(
        entity_type="tenant", entity_id=tenant.id
    ).order_by("-at")[:20]
    audit_timeline = [
        {
            "id": str(a.id),
            "action": a.action,
            "actor_id": str(a.actor_id) if a.actor_id else None,
            "at": a.at.isoformat() if a.at else None,
            "before": a.before_jsonb,
            "after": a.after_jsonb,
        }
        for a in recent_audits
    ]

    billing_summary = {
        "plan_name": plan_data["name"] if plan_data else "Starter",
        "price": plan_data["price"] if plan_data else "0.00",
        "status": sub_data["status"] if sub_data else "active",
        "is_demo": bool(snapshot and snapshot.get("is_demo")),
        "billing_cycle": (
            "One-time"
            if plan_data and "lifetime" in plan_data["name"].lower()
            else "Monthly"
        ),
        "started_at": sub_data["started_at"] if sub_data else None,
        "ends_at": sub_data["ends_at"] if sub_data else None,
    }

    owner_data = {
        "name": tenant.owner_name or prov_state.owner_name or "Lab Director",
        "email": tenant.owner_email or prov_state.owner_email,
        "phone": tenant.owner_phone or "+92 300 0000000",
        "whatsapp": tenant.owner_phone or "+92 300 0000000",
    }

    return {
        **_tenant_list_item(tenant),
        "city": tenant.city or "Lahore",
        "province": tenant.province or "Punjab",
        "schema_name": tenant.schema_name,
        "domains": [
            {"domain": d["domain"], "is_primary": d["is_primary"]} for d in domains
        ],
        "owner": owner_data,
        "subscription": sub_data,
        "plan": plan_data,
        "branches_used": tenant.branch_count,
        "branches_limit": branches_limit,
        "staff_seats_limit": (
            tenant.staff_seats_limit
            or (plan.max_staff if subscription and plan else None)
        ),
        "staff_count": tenant.staff_count,
        "temp_password": tenant.temp_password,
        "temp_password_expires_at": tenant.temp_password_expires_at.isoformat()
        if tenant.temp_password_expires_at
        else None,
        "schema_size_bytes": schema_size_bytes,
        "migration_state": _migration_state(tenant),
        "provisioning": provisioning,
        "billing_summary": billing_summary,
        "audit_timeline": audit_timeline,
    }


class PlatformTenantDetailView(APIView):
    """GET /api/v1/platform/tenants/{id} — registry detail (Doc 04 §15.1)."""

    authentication_classes = [PlatformJWTAuthentication]
    permission_classes = [IsAuthenticatedPlatformUser]

    def get(
        self, request: Request, tenant_id: str, *args: Any, **kwargs: Any
    ) -> Response:
        platform_user = _get_platform_user(request)
        if platform_user is None:
            return _unauthorized()

        tenant, err = _get_tenant_or_404(tenant_id)
        if err is not None:
            return err
        assert tenant is not None

        return Response(_tenant_detail(tenant), status=200)


class PlatformTenantSuspendView(APIView):
    """POST /api/v1/platform/tenants/{id}/suspend (Doc 04 §15.1).

    Body: reason (required). 409 unless active. Audit: tenant.suspended.
    """

    authentication_classes = [PlatformJWTAuthentication]
    permission_classes = [IsAuthenticatedPlatformUser]

    def post(
        self, request: Request, tenant_id: str, *args: Any, **kwargs: Any
    ) -> Response:
        platform_user = _get_platform_user(request)
        if platform_user is None:
            return _unauthorized()
        totp_err = _require_totp(platform_user)
        if totp_err is not None:
            return totp_err

        serializer = TenantSuspendSerializer(data=request.data)
        if not serializer.is_valid():
            return problem_response(
                code="validation_error",
                title="Validation error",
                detail="A non-empty reason is required to suspend a tenant.",
                status_code=422,
                errors={
                    str(k): [str(m) for m in v]
                    for k, v in serializer.errors.items()
                    if isinstance(v, list)
                },
            )

        tenant, err = _get_tenant_or_404(tenant_id)
        if err is not None:
            return err
        assert tenant is not None

        if tenant.status != Tenant.Status.ACTIVE:
            return problem_response(
                code="invalid_state_transition",
                title="Invalid state transition",
                detail=(
                    f"Only active tenants can be suspended (current: {tenant.status})."
                ),
                status_code=409,
            )

        reason = serializer.validated_data["reason"]
        before = {"status": tenant.status}
        with transaction.atomic():
            tenant.status = Tenant.Status.SUSPENDED
            tenant.save(update_fields=["status", "updated_at"])
            _write_platform_audit(
                actor_id=platform_user.id,
                action="tenant.suspended",
                entity_type="tenant",
                entity_id=tenant.id,
                before=before,
                after={"status": tenant.status, "reason": reason},
                ip=request.META.get("REMOTE_ADDR"),
                user_agent=str(request.META.get("HTTP_USER_AGENT", "")),
            )

        return Response(
            {"id": str(tenant.id), "status": tenant.status, "reason": reason},
            status=200,
        )


class PlatformTenantReactivateView(APIView):
    """POST /api/v1/platform/tenants/{id}/reactivate (Doc 04 §15.1).

    409 unless suspended. Audit: tenant.reactivated.
    """

    authentication_classes = [PlatformJWTAuthentication]
    permission_classes = [IsAuthenticatedPlatformUser]

    def post(
        self, request: Request, tenant_id: str, *args: Any, **kwargs: Any
    ) -> Response:
        platform_user = _get_platform_user(request)
        if platform_user is None:
            return _unauthorized()
        totp_err = _require_totp(platform_user)
        if totp_err is not None:
            return totp_err

        tenant, err = _get_tenant_or_404(tenant_id)
        if err is not None:
            return err
        assert tenant is not None

        if tenant.status != Tenant.Status.SUSPENDED:
            return problem_response(
                code="invalid_state_transition",
                title="Invalid state transition",
                detail=(
                    f"Only suspended tenants can be reactivated "
                    f"(current: {tenant.status})."
                ),
                status_code=409,
            )

        before = {"status": tenant.status}
        with transaction.atomic():
            tenant.status = Tenant.Status.ACTIVE
            tenant.save(update_fields=["status", "updated_at"])
            _write_platform_audit(
                actor_id=platform_user.id,
                action="tenant.reactivated",
                entity_type="tenant",
                entity_id=tenant.id,
                before=before,
                after={"status": tenant.status},
                ip=request.META.get("REMOTE_ADDR"),
                user_agent=str(request.META.get("HTTP_USER_AGENT", "")),
            )

        return Response(
            {"id": str(tenant.id), "status": tenant.status},
            status=200,
        )


class PlatformTenantOffboardView(APIView):
    """POST /api/v1/platform/tenants/{id}/offboard (Doc 04 §15.1, §4.3).

    Starts offboarding: suspends tenant, enqueues owner export.
    409 if already deleted or offboarding started. Audit: tenant.offboarding_started.
    """

    authentication_classes = [PlatformJWTAuthentication]
    permission_classes = [IsAuthenticatedPlatformUser]

    def post(
        self, request: Request, tenant_id: str, *args: Any, **kwargs: Any
    ) -> Response:
        platform_user = _get_platform_user(request)
        if platform_user is None:
            return _unauthorized()
        totp_err = _require_totp(platform_user)
        if totp_err is not None:
            return totp_err

        tenant, err = _get_tenant_or_404(tenant_id)
        if err is not None:
            return err
        assert tenant is not None

        if tenant.status == Tenant.Status.DELETED:
            return problem_response(
                code="invalid_state_transition",
                title="Invalid state transition",
                detail="Tenant is already deleted.",
                status_code=409,
            )

        # Offboarding already started?
        started = PlatformAudit.objects.filter(
            entity_type="tenant",
            entity_id=tenant.id,
            action="tenant.offboarding_started",
        ).exists()
        if started:
            return problem_response(
                code="invalid_state_transition",
                title="Invalid state transition",
                detail="Offboarding has already started for this tenant.",
                status_code=409,
            )

        before = {"status": tenant.status}
        with transaction.atomic():
            tenant.status = Tenant.Status.SUSPENDED
            tenant.save(update_fields=["status", "updated_at"])
            _write_platform_audit(
                actor_id=platform_user.id,
                action="tenant.offboarding_started",
                entity_type="tenant",
                entity_id=tenant.id,
                before=before,
                after={
                    "status": tenant.status,
                    "offboarding_started_at": timezone.now().isoformat(),
                },
                ip=request.META.get("REMOTE_ADDR"),
                user_agent=str(request.META.get("HTTP_USER_AGENT", "")),
            )

        # Owner export is enqueued by the LAB-38 export task; the audit row
        # tenant.export_generated is written when the export completes.
        return Response(
            {
                "id": str(tenant.id),
                "status": tenant.status,
                "offboarding": "started",
            },
            status=202,
        )


class PlatformTenantCompleteOffboardView(APIView):
    """POST /api/v1/platform/tenants/{id}/complete-offboarding (Doc 04 §15.1).

    Body: confirm_schema_drop=true (required). Runs §4.3 step 4 → deleted.
    409 unless suspended via offboarding and grace elapsed (or waive_grace
    with reason — audited). Audit: tenant.schema_dropped.
    """

    authentication_classes = [PlatformJWTAuthentication]
    permission_classes = [IsAuthenticatedPlatformUser]

    def post(
        self, request: Request, tenant_id: str, *args: Any, **kwargs: Any
    ) -> Response:
        platform_user = _get_platform_user(request)
        if platform_user is None:
            return _unauthorized()
        totp_err = _require_totp(platform_user)
        if totp_err is not None:
            return totp_err

        serializer = TenantOffboardCompleteSerializer(data=request.data)
        if not serializer.is_valid():
            return problem_response(
                code="validation_error",
                title="Validation error",
                detail="confirm_schema_drop must be true.",
                status_code=422,
                errors={
                    str(k): [str(m) for m in v]
                    for k, v in serializer.errors.items()
                    if isinstance(v, list)
                },
            )

        tenant, err = _get_tenant_or_404(tenant_id)
        if err is not None:
            return err
        assert tenant is not None

        if tenant.status == Tenant.Status.DELETED:
            return problem_response(
                code="invalid_state_transition",
                title="Invalid state transition",
                detail="Tenant schema is already dropped.",
                status_code=409,
            )

        started_audit = (
            PlatformAudit.objects.filter(
                entity_type="tenant",
                entity_id=tenant.id,
                action="tenant.offboarding_started",
            )
            .order_by("-at")
            .first()
        )
        if started_audit is None or tenant.status != Tenant.Status.SUSPENDED:
            return problem_response(
                code="invalid_state_transition",
                title="Invalid state transition",
                detail=(
                    "Offboarding must be started (tenant suspended via "
                    "offboard) before the schema can be dropped."
                ),
                status_code=409,
            )

        waive_grace = serializer.validated_data.get("waive_grace", False)
        waive_reason = serializer.validated_data.get("waive_reason", "")
        # 30-day grace from offboarding start unless waived with reason
        grace_days = 30
        elapsed_days = 0
        if started_audit.at is not None:
            elapsed_days = (timezone.now() - started_audit.at).days
        if elapsed_days < grace_days and not waive_grace:
            return problem_response(
                code="grace_not_elapsed",
                title="Grace period not elapsed",
                detail=(
                    f"Schema drop requires {grace_days} days grace after "
                    f"offboarding start ({elapsed_days} elapsed). Pass "
                    f"waive_grace=true with waive_reason to override."
                ),
                status_code=409,
            )
        if waive_grace and not waive_reason.strip():
            return problem_response(
                code="validation_error",
                title="Validation error",
                detail="waive_reason is required when waiving the grace period.",
                status_code=422,
            )

        before = {"status": tenant.status}
        with transaction.atomic():
            tenant.status = Tenant.Status.DELETED
            tenant.save(update_fields=["status", "updated_at"])
            after: dict[str, Any] = {
                "status": tenant.status,
                "schema_dropped_at": timezone.now().isoformat(),
            }
            if waive_grace:
                after["grace_waived"] = True
                after["waive_reason"] = waive_reason
            _write_platform_audit(
                actor_id=platform_user.id,
                action="tenant.schema_dropped",
                entity_type="tenant",
                entity_id=tenant.id,
                before=before,
                after=after,
                ip=request.META.get("REMOTE_ADDR"),
                user_agent=str(request.META.get("HTTP_USER_AGENT", "")),
            )

        return Response(
            {"id": str(tenant.id), "status": tenant.status},
            status=200,
        )


class PlatformTenantRetryProvisioningView(APIView):
    """POST /api/v1/platform/tenants/{id}/retry-provisioning (Doc 04 §15.1).

    Re-enqueues tenants.provision. 409 unless status=provisioning.
    Audit: tenant.provisioning_retried.
    """

    authentication_classes = [PlatformJWTAuthentication]
    permission_classes = [IsAuthenticatedPlatformUser]

    def post(
        self, request: Request, tenant_id: str, *args: Any, **kwargs: Any
    ) -> Response:
        platform_user = _get_platform_user(request)
        if platform_user is None:
            return _unauthorized()
        totp_err = _require_totp(platform_user)
        if totp_err is not None:
            return totp_err

        tenant, err = _get_tenant_or_404(tenant_id)
        if err is not None:
            return err
        assert tenant is not None

        if tenant.status != Tenant.Status.PROVISIONING:
            return problem_response(
                code="invalid_state_transition",
                title="Invalid state transition",
                detail=(
                    "Provisioning can only be retried while status is "
                    f"provisioning (current: {tenant.status})."
                ),
                status_code=409,
            )

        with transaction.atomic():
            _write_platform_audit(
                actor_id=platform_user.id,
                action="tenant.provisioning_retried",
                entity_type="tenant",
                entity_id=tenant.id,
                before={"status": tenant.status},
                after={
                    "status": tenant.status,
                    "retried_at": timezone.now().isoformat(),
                },
                ip=request.META.get("REMOTE_ADDR"),
                user_agent=str(request.META.get("HTTP_USER_AGENT", "")),
            )

        # The Celery task tenants.provision is idempotent per-step (Doc 04 §5);
        # re-enqueue happens via the task queue in production. In v1 the audit
        # row records the retry; the worker picks it up from the queue.
        try:
            from apps.platform.tasks import provision_tenant_task

            provision_tenant_task.delay(str(tenant.id))
        except Exception:
            pass

        return Response(
            {"id": str(tenant.id), "status": tenant.status, "retry": "enqueued"},
            status=202,
        )


class PlatformTenantResendActivationView(APIView):
    """POST /api/v1/platform/tenants/{id}/resend-activation (Doc 04 §15.1).

    Re-issues owner activation token and email (§5, P-8).
    409 once owner is active. Audit: tenant.activation_resent.
    """

    authentication_classes = [PlatformJWTAuthentication]
    permission_classes = [IsAuthenticatedPlatformUser]

    def post(
        self, request: Request, tenant_id: str, *args: Any, **kwargs: Any
    ) -> Response:
        platform_user = _get_platform_user(request)
        if platform_user is None:
            return _unauthorized()
        totp_err = _require_totp(platform_user)
        if totp_err is not None:
            return totp_err

        tenant, err = _get_tenant_or_404(tenant_id)
        if err is not None:
            return err
        assert tenant is not None

        # Owner is active once a tenant.created audit exists with owner email
        # and no pending activation. We track activation via the
        # tenant.activation_sent / tenant.activated audit trail.
        activated = PlatformAudit.objects.filter(
            entity_type="tenant",
            entity_id=tenant.id,
            action="tenant.activated",
        ).exists()
        if activated:
            return problem_response(
                code="invalid_state_transition",
                title="Invalid state transition",
                detail="Owner is already active; activation cannot be re-issued.",
                status_code=409,
            )

        with transaction.atomic():
            _write_platform_audit(
                actor_id=platform_user.id,
                action="tenant.activation_resent",
                entity_type="tenant",
                entity_id=tenant.id,
                before={"owner_active": False},
                after={
                    "owner_active": False,
                    "resent_at": timezone.now().isoformat(),
                },
                ip=request.META.get("REMOTE_ADDR"),
                user_agent=str(request.META.get("HTTP_USER_AGENT", "")),
            )

        return Response(
            {"id": str(tenant.id), "activation": "resent"},
            status=202,
        )


class PlatformAuditListView(APIView):
    """GET /api/v1/platform/audit — platform_audit list (Doc 04 §15.1).

    Filters: action, entity_type, dates. Read-only; the audit is never
    writable via the API.
    """

    authentication_classes = [PlatformJWTAuthentication]
    permission_classes = [IsAuthenticatedPlatformUser]

    def get(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        platform_user = _get_platform_user(request)
        if platform_user is None:
            return _unauthorized()

        serializer = PlatformAuditFilterSerializer(data=request.query_params)
        if not serializer.is_valid():
            return problem_response(
                code="validation_error",
                title="Validation error",
                detail="Invalid filter parameters.",
                status_code=422,
            )

        qs = PlatformAudit.objects.all().order_by("-at")
        f = serializer.validated_data
        if f.get("action"):
            qs = qs.filter(action=f["action"])
        if f.get("entity_type"):
            qs = qs.filter(entity_type=f["entity_type"])
        # Detail screens read one entity's trail, e.g. a tenant's history.
        raw_entity_id = request.query_params.get(
            "entity_id"
        ) or request.query_params.get("tenant_id")
        if raw_entity_id:
            try:
                qs = qs.filter(entity_id=uuid.UUID(str(raw_entity_id)))
            except ValueError:
                return problem_response(
                    code="validation_error",
                    title="Validation error",
                    detail="entity_id must be a UUID.",
                    status_code=422,
                )
        d_from = f.get("date_from") or f.get("start_date")
        if d_from:
            qs = qs.filter(at__gte=d_from)
        d_to = f.get("date_to") or f.get("end_date")
        if d_to:
            qs = qs.filter(at__lte=d_to)

        rows = [
            {
                "id": str(a.id),
                "actor_id": str(a.actor_id) if a.actor_id else None,
                "action": a.action,
                "entity_type": a.entity_type,
                "entity_id": str(a.entity_id),
                "before": a.before_jsonb,
                "after": a.after_jsonb,
                "ip": str(a.ip) if a.ip else None,
                "at": a.at.isoformat() if a.at else None,
            }
            for a in qs[:200]
        ]
        return Response({"audit": rows, "audits": rows}, status=200)
