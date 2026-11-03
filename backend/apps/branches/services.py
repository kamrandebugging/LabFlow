"""Branch operations service (Doc 04 §8.2, §8.3, §11.3, KAN-158 / LAB-33).

Five endpoints' business logic lives here; views are thin (role check,
strict serialization, error mapping). Every mutating operation writes its
audit row in the SAME transaction as the state change.

Decisions (spec ambiguities resolved — see LAB-33 final report):
- include_closed=true is owner-only → explicit 403 for other roles (the
  Doc 04 §15 table marks it "(O only)").
- "Referenced" for §8.2 code immutability = any patient OR sample row with
  branch FK = this branch (spec names patient/sample; invoices also FK to
  branch but are not named — deliberately not counted). Soft-deleted
  patients still count: the MRN was issued with the code.
- Unreferenced branch MAY accept a code change (TN-18); format and
  uniqueness are enforced on that path.
- No active subscription → plan limit not enforced (interim; provisioning
  always creates a subscription, so this is a data-anomaly path).
- Concurrent creates racing the last plan slot are serialized with
  pg_advisory_xact_lock keyed on the tenant (transaction-scoped,
  PgBouncer-safe per Doc 04 §11.3/F-5).
- Close takes a row lock on the branch inside the close transaction so two
  concurrent closes serialize; the preconditions are checked after the
  lock. A transfer created concurrently with the close is NOT blocked by
  this ticket — the transfer service would need the same row lock
  (follow-up, flagged in the final report).
- result_entry_enabled is NOT writable via these endpoints: Doc 04 §15's
  create/PATCH bodies do not list it (spec gap flagged in final report).
"""

import hashlib
import re
import uuid
from typing import Any

from django.db import IntegrityError, connection, transaction
from django.utils import timezone

from apps.accounts.models import AuditLog, Role, StaffUser
from apps.branches.models import Branch
from apps.core.models import Subscription
from apps.patients.models import Patient
from apps.samples.models import Sample, SampleTransfer

# Doc 04 §8.2: exactly 3 chars, uppercase letters and digits.
BRANCH_CODE_RE = re.compile(r"^[A-Z0-9]{3}$")

# Doc 04 §15 API table.
BRANCH_READ_ROLES = {
    Role.OWNER,
    Role.MANAGER,
    Role.RECEPTION,
    Role.TECHNICIAN,
    Role.PATHOLOGIST,
}
BRANCH_WRITE_ROLES = {Role.OWNER}

# Doc 04 §8.3: samples "held" at the branch block the close.
_HELD_SAMPLE_STATUSES = (
    Sample.Status.COLLECTED,
    Sample.Status.RECEIVED,
    Sample.Status.IN_PROCESS,
)

# Doc 04 §15 PATCH body (code is handled separately per §8.2).
PATCHABLE_FIELDS = ("name", "address", "phone", "is_collection_centre")


class BranchError(Exception):
    """Base branch error carrying an HTTP status + machine code."""

    __test__ = False
    status_code = 422
    error_code = "branch_error"

    def __init__(self, message: str = "", *, details: Any = None) -> None:
        super().__init__(message or self.error_code)
        self.details = details


class BranchNotFoundError(BranchError):
    status_code = 404
    error_code = "not_found"


class BranchCodeInvalidError(BranchError):
    status_code = 422
    error_code = "invalid_branch_code"


class BranchNameRequiredError(BranchError):
    status_code = 422
    error_code = "validation_error"


class DuplicateBranchCodeError(BranchError):
    status_code = 409
    error_code = "duplicate_branch_code"


class BranchCodeImmutableError(BranchError):
    status_code = 422
    error_code = "branch_code_immutable"


class PlanLimitReachedError(BranchError):
    status_code = 409
    error_code = "plan_limit_reached"


class BranchHasOpenWorkError(BranchError):
    status_code = 409
    error_code = "branch_has_open_work"


class VersionConflictError(BranchError):
    status_code = 409
    error_code = "version_conflict"


def _advisory_lock_key(tenant_id: Any) -> int:
    """Stable 63-bit key for pg_advisory_xact_lock, namespaced per tenant."""
    digest = hashlib.sha256(f"labflow:branch-create:{tenant_id}".encode()).digest()
    return int.from_bytes(digest[:8], "big") % (2**63)


class BranchService:
    """Branch CRUD + close/reopen (Doc 04 §8.2, §8.3, §11.3)."""

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    @classmethod
    def list_branches(
        cls, actor: StaffUser, include_closed: bool = False
    ) -> list[Branch]:
        """All (open) branches for branch pickers; closed only for the owner.

        No per-role filtering beyond closed: Doc 04 §15 lists GET roles as
        O M R T P with the closed filter as the only restriction — e.g. a
        transfer destination picker needs every open branch.
        """
        qs = Branch.objects.all()
        if not include_closed:
            qs = qs.filter(deleted_at__isnull=True)
        return list(qs.order_by("code"))

    # ------------------------------------------------------------------
    # Create
    # ------------------------------------------------------------------

    @classmethod
    def _active_branch_limit(cls) -> int | None:
        """max_branches of the tenant's active plan; None = unlimited.

        None also when the tenant has no active subscription (interim: a
        data anomaly — provisioning always creates one — must not brick
        branch creation).
        """
        tenant = getattr(connection, "tenant", None)
        if tenant is None:
            return None
        subscription = (
            Subscription.objects.filter(
                tenant=tenant, status=Subscription.Status.ACTIVE
            )
            .select_related("plan")
            .first()
        )
        if subscription is None:
            return None
        return subscription.plan.max_branches

    @classmethod
    def _acquire_create_lock(cls) -> None:
        """Serialize branch creates per tenant (Doc 04 §11.3).

        pg_advisory_xact_lock is transaction-scoped: held until the
        surrounding transaction commits/rolls back, PgBouncer-safe (F-5).
        """
        tenant = getattr(connection, "tenant", None)
        tenant_id = getattr(tenant, "id", "public") or "public"
        key = _advisory_lock_key(tenant_id)
        with connection.cursor() as cursor:
            cursor.execute("SELECT pg_advisory_xact_lock(%s)", [key])

    @classmethod
    def create_branch(
        cls,
        actor: StaffUser,
        data: dict[str, Any],
        ip: str | None = None,
        user_agent: str | None = None,
    ) -> Branch:
        code = data.get("code")
        if not isinstance(code, str) or not BRANCH_CODE_RE.match(code):
            raise BranchCodeInvalidError(
                "Branch code must be exactly 3 uppercase letters/digits."
            )
        name = data.get("name")
        if not isinstance(name, str) or not name.strip():
            raise BranchNameRequiredError(
                "Branch name is required.", details={"name": name}
            )

        with transaction.atomic():
            # Lock first: count + insert are serialized per tenant so two
            # racers for the last plan slot cannot both slip through.
            cls._acquire_create_lock()
            limit = cls._active_branch_limit()
            if limit is not None:
                count = Branch.objects.filter(deleted_at__isnull=True).count()
                if count >= limit:
                    raise PlanLimitReachedError(
                        f"Plan allows {limit} branches; {count} already active.",
                        details={"count": count, "limit": limit},
                    )
            if Branch.objects.filter(code=code).exists():
                raise DuplicateBranchCodeError(f"Branch code {code} is already in use.")
            try:
                branch = Branch.objects.create(
                    code=code,
                    name=name.strip(),
                    address=data.get("address"),
                    phone=data.get("phone"),
                    is_collection_centre=bool(data.get("is_collection_centre", False)),
                )
            except IntegrityError:
                # Race on uq_branch_code between exists() and INSERT.
                raise DuplicateBranchCodeError(
                    f"Branch code {code} is already in use."
                ) from None
            cls._audit(
                actor,
                "branch.created",
                branch,
                None,
                {
                    "code": branch.code,
                    "name": branch.name,
                    "is_collection_centre": branch.is_collection_centre,
                },
                ip,
                user_agent,
            )
        return branch

    # ------------------------------------------------------------------
    # Update
    # ------------------------------------------------------------------

    @classmethod
    def _branch_is_referenced(cls, branch: Branch) -> bool:
        """Doc 04 §8.2: referenced = any patient or sample points at it."""
        return Patient.objects.filter(branch=branch).exists() or (
            Sample.objects.filter(branch=branch).exists()
        )

    @classmethod
    def update_branch(
        cls,
        actor: StaffUser,
        branch_id: uuid.UUID,
        data: dict[str, Any],
        if_match: str | None = None,
        ip: str | None = None,
        user_agent: str | None = None,
    ) -> Branch:
        with transaction.atomic():
            try:
                branch = Branch.objects.select_for_update().get(pk=branch_id)
            except Branch.DoesNotExist:
                raise BranchNotFoundError("Branch not found.") from None

            # Optimistic concurrency (Doc 03 §6.1): the row lock makes the
            # check-then-write atomic against concurrent PATCHes.
            if if_match:
                clean = if_match.strip().strip('"').strip("'")
                current = branch.updated_at.isoformat()
                if clean not in (current, str(branch.updated_at)):
                    raise VersionConflictError(
                        "Branch was modified since it was last read."
                    )

            before: dict[str, Any] = {}
            after: dict[str, Any] = {}

            # §8.2 code rule: immutable once referenced; allowed (validated)
            # while the branch has no patient/sample referencing it.
            if "code" in data:
                new_code = data["code"]
                if cls._branch_is_referenced(branch):
                    raise BranchCodeImmutableError(
                        "Branch code is immutable once a patient or sample "
                        "references the branch; open a new branch instead."
                    )
                if not isinstance(new_code, str) or not BRANCH_CODE_RE.match(new_code):
                    raise BranchCodeInvalidError(
                        "Branch code must be exactly 3 uppercase letters/digits."
                    )
                if new_code != branch.code:
                    if (
                        Branch.objects.filter(code=new_code)
                        .exclude(pk=branch.pk)
                        .exists()
                    ):
                        raise DuplicateBranchCodeError(
                            f"Branch code {new_code} is already in use."
                        )
                    before["code"] = branch.code
                    branch.code = new_code
                    after["code"] = new_code

            for field in PATCHABLE_FIELDS:
                if field in data:
                    old_value = getattr(branch, field)
                    new_value = data[field]
                    if field == "name":
                        if not isinstance(new_value, str) or not new_value.strip():
                            raise BranchNameRequiredError(
                                "Branch name is required.",
                                details={"name": new_value},
                            )
                        new_value = new_value.strip()
                    if new_value != old_value:
                        before[field] = old_value
                        setattr(branch, field, new_value)
                        after[field] = new_value

            if after:
                try:
                    # update_fields: never clobber columns a concurrent
                    # transaction changed (the row lock serializes writers).
                    branch.save(update_fields=[*after.keys(), "updated_at"])
                except IntegrityError:
                    # Race: two concurrent PATCHes claiming the same new
                    # code on unreferenced branches.
                    raise DuplicateBranchCodeError(
                        "Branch code is already in use."
                    ) from None
                cls._audit(
                    actor, "branch.updated", branch, before, after, ip, user_agent
                )
        return branch

    # ------------------------------------------------------------------
    # Close / reopen
    # ------------------------------------------------------------------

    @classmethod
    def close_branch(
        cls,
        actor: StaffUser,
        branch_id: uuid.UUID,
        ip: str | None = None,
        user_agent: str | None = None,
    ) -> Branch:
        """Doc 04 §8.3: soft-delete after in-transaction preconditions."""
        with transaction.atomic():
            try:
                branch = Branch.objects.select_for_update().get(pk=branch_id)
            except Branch.DoesNotExist:
                raise BranchNotFoundError("Branch not found.") from None

            if branch.deleted_at is not None:
                return branch  # idempotent: state guard, no error, no audit

            open_in = SampleTransfer.objects.filter(
                to_branch=branch, status=SampleTransfer.Status.OPEN
            ).count()
            open_out = SampleTransfer.objects.filter(
                from_branch=branch, status=SampleTransfer.Status.OPEN
            ).count()
            held = Sample.objects.filter(
                branch=branch, status__in=_HELD_SAMPLE_STATUSES
            ).count()
            if open_in or open_out or held:
                raise BranchHasOpenWorkError(
                    "Branch has open work and cannot be closed.",
                    details={
                        "open_transfers_in": open_in,
                        "open_transfers_out": open_out,
                        "samples_held": held,
                    },
                )

            before = {"deleted_at": None}
            branch.deleted_at = timezone.now()
            branch.save(update_fields=["deleted_at", "updated_at"])
            after = {"deleted_at": branch.deleted_at.isoformat()}
            cls._audit(actor, "branch.closed", branch, before, after, ip, user_agent)
        return branch

    @classmethod
    def reopen_branch(
        cls,
        actor: StaffUser,
        branch_id: uuid.UUID,
        ip: str | None = None,
        user_agent: str | None = None,
    ) -> Branch:
        """Doc 04 §8.3: clear deleted_at; allowed whenever the row exists."""
        with transaction.atomic():
            try:
                branch = Branch.objects.select_for_update().get(pk=branch_id)
            except Branch.DoesNotExist:
                raise BranchNotFoundError("Branch not found.") from None

            if branch.deleted_at is None:
                return branch  # idempotent: no-op, no audit

            before = {"deleted_at": branch.deleted_at.isoformat()}
            branch.deleted_at = None
            branch.save(update_fields=["deleted_at", "updated_at"])
            after = {"deleted_at": None}
            cls._audit(actor, "branch.reopened", branch, before, after, ip, user_agent)
        return branch

    # ------------------------------------------------------------------
    # Audit
    # ------------------------------------------------------------------

    @classmethod
    def _audit(
        cls,
        actor: StaffUser,
        action: str,
        branch: Branch,
        before: dict[str, Any] | None,
        after: dict[str, Any] | None,
        ip: str | None,
        user_agent: str | None,
    ) -> None:
        AuditLog.objects.create(
            actor_id=actor.id,
            action=action,
            entity_type="branch",
            entity_id=branch.id,
            before_jsonb=before,
            after_jsonb=after,
            ip=ip or "",
            user_agent=user_agent or "",
        )
