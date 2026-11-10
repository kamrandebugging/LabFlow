"""Staff branch assignment service (Doc 04 §8.4 SB-1..SB-6, KAN-159 / LAB-34).

Business logic for GET / PUT /api/v1/staff/{id}/branches. Views stay thin
(role check, strict serialization, error mapping); every mutation writes its
audit row in the SAME transaction as the state change (SB-6).

Decisions (spec ambiguities resolved — see LAB-34 final report):
- SB-4 "exactly one is_primary=true per staff member" is enforced on the
  replacement set: >1 -> 422 two_primaries; 0 on a non-empty set ->
  422 primary_required (the ticket names only the former; the latter keeps
  the "exactly one" invariant the doc states).
- Assignments to CLOSED branches are accepted (the branch row exists; 404
  is only for unknown branches). Scope is computed from OPEN branches at
  read time (Doc 04 §8.5), so a closed-branch assignment grants nothing
  until the branch reopens — matching TN-22's "reopen restores scope".
- PUT validates the whole body before touching any row: any 422/404 leaves
  the old set and the audit log untouched (atomic replace).
"""

from __future__ import annotations

import uuid
from typing import Any

from django.db import transaction

from apps.accounts.models import AuditLog, Role, StaffBranch, StaffUser
from apps.branches.models import Branch

# Doc 04 §8.4: branch-scoped vs tenant-wide roles.
BRANCH_SCOPED_ROLES = {Role.MANAGER, Role.RECEPTION, Role.TECHNICIAN}
TENANT_WIDE_ROLES = {Role.OWNER, Role.PATHOLOGIST}

ASSIGNMENT_READ_ROLES = {Role.OWNER, Role.MANAGER}
ASSIGNMENT_WRITE_ROLES = {Role.OWNER}


class StaffBranchError(Exception):
    """Base staff-branch error carrying an HTTP status + machine code."""

    __test__ = False
    status_code = 422
    error_code = "staff_branch_error"

    def __init__(self, message: str = "", *, details: Any = None) -> None:
        super().__init__(message or self.error_code)
        self.details = details


class StaffNotFoundError(StaffBranchError):
    status_code = 404
    error_code = "not_found"


class AssignmentBranchNotFoundError(StaffBranchError):
    status_code = 404
    error_code = "not_found"


class AssignmentForbiddenError(StaffBranchError):
    status_code = 403
    error_code = "forbidden"


class StaffBranchRequiredError(StaffBranchError):
    status_code = 422
    error_code = "staff_branch_required"


class TenantWideRoleError(StaffBranchError):
    status_code = 422
    error_code = "tenant_wide_role"


class TwoPrimariesError(StaffBranchError):
    status_code = 422
    error_code = "two_primaries"


class PrimaryRequiredError(StaffBranchError):
    status_code = 422
    error_code = "primary_required"


class DuplicateBranchError(StaffBranchError):
    status_code = 422
    error_code = "duplicate_branch"


class AssignmentValidationError(StaffBranchError):
    status_code = 422
    error_code = "validation_error"


def _row_to_dict(row: StaffBranch) -> dict[str, Any]:
    branch = row.branch
    return {
        "branch_id": str(row.branch_id),
        "branch_code": branch.code,
        "branch_name": branch.name,
        "is_primary": row.is_primary,
    }


class StaffBranchService:
    """Read + atomic replace of a staff member's branch assignments."""

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    @classmethod
    def _get_staff(cls, staff_id: uuid.UUID) -> StaffUser:
        try:
            return StaffUser.objects.get(pk=staff_id)
        except (StaffUser.DoesNotExist, ValueError):
            raise StaffNotFoundError("Staff member not found.") from None

    @classmethod
    def assert_can_read(cls, actor: StaffUser, staff: StaffUser) -> None:
        """SB-5: Owner reads any roster; a Manager reads the roster of their
        own branches (target shares >=1 OPEN branch assignment with them)."""
        if actor.role == Role.OWNER:
            return
        if actor.role == Role.MANAGER:
            actor_branches = actor.assigned_branch_ids()
            target_branches = staff.assigned_branch_ids()
            if actor_branches & target_branches:
                return
        raise AssignmentForbiddenError(
            "Only the Owner, or a Manager for their own branches, "
            "may read branch assignments."
        )

    @classmethod
    def list_assignments(
        cls, actor: StaffUser, staff_id: uuid.UUID
    ) -> list[dict[str, Any]]:
        """GET /api/v1/staff/{id}/branches -> roster rows."""
        staff = cls._get_staff(staff_id)
        cls.assert_can_read(actor, staff)
        rows = (
            StaffBranch.objects.filter(staff_user=staff)
            .select_related("branch")
            .order_by("branch__code")
        )
        return [_row_to_dict(row) for row in rows]

    # ------------------------------------------------------------------
    # Replace (PUT)
    # ------------------------------------------------------------------

    @classmethod
    def _validate_items(cls, staff: StaffUser, items: Any) -> list[dict[str, Any]]:
        """Validate the whole replacement set; raise before any write."""
        if not isinstance(items, list):
            raise AssignmentValidationError(
                "Body must be a JSON list of {branch_id, is_primary} objects."
            )
        cleaned: list[dict[str, Any]] = []
        seen: set[uuid.UUID] = set()
        for index, item in enumerate(items):
            if not isinstance(item, dict):
                raise AssignmentValidationError(
                    f"Item {index} must be an object.", details={"index": index}
                )
            unknown = set(item) - {"branch_id", "is_primary"}
            if unknown:
                raise AssignmentValidationError(
                    f"Item {index} has unknown fields: {sorted(unknown)}.",
                    details={"index": index, "unknown": sorted(unknown)},
                )
            if set(item) != {"branch_id", "is_primary"}:
                raise AssignmentValidationError(
                    f"Item {index} must define exactly branch_id and is_primary.",
                    details={"index": index},
                )
            try:
                branch_id = uuid.UUID(str(item["branch_id"]))
            except (ValueError, AttributeError, TypeError):
                raise AssignmentValidationError(
                    f"Item {index} has an invalid branch_id.",
                    details={"index": index},
                ) from None
            is_primary = item["is_primary"]
            if not isinstance(is_primary, bool):
                raise AssignmentValidationError(
                    f"Item {index}: is_primary must be a boolean.",
                    details={"index": index},
                )
            if branch_id in seen:
                raise DuplicateBranchError(
                    f"Item {index}: branch {branch_id} appears twice.",
                    details={"index": index, "branch_id": str(branch_id)},
                )
            seen.add(branch_id)
            cleaned.append({"branch_id": branch_id, "is_primary": is_primary})

        # SB-1: branch-scoped roles need at least one assignment.
        if not cleaned and staff.role in BRANCH_SCOPED_ROLES:
            raise StaffBranchRequiredError(
                f"Role {staff.role} requires at least one branch assignment."
            )
        # SB-2: tenant-wide roles take no assignments.
        if cleaned and staff.role in TENANT_WIDE_ROLES:
            raise TenantWideRoleError(
                f"Role {staff.role} is tenant-wide and takes no branch assignments."
            )
        # SB-4: exactly one primary.
        primaries = sum(1 for row in cleaned if row["is_primary"])
        if primaries > 1:
            raise TwoPrimariesError(
                "At most one assignment may be primary.",
                details={"primaries": primaries},
            )
        if cleaned and primaries == 0:
            raise PrimaryRequiredError("Exactly one assignment must be primary (SB-4).")
        return cleaned

    @classmethod
    def replace_assignments(
        cls,
        actor: StaffUser,
        staff_id: uuid.UUID,
        items: Any,
        ip: str | None = None,
        user_agent: str | None = None,
    ) -> list[dict[str, Any]]:
        """PUT /api/v1/staff/{id}/branches — atomic whole-set replace.

        Validated whole, or nothing changes (SB-6 audit in the same
        transaction). Returns the new set.
        """
        staff = cls._get_staff(staff_id)
        # SB-5: only the Owner writes assignments.
        if actor.role not in ASSIGNMENT_WRITE_ROLES:
            raise AssignmentForbiddenError(
                "Only the Owner may write branch assignments."
            )
        cleaned = cls._validate_items(staff, items)

        with transaction.atomic():
            # 404 for unknown branches — resolved INSIDE the transaction so
            # a concurrent hard-delete cannot slip between validation and
            # the insert (branches are soft-deleted in v1, so this is
            # defence in depth, not a live race).
            branches = list(
                Branch.objects.filter(pk__in=[r["branch_id"] for r in cleaned])
            )
            found = {b.id for b in branches}
            missing = [
                str(r["branch_id"]) for r in cleaned if r["branch_id"] not in found
            ]
            if missing:
                raise AssignmentBranchNotFoundError(
                    "Unknown branch(es).", details={"branch_ids": missing}
                )
            by_id = {b.id: b for b in branches}

            before = [
                _row_to_dict(row)
                for row in StaffBranch.objects.filter(staff_user=staff)
                .select_related("branch")
                .order_by("branch__code")
            ]
            StaffBranch.objects.filter(staff_user=staff).delete()
            StaffBranch.objects.bulk_create(
                [
                    StaffBranch(
                        staff_user=staff,
                        branch=by_id[row["branch_id"]],
                        is_primary=row["is_primary"],
                    )
                    for row in cleaned
                ]
            )
            # Keep the home branch in lock-step with the primary assignment so
            # revoking a branch also revokes the v1 home-branch fallback.
            primary = next((row for row in cleaned if row["is_primary"]), None)
            staff.branch = by_id[primary["branch_id"]] if primary else None
            staff.save(update_fields=["branch", "updated_at"])
            after_rows = (
                StaffBranch.objects.filter(staff_user=staff)
                .select_related("branch")
                .order_by("branch__code")
            )
            after = [_row_to_dict(row) for row in after_rows]
            AuditLog.objects.create(
                actor_id=actor.id,
                action="staff.branches_assigned",
                entity_type="staff_user",
                entity_id=staff.id,
                before_jsonb={"branches": before},
                after_jsonb={"branches": after},
                ip=ip or None,
                user_agent=user_agent or None,
            )
        return after
