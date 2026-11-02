"""DRF views for Samples — accessioning + labels (Doc 03 §5.4 SM-1..SM-4,
KAN-137 / LAB-21, original LAB-23).

POST /api/v1/samples — roles Owner, Manager, Receptionist.
GET /api/v1/samples/{id}/label — roles Owner, Manager, Receptionist,
Technician.

Thin views: all business logic lives in SampleService.
"""

import uuid
from typing import Any, cast

from rest_framework import permissions, status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import StaffUser
from apps.samples.serializers import (
    SampleCreateSerializer,
    SampleLabelSerializer,
    SampleSerializer,
)
from apps.samples.services import (
    SAMPLE_LABEL_ROLES,
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
