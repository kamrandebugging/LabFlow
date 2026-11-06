"""Platform operator auth views — apex host only (Doc 04 §12.1, Doc 08 §4).

Contract mirrors the tenant auth surface in ``apps.accounts.views_auth`` with
``PlatformUser`` as the subject and a distinct refresh cookie path.
"""

import logging
from typing import Any, cast

from django.conf import settings
from django.db import transaction
from rest_framework import permissions, status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.models import PlatformUser
from apps.platform.auth_serializers import (
    PlatformLoginSerializer,
    PlatformPasswordResetConfirmSerializer,
    PlatformPasswordResetRequestSerializer,
    PlatformTotpConfirmSerializer,
    PlatformTotpVerifySerializer,
)
from apps.platform.auth_service import (
    PlatformAuthService,
    PlatformAuthUnavailable,
    write_platform_audit,
)
from apps.platform.platform_jwt import (
    PLATFORM_COOKIE_PATH,
    PLATFORM_REFRESH_COOKIE_NAME,
    PLATFORM_REFRESH_LIFETIME_SECONDS,
)
from apps.platform.views import (
    IsAuthenticatedPlatformUser,
    PlatformJWTAuthentication,
    problem_response,
)

logger = logging.getLogger(__name__)

GENERIC_INVALID_CREDENTIALS = "Email, password or code is not correct"


def get_client_ip(request: Request) -> str:
    """Client IP, honouring the Caddy-set X-Forwarded-For first hop."""
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR")
    if forwarded:
        return str(forwarded).split(",")[0].strip()
    return str(request.META.get("REMOTE_ADDR", "127.0.0.1"))


def _user_agent(request: Request) -> str:
    return str(request.META.get("HTTP_USER_AGENT", ""))


def _set_refresh_cookie(response: Response, token: str) -> None:
    """Host-only, HttpOnly refresh cookie scoped to the platform auth path.

    ``Secure`` is on whenever Django is not in DEBUG, so local HTTP development
    still works while every deployed environment enforces it.
    """
    response.set_cookie(
        key=PLATFORM_REFRESH_COOKIE_NAME,
        value=token,
        max_age=PLATFORM_REFRESH_LIFETIME_SECONDS,
        httponly=True,
        secure=not bool(getattr(settings, "DEBUG", False)),
        samesite="Lax",
        path=PLATFORM_COOKIE_PATH,
    )


def _clear_refresh_cookie(response: Response) -> None:
    response.delete_cookie(key=PLATFORM_REFRESH_COOKIE_NAME, path=PLATFORM_COOKIE_PATH)


def _unavailable() -> Response:
    return problem_response(
        code="service_unavailable",
        title="Authentication temporarily unavailable",
        detail="Authentication is temporarily unavailable. Please retry shortly.",
        status_code=503,
    )


def _invalid_credentials(status_code: int = 401) -> Response:
    return problem_response(
        code="invalid_credentials",
        title="Invalid credentials",
        detail=GENERIC_INVALID_CREDENTIALS,
        status_code=status_code,
    )


class PlatformLoginView(APIView):
    """POST /api/v1/platform/auth/login."""

    authentication_classes: list[Any] = []
    permission_classes = [permissions.AllowAny]

    def post(self, request: Request) -> Response:
        serializer = PlatformLoginSerializer(data=request.data)
        if not serializer.is_valid():
            return _invalid_credentials()

        email = str(serializer.validated_data["email"])
        password = str(serializer.validated_data["password"])
        ip = get_client_ip(request)
        agent = _user_agent(request)

        from apps.platform.auth_service import (
            check_and_record_platform_login_throttle,
        )

        try:
            throttled, retry_after = check_and_record_platform_login_throttle(email, ip)
        except PlatformAuthUnavailable as exc:
            logger.error("Platform login throttle unavailable: %s", exc)
            return _unavailable()

        if throttled:
            response = problem_response(
                code="rate_limited",
                title="Too many attempts",
                detail="Too many failed login attempts. Please try again later.",
                status_code=429,
            )
            response["Retry-After"] = str(retry_after)
            return response

        try:
            success, payload, _error = PlatformAuthService.login(
                email=email, password=password, ip=ip, user_agent=agent
            )
        except PlatformAuthUnavailable:
            return _unavailable()

        if not success or payload is None:
            return _invalid_credentials()

        if payload.get("totp_required"):
            return Response(
                {
                    "totp_required": True,
                    "challenge_id": payload["challenge_id"],
                },
                status=status.HTTP_200_OK,
            )

        response = Response(
            {
                "access": payload["access"],
                "expires_in": payload["expires_in"],
                "user": payload["user"],
            },
            status=status.HTTP_200_OK,
        )
        _set_refresh_cookie(response, str(payload["refresh_token"]))
        return response


class PlatformTotpVerifyView(APIView):
    """POST /api/v1/platform/auth/totp/verify."""

    authentication_classes: list[Any] = []
    permission_classes = [permissions.AllowAny]

    def post(self, request: Request) -> Response:
        serializer = PlatformTotpVerifySerializer(data=request.data)
        if not serializer.is_valid():
            return _invalid_credentials()

        try:
            success, payload, error = PlatformAuthService.verify_totp_challenge(
                email=str(serializer.validated_data["email"]),
                challenge_id=str(serializer.validated_data["challenge_id"]),
                code=str(serializer.validated_data["code"]),
                ip=get_client_ip(request),
                user_agent=_user_agent(request),
            )
        except PlatformAuthUnavailable:
            return _unavailable()

        if not success or payload is None:
            if error == "totp_challenge_expired":
                return problem_response(
                    code="totp_challenge_expired",
                    title="Challenge expired",
                    detail=(
                        "Verification challenge expired or max attempts reached. "
                        "Please sign in again."
                    ),
                    status_code=401,
                )
            return _invalid_credentials()

        response = Response(
            {
                "access": payload["access"],
                "expires_in": payload["expires_in"],
                "user": payload["user"],
            },
            status=status.HTTP_200_OK,
        )
        _set_refresh_cookie(response, str(payload["refresh_token"]))
        return response


class PlatformTotpEnrollView(APIView):
    """POST /api/v1/platform/auth/totp/enroll — returns secret + otpauth URI once."""

    authentication_classes = [PlatformJWTAuthentication]
    permission_classes = [IsAuthenticatedPlatformUser]

    def post(self, request: Request) -> Response:
        user = cast(PlatformUser, request.user)
        try:
            secret, uri = PlatformAuthService.enroll_totp(user)
        except PlatformAuthUnavailable:
            return _unavailable()

        with transaction.atomic():
            write_platform_audit(
                action="auth.totp_enrollment_started",
                actor_id=user.id,
                entity_id=user.id,
                after={"totp_enabled": user.totp_enabled},
                ip=get_client_ip(request),
                user_agent=_user_agent(request),
            )

        return Response({"secret": secret, "otpauth_uri": uri}, status=200)


class PlatformTotpEnrollConfirmView(APIView):
    """POST /api/v1/platform/auth/totp/enroll/confirm — activates + backup codes."""

    authentication_classes = [PlatformJWTAuthentication]
    permission_classes = [IsAuthenticatedPlatformUser]

    def post(self, request: Request) -> Response:
        serializer = PlatformTotpConfirmSerializer(data=request.data)
        if not serializer.is_valid():
            return problem_response(
                code="invalid_code",
                title="Invalid code",
                detail="Enter the 6-digit code from your authenticator app.",
                status_code=400,
            )

        user = cast(PlatformUser, request.user)
        try:
            success, backup_codes, error = PlatformAuthService.confirm_totp_enrollment(
                user=user,
                code=str(serializer.validated_data["code"]),
                ip=get_client_ip(request),
                user_agent=_user_agent(request),
            )
        except PlatformAuthUnavailable:
            return _unavailable()

        if not success or backup_codes is None:
            if error == "enrolment_expired":
                return problem_response(
                    code="enrolment_expired",
                    title="Enrolment expired",
                    detail="Enrolment session expired. Please start again.",
                    status_code=400,
                )
            return problem_response(
                code="invalid_code",
                title="Invalid code",
                detail="Code does not match the pending secret.",
                status_code=400,
            )

        return Response({"backup_codes": backup_codes}, status=200)


class PlatformRefreshView(APIView):
    """POST /api/v1/platform/auth/refresh — rotation-on-use."""

    authentication_classes: list[Any] = []
    permission_classes = [permissions.AllowAny]

    def post(self, request: Request) -> Response:
        raw = request.COOKIES.get(PLATFORM_REFRESH_COOKIE_NAME)
        if not raw:
            return problem_response(
                code="invalid_refresh_token",
                title="Invalid refresh token",
                detail="Missing refresh token.",
                status_code=401,
            )

        try:
            success, data, error = PlatformAuthService.refresh_tokens(
                raw_refresh_token=str(raw),
                ip=get_client_ip(request),
                user_agent=_user_agent(request),
            )
        except PlatformAuthUnavailable:
            return _unavailable()

        if not success or data is None:
            if error == "refresh_reuse_detected":
                response = problem_response(
                    code="refresh_reuse_detected",
                    title="Refresh token reuse detected",
                    detail="Token reuse detected; all sessions were revoked.",
                    status_code=401,
                )
                _clear_refresh_cookie(response)
                return response
            response = problem_response(
                code="invalid_refresh_token",
                title="Invalid refresh token",
                detail="Invalid or expired refresh token.",
                status_code=401,
            )
            _clear_refresh_cookie(response)
            return response

        response = Response(
            {
                "access": data["access"],
                "expires_in": data["expires_in"],
                "user": data.get("user"),
            },
            status=200,
        )
        _set_refresh_cookie(response, str(data["refresh_token"]))
        return response


class PlatformLogoutView(APIView):
    """POST /api/v1/platform/auth/logout — revokes this session only."""

    authentication_classes: list[Any] = []
    permission_classes = [permissions.AllowAny]

    def post(self, request: Request) -> Response:
        auth_header = str(request.META.get("HTTP_AUTHORIZATION", ""))
        parts = auth_header.split()
        is_bearer = len(parts) == 2 and parts[0].lower() == "bearer"
        access_token = parts[1] if is_bearer else None
        refresh_token = request.COOKIES.get(PLATFORM_REFRESH_COOKIE_NAME)

        try:
            PlatformAuthService.logout(
                access_token=access_token,
                refresh_token=str(refresh_token) if refresh_token else None,
                ip=get_client_ip(request),
                user_agent=_user_agent(request),
            )
        except PlatformAuthUnavailable:
            return _unavailable()

        response = Response(status=status.HTTP_204_NO_CONTENT)
        _clear_refresh_cookie(response)
        return response


class PlatformPasswordResetRequestView(APIView):
    """POST /api/v1/platform/auth/password-reset/request — always 202."""

    authentication_classes: list[Any] = []
    permission_classes = [permissions.AllowAny]

    def post(self, request: Request) -> Response:
        serializer = PlatformPasswordResetRequestSerializer(data=request.data)
        raw_email = ""
        if serializer.is_valid():
            raw_email = (
                str(serializer.validated_data.get("email") or "").strip().lower()
            )

        if raw_email:
            try:
                raw_token = PlatformAuthService.request_password_reset(
                    email=raw_email,
                    ip=get_client_ip(request),
                    user_agent=_user_agent(request),
                )
            except PlatformAuthUnavailable:
                raw_token = None
            if raw_token:
                logger.info("Platform password reset token issued for %s", raw_email)
            # Delivery is owned by the operations mailbox (Phase 2); the token
            # is never logged and never returned in the response body.

        return Response({"accepted": True}, status=status.HTTP_202_ACCEPTED)


class PlatformPasswordResetConfirmView(APIView):
    """POST /api/v1/platform/auth/password-reset/confirm."""

    authentication_classes: list[Any] = []
    permission_classes = [permissions.AllowAny]

    def post(self, request: Request) -> Response:
        serializer = PlatformPasswordResetConfirmSerializer(data=request.data)
        data: dict[str, Any] = (
            serializer.validated_data if serializer.is_valid() else {}
        )
        token = str(data.get("token") or "").strip()
        new_password = str(data.get("new_password") or "")

        try:
            ok, code, message = PlatformAuthService.confirm_password_reset(
                token=token,
                new_password=new_password,
                ip=get_client_ip(request),
                user_agent=_user_agent(request),
            )
        except PlatformAuthUnavailable:
            return _unavailable()

        if not ok:
            if code == "invalid_reset_token":
                return problem_response(
                    code="invalid_reset_token",
                    title="Invalid reset token",
                    detail="Invalid or expired reset token.",
                    status_code=400,
                )
            return problem_response(
                code=code or "validation_error",
                title="Password rejected",
                detail=message or "Password does not meet the policy.",
                status_code=422,
            )

        return Response(
            {"status": "success", "message": "Password reset successfully"},
            status=200,
        )
