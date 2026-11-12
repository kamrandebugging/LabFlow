"""Branch scope enforcement — Layer 1 (Doc 04 §8.5, KAN-159 / LAB-34).

The queryset mixin: every branch-scoped model declares one class attribute
naming its scope path (``branch_scope_field``, e.g. ``"branch_id"`` or
``"sample__branch_id"``). ``BranchScopedQuerySet.scoped_to(user)`` and
``BranchScopedManager.scoped_to(user)`` filter to the caller's assignments.

This module is import-safe for models.py (pure Django, no DRF import —
DRF pulls settings → auth → models and would cycle). Layers 2 and 3
(``BranchScopedAPIView``, ``IsInBranchScope``, the TN-20 conformance guard)
live in ``apps.branches.scope_views``; together the two modules are the
only place branch scope is implemented.

Scope rules (Doc 03 BS-1..BS-6, Doc 04 §8.4 SB-1..SB-6):
- Tenant-wide roles (owner, pathologist) bypass scope entirely (BS-1).
- Everyone else is filtered to their ``staff_branch`` assignments on OPEN
  branches only — closing a branch revokes scope there at once (LAB-33),
  reopening restores it; history stays readable by ID.
- ``staff_user.branch`` is a display default, NEVER the scope source (SB-3).

The one named exception is BS-4's identifiers-only search, which lives in
``PatientService.list_patients`` and is the only method allowed to cross
branch scope — it is deliberately NOT routed through ``scoped_to``.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from typing import TYPE_CHECKING, TypeVar

from django.core.exceptions import ImproperlyConfigured
from django.db import models

if TYPE_CHECKING:
    from apps.accounts.models import StaffUser

_M = TypeVar("_M", bound=models.Model)


def effective_branch_ids(user: StaffUser) -> set[uuid.UUID]:
    """All branches a branch-scoped caller may act in.

    ``staff_branch`` rows are the documented scope source (SB-3); the home
    ``staff_user.branch`` is accepted as a v1 fallback so accounts created by
    Staff CRUD (one home branch + one assignment) behave identically.
    """
    ids = set(user.assigned_branch_ids())
    if user.branch_id:
        ids.add(user.branch_id)
    return ids


def in_branch_scope(user: StaffUser, branch_id: uuid.UUID | None) -> bool:
    """True when ``branch_id`` is inside the caller's branch scope.

    Tenant-wide roles (Owner/Pathologist) bypass scope by design (BS-1).
    A branch-scoped caller with no assignment matches nothing (fail closed).
    """
    if user.is_tenant_wide:
        return True
    if branch_id is None:
        return False
    return branch_id in effective_branch_ids(user)


def get_scoped_or_404[T: models.Model](
    model: type[T],
    user: StaffUser,
    pk: uuid.UUID | str,
    *,
    error_factory: Callable[[str], Exception],
    select_for_update: bool = False,
) -> T:
    """Fetch one branch-scoped object for ``user`` or raise ``error_factory``.

    This is the single front door for per-object fetches (LAB-49 Phase 1.2,
    OWASP API1 BOLA): the scope predicate is applied in the query, so a
    foreign object is indistinguishable from a missing one (404, P-7).
    """
    queryset = model.objects.scoped_to(user)
    if select_for_update:
        queryset = queryset.select_for_update()
    try:
        return queryset.get(pk=pk)
    except (model.DoesNotExist, ValueError, TypeError):
        raise error_factory("Not found.") from None


class BranchScopedQuerySet(models.QuerySet[_M, _M]):
    """Layer 1 — queryset-level branch scope (Doc 04 §8.5).

    ``scope_field`` is the model's declared scope path
    (``branch_scope_field``). It is resolved from the model on every call
    (never cached on the instance — Django's ``_clone()`` rebuilds
    querysets on chaining and would drop a cached attribute).
    """

    scope_field: str | None = None

    def _resolve_scope_field(self) -> str:
        field = self.scope_field or getattr(self.model, "branch_scope_field", None)
        if field is None:
            raise ImproperlyConfigured(
                f"{self.model.__name__} declares no branch_scope_field; "
                "scoped_to() cannot be applied."
            )
        return field

    def scoped_to(self, user: StaffUser) -> BranchScopedQuerySet[_M]:
        """Filter this queryset to the caller's branch scope.

        Tenant-wide roles (owner, pathologist) are unfiltered (BS-1);
        everyone else sees only rows on their assigned OPEN branches.
        """
        scope_field = self._resolve_scope_field()
        if user.is_tenant_wide:
            return self
        branch_ids = user.assigned_branch_ids()
        return self.filter(**{f"{scope_field}__in": branch_ids})


class BranchScopedManager(models.Manager[_M]):
    """Manager exposing ``scoped_to(user)`` (Doc 04 §8.5).

    Attach as ``objects`` on every branch-scoped model and declare the
    scope path on the model as ``branch_scope_field``. Catalog models keep
    the default manager — they are tenant-wide reference data (BS-5).
    """

    def get_queryset(self) -> BranchScopedQuerySet[_M]:
        return BranchScopedQuerySet(self.model, using=self._db)

    def scoped_to(self, user: StaffUser) -> BranchScopedQuerySet[_M]:
        """``Model.objects.scoped_to(request.user)`` — the Layer-1 entry point."""
        return self.get_queryset().scoped_to(user)
