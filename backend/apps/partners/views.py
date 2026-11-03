"""DRF views for the referral-partner registry (Doc 05 §5.1–§5.4, §10,
KAN-164 / LAB-39).

Access matrix (Doc 05 §4, RM-1..RM-6): every endpoint here is Owner only.
A "—" cell returns 403; hiding the menu is not the control.

Thin views: all business logic lives in PartnerService / RuleService /
DashboardService.
"""

from __future__ import annotations

import uuid
from typing import Any, cast

from rest_framework import permissions, status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import Role, StaffUser
from apps.partners.serializers import (
    PartnerCreateSerializer,
    PartnerUpdateSerializer,
    RuleCreateSerializer,
    RuleUpdateSerializer,
    format_partner,
    format_rule,
)
from apps.partners.services import (
    DashboardService,
    PartnerError,
    PartnerService,
    RuleService,
)

OWNER_ONLY = {Role.OWNER}


def _get_client_ip(request: Request) -> str:
    x_forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
    if x_forwarded_for:
        return x_forwarded_for.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR", "")


def _format_error(code: str, message: str, details: Any = None) -> dict[str, Any]:
    err: dict[str, Any] = {"code": code, "message": message}
    if details is not None:
        err["details"] = details
    return {"error": err}


def _require_owner(request: Request) -> Response | None:
    user = cast(StaffUser, request.user)
    if user.role not in OWNER_ONLY:
        return Response(
            _format_error(
                "forbidden",
                "Only the Owner may access the referral-partner registry.",
            ),
            status=status.HTTP_403_FORBIDDEN,
        )
    return None


def _service_error(exc: PartnerError) -> Response:
    return Response(
        _format_error(exc.error_code, str(exc) or exc.error_code),
        status=exc.status_code,
    )


def _validation_error(serializer: Any) -> Response:
    errors = serializer.errors
    code = "validation_error"
    # Surface the first machine-readable code when the serializer set one.
    if isinstance(errors, dict):
        for value in errors.values():
            items = value if isinstance(value, list) else [value]
            for item in items:
                item_code = getattr(item, "code", None)
                if item_code:
                    code = str(item_code)
                    break
    return Response(
        _format_error(code, "Request validation failed.", errors),
        status=status.HTTP_422_UNPROCESSABLE_ENTITY,
    )


class PartnerCollectionView(APIView):
    """GET /api/v1/referral-partners — Owner only, live partners by name.

    POST /api/v1/referral-partners — Owner only (RP-1). Idempotency-Key
    required; same key + same payload -> 200 original; same key +
    different payload -> 409 idempotency_key_reused.
    """

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request: Request) -> Response:
        denied = _require_owner(request)
        if denied is not None:
            return denied
        partners = PartnerService.list_partners()
        return Response(
            {"results": [format_partner(p) for p in partners]},
            status=status.HTTP_200_OK,
        )

    def post(self, request: Request) -> Response:
        denied = _require_owner(request)
        if denied is not None:
            return denied
        user = cast(StaffUser, request.user)

        idempotency_key = request.META.get("HTTP_IDEMPOTENCY_KEY")
        if not idempotency_key:
            return Response(
                _format_error(
                    "idempotency_key_required",
                    "The Idempotency-Key header is required.",
                ),
                status=status.HTTP_422_UNPROCESSABLE_ENTITY,
            )

        serializer = PartnerCreateSerializer(data=request.data)
        if not serializer.is_valid():
            return _validation_error(serializer)
        try:
            partner, created = PartnerService.create_partner(
                actor=user,
                payload=dict(serializer.validated_data),
                idempotency_key=idempotency_key,
                ip=_get_client_ip(request),
            )
        except PartnerError as exc:
            return _service_error(exc)
        return Response(
            format_partner(partner),
            status=(status.HTTP_201_CREATED if created else status.HTTP_200_OK),
        )


class PartnerDetailView(APIView):
    """GET /api/v1/referral-partners/{id} — Owner only.

    PATCH — Owner only; identity fields editable any time (RP-4).
    DELETE — Owner only; soft delete; 409 partner_has_ledger_entries (RP-5).
    """

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request: Request, partner_id: uuid.UUID) -> Response:
        denied = _require_owner(request)
        if denied is not None:
            return denied
        try:
            partner = PartnerService.get_partner(partner_id)
        except PartnerError as exc:
            return _service_error(exc)
        return Response(format_partner(partner), status=status.HTTP_200_OK)

    def patch(self, request: Request, partner_id: uuid.UUID) -> Response:
        denied = _require_owner(request)
        if denied is not None:
            return denied
        user = cast(StaffUser, request.user)
        serializer = PartnerUpdateSerializer(data=request.data)
        if not serializer.is_valid():
            return _validation_error(serializer)
        try:
            partner = PartnerService.update_partner(
                actor=user,
                partner_id=partner_id,
                payload=dict(serializer.validated_data),
                ip=_get_client_ip(request),
            )
        except PartnerError as exc:
            return _service_error(exc)
        return Response(format_partner(partner), status=status.HTTP_200_OK)

    def delete(self, request: Request, partner_id: uuid.UUID) -> Response:
        denied = _require_owner(request)
        if denied is not None:
            return denied
        user = cast(StaffUser, request.user)
        try:
            PartnerService.delete_partner(
                actor=user,
                partner_id=partner_id,
                ip=_get_client_ip(request),
            )
        except PartnerError as exc:
            return _service_error(exc)
        return Response(status=status.HTTP_204_NO_CONTENT)


class PartnerDashboardView(APIView):
    """GET /api/v1/referral-partners/{id}/dashboard — Owner only (RM-3).

    YTD earned, YTD settled, pending total, last 6 settlements,
    late_entries count, has_email — all computed at read time.
    """

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request: Request, partner_id: uuid.UUID) -> Response:
        denied = _require_owner(request)
        if denied is not None:
            return denied
        try:
            data = DashboardService.get_dashboard(partner_id)
        except PartnerError as exc:
            return _service_error(exc)
        body = {
            "partner_id": str(data["partner_id"]),
            "partner_name": data["partner_name"],
            "has_email": data["has_email"],
            "ytd_earned": data["ytd_earned"],
            "ytd_settled": data["ytd_settled"],
            "pending_total": data["pending_total"],
            "late_entries": data["late_entries"],
            "last_6_settlements": [
                {
                    "id": str(s.id),
                    "period": s.period,
                    "status": s.status,
                    "total": f"{s.total:.2f}",
                }
                for s in data["last_6_settlements"]
            ],
        }
        return Response(body, status=status.HTTP_200_OK)


class RuleCollectionView(APIView):
    """GET /api/v1/referral-partners/{id}/rules — Owner only.

    POST — Owner only (RR-1). Bucket-aware (partner, branch, category);
    same-bucket overlap -> 422 rule_overlap (RR-7).
    """

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request: Request, partner_id: uuid.UUID) -> Response:
        denied = _require_owner(request)
        if denied is not None:
            return denied
        try:
            rules = RuleService.list_rules(partner_id)
        except PartnerError as exc:
            return _service_error(exc)
        return Response(
            {"results": [format_rule(r) for r in rules]},
            status=status.HTTP_200_OK,
        )

    def post(self, request: Request, partner_id: uuid.UUID) -> Response:
        denied = _require_owner(request)
        if denied is not None:
            return denied
        user = cast(StaffUser, request.user)
        serializer = RuleCreateSerializer(data=request.data)
        if not serializer.is_valid():
            return _validation_error(serializer)
        try:
            rule = RuleService.create_rule(
                actor=user,
                partner_id=partner_id,
                payload=dict(serializer.validated_data),
                ip=_get_client_ip(request),
            )
        except PartnerError as exc:
            return _service_error(exc)
        return Response(format_rule(rule), status=status.HTTP_201_CREATED)


class RuleDetailView(APIView):
    """PATCH /api/v1/revenue-share-rules/{id} — Owner only.

    Close-old + insert-new (RR-3): the old row's percent and
    effective_from are never mutated; only effective_to is set.
    Returns the NEW rule row.
    """

    permission_classes = [permissions.IsAuthenticated]

    def patch(self, request: Request, rule_id: uuid.UUID) -> Response:
        denied = _require_owner(request)
        if denied is not None:
            return denied
        user = cast(StaffUser, request.user)
        serializer = RuleUpdateSerializer(data=request.data)
        if not serializer.is_valid():
            return _validation_error(serializer)
        if not serializer.validated_data:
            return Response(
                _format_error(
                    "validation_error",
                    "Nothing to update: provide percent and/or effective_from.",
                ),
                status=status.HTTP_422_UNPROCESSABLE_ENTITY,
            )
        try:
            new_rule = RuleService.update_rule(
                actor=user,
                rule_id=rule_id,
                payload=dict(serializer.validated_data),
                ip=_get_client_ip(request),
            )
        except PartnerError as exc:
            return _service_error(exc)
        return Response(format_rule(new_rule), status=status.HTTP_200_OK)
