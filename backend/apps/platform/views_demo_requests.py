"""Phase 2 Demo Requests views (Doc 16/17).

Covers:
- POST /api/v1/demo-requests (public capture endpoint)
- GET /api/v1/platform/demo-requests (inbox list + counts)
- GET /api/v1/platform/demo-requests/<id> (detail)
- PATCH /api/v1/platform/demo-requests/<id> (status / notes update, TOTP-gated, audit)
- POST /api/v1/platform/demo-requests/<id>/convert (linking, TOTP-gated)
"""

import uuid

from rest_framework import permissions, status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.models import DemoRequest, Tenant
from apps.platform.views import (
    IsAuthenticatedPlatformUser,
    PlatformJWTAuthentication,
    problem_response,
)
from apps.platform.views_admin import (
    _get_platform_user,
    _require_totp,
    _unauthorized,
    _write_platform_audit,
)


class PublicDemoRequestCaptureView(APIView):
    """POST /api/v1/demo-requests — public lead capture for Book a Demo."""

    permission_classes = [permissions.AllowAny]

    def post(self, request: Request) -> Response:
        data = request.data if isinstance(request.data, dict) else {}
        lab_name = str(data.get("lab_name", "")).strip()
        contact_person = str(data.get("contact_person", "")).strip()
        whatsapp = str(data.get("whatsapp", "")).strip()
        message = str(data.get("message", "")).strip()

        if not lab_name:
            return problem_response(
                code="validation_error",
                title="Validation error",
                detail="Laboratory name is required.",
                status_code=422,
            )
        if not contact_person:
            return problem_response(
                code="validation_error",
                title="Validation error",
                detail="Contact person name is required.",
                status_code=422,
            )
        if not whatsapp:
            return problem_response(
                code="validation_error",
                title="Validation error",
                detail="WhatsApp contact number is required.",
                status_code=422,
            )

        demo_req = DemoRequest.objects.create(
            lab_name=lab_name,
            contact_person=contact_person,
            whatsapp=whatsapp,
            message=message,
            status=DemoRequest.Status.NEW,
        )

        return Response(
            {
                "ok": True,
                "id": str(demo_req.id),
                "message": "Demo request received. Our team will contact you shortly.",
            },
            status=status.HTTP_201_CREATED,
        )


class PlatformDemoRequestListView(APIView):
    """GET /api/v1/platform/demo-requests — inbox of demo requests."""

    authentication_classes = [PlatformJWTAuthentication]
    permission_classes = [IsAuthenticatedPlatformUser]

    def get(self, request: Request) -> Response:
        user = _get_platform_user(request)
        if not user:
            return _unauthorized()

        status_param = request.query_params.get("status", "").strip().lower()
        search_query = request.query_params.get("q", "").strip().lower()

        qs = DemoRequest.objects.select_related("converted_tenant").all()

        if status_param and status_param != "all":
            qs = qs.filter(status=status_param)

        if search_query:
            qs = (
                qs.filter(lab_name__icontains=search_query)
                | qs.filter(contact_person__icontains=search_query)
                | qs.filter(whatsapp__icontains=search_query)
            )

        qs = qs.order_by("-requested_at")

        requests_data = [
            {
                "id": str(r.id),
                "lab_name": r.lab_name,
                "contact_person": r.contact_person,
                "whatsapp": r.whatsapp,
                "message": r.message,
                "status": r.status,
                "notes": r.notes,
                "requested_at": r.requested_at.isoformat(),
                "converted_tenant_id": str(r.converted_tenant_id)
                if r.converted_tenant_id
                else None,
            }
            for r in qs
        ]

        all_reqs = DemoRequest.objects.all()
        summary = {
            "new_count": all_reqs.filter(status=DemoRequest.Status.NEW).count(),
            "demo_done_count": all_reqs.filter(
                status=DemoRequest.Status.DEMO_DONE
            ).count(),
            "converted_count": all_reqs.filter(
                status=DemoRequest.Status.CONVERTED
            ).count(),
            "total_count": all_reqs.count(),
        }

        return Response(
            {"requests": requests_data, "summary": summary}, status=status.HTTP_200_OK
        )


class PlatformDemoRequestDetailView(APIView):
    """GET / PATCH /api/v1/platform/demo-requests/<id> — single inquiry management."""

    authentication_classes = [PlatformJWTAuthentication]
    permission_classes = [IsAuthenticatedPlatformUser]

    def get(self, request: Request, request_id: uuid.UUID) -> Response:
        user = _get_platform_user(request)
        if not user:
            return _unauthorized()

        demo_req = (
            DemoRequest.objects.select_related("converted_tenant")
            .filter(id=request_id)
            .first()
        )
        if not demo_req:
            return problem_response(
                code="not_found",
                title="Not found",
                detail="Demo request not found.",
                status_code=404,
            )

        return Response(
            {
                "id": str(demo_req.id),
                "lab_name": demo_req.lab_name,
                "contact_person": demo_req.contact_person,
                "whatsapp": demo_req.whatsapp,
                "message": demo_req.message,
                "status": demo_req.status,
                "notes": demo_req.notes,
                "requested_at": demo_req.requested_at.isoformat(),
                "converted_tenant": {
                    "id": str(demo_req.converted_tenant.id),
                    "name": demo_req.converted_tenant.name,
                    "slug": demo_req.converted_tenant.slug,
                }
                if demo_req.converted_tenant
                else None,
            },
            status=status.HTTP_200_OK,
        )

    def patch(self, request: Request, request_id: uuid.UUID) -> Response:
        user = _get_platform_user(request)
        if not user:
            return _unauthorized()

        totp_err = _require_totp(user)
        if totp_err:
            return totp_err

        demo_req = DemoRequest.objects.filter(id=request_id).first()
        if not demo_req:
            return problem_response(
                code="not_found",
                title="Not found",
                detail="Demo request not found.",
                status_code=404,
            )

        data = request.data if isinstance(request.data, dict) else {}
        before_state = {
            "status": demo_req.status,
            "notes": demo_req.notes,
        }

        if "status" in data:
            demo_req.status = str(data["status"]).strip().lower()
        if "notes" in data:
            demo_req.notes = str(data["notes"])
        demo_req.save()

        after_state = {
            "status": demo_req.status,
            "notes": demo_req.notes,
        }

        _write_platform_audit(
            actor_id=user.id,
            action="demo_request.updated",
            entity_type="demo_request",
            entity_id=demo_req.id,
            before=before_state,
            after=after_state,
            ip=request.META.get("REMOTE_ADDR"),
            user_agent=request.META.get("HTTP_USER_AGENT"),
        )

        return Response(
            {"ok": True, "id": str(demo_req.id), "status": demo_req.status},
            status=status.HTTP_200_OK,
        )


class PlatformDemoRequestConvertView(APIView):
    """POST /api/v1/platform/demo-requests/<id>/convert — link to provisioned tenant."""

    authentication_classes = [PlatformJWTAuthentication]
    permission_classes = [IsAuthenticatedPlatformUser]

    def post(self, request: Request, request_id: uuid.UUID) -> Response:
        user = _get_platform_user(request)
        if not user:
            return _unauthorized()

        totp_err = _require_totp(user)
        if totp_err:
            return totp_err

        demo_req = DemoRequest.objects.filter(id=request_id).first()
        if not demo_req:
            return problem_response(
                code="not_found",
                title="Not found",
                detail="Demo request not found.",
                status_code=404,
            )

        data = request.data if isinstance(request.data, dict) else {}
        tenant_id = data.get("tenant_id")
        if not tenant_id:
            return problem_response(
                code="validation_error",
                title="Validation error",
                detail="tenant_id is required.",
                status_code=422,
            )

        tenant = Tenant.objects.filter(id=tenant_id).first()
        if not tenant:
            return problem_response(
                code="not_found",
                title="Not found",
                detail="Tenant not found.",
                status_code=404,
            )

        demo_req.converted_tenant = tenant
        demo_req.status = DemoRequest.Status.CONVERTED
        demo_req.save()

        _write_platform_audit(
            actor_id=user.id,
            action="demo_request.converted",
            entity_type="demo_request",
            entity_id=demo_req.id,
            after={"converted_tenant_id": str(tenant.id), "status": demo_req.status},
            ip=request.META.get("REMOTE_ADDR"),
            user_agent=request.META.get("HTTP_USER_AGENT"),
        )

        return Response(
            {
                "ok": True,
                "id": str(demo_req.id),
                "converted_tenant_id": str(tenant.id),
                "status": demo_req.status,
            },
            status=status.HTTP_200_OK,
        )
