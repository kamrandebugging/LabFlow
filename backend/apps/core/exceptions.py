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


class BranchScopeDenied(APIException):
    """403 branch_scope_denied — BS-2's explicit refusal (Doc 04 §8.5)."""

    status_code = 403
    default_detail = "Branch scope denied."
    default_code = "branch_scope_denied"


class OnboardingIncomplete(APIException):
    """403 while a login session is limited to password/TOTP onboarding.

    The machine code is either ``password_change_required`` (S7) or
    ``totp_enrollment_required`` (S6); both are distinct from an
    authentication failure so the client can route to the right flow.
    """

    status_code = 403
    default_detail = "Account onboarding is incomplete."
    default_code = "onboarding_incomplete"


def problem_json_exception_handler(exc: Exception, context: dict[str, Any]) -> Any:
    """DRF EXCEPTION_HANDLER: stable codes for scope + onboarding refusals."""
    if isinstance(exc, BranchScopeDenied):
        detail = exc.detail if isinstance(exc.detail, str) else str(exc.detail)
        return Response(
            {"error": {"code": "branch_scope_denied", "message": detail}},
            status=403,
        )
    if isinstance(exc, OnboardingIncomplete):
        code = str(exc.detail)
        message = (
            "Change your temporary password before continuing."
            if code == "password_change_required"
            else "Enrol two-factor authentication before continuing."
        )
        return Response(
            {"error": {"code": code, "message": message}},
            status=403,
        )
    # Imported lazily: DRF imports the authentication backend while building
    # its settings, and ``rest_framework.views`` is still partially initialised
    # at that point.
    from rest_framework.views import exception_handler

    return exception_handler(exc, context)
