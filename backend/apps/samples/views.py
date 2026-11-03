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
POST /api/v1/samples/{id}/transfer — roles Owner, Manager, Receptionist,
Technician (KAN-143 / LAB-23).
POST /api/v1/transfers/{id}/receive — roles Owner, Manager, Receptionist,
Technician.
POST /api/v1/transfers/{id}/cancel — roles Owner, Manager.
POST /api/v1/transfers/{id}/mark-lost — roles Owner, Manager.
GET /api/v1/samples/{id}/events — roles Owner, Manager, Receptionist,
Technician, Pathologist.
GET /api/v1/transfers/exceptions — roles Owner, Manager.

Thin views: all business logic lives in SampleService / TransferService.
"""

import uuid
from datetime import date, datetime
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
    TransferCreateSerializer,
    TransferMarkLostSerializer,
    TransferSerializer,
)
from apps.samples.services import (
    SAMPLE_CANCEL_ROLES,
    SAMPLE_EVENTS_ROLES,
    SAMPLE_LABEL_ROLES,
    SAMPLE_RECEIVE_ROLES,
    SAMPLE_RECOLLECT_ROLES,
    SAMPLE_REJECT_ROLES,
    SAMPLE_WRITE_ROLES,
    TRANSFER_CANCEL_ROLES,
    TRANSFER_CREATE_ROLES,
    TRANSFER_EXCEPTIONS_ROLES,
    TRANSFER_MARK_LOST_ROLES,
    TRANSFER_RECEIVE_ROLES,
    SampleError,
    SampleService,
    TransferService,
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


class SampleTransferCreateView(APIView):
    """POST /api/v1/samples/{id}/transfer — dispatch to a branch (SM-7)."""

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request: Request, sample_id: uuid.UUID) -> Response:
        user = cast(StaffUser, request.user)
        denied = _role_guard(
            user,
            TRANSFER_CREATE_ROLES,
            "Only Owner, Manager, Receptionist or Technician may transfer samples.",
        )
        if denied is not None:
            return denied
        data, error = _validate(TransferCreateSerializer(data=request.data))
        if error is not None:
            return error
        assert data is not None
        try:
            transfer = TransferService.create_transfer(
                sample_id=sample_id,
                to_branch_id=data["to_branch_id"],
                actor=user,
                ip=_get_client_ip(request),
                user_agent=request.META.get("HTTP_USER_AGENT", ""),
            )
        except SampleError as exc:
            return Response(
                _format_error(exc.error_code, str(exc) or exc.error_code),
                status=exc.status_code,
            )
        return Response(
            TransferSerializer(transfer).data, status=status.HTTP_201_CREATED
        )


class TransferReceiveView(APIView):
    """POST /api/v1/transfers/{id}/receive — receive at destination (SM-7)."""

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request: Request, transfer_id: uuid.UUID) -> Response:
        user = cast(StaffUser, request.user)
        denied = _role_guard(
            user,
            TRANSFER_RECEIVE_ROLES,
            "Only Owner, Manager, Receptionist or Technician may receive transfers.",
        )
        if denied is not None:
            return denied
        try:
            transfer = TransferService.receive_transfer(
                transfer_id=transfer_id,
                actor=user,
                ip=_get_client_ip(request),
                user_agent=request.META.get("HTTP_USER_AGENT", ""),
            )
        except SampleError as exc:
            return Response(
                _format_error(exc.error_code, str(exc) or exc.error_code),
                status=exc.status_code,
            )
        return Response(TransferSerializer(transfer).data, status=status.HTTP_200_OK)


class TransferCancelView(APIView):
    """POST /api/v1/transfers/{id}/cancel — sender cancels (Doc 04 §9.2)."""

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request: Request, transfer_id: uuid.UUID) -> Response:
        user = cast(StaffUser, request.user)
        denied = _role_guard(
            user,
            TRANSFER_CANCEL_ROLES,
            "Only Owner or Manager may cancel transfers.",
        )
        if denied is not None:
            return denied
        try:
            transfer = TransferService.cancel_transfer(
                transfer_id=transfer_id,
                actor=user,
                ip=_get_client_ip(request),
                user_agent=request.META.get("HTTP_USER_AGENT", ""),
            )
        except SampleError as exc:
            return Response(
                _format_error(exc.error_code, str(exc) or exc.error_code),
                status=exc.status_code,
            )
        return Response(TransferSerializer(transfer).data, status=status.HTTP_200_OK)


class TransferMarkLostView(APIView):
    """POST /api/v1/transfers/{id}/mark-lost — sender marks lost (SM-7)."""

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request: Request, transfer_id: uuid.UUID) -> Response:
        user = cast(StaffUser, request.user)
        denied = _role_guard(
            user,
            TRANSFER_MARK_LOST_ROLES,
            "Only Owner or Manager may mark transfers lost.",
        )
        if denied is not None:
            return denied
        data, error = _validate(TransferMarkLostSerializer(data=request.data))
        if error is not None:
            return error
        assert data is not None
        try:
            transfer = TransferService.mark_lost_transfer(
                transfer_id=transfer_id,
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
        return Response(TransferSerializer(transfer).data, status=status.HTTP_200_OK)


class SampleEventsView(APIView):
    """GET /api/v1/samples/{id}/events — chain-of-custody timeline (R-5)."""

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request: Request, sample_id: uuid.UUID) -> Response:
        user = cast(StaffUser, request.user)
        denied = _role_guard(
            user,
            SAMPLE_EVENTS_ROLES,
            "Only staff may view the sample event timeline.",
        )
        if denied is not None:
            return denied
        try:
            events = TransferService.get_events(sample_id=sample_id, actor=user)
        except SampleError as exc:
            return Response(
                _format_error(exc.error_code, str(exc) or exc.error_code),
                status=exc.status_code,
            )
        return Response({"events": events}, status=status.HTTP_200_OK)


def _parse_iso_date(
    value: str | None, name: str
) -> tuple[date | None, Response | None]:
    """Parse a YYYY-MM-DD query param; 422 on bad input."""
    if value is None:
        return None, None
    try:
        return datetime.strptime(value, "%Y-%m-%d").date(), None
    except ValueError:
        return None, Response(
            _format_error("validation_error", f"Invalid {name}: expected YYYY-MM-DD."),
            status=status.HTTP_422_UNPROCESSABLE_ENTITY,
        )


def _parse_month(value: str | None) -> tuple[str | None, Response | None]:
    """Parse a YYYY-MM query param; 422 on bad input."""
    if value is None:
        return None, None
    try:
        datetime.strptime(value, "%Y-%m")
        return value, None
    except ValueError:
        return None, Response(
            _format_error("validation_error", "Invalid month: expected YYYY-MM."),
            status=status.HTTP_422_UNPROCESSABLE_ENTITY,
        )


class TransferExceptionsView(APIView):
    """GET /api/v1/transfers/exceptions — late / lost / route-health (Doc 04 §9.4)."""

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request: Request) -> Response:
        user = cast(StaffUser, request.user)
        denied = _role_guard(
            user,
            TRANSFER_EXCEPTIONS_ROLES,
            "Only Owner or Manager may view transfer exceptions.",
        )
        if denied is not None:
            return denied
        report = request.query_params.get("report")
        if report is not None and report not in ("late", "lost", "route_health"):
            return Response(
                _format_error(
                    "validation_error",
                    "Invalid report: expected late, lost or route_health.",
                ),
                status=status.HTTP_422_UNPROCESSABLE_ENTITY,
            )
        from_date, error = _parse_iso_date(request.query_params.get("from"), "from")
        if error is not None:
            return error
        to_date, error = _parse_iso_date(request.query_params.get("to"), "to")
        if error is not None:
            return error
        month, error = _parse_month(request.query_params.get("month"))
        if error is not None:
            return error
        sections = TransferService.get_exceptions(
            actor=user,
            report=report,
            from_date=from_date,
            to_date=to_date,
            month=month,
        )
        return Response(sections, status=status.HTTP_200_OK)
