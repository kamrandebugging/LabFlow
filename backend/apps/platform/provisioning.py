import json
import logging
import re
import secrets
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import timedelta
from typing import Any, cast

from django.conf import settings
from django.contrib.auth.hashers import make_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.mail import send_mail
from django.core.management import call_command
from django.core.validators import validate_email
from django.db import IntegrityError, connection, transaction
from django.utils import timezone
from django_tenants.utils import schema_context

from apps.accounts.models import PasswordResetToken, Role, StaffUser
from apps.core.models import Domain, Plan, PlatformAudit, Subscription, Tenant
from apps.platform.seeds import seed_tenant_p6_data, seed_tenant_p7_settings
from apps.platform.tasks import provision_tenant_task

logger = logging.getLogger("labflow.provisioning")

SLUG_REGEX = re.compile(r"^[a-z][a-z0-9]{2,29}$")
SCHEMA_NAME_REGEX = re.compile(r"^tenant_[a-z][a-z0-9]{2,29}$")

PROVISIONING_STEPS: tuple[str, ...] = (
    "P-3",
    "P-4",
    "P-5",
    "P-6",
    "P-7",
    "P-8",
    "P-9",
)

ACTIVATION_TOKEN_TTL_HOURS: int = 72

TENANT_APPEND_ONLY_TABLES: tuple[str, ...] = (
    "audit_log",
    "payment",
    "sample_event",
    "report_version",
    "critical_notification",
    "share_ledger_entry",
)

RESERVED_SLUGS: frozenset[str] = frozenset(
    {
        # Platform / service names (Doc 04 §5.1)
        "www",
        "api",
        "admin",
        "app",
        "platform",
        "internal",
        "static",
        "media",
        "assets",
        "cdn",
        "n8n",
        "sentry",
        "minio",
        "staging",
        "health",
        "metrics",
        # Account words (Doc 04 §5.1)
        "login",
        "signup",
        "register",
        "account",
        "billing",
        "support",
        "help",
        # Mail / protocol names (Doc 04 §5.1)
        "mail",
        "smtp",
        "imap",
        "ftp",
        # System words (Doc 04 §5.1)
        "public",
        "tenant",
        "tenants",
        "system",
        "root",
        "labflow",
        "test",
        "demo",
        "example",
        "null",
    }
)


class ProvisioningError(Exception):
    """Domain exception carrying RFC 9457 problem+json fields

    (Doc 03 §6.1, Doc 04 §15).
    """

    def __init__(
        self,
        *,
        code: str,
        title: str,
        detail: str,
        status_code: int,
        errors: dict[str, list[str]] | None = None,
    ) -> None:
        super().__init__(detail)
        self.code = code
        self.title = title
        self.detail = detail
        self.status_code = status_code
        self.errors = errors or {}


@dataclass(frozen=True)
class ProvisionTenantInput:
    name: str
    slug: str
    plan_id: uuid.UUID
    owner_email: str
    owner_name: str
    actor_id: uuid.UUID | None = None
    idempotency_key: str | None = None
    ip_address: str | None = None
    user_agent: str = ""


@dataclass(frozen=True)
class ProvisionTenantResult:
    tenant: Tenant
    domain: Domain
    subscription: Subscription
    owner_email: str
    owner_name: str


@dataclass(frozen=True)
class ProvisioningStateSnapshot:
    current_step: str | None
    completed_steps: list[str]
    failed_step: str | None
    error: str | None
    owner_email: str
    owner_name: str


def get_platform_base_domain() -> str:
    base = getattr(settings, "PLATFORM_BASE_DOMAIN", "labflow.app")
    return str(base).strip().lower() or "labflow.app"


def validate_slug(slug: str) -> str:
    """Validate slug format and reserved list per Doc 04 §5.1 (P-1)."""
    if not isinstance(slug, str) or not SLUG_REGEX.match(slug):
        raise ProvisioningError(
            code="slug_invalid",
            title="Invalid tenant slug",
            detail=(
                "Slug must be 3 to 30 lowercase alphanumeric characters, "
                "starting with a letter, with no hyphens."
            ),
            status_code=422,
            errors={"slug": ["Invalid slug format."]},
        )
    if slug in RESERVED_SLUGS:
        raise ProvisioningError(
            code="slug_reserved",
            title="Reserved tenant slug",
            detail=f"The slug '{slug}' is reserved and cannot be used.",
            status_code=422,
            errors={"slug": ["Slug is reserved."]},
        )
    return slug


def _validate_p1(data: ProvisionTenantInput) -> Plan:
    """Execute P-1 validation checks before opening a write transaction (Doc 04 §5)."""
    validate_slug(data.slug)

    cleaned_name = data.name.strip() if isinstance(data.name, str) else ""
    if not cleaned_name:
        raise ProvisioningError(
            code="validation_error",
            title="Validation error",
            detail="Tenant name is required.",
            status_code=422,
            errors={"name": ["This field may not be blank."]},
        )

    cleaned_owner_name = (
        data.owner_name.strip() if isinstance(data.owner_name, str) else ""
    )
    if not cleaned_owner_name:
        raise ProvisioningError(
            code="validation_error",
            title="Validation error",
            detail="Owner name is required.",
            status_code=422,
            errors={"owner_name": ["This field may not be blank."]},
        )

    cleaned_owner_email = (
        data.owner_email.strip().lower() if isinstance(data.owner_email, str) else ""
    )
    try:
        validate_email(cleaned_owner_email)
    except DjangoValidationError as exc:
        raise ProvisioningError(
            code="validation_error",
            title="Validation error",
            detail="Enter a valid owner email address.",
            status_code=422,
            errors={"owner_email": ["Enter a valid email address."]},
        ) from exc

    plan = Plan.objects.filter(id=data.plan_id).first()
    if plan is None or not plan.is_active:
        raise ProvisioningError(
            code="plan_inactive",
            title="Inactive or unknown plan",
            detail="The selected plan does not exist or is not active.",
            status_code=422,
            errors={"plan_id": ["Plan does not exist or is inactive."]},
        )

    return plan


def _check_existing_for_idempotency_or_conflict(
    data: ProvisionTenantInput,
    primary_domain: str,
) -> ProvisionTenantResult | None:
    """
    Check if slug or domain is already registered (Doc 04 §5 P-2, §15.1).
    If idempotency_key matches an existing provisioning record with identical
    parameters, return it idempotently; otherwise raise 409 slug_taken.
    """
    existing_tenant = Tenant.objects.filter(slug=data.slug).first()
    existing_domain = (
        Domain.objects.select_related("tenant").filter(domain=primary_domain).first()
    )

    if existing_tenant is None and existing_domain is None:
        return None

    if existing_tenant is not None and data.idempotency_key:
        matching_audit = PlatformAudit.objects.filter(
            action="tenant.created",
            entity_type="tenant",
            entity_id=existing_tenant.id,
        ).first()
        if matching_audit and isinstance(matching_audit.after_jsonb, dict):
            recorded_key = matching_audit.after_jsonb.get("idempotency_key")
            recorded_plan = matching_audit.after_jsonb.get("plan_id")
            recorded_email = matching_audit.after_jsonb.get("owner_email")
            recorded_name = matching_audit.after_jsonb.get("name")
            if recorded_key == data.idempotency_key:
                if (
                    recorded_plan == str(data.plan_id)
                    and recorded_email == data.owner_email.strip().lower()
                    and recorded_name == data.name.strip()
                ):
                    dom = Domain.objects.get(tenant=existing_tenant, is_primary=True)
                    sub = Subscription.objects.get(
                        tenant=existing_tenant, status="active"
                    )
                    return ProvisionTenantResult(
                        tenant=existing_tenant,
                        domain=dom,
                        subscription=sub,
                        owner_email=data.owner_email.strip().lower(),
                        owner_name=data.owner_name.strip(),
                    )
                raise ProvisioningError(
                    code="idempotency_key_reused",
                    title="Idempotency key reused with different payload",
                    detail=(
                        "The Idempotency-Key was already used with "
                        "different parameters."
                    ),
                    status_code=409,
                    errors={"idempotency_key": ["Key reused with different payload."]},
                )

    raise ProvisioningError(
        code="slug_taken",
        title="Tenant slug or domain already taken",
        detail=(
            f"The slug '{data.slug}' or domain '{primary_domain}' is "
            f"already registered."
        ),
        status_code=409,
        errors={"slug": ["Slug or domain is already taken."]},
    )


def create_tenant_provisioning(data: ProvisionTenantInput) -> ProvisionTenantResult:
    """
    Execute P-1 (validate) and P-2 (atomic public-schema registration + on_commit task)
    per Doc 04 §5 and §15.1.
    """
    plan = _validate_p1(data)
    base_domain = get_platform_base_domain()
    primary_domain = f"{data.slug}.{base_domain}"
    schema_name = f"tenant_{data.slug}"
    cleaned_name = data.name.strip()
    cleaned_owner_email = data.owner_email.strip().lower()
    cleaned_owner_name = data.owner_name.strip()

    existing_result = _check_existing_for_idempotency_or_conflict(data, primary_domain)
    if existing_result is not None:
        return existing_result

    try:
        with transaction.atomic():
            if data.idempotency_key:
                prior_key_audit = PlatformAudit.objects.filter(
                    action="tenant.created",
                    after_jsonb__idempotency_key=data.idempotency_key,
                ).first()
                if prior_key_audit is not None:
                    raise ProvisioningError(
                        code="idempotency_key_reused",
                        title="Idempotency key reused with different payload",
                        detail=(
                            "The Idempotency-Key was already used for another tenant."
                        ),
                        status_code=409,
                        errors={
                            "idempotency_key": ["Key reused with different payload."]
                        },
                    )

            tenant = Tenant(
                slug=data.slug,
                name=cleaned_name,
                schema_name=schema_name,
                status="provisioning",
            )
            tenant.auto_create_schema = False
            tenant.save()

            domain = Domain.objects.create(
                tenant=tenant,
                domain=primary_domain,
                is_primary=True,
            )

            subscription = Subscription.objects.create(
                tenant=tenant,
                plan=plan,
                status="active",
                starts_at=timezone.now(),
                ends_at=None,
            )

            after_payload: dict[str, Any] = {
                "slug": tenant.slug,
                "name": tenant.name,
                "schema_name": tenant.schema_name,
                "status": tenant.status,
                "domain": domain.domain,
                "plan_id": str(plan.id),
                "subscription_id": str(subscription.id),
                "owner_email": cleaned_owner_email,
                "owner_name": cleaned_owner_name,
                "current_step": "P-2",
                "completed_steps": ["P-1", "P-2"],
            }
            if data.idempotency_key:
                after_payload["idempotency_key"] = data.idempotency_key

            PlatformAudit.objects.create(
                actor_id=data.actor_id,
                action="tenant.created",
                entity_type="tenant",
                entity_id=tenant.id,
                before_jsonb=None,
                after_jsonb=after_payload,
                ip=data.ip_address,
                user_agent=data.user_agent,
            )

            slug_to_enqueue = tenant.slug
            transaction.on_commit(lambda: provision_tenant_task.delay(slug_to_enqueue))
    except IntegrityError as exc:
        raise ProvisioningError(
            code="slug_taken",
            title="Tenant slug or domain already taken",
            detail=(
                f"The slug '{data.slug}' or domain '{primary_domain}' is "
                f"already registered."
            ),
            status_code=409,
            errors={"slug": ["Slug or domain is already taken."]},
        ) from exc

    return ProvisionTenantResult(
        tenant=tenant,
        domain=domain,
        subscription=subscription,
        owner_email=cleaned_owner_email,
        owner_name=cleaned_owner_name,
    )


def get_provisioning_state(tenant: Tenant) -> ProvisioningStateSnapshot:
    """
    Reconstruct the current provisioning state (completed steps, current/failed step,
    and error detail) for `tenant` from `PlatformAudit` rows (Doc 02 §4.1, Doc 04 §5).
    """
    audits = PlatformAudit.objects.filter(
        entity_type="tenant",
        entity_id=tenant.id,
    ).order_by("at", "id")

    completed: list[str] = []
    current_step: str | None = None
    failed_step: str | None = None
    error: str | None = None
    owner_email = ""
    owner_name = ""

    for audit in audits:
        payload = audit.after_jsonb if isinstance(audit.after_jsonb, dict) else {}
        if audit.action == "tenant.created":
            owner_email = str(payload.get("owner_email", owner_email))
            owner_name = str(payload.get("owner_name", owner_name))
            current_step = str(payload.get("current_step", "P-2"))
            for step_item in payload.get("completed_steps", ["P-1", "P-2"]):
                step_str = str(step_item)
                if step_str not in completed:
                    completed.append(step_str)
        elif audit.action == "tenant.provisioning_step_started":
            current_step = str(payload.get("step", "")) or current_step
            failed_step = None
            error = None
        elif audit.action == "tenant.provisioning_step_completed":
            step_done = str(payload.get("step", ""))
            if step_done and step_done not in completed:
                completed.append(step_done)
            current_step = step_done or current_step
            failed_step = None
            error = None
        elif audit.action == "tenant.provisioning_failed":
            failed_step = str(payload.get("failed_step", "")) or current_step
            error = str(payload.get("error", ""))
            current_step = failed_step
        elif audit.action == "tenant.provisioned":
            if "P-9" not in completed:
                completed.append("P-9")
            current_step = "P-9"
            failed_step = None
            error = None

    return ProvisioningStateSnapshot(
        current_step=current_step,
        completed_steps=completed,
        failed_step=failed_step,
        error=error,
        owner_email=owner_email,
        owner_name=owner_name,
    )


def _log_provisioning_step(
    *,
    tenant_slug: str,
    step: str,
    outcome: str,
    duration_ms: float,
    error: str | None = None,
) -> None:
    """Emit structured JSON log line with tenant_slug on every line (Doc 04 §5.2)."""
    payload: dict[str, Any] = {
        "event": "provisioning_step",
        "tenant_slug": tenant_slug,
        "step": step,
        "outcome": outcome,
        "duration_ms": round(duration_ms, 3),
    }
    if error is not None:
        payload["error"] = error
    logger.info(json.dumps(payload, sort_keys=True))


def _verify_tenant_schema_identity(tenant: Tenant) -> str:
    """
    Verify that `tenant.schema_name` matches `tenant_<slug>`, obeys `SCHEMA_NAME_REGEX`,
    and is not claimed by any other Tenant row in the public schema (Doc 04 §5 P-3).
    """
    expected_schema_name = f"tenant_{tenant.slug}"
    if tenant.schema_name != expected_schema_name:
        raise ValueError(
            f"Tenant schema_name mismatch: expected '{expected_schema_name}', "
            f"got '{tenant.schema_name}'."
        )
    if not SCHEMA_NAME_REGEX.match(tenant.schema_name):
        raise ValueError(f"Unsafe schema_name '{tenant.schema_name}'")

    conflicting_owner = (
        Tenant.objects.filter(schema_name=tenant.schema_name)
        .exclude(id=tenant.id)
        .exists()
    )
    if conflicting_owner:
        raise ValueError(
            f"Schema '{tenant.schema_name}' is already claimed by another "
            f"tenant record."
        )
    return expected_schema_name


# ---------------------------------------------------------------------------
# Provisioning Step Handlers (P-3 through P-9)
# ---------------------------------------------------------------------------


def _set_schema_to_public() -> None:
    set_schema = getattr(connection, "set_schema_to_public", None)
    if callable(set_schema):
        set_schema()


def execute_step_p3_create_schema(
    tenant: Tenant, _state: ProvisioningStateSnapshot
) -> None:
    """
    P-3: Create the tenant's PostgreSQL schema idempotently (Doc 04 §5 P-3).
    """
    schema_name = _verify_tenant_schema_identity(tenant)
    _set_schema_to_public()

    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT 1 FROM information_schema.schemata WHERE schema_name = %s",
            [schema_name],
        )
        already_exists = cursor.fetchone() is not None

        if not already_exists:
            cursor.execute(f'CREATE SCHEMA IF NOT EXISTS "{schema_name}"')

    _set_schema_to_public()


def execute_step_p4_migrate_schema(
    tenant: Tenant, _state: ProvisioningStateSnapshot
) -> None:
    """
    P-4: Run tenant migrations for this single schema only (Doc 04 §5 P-4).
    """
    schema_name = _verify_tenant_schema_identity(tenant)
    _set_schema_to_public()

    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT 1 FROM information_schema.schemata WHERE schema_name = %s",
            [schema_name],
        )
        if cursor.fetchone() is None:
            raise RuntimeError(
                f"Cannot run P-4 migrations: schema '{schema_name}' does not exist."
            )

    try:
        call_command(
            "migrate_schemas",
            tenant=True,
            schema_name=schema_name,
            interactive=False,
            verbosity=0,
        )
    finally:
        _set_schema_to_public()


def execute_step_p5_revoke_append_only(
    tenant: Tenant, _state: ProvisioningStateSnapshot
) -> None:
    """
    P-5: Apply and confirm the append-only REVOKE set on all 6 tenant append-only tables
    in the new schema (Doc 02 §6, Doc 04 §5 P-5 — TN-07).
    """
    schema_name = _verify_tenant_schema_identity(tenant)
    _set_schema_to_public()

    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = %s AND table_type = 'BASE TABLE'
                """,
                [schema_name],
            )
            existing_tables = {row[0] for row in cursor.fetchall()}

            missing_tables = [
                tbl for tbl in TENANT_APPEND_ONLY_TABLES if tbl not in existing_tables
            ]
            if missing_tables:
                raise RuntimeError(
                    f"P-5 append-only verification failed in schema '{schema_name}': "
                    f"missing tables {missing_tables}."
                )

            cursor.execute("SELECT 1 FROM pg_roles WHERE rolname = 'labflow_app'")
            has_labflow_app_role = cursor.fetchone() is not None

            for table_name in TENANT_APPEND_ONLY_TABLES:
                revoke_sql = (
                    "REVOKE UPDATE, DELETE, TRUNCATE ON TABLE "
                    f'"{schema_name}"."{table_name}" FROM PUBLIC, CURRENT_USER'
                )
                cursor.execute(revoke_sql)
                if has_labflow_app_role:
                    revoke_app_sql = (
                        "REVOKE UPDATE, DELETE, TRUNCATE ON TABLE "
                        f'"{schema_name}"."{table_name}" FROM labflow_app'
                    )
                    cursor.execute(revoke_app_sql)

            cursor.execute(
                """
                SELECT table_name, grantee, privilege_type
                FROM information_schema.role_table_grants
                WHERE table_schema = %s
                  AND table_name = ANY(%s)
                  AND privilege_type IN ('UPDATE', 'DELETE', 'TRUNCATE')
                  AND (
                      grantee IN ('PUBLIC', 'labflow_app')
                      OR grantee = CURRENT_USER
                  )
                """,
                [schema_name, list(TENANT_APPEND_ONLY_TABLES)],
            )
            remaining_grants = cursor.fetchall()
            if remaining_grants:
                raise RuntimeError(
                    f"P-5 append-only privilege check failed in schema "
                    f"'{schema_name}': forbidden grants still present: "
                    f"{remaining_grants}."
                )

            cursor.execute(
                """
                SELECT c.relname
                FROM pg_trigger t
                JOIN pg_class c ON c.oid = t.tgrelid
                JOIN pg_namespace n ON n.oid = c.relnamespace
                WHERE n.nspname = %s
                  AND c.relname = ANY(%s)
                  AND NOT t.tgisinternal
                  AND t.tgenabled <> 'D'
                """,
                [schema_name, list(TENANT_APPEND_ONLY_TABLES)],
            )
            trigger_protected_tables = {row[0] for row in cursor.fetchall()}
            unprotected_tables = [
                tbl
                for tbl in TENANT_APPEND_ONLY_TABLES
                if tbl not in trigger_protected_tables
            ]
            if unprotected_tables:
                raise RuntimeError(
                    f"P-5 append-only trigger check failed in schema '{schema_name}': "
                    f"tables missing active append-only trigger: {unprotected_tables}."
                )
    finally:
        _set_schema_to_public()


def execute_step_p6_seed_data(
    tenant: Tenant, _state: ProvisioningStateSnapshot
) -> None:
    """
    P-6: Seed default branch, starter catalogue with panel components and reference
    ranges, and EN/UR notification templates via get_or_create (Doc 02 §16).
    Never seeds a revenue_share_rule row (A-10) or any clinical/demo data.
    """
    _verify_tenant_schema_identity(tenant)
    _set_schema_to_public()
    try:
        seed_tenant_p6_data(tenant)
    finally:
        _set_schema_to_public()


def execute_step_p7_settings_defaults(
    tenant: Tenant, _state: ProvisioningStateSnapshot
) -> None:
    """
    P-7: Seed default `tenant_setting` rows via get_or_create (Doc 04 §5 P-7, §10.2).
    """
    _verify_tenant_schema_identity(tenant)
    _set_schema_to_public()
    try:
        seed_tenant_p7_settings(tenant)
    finally:
        _set_schema_to_public()


def send_owner_activation_email(
    tenant: Tenant,
    owner: StaffUser,
    raw_token: str,
    owner_name: str = "",
) -> None:
    """
    Send owner activation email with link to tenant subdomain (Doc 04 §5 P-8).

    Email failures are logged as warnings and never block provisioning completion.
    """
    primary_domain_obj = Domain.objects.filter(tenant=tenant, is_primary=True).first()
    if primary_domain_obj and primary_domain_obj.domain:
        domain_name = primary_domain_obj.domain
    else:
        domain_name = f"{tenant.slug}.{get_platform_base_domain()}"

    activation_url = f"https://{domain_name}/activate#{raw_token}"
    greeting = f"Hello {owner_name},\n\n" if owner_name else ""
    subject = f"Activate your LabFlow account - {tenant.name}"
    message = (
        f"{greeting}Welcome to LabFlow.\n\n"
        f"An account has been created for you as the Owner of {tenant.name}.\n"
        f"Please use the following link to set your password and activate your "
        f"account:\n\n"
        f"{activation_url}\n\n"
        f"This link is valid for {ACTIVATION_TOKEN_TTL_HOURS} hours.\n"
        f"If you did not request this, please contact platform support.\n"
    )
    from_email = getattr(settings, "DEFAULT_FROM_EMAIL", "noreply@labflow.app")

    try:
        send_mail(
            subject=subject,
            message=message,
            from_email=from_email,
            recipient_list=[owner.email],
            fail_silently=False,
        )
    except Exception as exc:
        logger.warning(
            "Failed to send owner activation email for tenant '%s' to '%s': %s",
            tenant.slug,
            owner.email,
            exc,
        )


def _resolve_owner_email(tenant: Tenant) -> str:
    """Extract owner_email from the tenant.created PlatformAudit entry."""
    audit = (
        PlatformAudit.objects.filter(
            entity_type="tenant",
            entity_id=tenant.id,
            action="tenant.created",
        )
        .order_by("-at", "-id")
        .first()
    )
    if audit and isinstance(audit.after_jsonb, dict):
        email = str(audit.after_jsonb.get("owner_email", "")).strip().lower()
        if email:
            return email
    raise ValueError(f"Cannot resolve owner_email for tenant '{tenant.slug}'")


def create_tenant_owner_activation(
    tenant: Tenant,
    *,
    owner_email: str,
    owner_name: str = "",
) -> tuple[StaffUser, PasswordResetToken, str]:
    """
    Create or look up inactive Lab Owner staff_user and issue a fresh activation
    token inside the tenant's schema context (Doc 02 §5.1, Doc 04 §5 P-8, Doc 08 §4.5).

    Returns:
        tuple of (StaffUser, PasswordResetToken, raw_token)
    """
    cleaned_email = owner_email.strip().lower()
    if not cleaned_email:
        raise ValueError("owner_email cannot be empty")

    with schema_context(tenant.schema_name):
        now = timezone.now()
        owner = StaffUser.objects.filter(email=cleaned_email).first()
        if owner is None:
            owner = StaffUser.objects.create(
                email=cleaned_email,
                role=Role.OWNER,
                branch=None,
                password_hash=make_password(None),
                is_active=False,
                totp_enabled=False,
            )

        if owner.is_active:
            latest_token = (
                PasswordResetToken.objects.filter(
                    staff_user=owner,
                    purpose=PasswordResetToken.Purpose.ACTIVATION,
                )
                .order_by("-created_at")
                .first()
            )
            if latest_token is not None:
                return owner, latest_token, ""

        raw_token = secrets.token_urlsafe(32)
        token_hash = make_password(raw_token)
        expires_at = now + timedelta(hours=ACTIVATION_TOKEN_TTL_HOURS)

        # Invalidate any live predecessor activation tokens for this owner (Doc 08 §4.5)
        PasswordResetToken.objects.filter(
            staff_user=owner,
            purpose=PasswordResetToken.Purpose.ACTIVATION,
            used_at__isnull=True,
        ).update(used_at=now)

        token_record = PasswordResetToken.objects.create(
            staff_user=owner,
            token_hash=token_hash,
            purpose=PasswordResetToken.Purpose.ACTIVATION,
            expires_at=expires_at,
            used_at=None,
        )

    send_owner_activation_email(
        tenant=tenant,
        owner=owner,
        raw_token=raw_token,
        owner_name=owner_name,
    )
    return owner, token_record, raw_token


def execute_step_p8_create_owner(
    tenant: Tenant, _state: ProvisioningStateSnapshot
) -> None:
    """
    P-8: Create inactive Lab Owner and hashed activation token (Doc 04 §5 P-8).
    """
    _verify_tenant_schema_identity(tenant)
    _set_schema_to_public()
    try:
        owner_email = _state.owner_email or _resolve_owner_email(tenant)
        create_tenant_owner_activation(
            tenant,
            owner_email=owner_email,
            owner_name=_state.owner_name,
        )
    finally:
        _set_schema_to_public()


def execute_step_p9_activate(tenant: Tenant, _state: ProvisioningStateSnapshot) -> None:
    """
    P-9: Activate tenant (status='active') and write 'tenant.provisioned'
    (Doc 04 §5 P-9). Guarded so it only transitions from 'provisioning'.
    """
    with transaction.atomic():
        locked = Tenant.objects.select_for_update().get(id=tenant.id)
        if locked.status == "provisioning":
            locked.status = "active"
            locked.save(update_fields=["status", "updated_at"])
        tenant.status = locked.status


STEP_HANDLERS: dict[str, Callable[[Tenant, ProvisioningStateSnapshot], None]] = {
    "P-3": execute_step_p3_create_schema,
    "P-4": execute_step_p4_migrate_schema,
    "P-5": execute_step_p5_revoke_append_only,
    "P-6": execute_step_p6_seed_data,
    "P-7": execute_step_p7_settings_defaults,
    "P-8": execute_step_p8_create_owner,
    "P-9": execute_step_p9_activate,
}


def run_provisioning_state_machine(tenant_slug: str) -> dict[str, Any]:
    """
    TP-3 Resumable Provisioning State Machine Runner (Doc 04 §5).
    """
    run_start = time.monotonic()
    tenant = Tenant.objects.filter(slug=tenant_slug).first()
    if tenant is None:
        raise LookupError(f"Tenant with slug '{tenant_slug}' does not exist.")

    state = get_provisioning_state(tenant)
    if tenant.status == "active" and all(
        s in state.completed_steps for s in PROVISIONING_STEPS
    ):
        return {
            "tenant_slug": tenant.slug,
            "status": tenant.status,
            "resumed_noop": True,
            "completed_steps": state.completed_steps,
        }

    if tenant.status != "provisioning":
        return {
            "tenant_slug": tenant.slug,
            "status": tenant.status,
            "resumed_noop": True,
            "completed_steps": state.completed_steps,
        }

    completed_set = set(state.completed_steps)

    for step in PROVISIONING_STEPS:
        if step in completed_set:
            continue

        handler = STEP_HANDLERS[step]
        PlatformAudit.objects.create(
            actor_id=None,
            action="tenant.provisioning_step_started",
            entity_type="tenant",
            entity_id=tenant.id,
            before_jsonb={"status": tenant.status},
            after_jsonb={"step": step, "tenant_slug": tenant.slug},
        )
        Tenant.objects.filter(id=tenant.id).update(updated_at=timezone.now())

        step_start = time.monotonic()
        try:
            handler(tenant, state)
        except Exception as exc:
            duration_ms = (time.monotonic() - step_start) * 1000.0
            error_msg = f"{type(exc).__name__}: {exc}"
            _log_provisioning_step(
                tenant_slug=tenant.slug,
                step=step,
                outcome="failed",
                duration_ms=duration_ms,
                error=error_msg,
            )
            PlatformAudit.objects.create(
                actor_id=None,
                action="tenant.provisioning_failed",
                entity_type="tenant",
                entity_id=tenant.id,
                before_jsonb={"status": "provisioning", "step": step},
                after_jsonb={
                    "failed_step": step,
                    "error": error_msg,
                    "duration_ms": round(duration_ms, 3),
                    "tenant_slug": tenant.slug,
                },
            )
            raise

        duration_ms = (time.monotonic() - step_start) * 1000.0
        _log_provisioning_step(
            tenant_slug=tenant.slug,
            step=step,
            outcome="completed",
            duration_ms=duration_ms,
        )
        completed_set.add(step)

        PlatformAudit.objects.create(
            actor_id=None,
            action="tenant.provisioning_step_completed",
            entity_type="tenant",
            entity_id=tenant.id,
            before_jsonb={"step": step},
            after_jsonb={
                "step": step,
                "duration_ms": round(duration_ms, 3),
                "tenant_slug": tenant.slug,
            },
        )

        if step == "P-9":
            total_duration_ms = (time.monotonic() - run_start) * 1000.0
            PlatformAudit.objects.create(
                actor_id=None,
                action="tenant.provisioned",
                entity_type="tenant",
                entity_id=tenant.id,
                before_jsonb={"status": "provisioning"},
                after_jsonb={
                    "status": "active",
                    "total_duration_ms": round(total_duration_ms, 3),
                    "tenant_slug": tenant.slug,
                },
            )

    tenant.refresh_from_db()
    final_state = get_provisioning_state(tenant)
    return {
        "tenant_slug": tenant.slug,
        "status": tenant.status,
        "resumed_noop": False,
        "completed_steps": final_state.completed_steps,
    }


def cleanup_abandoned_provisioning(
    tenant_slug: str,
    *,
    actor_id: uuid.UUID | None = None,
) -> Tenant:
    """
    Clean up a tenant abandoned in `provisioning` state (Doc 04 §4.2, §5.2 — TN-09).
    """
    tenant = Tenant.objects.filter(slug=tenant_slug).first()
    if tenant is None:
        raise ProvisioningError(
            code="not_found",
            title="Tenant not found",
            detail=f"Tenant '{tenant_slug}' does not exist.",
            status_code=404,
        )

    if tenant.status != "provisioning":
        raise ProvisioningError(
            code="invalid_state_transition",
            title="Invalid state transition",
            detail=(
                f"Cannot clean up abandoned provisioning for tenant '{tenant_slug}' "
                f"in status '{tenant.status}'."
            ),
            status_code=409,
            errors={
                "status": [f"Tenant is in '{tenant.status}' state, not 'provisioning'."]
            },
        )

    if not SCHEMA_NAME_REGEX.match(tenant.schema_name):
        raise ValueError(f"Unsafe schema_name '{tenant.schema_name}'")

    _set_schema_to_public()

    with connection.cursor() as cursor:
        cursor.execute(f'DROP SCHEMA IF EXISTS "{tenant.schema_name}" CASCADE')

    _set_schema_to_public()

    with transaction.atomic():
        deleted_domains_count, _ = Domain.objects.filter(tenant=tenant).delete()

        tenant.auto_create_schema = False
        tenant.status = "deleted"
        tenant.save(update_fields=["status", "updated_at"])

        PlatformAudit.objects.create(
            actor_id=actor_id,
            action="tenant.abandoned_cleaned_up",
            entity_type="tenant",
            entity_id=tenant.id,
            before_jsonb={"status": "provisioning"},
            after_jsonb={
                "status": "deleted",
                "schema_dropped": tenant.schema_name,
                "domains_deleted": deleted_domains_count,
                "tenant_slug": tenant.slug,
            },
        )

    return cast(Tenant, tenant)
