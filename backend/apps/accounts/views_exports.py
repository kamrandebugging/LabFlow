"""Views for tenant data exports (Doc 04 §4.3; KAN-163 / LAB-38).

POST /api/v1/exports — Lab Owner requests a data-portability export.
GET  /api/v1/exports/{id} — export status.
GET  /api/v1/exports/{id}/download — signed 7-day download (query ?sig=).

The export path is explicitly available in read-only subscription mode
(Doc 04 §4.3; LAB-38 DoD) — it is exempt from the 403
subscription_read_only gate.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any, cast

from django.core.signing import BadSignature, SignatureExpired, TimestampSigner
from django.db import transaction
from django.http import FileResponse
from rest_framework import permissions, status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import AuditLog, DataExport, Role, StaffUser

logger = logging.getLogger(__name__)

EXPORT_SIGNER_SALT = "labflow.data-export"
# 7 days, matching the signed download link validity (Doc 04 §4.3).
EXPORT_LINK_MAX_AGE_SECONDS = 7 * 86400

EXPORT_REQUEST_ROLES = frozenset({Role.OWNER})


def _format_error(code: str, detail: str) -> dict[str, Any]:
    return {
        "type": f"https://labflow.example/problems/{code.replace('_', '-')}",
        "title": code.replace("_", " ").title(),
        "status": 400,
        "detail": detail,
        "code": code,
    }


def _tenant_access_mode(request: Request) -> str:
    """Return 'full' or 'read_only' for the current tenant.

    Overridable seam for tests. Production wiring resolves the
    subscription state (LAB-36); the export endpoint treats both modes
    identically — it never returns 403 subscription_read_only.
    """
    return "full"


class ExportRequestView(APIView):
    """POST /api/v1/exports — request a data-portability export."""

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request: Request) -> Response:
        user = cast(StaffUser, request.user)
        if user.role not in EXPORT_REQUEST_ROLES:
            return Response(
                _format_error(
                    "forbidden",
                    "Only the Lab Owner may request a data export.",
                ),
                status=status.HTTP_403_FORBIDDEN,
            )
        # Idempotency-Key required for non-idempotent writes (standing rule).
        idempotency_key = request.headers.get("Idempotency-Key")
        if not idempotency_key:
            return Response(
                _format_error(
                    "idempotency_key_required",
                    "Idempotency-Key header is required.",
                ),
                status=status.HTTP_422_UNPROCESSABLE_ENTITY,
            )

        tenant = getattr(request, "tenant", None)
        schema_name = (
            str(tenant.schema_name) if tenant and hasattr(tenant, "schema_name") else ""
        )
        with transaction.atomic():
            export = DataExport.objects.create(
                requested_by=user,
                status=DataExport.Status.PENDING,
            )
            AuditLog.objects.create(
                actor_id=user.id,
                action="data.export_requested",
                entity_type="data_export",
                entity_id=export.id,
                after_jsonb={
                    "export_id": str(export.id),
                    "event": "data.export_requested",
                },
            )
        # Enqueue after commit (task reads the row).
        from apps.platform.tasks import export_tenant_task

        transaction.on_commit(
            lambda: export_tenant_task.delay(schema_name, str(export.id))
        )
        return Response(
            {
                "export_id": str(export.id),
                "status": export.status,
            },
            status=status.HTTP_202_ACCEPTED,
        )


class ExportDetailView(APIView):
    """GET /api/v1/exports/{id} — export status."""

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request: Request, export_id: Any) -> Response:
        user = cast(StaffUser, request.user)
        if user.role not in EXPORT_REQUEST_ROLES:
            return Response(
                _format_error("forbidden", "Only the Lab Owner may view exports."),
                status=status.HTTP_403_FORBIDDEN,
            )
        try:
            pk = uuid.UUID(str(export_id))
        except (ValueError, TypeError):
            return Response(
                _format_error("not_found", "Export not found."),
                status=status.HTTP_404_NOT_FOUND,
            )
        export = DataExport.objects.filter(pk=pk).first()
        if export is None:
            return Response(
                _format_error("not_found", "Export not found."),
                status=status.HTTP_404_NOT_FOUND,
            )
        payload: dict[str, Any] = {
            "export_id": str(export.id),
            "status": export.status,
            "created_at": export.created_at.isoformat(),
        }
        if export.status == DataExport.Status.COMPLETE:
            payload["download_url"] = export.download_url
            payload["download_expires_at"] = (
                export.download_expires_at.isoformat()
                if export.download_expires_at
                else None
            )
        if export.status == DataExport.Status.FAILED:
            payload["error"] = export.error
        return Response(payload, status=status.HTTP_200_OK)


class ExportDownloadView(APIView):
    """GET /api/v1/exports/{id}/download?sig= — signed bundle download.

    AllowAny: the signed token is the credential (7-day validity, the
    report-link pattern from Doc 04 §4.3).
    """

    permission_classes = [permissions.AllowAny]
    authentication_classes: list[Any] = []

    def get(self, request: Request, export_id: Any) -> Response:
        sig = request.query_params.get("sig")
        if not sig:
            return Response(
                _format_error("forbidden", "Missing download signature."),
                status=status.HTTP_403_FORBIDDEN,
            )
        signer = TimestampSigner(salt=EXPORT_SIGNER_SALT)
        try:
            unsigned = signer.unsign(sig, max_age=EXPORT_LINK_MAX_AGE_SECONDS)
        except (BadSignature, SignatureExpired):
            return Response(
                _format_error("forbidden", "Invalid or expired download link."),
                status=status.HTTP_403_FORBIDDEN,
            )
        if unsigned != str(export_id):
            return Response(
                _format_error("forbidden", "Signature does not match export."),
                status=status.HTTP_403_FORBIDDEN,
            )
        try:
            pk = uuid.UUID(str(export_id))
        except (ValueError, TypeError):
            return Response(
                _format_error("not_found", "Export not found."),
                status=status.HTTP_404_NOT_FOUND,
            )
        export = DataExport.objects.filter(
            pk=pk, status=DataExport.Status.COMPLETE
        ).first()
        if export is None or not export.bundle_key:
            return Response(
                _format_error("not_found", "Export not ready."),
                status=status.HTTP_404_NOT_FOUND,
            )
        from django.core.files.storage import default_storage

        if not default_storage.exists(export.bundle_key):
            return Response(
                _format_error("not_found", "Export bundle missing."),
                status=status.HTTP_404_NOT_FOUND,
            )
        fh = default_storage.open(export.bundle_key, "rb")
        response = FileResponse(fh, content_type="application/zip")
        response["Content-Disposition"] = (
            f'attachment; filename="export-{export.id}.zip"'
        )
        return response  # type: ignore[return-value]
