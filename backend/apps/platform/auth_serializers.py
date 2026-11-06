"""Serializers for platform operator auth (Doc 08 §4.4)."""

from typing import Any

from rest_framework import serializers


class PlatformLoginSerializer(serializers.Serializer[dict[str, Any]]):
    """POST /api/v1/platform/auth/login body."""

    email = serializers.CharField(
        required=True, allow_blank=False, trim_whitespace=True
    )
    password = serializers.CharField(
        required=True,
        allow_blank=False,
        trim_whitespace=False,
        style={"input_type": "password"},
    )


class PlatformTotpVerifySerializer(serializers.Serializer[dict[str, Any]]):
    """POST /api/v1/platform/auth/totp/verify body."""

    email = serializers.CharField(
        required=True, allow_blank=False, trim_whitespace=True
    )
    challenge_id = serializers.CharField(
        required=True, allow_blank=False, trim_whitespace=True
    )
    code = serializers.CharField(
        required=True, allow_blank=False, trim_whitespace=True, max_length=32
    )


class PlatformTotpConfirmSerializer(serializers.Serializer[dict[str, Any]]):
    """POST /api/v1/platform/auth/totp/enroll/confirm body."""

    code = serializers.CharField(
        required=True, allow_blank=False, trim_whitespace=True, max_length=32
    )


class PlatformPasswordResetRequestSerializer(serializers.Serializer[dict[str, Any]]):
    """POST /api/v1/platform/auth/password-reset/request body."""

    email = serializers.CharField(
        required=False, allow_blank=True, trim_whitespace=True
    )


class PlatformPasswordResetConfirmSerializer(serializers.Serializer[dict[str, Any]]):
    """POST /api/v1/platform/auth/password-reset/confirm body."""

    token = serializers.CharField(required=False, allow_blank=True)
    new_password = serializers.CharField(required=False, allow_blank=True)
