"""DRF views for Samples — accessioning, labels & lifecycle
(Doc 03 §5.4 SM-1..SM-11, KAN-137 / LAB-21, KAN-138 / LAB-22).

POST /api/v1/samples — roles Owner, Manager, Receptionist.
GET /api/v1/samples/{id}/label — roles Owner, Manager, Receptionist,
Technician.
POST /api/v1/samples/{id}/receive — roles Owner, Manager, Technician.
POST /api/v1/samples/{id}/reject — roles Owner, Manager, Receptionist,
Technician.
POST /api/v1/samples/{id}/recollect — roles Owner, Manager, Receptionist.
POST /api/v1/samples/{id}/cancel — roles Owner, Manager.

Thin views: all business logic lives in SampleService.
"""

import uuid
from typing import Any, cast

from rest_framework import permissions, status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import Role, StaffUser
from apps.samples.serializers import (
    SampleCancelSerializer,
    SampleCreateSerializer,
    SampleLabelSerializer,
    SampleRejectSerializer,
    SampleSerializer,
)
from apps.samples.services import (
    SAMPLE_CANCEL_ROLES,
    SAMPLE_LABEL_ROLES,
    SAMPLE_RECEIVE_ROLES,
    SAMPLE_RECOLLECT_ROLES,
    SAMPLE_REJECT_ROLES,
    SAMPLE_WRITE_ROLES,
    SampleError,
    SampleService,
)


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


class SampleCollectionView(APIView):
    """POST /api/v1/samples — collect a sample (SM-1..SM-3)."""

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request: Request) -> Response:
        user = cast(StaffUser, request.user)
        if user.role not in SAMPLE_WRITE_ROLES:
            return Response(
                _format_error(
                    "forbidden",
                    "Only Owner, Manager or Receptionist may collect samples.",
                ),
                status=status.HTTP_403_FORBIDDEN,
            )
        serializer = SampleCreateSerializer(data=request.data)
        if not serializer.is_valid():
            first = next(iter(serializer.errors.values()))
            msg = first[0] if isinstance(first, list) else str(first)
            return Response(
                _format_error("validation_error", str(msg)),
                status=status.HTTP_422_UNPROCESSABLE_ENTITY,
            )
        data = serializer.validated_data
        try:
            sample = SampleService.collect_sample(
                invoice_id=data["invoice_id"],
                invoice_item_ids=data.get("invoice_item_ids"),
                actor=user,
                ip=_get_client_ip(request),
                user_agent=request.META.get("HTTP_USER_AGENT", ""),
            )
        except SampleError as exc:
            return Response(
                _format_error(exc.error_code, str(exc) or exc.error_code),
                status=exc.status_code,
            )
        return Response(SampleSerializer(sample).data, status=status.HTTP_201_CREATED)


class SampleLabelView(APIView):
    """GET /api/v1/samples/{id}/label — Code128 label payload (SM-4)."""

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request: Request, sample_id: uuid.UUID) -> Response:
        user = cast(StaffUser, request.user)
        if user.role not in SAMPLE_LABEL_ROLES:
            return Response(
                _format_error("forbidden", "Only staff may print sample labels."),
                status=status.HTTP_403_FORBIDDEN,
            )
        try:
            payload = SampleService.get_label(
                sample_id=sample_id,
                actor=user,
                ip=_get_client_ip(request),
                user_agent=request.META.get("HTTP_USER_AGENT", ""),
            )
        except SampleError as exc:
            return Response(
                _format_error(exc.error_code, str(exc) or exc.error_code),
                status=exc.status_code,
            )
        return Response(SampleLabelSerializer(payload).data, status=status.HTTP_200_OK)


def _role_guard(user: StaffUser, allowed: set[Role], message: str) -> Response | None:
    """Return a 403 response when the user's role is not allowed, else None."""
    if user.role not in allowed:
        return Response(
            _format_error("forbidden", message),
            status=status.HTTP_403_FORBIDDEN,
        )
    return None


def _validate(
    serializer: Any,
) -> tuple[dict[str, Any] | None, Response | None]:
    """Run a serializer; return (data, None) or (None, 422 response)."""
    if not serializer.is_valid():
        first = next(iter(serializer.errors.values()))
        msg = first[0] if isinstance(first, list) else str(first)
        return None, Response(
            _format_error("validation_error", str(msg)),
            status=status.HTTP_422_UNPROCESSABLE_ENTITY,
        )
    return serializer.validated_data, None


class SampleReceiveView(APIView):
    """POST /api/v1/samples/{id}/receive — collected -> received (SM-7)."""

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request: Request, sample_id: uuid.UUID) -> Response:
        user = cast(StaffUser, request.user)
        denied = _role_guard(
            user,
            SAMPLE_RECEIVE_ROLES,
            "Only Owner, Manager or Technician may receive samples.",
        )
        if denied is not None:
            return denied
        try:
            sample = SampleService.receive_sample(
                sample_id=sample_id,
                actor=user,
                ip=_get_client_ip(request),
                user_agent=request.META.get("HTTP_USER_AGENT", ""),
            )
        except SampleError as exc:
            return Response(
                _format_error(exc.error_code, str(exc) or exc.error_code),
                status=exc.status_code,
            )
        return Response(SampleSerializer(sample).data, status=status.HTTP_200_OK)


class SampleRejectView(APIView):
    """POST /api/v1/samples/{id}/reject — quality rejection (SM-8)."""

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request: Request, sample_id: uuid.UUID) -> Response:
        user = cast(StaffUser, request.user)
        denied = _role_guard(
            user,
            SAMPLE_REJECT_ROLES,
            "Only staff may reject samples.",
        )
        if denied is not None:
            return denied
        data, error = _validate(SampleRejectSerializer(data=request.data))
        if error is not None:
            return error
        assert data is not None
        try:
            sample = SampleService.reject_sample(
                sample_id=sample_id,
                reason_code=data["reason_code"],
                note=data.get("note"),
                actor=user,
                ip=_get_client_ip(request),
                user_agent=request.META.get("HTTP_USER_AGENT", ""),
            )
        except SampleError as exc:
            return Response(
                _format_error(exc.error_code, str(exc) or exc.error_code),
                status=exc.status_code,
            )
        return Response(SampleSerializer(sample).data, status=status.HTTP_200_OK)


class SampleRecollectView(APIView):
    """POST /api/v1/samples/{id}/recollect — new sample after rejection (SM-9)."""

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request: Request, sample_id: uuid.UUID) -> Response:
        user = cast(StaffUser, request.user)
        denied = _role_guard(
            user,
            SAMPLE_RECOLLECT_ROLES,
            "Only Owner, Manager or Receptionist may recollect samples.",
        )
        if denied is not None:
            return denied
        try:
            sample = SampleService.recollect_sample(
                sample_id=sample_id,
                actor=user,
                ip=_get_client_ip(request),
                user_agent=request.META.get("HTTP_USER_AGENT", ""),
            )
        except SampleError as exc:
            return Response(
                _format_error(exc.error_code, str(exc) or exc.error_code),
                status=exc.status_code,
            )
        return Response(SampleSerializer(sample).data, status=status.HTTP_201_CREATED)


class SampleCancelView(APIView):
    """POST /api/v1/samples/{id}/cancel — sample cancellation (SM-11)."""

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request: Request, sample_id: uuid.UUID) -> Response:
        user = cast(StaffUser, request.user)
        denied = _role_guard(
            user,
            SAMPLE_CANCEL_ROLES,
            "Only Owner or Manager may cancel samples.",
        )
        if denied is not None:
            return denied
        data, error = _validate(SampleCancelSerializer(data=request.data))
        if error is not None:
            return error
        assert data is not None
        try:
            sample = SampleService.cancel_sample(
                sample_id=sample_id,
                reason=data.get("reason"),
                actor=user,
                ip=_get_client_ip(request),
                user_agent=request.META.get("HTTP_USER_AGENT", ""),
            )
        except SampleError as exc:
            return Response(
                _format_error(exc.error_code, str(exc) or exc.error_code),
                status=exc.status_code,
            )
        return Response(SampleSerializer(sample).data, status=status.HTTP_200_OK)
