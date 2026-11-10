"""DRF Views for Patient Management (Doc 03 §5.1, §6.2, Doc 04 §8.5).

Implements:
- POST /api/v1/patients: Create patient with PT-3 duplicate check and MRN generation.
- GET /api/v1/patients: List/search with BS-1 to BS-4 multi-branch scoping.
- GET /api/v1/patients/{id}: Detail view with P-7 anti-oracle 404.
- PATCH /api/v1/patients/{id}: Update with If-Match (T-37) & PT-4 identity gate.
- DELETE /api/v1/patients/{id}: Soft delete with sample-in-flight guard.
"""

import uuid
from typing import cast

from rest_framework import permissions, status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import Role, StaffUser
from apps.branches.scope_views import BranchScopedAPIView, IsInBranchScope
from apps.patients.serializers import (
    PatientCandidateSerializer,
    PatientCreateSerializer,
    PatientDetailSerializer,
    PatientSummarySerializer,
    PatientUpdateSerializer,
)
from apps.patients.services import (
    BranchScopeDeniedError,
    IdentityEditForbiddenError,
    PatientNotFoundError,
    PatientService,
    PossibleDuplicateError,
    SamplesInFlightError,
    VersionConflictError,
)


def _get_client_ip(request: Request) -> str:
    x_forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
    if x_forwarded_for:
        return x_forwarded_for.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR", "")


class PatientListCreateView(BranchScopedAPIView):
    """GET /api/v1/patients & POST /api/v1/patients.

    Branch scope (Doc 04 §8.5): the list/search is scoped inside
    PatientService.list_patients — including the BS-4 identifiers-only
    exception, the one method allowed to cross scope, which is deliberately
    NOT routed through scoped_to. IsInBranchScope re-checks the body's
    branch_id on registration (Layer 3, defence in depth over the service
    check).
    """

    permission_classes = [permissions.IsAuthenticated, IsInBranchScope]
    scope_branch_source = "body:branch_id"

    def get(self, request: Request) -> Response:
        user = cast(StaffUser, request.user)
        q = request.query_params.get("q")
        branch_id_str = request.query_params.get("branch_id")
        branch_id = uuid.UUID(branch_id_str) if branch_id_str else None

        ip = _get_client_ip(request)
        user_agent = request.META.get("HTTP_USER_AGENT", "")

        patients = PatientService.list_patients(
            actor=user,
            q=q,
            branch_id=branch_id,
            ip=ip,
            user_agent=user_agent,
        )
        serializer = PatientSummarySerializer(patients, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    def post(self, request: Request) -> Response:
        user = cast(StaffUser, request.user)
        if user.role not in (Role.OWNER, Role.MANAGER, Role.RECEPTION):
            return Response(
                {
                    "error": {
                        "code": "forbidden",
                        "message": (
                            "Only Owner, Manager, or Receptionist may register."
                        ),
                    }
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        serializer = PatientCreateSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(
                {
                    "error": {
                        "code": "validation_error",
                        "message": "Invalid patient payload.",
                        "details": serializer.errors,
                    }
                },
                status=status.HTTP_422_UNPROCESSABLE_ENTITY,
            )

        data = serializer.validated_data
        ip = _get_client_ip(request)
        user_agent = request.META.get("HTTP_USER_AGENT", "")

        try:
            patient = PatientService.register_patient(
                actor=user,
                name=data["name"],
                phone=data["phone"],
                sex=data["sex"],
                branch_id=data["branch_id"],
                date_of_birth=data.get("date_of_birth"),
                confirm_duplicate=data.get("confirm_duplicate", False),
                whatsapp_number=data.get("whatsapp_number"),
                consent_reports=data.get("consent_reports", False),
                ip=ip,
                user_agent=user_agent,
            )
        except BranchScopeDeniedError as exc:
            return Response(
                {
                    "error": {
                        "code": "branch_scope_denied",
                        "message": str(exc),
                    }
                },
                status=status.HTTP_403_FORBIDDEN,
            )
        except PossibleDuplicateError as exc:
            candidates_data = PatientCandidateSerializer(exc.candidates, many=True).data
            return Response(
                {
                    "error": {
                        "code": "possible_duplicate",
                        "message": str(exc),
                        "candidates": candidates_data,
                    },
                    "candidates": candidates_data,
                },
                status=status.HTTP_409_CONFLICT,
            )

        detail_serializer = PatientDetailSerializer(patient)
        return Response(detail_serializer.data, status=status.HTTP_201_CREATED)


class PatientDetailView(APIView):
    """GET, PATCH, DELETE /api/v1/patients/{id}."""

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request: Request, id: uuid.UUID) -> Response:
        user = cast(StaffUser, request.user)
        ip = _get_client_ip(request)
        user_agent = request.META.get("HTTP_USER_AGENT", "")

        try:
            patient = PatientService.get_patient_detail(
                actor=user,
                patient_id=id,
                ip=ip,
                user_agent=user_agent,
            )
        except PatientNotFoundError:
            return Response(
                {
                    "error": {
                        "code": "not_found",
                        "message": "Patient not found.",
                    }
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        serializer = PatientDetailSerializer(patient)
        return Response(serializer.data, status=status.HTTP_200_OK)

    def patch(self, request: Request, id: uuid.UUID) -> Response:
        user = cast(StaffUser, request.user)
        if user.role not in (Role.OWNER, Role.MANAGER, Role.RECEPTION):
            return Response(
                {
                    "error": {
                        "code": "forbidden",
                        "message": "Role not permitted to edit patients.",
                    }
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        serializer = PatientUpdateSerializer(data=request.data, partial=True)
        if not serializer.is_valid():
            return Response(
                {
                    "error": {
                        "code": "validation_error",
                        "message": "Invalid update data.",
                        "details": serializer.errors,
                    }
                },
                status=status.HTTP_422_UNPROCESSABLE_ENTITY,
            )

        if_match = request.META.get("HTTP_IF_MATCH")
        ip = _get_client_ip(request)
        user_agent = request.META.get("HTTP_USER_AGENT", "")

        try:
            updated_patient = PatientService.update_patient(
                actor=user,
                patient_id=id,
                data=serializer.validated_data,
                if_match=if_match,
                ip=ip,
                user_agent=user_agent,
            )
        except PatientNotFoundError:
            return Response(
                {
                    "error": {
                        "code": "not_found",
                        "message": "Patient not found.",
                    }
                },
                status=status.HTTP_404_NOT_FOUND,
            )
        except VersionConflictError as exc:
            return Response(
                {
                    "error": {
                        "code": "version_conflict",
                        "message": str(exc),
                    }
                },
                status=status.HTTP_409_CONFLICT,
            )
        except IdentityEditForbiddenError as exc:
            return Response(
                {
                    "error": {
                        "code": "identity_edit_requires_management",
                        "message": str(exc),
                    }
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        detail_serializer = PatientDetailSerializer(updated_patient)
        return Response(detail_serializer.data, status=status.HTTP_200_OK)

    def delete(self, request: Request, id: uuid.UUID) -> Response:
        user = cast(StaffUser, request.user)
        ip = _get_client_ip(request)
        user_agent = request.META.get("HTTP_USER_AGENT", "")

        try:
            PatientService.soft_delete_patient(
                actor=user,
                patient_id=id,
                ip=ip,
                user_agent=user_agent,
            )
        except BranchScopeDeniedError as exc:
            return Response(
                {
                    "error": {
                        "code": "forbidden",
                        "message": str(exc),
                    }
                },
                status=status.HTTP_403_FORBIDDEN,
            )
        except PatientNotFoundError:
            return Response(
                {
                    "error": {
                        "code": "not_found",
                        "message": "Patient not found.",
                    }
                },
                status=status.HTTP_404_NOT_FOUND,
            )
        except SamplesInFlightError as exc:
            return Response(
                {
                    "error": {
                        "code": "samples_in_flight",
                        "message": str(exc),
                    }
                },
                status=status.HTTP_409_CONFLICT,
            )

        return Response(status=status.HTTP_204_NO_CONTENT)


class PatientHistoryView(APIView):
    """GET /api/v1/patients/{id}/history."""

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request: Request, id: uuid.UUID) -> Response:
        user = cast(StaffUser, request.user)
        ip = _get_client_ip(request)
        user_agent = request.META.get("HTTP_USER_AGENT", "")

        try:
            patient = PatientService.get_patient_detail(
                actor=user,
                patient_id=id,
                ip=ip,
                user_agent=user_agent,
            )
        except PatientNotFoundError:
            return Response(
                {
                    "error": {
                        "code": "not_found",
                        "message": "Patient not found.",
                    }
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        # Return history of chronological visits scoped per BS-3
        from apps.samples.models import Sample

        is_tenant_wide, assigned_branches = PatientService.get_caller_branch_scope(user)
        sample_qs = Sample.objects.filter(invoice__patient=patient)
        if not is_tenant_wide:
            sample_qs = sample_qs.filter(branch_id__in=assigned_branches)

        samples_history = [
            {
                "accession_id": s.accession_id,
                "status": s.status,
                "created_at": s.created_at.isoformat(),
            }
            for s in sample_qs.order_by("-created_at")
        ]
        return Response(
            {
                "patient_id": str(patient.id),
                "mrn": patient.mrn,
                "visits": samples_history,
            },
            status=status.HTTP_200_OK,
        )
