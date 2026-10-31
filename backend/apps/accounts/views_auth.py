"""Views for LabFlow Auth Engine & Session Management (Doc 07 §5, Doc 08 §4)."""

import logging
import uuid
from typing import cast

from django.conf import settings
from rest_framework import permissions, status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.auth_service import AuthService
from apps.accounts.models import LoginEvent, StaffUser
from apps.accounts.serializers_auth import (
    LoginRequestSerializer,
    PasswordChangeRequestSerializer,
    SessionItemSerializer,
    TotpEnrollConfirmSerializer,
    TotpVerifySerializer,
)
from apps.accounts.throttling import (
    check_and_record_login_throttle,
)

logger = logging.getLogger(__name__)

REFRESH_COOKIE_NAME = getattr(settings, "AUTH_COOKIE_NAME", "refresh_token")
CHALLENGE_COOKIE_NAME = getattr(
    settings, "AUTH_CHALLENGE_COOKIE_NAME", "auth_challenge"
)
COOKIE_PATH = "/api/v1/auth/"
SEVEN_DAYS_SECONDS = 7 * 86400
FIVE_MINUTES_SECONDS = 300


def _get_client_ip(request: Request) -> str:
    x_forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
    if x_forwarded_for:
        return x_forwarded_for.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR", "127.0.0.1")


def _get_tenant_id(request: Request) -> str:
    tenant = getattr(request, "tenant", None)
    if tenant and hasattr(tenant, "schema_name"):
        return str(tenant.schema_name)
    return "tenant"


class LoginView(APIView):
    """POST /api/v1/auth/login."""

    permission_classes = [permissions.AllowAny]

    def post(self, request: Request) -> Response:
        serializer = LoginRequestSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(
                {
                    "error": {
                        "code": "invalid_credentials",
                        "message": "Email, password or code is not correct",
                    }
                },
                status=status.HTTP_401_UNAUTHORIZED,
            )

        email = serializer.validated_data["email"]
        password = serializer.validated_data["password"]
        ip = _get_client_ip(request)
        user_agent = request.META.get("HTTP_USER_AGENT", "")
        tenant_id = _get_tenant_id(request)

        # 1. Throttling Check (Doc 08 §10.1 & §10.3 fail-closed)
        try:
            is_throttled, retry_after = check_and_record_login_throttle(
                tenant_id=tenant_id,
                email=email,
                ip=ip,
            )
        except Exception as exc:
            logger.error("Login throttle failed closed: %s", exc)
            return Response(
                {
                    "error": {
                        "code": "service_unavailable",
                        "message": "Authentication service temporarily unavailable",
                    }
                },
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        if is_throttled:
            # Subtask 2: Throttled attempt still writes login_event (marked failure)
            LoginEvent.objects.create(
                staff_user=None,
                email_attempted=email,
                success=False,
                ip=ip,
                user_agent=user_agent,
            )
            response = Response(
                {
                    "error": {
                        "code": "rate_limited",
                        "message": (
                            "Too many failed login attempts. Please try again later."
                        ),
                    }
                },
                status=status.HTTP_429_TOO_MANY_REQUESTS,
            )
            response["Retry-After"] = str(retry_after)
            return response

        # 2. Authenticate Staff User
        success, payload, err_code = AuthService.login(
            email=email,
            password=password,
            ip=ip,
            user_agent=user_agent,
            tenant_id=tenant_id,
        )

        if not success or payload is None:
            return Response(
                {
                    "error": {
                        "code": "invalid_credentials",
                        "message": "Email, password or code is not correct",
                    }
                },
                status=status.HTTP_401_UNAUTHORIZED,
            )

        # 3. TOTP Challenge required?
        if payload.get("totp_required"):
            challenge_token = AuthService.create_totp_challenge(payload["user_id"])
            response = Response({"totp_required": True}, status=status.HTTP_200_OK)
            response.set_cookie(
                key=CHALLENGE_COOKIE_NAME,
                value=challenge_token,
                max_age=FIVE_MINUTES_SECONDS,
                httponly=True,
                secure=getattr(settings, "SESSION_COOKIE_SECURE", False),
                samesite="Lax",
                path=COOKIE_PATH,
            )
            return response

        # 4. Success: Set httpOnly refresh cookie, return access token in body
        refresh_token = payload["refresh_token"]
        body_data = {
            "access": payload["access"],
            "expires_in": payload["expires_in"],
            "user": payload["user"],
        }

        response = Response(body_data, status=status.HTTP_200_OK)
        response.set_cookie(
            key=REFRESH_COOKIE_NAME,
            value=refresh_token,
            max_age=SEVEN_DAYS_SECONDS,
            httponly=True,
            secure=getattr(settings, "SESSION_COOKIE_SECURE", False),
            samesite="Lax",
            path=COOKIE_PATH,
        )
        return response


class RefreshView(APIView):
    """POST /api/v1/auth/refresh."""

    permission_classes = [permissions.AllowAny]

    def post(self, request: Request) -> Response:
        refresh_token = request.COOKIES.get(REFRESH_COOKIE_NAME)
        if not refresh_token:
            return Response(
                {
                    "error": {
                        "code": "invalid_refresh_token",
                        "message": "Missing refresh token",
                    }
                },
                status=status.HTTP_401_UNAUTHORIZED,
            )

        ip = _get_client_ip(request)
        user_agent = request.META.get("HTTP_USER_AGENT", "")

        success, data, err_code = AuthService.refresh_tokens(
            raw_refresh_token=refresh_token,
            ip=ip,
            user_agent=user_agent,
        )

        if not success or data is None:
            if err_code == "refresh_reuse_detected":
                return Response(
                    {
                        "error": {
                            "code": "refresh_reuse_detected",
                            "message": "Token reuse detected; all sessions revoked",
                        }
                    },
                    status=status.HTTP_401_UNAUTHORIZED,
                )
            return Response(
                {
                    "error": {
                        "code": "invalid_refresh_token",
                        "message": "Invalid or expired refresh token",
                    }
                },
                status=status.HTTP_401_UNAUTHORIZED,
            )

        # Set new rotated refresh cookie
        new_refresh_token = data["refresh_token"]
        response = Response(
            {"access": data["access"], "expires_in": data["expires_in"]},
            status=status.HTTP_200_OK,
        )
        response.set_cookie(
            key=REFRESH_COOKIE_NAME,
            value=new_refresh_token,
            max_age=SEVEN_DAYS_SECONDS,
            httponly=True,
            secure=getattr(settings, "SESSION_COOKIE_SECURE", False),
            samesite="Lax",
            path=COOKIE_PATH,
        )
        return response


class LogoutView(APIView):
    """POST /api/v1/auth/logout."""

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request: Request) -> Response:
        auth_header = request.META.get("HTTP_AUTHORIZATION", "")
        access_token = auth_header.split()[1] if len(auth_header.split()) == 2 else None
        refresh_token = request.COOKIES.get(REFRESH_COOKIE_NAME)
        user = getattr(request, "user", None)
        tenant_id = _get_tenant_id(request)

        AuthService.logout(
            access_token=access_token,
            refresh_token=refresh_token,
            staff_user_id=user.id if user else None,
            tenant_id=tenant_id,
        )

        response = Response(status=status.HTTP_204_NO_CONTENT)
        response.delete_cookie(key=REFRESH_COOKIE_NAME, path=COOKIE_PATH)
        return response


class SessionListView(APIView):
    """GET /api/v1/auth/sessions."""

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request: Request) -> Response:
        user = cast(StaffUser, request.user)
        tenant_id = _get_tenant_id(request)

        auth_payload = getattr(request, "auth", {}) or {}
        caller_sid = auth_payload.get("sid") if isinstance(auth_payload, dict) else None
        sessions = AuthService.list_active_sessions(
            staff_user_id=user.id,
            current_session_id=caller_sid,
            tenant_id=tenant_id,
        )

        # Fallback to IP/UA matching if caller_sid not matched
        if sessions and not any(s.get("current") for s in sessions):
            req_ua = request.META.get("HTTP_USER_AGENT", "")
            req_ip = _get_client_ip(request)
            for s in sessions:
                if s["user_agent"] == req_ua and s["ip"] == req_ip:
                    s["current"] = True
                    break

        serializer = SessionItemSerializer(sessions, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)


class SessionDetailView(APIView):
    """DELETE /api/v1/auth/sessions/<uuid:session_id>."""

    permission_classes = [permissions.IsAuthenticated]

    def delete(self, request: Request, session_id: uuid.UUID) -> Response:
        user = cast(StaffUser, request.user)
        tenant_id = _get_tenant_id(request)
        ip = _get_client_ip(request)
        user_agent = request.META.get("HTTP_USER_AGENT", "")

        success = AuthService.revoke_remote_session(
            caller_user_id=user.id,
            session_id=session_id,
            tenant_id=tenant_id,
            ip=ip,
            user_agent=user_agent,
        )

        if not success:
            return Response(
                {
                    "error": {
                        "code": "session_not_found",
                        "message": "Session not found",
                    }
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        return Response(status=status.HTTP_204_NO_CONTENT)


class RevokeAllSessionsView(APIView):
    """POST /api/v1/auth/sessions/revoke-all."""

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request: Request) -> Response:
        user = cast(StaffUser, request.user)
        tenant_id = _get_tenant_id(request)
        ip = _get_client_ip(request)
        user_agent = request.META.get("HTTP_USER_AGENT", "")

        AuthService.revoke_all_sessions(
            staff_user_id=user.id,
            tenant_id=tenant_id,
            except_session_id=None,
            reason="user_revoke_all",
            ip=ip,
            user_agent=user_agent,
        )
        return Response(status=status.HTTP_204_NO_CONTENT)


class PasswordChangeView(APIView):
    """POST /api/v1/auth/password/change."""

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request: Request) -> Response:
        serializer = PasswordChangeRequestSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(
                {
                    "error": {
                        "code": "validation_error",
                        "message": "Invalid password data",
                    }
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        user = cast(StaffUser, request.user)
        current_password = serializer.validated_data["current_password"]
        new_password = serializer.validated_data["new_password"]
        tenant_id = _get_tenant_id(request)
        ip = _get_client_ip(request)
        user_agent = request.META.get("HTTP_USER_AGENT", "")

        # Find current session to preserve
        auth_payload = getattr(request, "auth", {}) or {}
        current_sid = (
            auth_payload.get("sid") if isinstance(auth_payload, dict) else None
        )
        if not current_sid:
            sessions = AuthService.list_active_sessions(user.id, tenant_id=tenant_id)
            for s in sessions:
                if s["user_agent"] == user_agent and s["ip"] == ip:
                    current_sid = s["id"]
                    break

        success, err = AuthService.change_password(
            staff_user=user,
            current_password=current_password,
            new_password=new_password,
            current_session_id=current_sid,
            ip=ip,
            user_agent=user_agent,
            tenant_id=tenant_id,
        )

        if not success:
            return Response(
                {
                    "error": {
                        "code": "invalid_credentials",
                        "message": "Current password is not correct",
                    }
                },
                status=status.HTTP_401_UNAUTHORIZED,
            )

        return Response(
            {"status": "ok", "message": "Password changed successfully"},
            status=status.HTTP_200_OK,
        )


class TotpEnrollView(APIView):
    """POST /api/v1/auth/totp/enroll (Doc 08 §4.4, §17 A-25)."""

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request: Request) -> Response:
        user = cast(StaffUser, request.user)
        secret, otpauth_uri = AuthService.enroll_totp(user)
        return Response(
            {
                "secret": secret,
                "otpauth_uri": otpauth_uri,
            },
            status=status.HTTP_200_OK,
        )


class TotpEnrollConfirmView(APIView):
    """POST /api/v1/auth/totp/enroll/confirm (Doc 08 §4.4, §17 A-25)."""

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request: Request) -> Response:
        serializer = TotpEnrollConfirmSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(
                {
                    "error": {
                        "code": "invalid_code",
                        "message": "Invalid code format",
                    }
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        code = serializer.validated_data["code"]
        user = cast(StaffUser, request.user)
        ip = _get_client_ip(request)
        user_agent = request.META.get("HTTP_USER_AGENT", "")

        success, backup_codes, err_code = AuthService.confirm_totp_enrollment(
            user=user,
            code=code,
            ip=ip,
            user_agent=user_agent,
        )

        if not success or backup_codes is None:
            if err_code == "enrolment_expired":
                return Response(
                    {
                        "error": {
                            "code": "enrolment_expired",
                            "message": "Enrolment session expired. Please start again.",
                        }
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )
            return Response(
                {
                    "error": {
                        "code": "invalid_code",
                        "message": "Code does not match pending secret",
                    }
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        return Response(
            {"backup_codes": backup_codes},
            status=status.HTTP_200_OK,
        )


class TotpVerifyView(APIView):
    """POST /api/v1/auth/totp/verify (Doc 08 §4.4)."""

    permission_classes = [permissions.AllowAny]

    def post(self, request: Request) -> Response:
        challenge_token = request.COOKIES.get(CHALLENGE_COOKIE_NAME) or request.data.get("challenge_token")
        if not challenge_token:
            return Response(
                {
                    "error": {
                        "code": "totp_challenge_expired",
                        "message": "Challenge missing or expired. Please login again.",
                    }
                },
                status=status.HTTP_401_UNAUTHORIZED,
            )

        serializer = TotpVerifySerializer(data=request.data)
        if not serializer.is_valid():
            return Response(
                {
                    "error": {
                        "code": "invalid_credentials",
                        "message": "Email, password or code is not correct",
                    }
                },
                status=status.HTTP_401_UNAUTHORIZED,
            )

        code = serializer.validated_data["code"]
        ip = _get_client_ip(request)
        user_agent = request.META.get("HTTP_USER_AGENT", "")
        tenant_id = _get_tenant_id(request)

        success, payload, err_code = AuthService.verify_totp_challenge(
            challenge_token=challenge_token,
            code=code,
            ip=ip,
            user_agent=user_agent,
            tenant_id=tenant_id,
        )

        if not success or payload is None:
            if err_code == "totp_challenge_expired":
                res = Response(
                    {
                        "error": {
                            "code": "totp_challenge_expired",
                            "message": "Verification challenge expired or max attempts reached.",
                        }
                    },
                    status=status.HTTP_401_UNAUTHORIZED,
                )
                res.delete_cookie(CHALLENGE_COOKIE_NAME, path=COOKIE_PATH)
                return res

            return Response(
                {
                    "error": {
                        "code": "invalid_credentials",
                        "message": "Email, password or code is not correct",
                    }
                },
                status=status.HTTP_401_UNAUTHORIZED,
            )

        # Success: Set httpOnly refresh cookie and clear challenge cookie
        refresh_token = payload["refresh_token"]
        body_data = {
            "access": payload["access"],
            "expires_in": payload["expires_in"],
            "user": payload["user"],
        }

        response = Response(body_data, status=status.HTTP_200_OK)
        response.set_cookie(
            key=REFRESH_COOKIE_NAME,
            value=refresh_token,
            max_age=SEVEN_DAYS_SECONDS,
            httponly=True,
            secure=getattr(settings, "SESSION_COOKIE_SECURE", False),
            samesite="Lax",
            path=COOKIE_PATH,
        )
        response.delete_cookie(CHALLENGE_COOKIE_NAME, path=COOKIE_PATH)
        return response


class StaffTotpResetView(APIView):
    """POST /api/v1/staff/<uuid:user_id>/reset-totp (Doc 08 §4.4, LAB-52)."""

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request: Request, user_id: uuid.UUID) -> Response:
        actor = cast(StaffUser, request.user)
        target_user = StaffUser.objects.filter(id=user_id).first()
        if not target_user:
            return Response(
                {"error": {"code": "not_found", "message": "Staff user not found"}},
                status=status.HTTP_404_NOT_FOUND,
            )

        ip = _get_client_ip(request)
        user_agent = request.META.get("HTTP_USER_AGENT", "")

        success, err = AuthService.reset_staff_totp(
            actor=actor,
            target_user=target_user,
            ip=ip,
            user_agent=user_agent,
        )

        if not success:
            return Response(
                {"error": {"code": "forbidden", "message": "Only Lab Owner can reset staff TOTP"}},
                status=status.HTTP_403_FORBIDDEN,
            )

        return Response(
            {"status": "ok", "message": "Staff TOTP reset successfully"},
            status=status.HTTP_200_OK,
        )

