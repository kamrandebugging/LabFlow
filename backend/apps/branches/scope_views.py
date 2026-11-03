"""Branch scope enforcement — Layers 2 and 3 (Doc 04 §8.5, KAN-159 / LAB-34).

Layer 2 — the base view. Every viewset for a scoped model inherits
``BranchScopedAPIView``; lists, details and actions fetch through the scoped
queryset, so an out-of-scope object is simply not found: 404,
indistinguishable from a missing one (Doc 03 P-7). TN-20's structural test
fails the suite if a scoped viewset skips this base class.

Layer 3 — the permission. ``IsInBranchScope`` sits on the same viewsets as
defence in depth, re-checking an object's scope branch against the caller's
assignments. It covers what the queryset cannot see — actions receiving a
branch in the request body — and Doc 03's explicit refusal: a zero-assignment
write returns 403 ``branch_scope_denied``, not a misleading 404 (BS-2).

Kept separate from ``apps.branches.scoping`` because DRF imports pull
settings → auth → models; models.py must be able to import the Layer-1
mixin without cycling.
"""

from __future__ import annotations

import uuid
from typing import Any

from django.core.exceptions import ImproperlyConfigured
from django.db import models
from rest_framework import permissions
from rest_framework.views import APIView

from apps.core.exceptions import BranchScopeDenied


class BranchScopedAPIView(APIView):
    """Layer-2 base class for viewsets over branch-scoped models.

    Subclasses fetch through ``get_scoped_queryset()`` so lists, details
    and actions share one scope implementation; an out-of-scope object is
    simply not found → 404 (Doc 03 P-7).
    """

    scoped_model: type[models.Model] | None = None

    def get_scoped_queryset(self, user: Any = None) -> models.QuerySet:
        """``scoped_model.objects.scoped_to(...)`` for the current caller."""
        model = self.scoped_model
        if model is None:
            raise ImproperlyConfigured(
                f"{type(self).__name__} must declare scoped_model."
            )
        manager = model._default_manager
        scoped = getattr(manager, "scoped_to", None)
        if scoped is None:
            raise ImproperlyConfigured(
                f"{model.__name__}._default_manager has no scoped_to(); "
                "attach BranchScopedManager."
            )
        actor = user if user is not None else self.request.user
        return scoped(actor)


class IsInBranchScope(permissions.BasePermission):
    """Layer-3 defence in depth for branch-scoped writes (Doc 04 §8.5).

    Reads are scoped by the queryset (Layer 2 → 404); this permission
    covers what the queryset cannot see — actions receiving a branch in
    the request body — and enforces BS-2's explicit refusal: a
    zero-assignment write returns 403 ``branch_scope_denied``, never a
    misleading 404.

    Views declare where their write's branch travels::

        scope_branch_source = "body:branch_id"   # branch UUID in request.data
        scope_branch_source = None               # no branch travels; only the
                                                 # zero-assignment gate applies
    """

    message = "Branch scope denied."

    def has_permission(self, request: Any, view: Any) -> bool:
        if request.method in permissions.SAFE_METHODS:
            return True
        user = request.user
        if not getattr(user, "is_authenticated", False):
            # IsAuthenticated (listed before this class) owns this case.
            return False
        if user.is_tenant_wide:
            return True
        assigned = user.assigned_branch_ids()
        if not assigned:
            raise BranchScopeDenied("This account has no branch assignments.")
        branch_id = self._resolve_branch(request, view)
        if branch_id is not None and branch_id not in assigned:
            raise BranchScopeDenied("Branch is outside the caller's scope.")
        return True

    def _resolve_branch(self, request: Any, view: Any) -> uuid.UUID | None:
        source = getattr(view, "scope_branch_source", None)
        if not source:
            return None
        kind, _, field = str(source).partition(":")
        raw: Any = None
        if kind == "body":
            data: Any = getattr(request, "data", None)
            raw = data.get(field) if hasattr(data, "get") else None
        elif kind == "kwargs":
            parser_context: Any = getattr(request, "parser_context", None)
            kwargs = (
                parser_context.get("kwargs", {})
                if isinstance(parser_context, dict)
                else {}
            )
            raw = kwargs.get(field)
        if raw is None:
            return None
        try:
            return uuid.UUID(str(raw))
        except (ValueError, AttributeError, TypeError):
            # Malformed input is the serializer's 422, not a scope refusal.
            return None


def get_branch_scoped_list_views() -> list[type[APIView]]:
    """The key list endpoints a branch scope path applies to (Doc 04 §8.5).

    Lazily imported: ``apps.branches.scoping`` is imported by models.py,
    so importing views at module level would cycle.

    Scope-wire decisions (KAN-159):
    - patients list: scope lives in ``PatientService.list_patients`` (it
      also carries the BS-4 identifiers-only exception, which must NOT go
      through ``scoped_to``) — the view inherits the base for the guard.
    - invoices list/detail: scoped via ``Invoice.objects.scoped_to(actor)``
      inside ``InvoiceQueryService`` (previously unscoped — the bypass this
      ticket closes).
    - samples / results / reports: no list endpoints exist in v1; the
      per-object actions enforce scope in their services (transfers via the
      source-hold rule, SM-7). ``Sample``/``Result``/``Report`` still carry
      the scoped manager so ``scoped_to`` is available to services.
    """
    from apps.billing.views import InvoiceCollectionView
    from apps.patients.views import PatientListCreateView

    return [PatientListCreateView, InvoiceCollectionView]


def assert_branch_scope_conformance(
    views: list[type[APIView]] | None = None,
) -> None:
    """TN-20 structural guard: every scoped viewset inherits the base class.

    Raises AssertionError naming the offending view — a viewset that skips
    ``BranchScopedAPIView`` fails the suite (Doc 04 §8.5, TN-20).
    """
    targets = get_branch_scoped_list_views() if views is None else views
    offenders = [
        view.__name__
        for view in targets
        if not (isinstance(view, type) and issubclass(view, BranchScopedAPIView))
    ]
    if offenders:
        raise AssertionError(
            "Scoped viewset(s) skip the BranchScopedAPIView base class "
            f"(Doc 04 §8.5 Layer 2): {', '.join(offenders)}"
        )
