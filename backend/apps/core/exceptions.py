"""Problem+JSON exception shaping (Doc 03 §6.1, Doc 04 §8.5).

``BranchScopeDenied`` is the Layer-3 scope refusal: a zero-assignment or
out-of-scope write returns 403 with the machine-stable code
``branch_scope_denied`` (BS-2) — never a misleading 404 and never DRF's
generic ``{"detail": ...}`` shape. Every other exception delegates to
DRF's default handler unchanged.
"""

from __future__ import annotations

from typing import Any

from rest_framework.exceptions import APIException
from rest_framework.response import Response
from rest_framework.views import exception_handler


class BranchScopeDenied(APIException):
    """403 branch_scope_denied — BS-2's explicit refusal (Doc 04 §8.5)."""

    status_code = 403
    default_detail = "Branch scope denied."
    default_code = "branch_scope_denied"


def problem_json_exception_handler(exc: Exception, context: dict[str, Any]) -> Any:
    """DRF EXCEPTION_HANDLER: problem+json for BranchScopeDenied, default else."""
    if isinstance(exc, BranchScopeDenied):
        detail = exc.detail if isinstance(exc.detail, str) else str(exc.detail)
        return Response(
            {"error": {"code": "branch_scope_denied", "message": detail}},
            status=403,
        )
    return exception_handler(exc, context)
