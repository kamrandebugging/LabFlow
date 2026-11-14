"""Staff CRUD and credential resets (D4, FR-2/3/7/9/10/11, S2/S3/S4/S12/S14).

Business rules live here; views stay thin. Every mutation writes its audit row
in the same transaction as the state change. Nothing in this module accepts a
tenant id from a request body: the active PostgreSQL schema is the tenant.

Security invariants:
- The Lab Owner may call any method. A Manager may reset ONLY Receptionist and
  Technician credentials (password and 2FA), never Owner, Manager or
  Pathologist, and never their own account.
- The Owner account can be read but never edited, deactivated, reactivated or
  credential-reset through these methods (Owner resets are Flow 1, issued by the
  Platform Owner).
- A role must be enabled for this tenant on every create AND every edit.
- The branch must belong to this tenant (schema-scoped query).
- Password hashes, TOTP secrets and backup codes never leave this module.
"""

from __future__ import annotations

import uuid
from datetime import timedelta
from typing import Any

from django.contrib.auth.hashers import make_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.validators import validate_email
from django.db import IntegrityError, connection, transaction
from django.db.models import Q
from django.utils import timezone

from apps.accounts.auth_service import MANDATORY_TOTP_ROLES, AuthService
from apps.accounts.models import (
    AuditLog,
    Role,
    StaffBranch,
    StaffPasswordResetRequest,
    StaffUser,
)
from apps.accounts.role_config import (
    CREATABLE_ROLES,
    ROLE_LABELS,
    effective_enabled_roles,
    get_current_tenant,
    normalize_role,
    role_label,
)
from apps.branches.models import Branch
from apps.core.models import Subscription, Tenant
from apps.core.temp_password import generate_temp_password

BRANCH_REQUIRED_ROLES = {Role.MANAGER, Role.RECEPTION, Role.TECHNICIAN}
TENANT_WIDE_ROLES = {Role.OWNER, Role.PATHOLOGIST}

_EDITABLE_FIELDS = {"display_name", "role", "branch_id"}
_CREATE_FIELDS = {"display_name", "email", "role", "branch_id"}


class StaffError(Exception):
    """Base staff CRUD error carrying an HTTP status + machine code."""

    __test__ = False
    status_code = 422
    error_code = "staff_error"

    def __init__(self, message: str = "", *, details: Any = None) -> None:
        super().__init__(message or self.error_code)
        self.details = details


class StaffNotFoundError(StaffError):
    status_code = 404
    error_code = "not_found"


class StaffForbiddenError(StaffError):
    status_code = 403
    error_code = "forbidden"


class OwnerImmutableError(StaffError):
    status_code = 403
    error_code = "owner_immutable"


class RoleNotEnabledError(StaffError):
    status_code = 422
    error_code = "role_not_enabled"


class BranchNotInTenantError(StaffError):
    status_code = 422
    error_code = "branch_not_in_tenant"


class EmailExistsError(StaffError):
    status_code = 409
    error_code = "email_exists"


class StaffLimitReachedError(StaffError):
    status_code = 422
    error_code = "staff_limit_reached"


class StaffValidationError(StaffError):
    status_code = 422
    error_code = "validation_error"


def generate_staff_temp_password() -> str:
    """CSPRNG ``LBF-XXXX-XX#`` temporary password.

    Kept as the staff-facing name; the implementation is the one shared
    generator in ``apps.core.temp_password`` so Owner and staff issuance can
    never drift into two formats.
    """
    return generate_temp_password()


def staff_seat_limit() -> int | None:
    """Effective seat cap for this tenant, or None for unlimited (FR-7).

    The lower of the active plan's ``max_staff`` and the tenant's
    ``staff_seats_limit`` wins. D-E counts every ``StaffUser`` row, including
    the Owner.
    """
    tenant = get_current_tenant()
    if tenant is None:
        return None
    limits: list[int] = []
    subscription = (
        Subscription.objects.filter(tenant=tenant, status=Subscription.Status.ACTIVE)
        .select_related("plan")
        .first()
    )
    if subscription and subscription.plan.max_staff is not None:
        limits.append(int(subscription.plan.max_staff))
    if tenant.staff_seats_limit is not None:
        limits.append(int(tenant.staff_seats_limit))
    return min(limits) if limits else None


def _current_schema() -> str:
    schema = getattr(connection, "schema_name", None)
    if not schema or schema == "public":
        raise StaffForbiddenError("Staff management requires a tenant schema.")
    return str(schema)


def _display_name(staff: StaffUser) -> str:
    return (staff.display_name or "").strip() or staff.email


def _branch_payload(staff: StaffUser) -> dict[str, Any] | None:
    branch = staff.branch
    if branch is None:
        return None
    return {"id": str(branch.id), "code": branch.code, "name": branch.name}


def serialize_staff(staff: StaffUser) -> dict[str, Any]:
    """Staff row without any credential material (S11)."""
    return {
        "id": str(staff.id),
        "display_name": _display_name(staff),
        "email": staff.email,
        "role": staff.role,
        "role_label": role_label(staff.role),
        "is_owner": staff.role == Role.OWNER,
        "branch": _branch_payload(staff),
        "status": "active" if staff.is_active else "deactivated",
        "is_active": staff.is_active,
        "totp_status": "enabled" if staff.totp_enabled else "disabled",
        "totp_enabled": bool(staff.totp_enabled),
        "created_at": staff.created_at.isoformat(),
        "updated_at": staff.updated_at.isoformat(),
    }


def _audit(
    *,
    actor: StaffUser,
    action: str,
    staff: StaffUser,
    before: dict[str, Any] | None,
    after: dict[str, Any] | None,
    ip: str | None = None,
    user_agent: str | None = None,
) -> None:
    AuditLog.objects.create(
        actor_id=actor.id,
        action=action,
        entity_type="staff_user",
        entity_id=staff.id,
        before_jsonb=before,
        after_jsonb=after,
        ip=ip or None,
        user_agent=user_agent or None,
    )


def _assert_owner(actor: StaffUser) -> None:
    if actor.role != Role.OWNER:
        raise StaffForbiddenError("Only the Lab Owner may manage staff.")


def _get_staff(staff_id: uuid.UUID) -> StaffUser:
    try:
        return StaffUser.objects.select_related("branch").get(pk=staff_id)
    except (StaffUser.DoesNotExist, ValueError, TypeError):
        raise StaffNotFoundError("Staff member not found.") from None


def _assert_not_owner(staff: StaffUser) -> None:
    if staff.role == Role.OWNER:
        raise OwnerImmutableError(
            "The Owner account cannot be changed through Staff management."
        )


# Flow 2: a Manager may reset these roles only.
MANAGER_RESETTABLE_ROLES: frozenset[str] = frozenset({Role.RECEPTION, Role.TECHNICIAN})

TEMP_PASSWORD_TTL_HOURS = 24


def _assert_can_reset(actor: StaffUser, staff: StaffUser) -> None:
    """Owner: any non-owner. Manager: Receptionist/Technician only.

    Enforced server-side on every request (never by hiding the button).
    """
    if actor.role == Role.OWNER:
        _assert_not_owner(staff)
        return
    if actor.role == Role.MANAGER:
        if staff.id == actor.id or staff.role not in MANAGER_RESETTABLE_ROLES:
            raise StaffForbiddenError(
                "Managers may reset only Receptionist and Technician accounts."
            )
        return
    raise StaffForbiddenError("Only the Lab Owner or a Manager may reset credentials.")


def _assert_owner_or_manager(actor: StaffUser) -> None:
    if actor.role not in (Role.OWNER, Role.MANAGER):
        raise StaffForbiddenError(
            "Only the Lab Owner or a Manager may review reset requests."
        )


def _clear_pending_totp_challenges(staff: StaffUser) -> None:
    """Drop any pending enrolment secret and login challenge for this account."""
    AuthService.clear_pending_totp_challenges(staff, _current_schema())


def _assert_role_enabled(role: str) -> None:
    tenant = get_current_tenant()
    enabled = effective_enabled_roles(tenant)
    if role not in enabled:
        raise RoleNotEnabledError(
            f"The {role_label(role)} role is not enabled for this lab.",
            details={"role": role, "enabled_roles": enabled},
        )


def _resolve_branch(role: str, raw_branch_id: Any) -> Branch | None:
    """Validate branch for a role; pathologists are tenant-wide in v1."""
    if role in TENANT_WIDE_ROLES:
        return None
    if raw_branch_id in (None, ""):
        raise BranchNotInTenantError(
            "A branch is required for this role.",
            details={"role": role},
        )
    try:
        branch_id = uuid.UUID(str(raw_branch_id))
    except (ValueError, AttributeError, TypeError):
        raise BranchNotInTenantError(
            "Invalid branch id.", details={"branch_id": str(raw_branch_id)}
        ) from None
    branch = Branch.objects.filter(pk=branch_id, deleted_at__isnull=True).first()
    if branch is None:
        raise BranchNotInTenantError("Unknown branch for this lab.")
    return branch


def _normalise_email(raw: Any) -> str:
    email = str(raw or "").strip().lower()
    try:
        validate_email(email)
    except DjangoValidationError:
        raise StaffValidationError("Enter a valid email address.") from None
    if len(email) > 255:
        raise StaffValidationError("Email is too long.")
    return email


def _normalise_display_name(raw: Any) -> str:
    name = str(raw or "").strip()
    if not name:
        raise StaffValidationError("Display name is required.")
    if len(name) > 255:
        raise StaffValidationError("Display name is too long.")
    return name


def _reject_unknown_fields(data: Any, allowed: set[str]) -> dict[str, Any]:
    if not isinstance(data, dict):
        raise StaffValidationError("Body must be a JSON object.")
    unknown = sorted(set(data) - allowed)
    if unknown:
        raise StaffValidationError(
            "Request contains unsupported fields.",
            details={"unknown_fields": unknown},
        )
    return data


def _set_branch_assignment(staff: StaffUser, branch: Branch | None) -> None:
    """Keep ``staff_user.branch`` and the ``staff_branch`` scope row in sync."""
    StaffBranch.objects.filter(staff_user=staff).delete()
    if branch is not None:
        StaffBranch.objects.create(staff_user=staff, branch=branch, is_primary=True)


def _sync_tenant_staff_count() -> None:
    """Mirror the real row count onto the public Tenant registry.

    The Platform labs list reads ``Tenant.staff_count``. D-E counts every
    StaffUser row, including the Owner, so the mirror uses the same rule.
    """
    tenant = get_current_tenant()
    if tenant is None:
        return
    tenant.staff_count = StaffUser.objects.count()
    tenant.save(update_fields=["staff_count", "updated_at"])


def _enforce_seat_limit() -> None:
    limit = staff_seat_limit()
    if limit is None:
        return
    current = StaffUser.objects.count()
    if current >= limit:
        raise StaffLimitReachedError(
            f"The plan allows {limit} staff seats; {current} are already used.",
            details={"limit": limit, "current": current, "upgrade_required": True},
        )


class StaffService:
    """Owner-only staff lifecycle."""

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    @classmethod
    def list_staff(
        cls,
        actor: StaffUser,
        *,
        limit: int = 50,
        cursor: str | None = None,
        status_filter: str | None = None,
        role_filter: str | None = None,
        q: str | None = None,
    ) -> dict[str, Any]:
        # The Owner sees every non-owner account. A Manager may use the same
        # list only to feed the "Staff passwords" section, so the server
        # narrows it to the roles a Manager is allowed to reset. Detail, edit,
        # create and lifecycle operations stay Owner-only.
        _assert_owner_or_manager(actor)
        is_owner = actor.role == Role.OWNER
        limit = max(1, min(int(limit), 200))

        owner = None
        if is_owner:
            owner = (
                StaffUser.objects.select_related("branch")
                .filter(role=Role.OWNER)
                .order_by("created_at")
                .first()
            )
        queryset = StaffUser.objects.select_related("branch").exclude(role=Role.OWNER)
        if not is_owner:
            queryset = queryset.filter(role__in=MANAGER_RESETTABLE_ROLES)

        if status_filter == "active":
            queryset = queryset.filter(is_active=True)
        elif status_filter == "deactivated":
            queryset = queryset.filter(is_active=False)
        if role_filter:
            normalized = normalize_role(role_filter)
            if normalized:
                queryset = queryset.filter(role=normalized)
        if q:
            needle = q.strip()
            queryset = queryset.filter(
                Q(email__icontains=needle) | Q(display_name__icontains=needle)
            )

        queryset = queryset.order_by("-created_at", "-id")
        if cursor:
            try:
                anchor = StaffUser.objects.get(pk=uuid.UUID(str(cursor)))
            except (StaffUser.DoesNotExist, ValueError, TypeError):
                raise StaffValidationError("Invalid cursor.") from None
            queryset = queryset.filter(
                Q(created_at__lt=anchor.created_at)
                | Q(created_at=anchor.created_at, id__lt=anchor.id)
            )

        rows = list(queryset[: limit + 1])
        has_more = len(rows) > limit
        page = rows[:limit]
        # The anchor is the LAST RETURNED row, never the look-ahead row, or
        # that row is skipped by the strict "<" filter on the next page.
        next_cursor = str(page[-1].id) if has_more and page else None

        tenant = get_current_tenant()
        enabled = effective_enabled_roles(tenant)
        branch_rows: list[dict[str, Any]] = []
        for branch in Branch.objects.filter(deleted_at__isnull=True).order_by("code"):
            branch_rows.append(
                {"id": str(branch.id), "code": branch.code, "name": branch.name}
            )

        return {
            "owner": serialize_staff(owner) if owner else None,
            "results": [serialize_staff(row) for row in page],
            "next_cursor": next_cursor,
            "staff_count": StaffUser.objects.count(),
            "plan_staff_limit": staff_seat_limit(),
            "enabled_roles": [
                {"role": role, "label": ROLE_LABELS.get(role, role)}
                for role in enabled
                if role != Role.OWNER
            ],
            "branches": branch_rows,
        }

    @classmethod
    def get_staff(cls, actor: StaffUser, staff_id: uuid.UUID) -> dict[str, Any]:
        _assert_owner(actor)
        staff = _get_staff(staff_id)
        history = (
            AuditLog.objects.filter(entity_type="staff_user", entity_id=staff.id)
            .order_by("-at")
            .values("id", "action", "actor_id", "before_jsonb", "after_jsonb", "at")[
                :50
            ]
        )
        payload = serialize_staff(staff)
        payload["created_by"] = (
            str(staff.created_by_id) if staff.created_by_id else None
        )
        payload["audit_history"] = [
            {
                "id": str(row["id"]),
                "action": row["action"],
                "actor_id": str(row["actor_id"]) if row["actor_id"] else None,
                "before": row["before_jsonb"],
                "after": row["after_jsonb"],
                "at": row["at"].isoformat() if row["at"] else None,
            }
            for row in history
        ]
        return payload

    # ------------------------------------------------------------------
    # Create
    # ------------------------------------------------------------------

    @classmethod
    def create_staff(
        cls,
        actor: StaffUser,
        data: Any,
        *,
        ip: str | None = None,
        user_agent: str | None = None,
    ) -> dict[str, Any]:
        _assert_owner(actor)
        payload = _reject_unknown_fields(data, _CREATE_FIELDS)

        display_name = _normalise_display_name(payload.get("display_name"))
        email = _normalise_email(payload.get("email"))
        role = normalize_role(payload.get("role"))
        if role is None or role not in CREATABLE_ROLES:
            raise StaffValidationError(
                "Role must be one of manager, reception, technician or pathologist.",
                details={"role": payload.get("role")},
            )
        branch = _resolve_branch(role, payload.get("branch_id"))
        temp_password = generate_staff_temp_password()
        temp_password_expires_at = timezone.now() + timedelta(
            hours=TEMP_PASSWORD_TTL_HOURS
        )

        with transaction.atomic():
            # Serialize staff creation per tenant so the seat limit and email
            # pre-check cannot both pass two concurrent requests.
            tenant = get_current_tenant()
            if tenant is not None:
                Tenant.objects.select_for_update().get(pk=tenant.id)
            _assert_role_enabled(role)
            if StaffUser.objects.filter(email__iexact=email).exists():
                raise EmailExistsError(
                    "A staff account with this email already exists."
                )
            _enforce_seat_limit()
            try:
                staff = StaffUser.objects.create(
                    email=email,
                    display_name=display_name,
                    role=role,
                    branch=branch,
                    password_hash=make_password(temp_password),
                    is_active=True,
                    password_is_temporary=True,
                    temp_password_expires_at=temp_password_expires_at,
                    totp_enabled=False,
                    created_by=actor,
                )
            except IntegrityError:
                raise EmailExistsError(
                    "A staff account with this email already exists."
                ) from None
            _set_branch_assignment(staff, branch)
            _audit(
                actor=actor,
                action="staff.created",
                staff=staff,
                before=None,
                after={
                    "display_name": display_name,
                    "email": email,
                    "role": role,
                    "branch_id": str(branch.id) if branch else None,
                    "status": "active",
                },
                ip=ip,
                user_agent=user_agent,
            )
            _sync_tenant_staff_count()
        return {
            "staff": serialize_staff(staff),
            "temp_password": temp_password,
            "password_is_temporary": True,
            "expires_at": temp_password_expires_at.isoformat(),
        }

    # ------------------------------------------------------------------
    # Edit
    # ------------------------------------------------------------------

    @classmethod
    def update_staff(
        cls,
        actor: StaffUser,
        staff_id: uuid.UUID,
        data: Any,
        *,
        ip: str | None = None,
        user_agent: str | None = None,
    ) -> dict[str, Any]:
        _assert_owner(actor)
        staff = _get_staff(staff_id)
        _assert_not_owner(staff)
        payload = _reject_unknown_fields(data, _EDITABLE_FIELDS)
        if not payload:
            raise StaffValidationError("Provide at least one field to update.")

        display_name: str = _display_name(staff)
        before = {
            "display_name": display_name,
            "role": staff.role,
            "branch_id": str(staff.branch_id) if staff.branch_id else None,
        }

        if "display_name" in payload:
            display_name = _normalise_display_name(payload["display_name"])

        role = staff.role
        if "role" in payload:
            normalized = normalize_role(payload["role"])
            if normalized is None or normalized not in CREATABLE_ROLES:
                raise StaffValidationError(
                    "Role must be one of manager, reception, technician or pathologist."
                )
            if normalized != staff.role:
                _assert_role_enabled(normalized)
            role = normalized

        role_changed = role != staff.role
        branch_changed = "branch_id" in payload or role_changed
        branch = staff.branch
        if branch_changed:
            branch = _resolve_branch(
                role,
                payload.get("branch_id", staff.branch_id),
            )

        with transaction.atomic():
            staff.display_name = display_name
            staff.role = role
            staff.branch = branch
            staff.save(update_fields=["display_name", "role", "branch", "updated_at"])
            # SB-4/SB-5: a rename must never wipe a multi-branch roster.
            if branch_changed:
                _set_branch_assignment(staff, branch)
            after = {
                "display_name": display_name,
                "role": role,
                "branch_id": str(branch.id) if branch else None,
            }
            _audit(
                actor=actor,
                action="staff.updated",
                staff=staff,
                before=before,
                after=after,
                ip=ip,
                user_agent=user_agent,
            )

        # A role promotion into a mandatory-TOTP role must not inherit a full
        # pre-promotion session. Force a fresh login + enrolment.
        if role_changed and role in MANDATORY_TOTP_ROLES and not staff.totp_enabled:
            AuthService.revoke_all_sessions(
                staff_user_id=staff.id,
                tenant_id=_current_schema(),
                reason="role_requires_totp",
                ip=ip,
                user_agent=user_agent,
                actor_id=actor.id,
            )

        return serialize_staff(staff)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    @classmethod
    def deactivate_staff(
        cls,
        actor: StaffUser,
        staff_id: uuid.UUID,
        *,
        ip: str | None = None,
        user_agent: str | None = None,
    ) -> dict[str, Any]:
        _assert_owner(actor)
        staff = _get_staff(staff_id)
        _assert_not_owner(staff)
        if not staff.is_active:
            return serialize_staff(staff)

        with transaction.atomic():
            staff.is_active = False
            staff.save(update_fields=["is_active", "updated_at"])
            _audit(
                actor=actor,
                action="staff.deactivated",
                staff=staff,
                before={"status": "active"},
                after={"status": "deactivated"},
                ip=ip,
                user_agent=user_agent,
            )

        # S12: deactivation immediately kills every live session/refresh token.
        AuthService.revoke_all_sessions(
            staff_user_id=staff.id,
            tenant_id=_current_schema(),
            reason="staff_deactivated",
            ip=ip,
            user_agent=user_agent,
            actor_id=actor.id,
        )
        _sync_tenant_staff_count()
        return serialize_staff(staff)

    @classmethod
    def reactivate_staff(
        cls,
        actor: StaffUser,
        staff_id: uuid.UUID,
        *,
        ip: str | None = None,
        user_agent: str | None = None,
    ) -> dict[str, Any]:
        _assert_owner(actor)
        staff = _get_staff(staff_id)
        _assert_not_owner(staff)
        if staff.is_active:
            return serialize_staff(staff)

        # A disabled role cannot come back silently (D1/D-D). The account row
        # already exists, so reactivation does not consume a new seat.
        _assert_role_enabled(staff.role)

        with transaction.atomic():
            staff.is_active = True
            staff.save(update_fields=["is_active", "updated_at"])
            _audit(
                actor=actor,
                action="staff.reactivated",
                staff=staff,
                before={"status": "deactivated"},
                after={"status": "active", "totp_preserved": staff.totp_enabled},
                ip=ip,
                user_agent=user_agent,
            )
        _sync_tenant_staff_count()
        return serialize_staff(staff)

    @classmethod
    def reset_password(
        cls,
        actor: StaffUser,
        staff_id: uuid.UUID,
        *,
        ip: str | None = None,
        user_agent: str | None = None,
    ) -> dict[str, Any]:
        staff = _get_staff(staff_id)
        _assert_can_reset(actor, staff)

        temp_password = generate_staff_temp_password()
        expires_at = timezone.now() + timedelta(hours=TEMP_PASSWORD_TTL_HOURS)
        was_temporary = staff.password_is_temporary
        with transaction.atomic():
            staff.password_hash = make_password(temp_password)
            staff.password_is_temporary = True
            staff.temp_password_expires_at = expires_at
            staff.save(
                update_fields=[
                    "password_hash",
                    "password_is_temporary",
                    "temp_password_expires_at",
                    "updated_at",
                ]
            )
            _audit(
                actor=actor,
                action="staff.password_reset",
                staff=staff,
                before={"password_is_temporary": was_temporary},
                after={
                    "password_is_temporary": True,
                    "temp_password_expires_at": expires_at.isoformat(),
                    "totp_preserved": bool(staff.totp_enabled),
                },
                ip=ip,
                user_agent=user_agent,
            )
            # Issuing the temp password answers any pending forgot-password
            # request for this account.
            StaffPasswordResetRequest.objects.filter(
                email__iexact=staff.email,
                status=StaffPasswordResetRequest.Status.PENDING,
            ).update(
                status=StaffPasswordResetRequest.Status.RESOLVED,
                resolved_at=timezone.now(),
                resolved_by=actor.id,
            )

        AuthService.revoke_all_sessions(
            staff_user_id=staff.id,
            tenant_id=_current_schema(),
            reason="staff_password_reset",
            ip=ip,
            user_agent=user_agent,
            actor_id=actor.id,
        )
        return {
            "staff": serialize_staff(staff),
            "temp_password": temp_password,
            "password_is_temporary": True,
            "expires_at": expires_at.isoformat(),
        }

    @classmethod
    def reset_totp(
        cls,
        actor: StaffUser,
        staff_id: uuid.UUID,
        *,
        ip: str | None = None,
        user_agent: str | None = None,
    ) -> dict[str, Any]:
        """Clear TOTP secret + backup codes and drop pending challenges.

        Re-enrolment stays OPTIONAL (D2): the user is warned after login, never
        blocked. No secret is ever returned by this method.
        """
        staff = _get_staff(staff_id)
        _assert_can_reset(actor, staff)

        was_enabled = bool(staff.totp_enabled)
        with transaction.atomic():
            staff.totp_secret_encrypted = None
            staff.totp_backup_codes_hash = None
            staff.totp_enabled = False
            staff.save(
                update_fields=[
                    "totp_secret_encrypted",
                    "totp_backup_codes_hash",
                    "totp_enabled",
                    "updated_at",
                ]
            )
            _audit(
                actor=actor,
                action="staff.totp_reset",
                staff=staff,
                before={"totp_enabled": was_enabled},
                after={"totp_enabled": False, "re_enrolment": "optional"},
                ip=ip,
                user_agent=user_agent,
            )

        _clear_pending_totp_challenges(staff)
        return {"staff": serialize_staff(staff), "totp_enabled": False}

    # -- Forgot-password requests (staff -> Lab Owner) ---------------------

    @classmethod
    def create_password_reset_request(
        cls, email: str, display_name: str = ""
    ) -> StaffPasswordResetRequest | None:
        """Record a staff request for the Owner. Never reveals account state.

        The public endpoint always answers 202, but a row is written ONLY when
        a staff account with that email exists in this tenant. A request for an
        unknown address must not create a notification (or a stored email).
        """
        clean_email = email.strip().lower()
        if not StaffUser.objects.filter(email__iexact=clean_email).exists():
            return None
        existing = StaffPasswordResetRequest.objects.filter(
            email__iexact=clean_email,
            status=StaffPasswordResetRequest.Status.PENDING,
        ).first()
        if existing is not None:
            return existing
        return StaffPasswordResetRequest.objects.create(
            email=clean_email,
            display_name=display_name.strip()[:255],
        )

    @classmethod
    def list_password_reset_requests(cls, actor: StaffUser) -> list[dict[str, Any]]:
        _assert_owner_or_manager(actor)
        rows = StaffPasswordResetRequest.objects.filter(
            status=StaffPasswordResetRequest.Status.PENDING
        ).order_by("-created_at")
        if actor.role == Role.MANAGER:
            # A Manager may only see requests for the roles they can reset.
            allowed = {
                email.lower()
                for email in StaffUser.objects.filter(
                    role__in=MANAGER_RESETTABLE_ROLES
                ).values_list("email", flat=True)
            }
            rows = [row for row in rows if row.email.lower() in allowed]
        return [
            {
                "id": str(row.id),
                "email": row.email,
                "display_name": row.display_name,
                "status": row.status,
                "created_at": row.created_at.isoformat(),
            }
            for row in rows
        ]

    @classmethod
    def resolve_password_reset_request(
        cls,
        actor: StaffUser,
        request_id: uuid.UUID,
        *,
        ip: str | None = None,
        user_agent: str | None = None,
    ) -> dict[str, Any]:
        _assert_owner_or_manager(actor)
        row = StaffPasswordResetRequest.objects.filter(pk=request_id).first()
        if row is None:
            raise StaffNotFoundError("Password reset request not found.")
        if (
            actor.role == Role.MANAGER
            and not StaffUser.objects.filter(
                email__iexact=row.email, role__in=MANAGER_RESETTABLE_ROLES
            ).exists()
        ):
            raise StaffForbiddenError(
                "Managers may resolve only Receptionist and Technician requests."
            )
        row.status = StaffPasswordResetRequest.Status.RESOLVED
        row.resolved_at = timezone.now()
        row.resolved_by = actor.id
        row.save(update_fields=["status", "resolved_at", "resolved_by"])
        AuditLog.objects.create(
            actor_id=actor.id,
            action="staff.password_reset_request_resolved",
            entity_type="staff_password_request",
            entity_id=row.id,
            after_jsonb={"status": "resolved"},
            ip=ip or None,
            user_agent=user_agent or None,
        )
        return {"id": str(row.id), "status": row.status}
