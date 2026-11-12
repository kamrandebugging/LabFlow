"""DRF Serializers for Authentication & Session management (Doc 07 §5, Doc 08 §4)."""

from rest_framework import serializers

from apps.core.serializers import StrictSerializer


class LoginRequestSerializer(StrictSerializer):
    email = serializers.EmailField(required=True, max_length=255)
    password = serializers.CharField(required=True, write_only=True, max_length=128)


class PasswordChangeRequestSerializer(StrictSerializer):
    current_password = serializers.CharField(
        required=True, write_only=True, max_length=128
    )
    new_password = serializers.CharField(required=True, write_only=True, max_length=128)


class SessionItemSerializer(serializers.Serializer):
    id = serializers.UUIDField(read_only=True)
    ip = serializers.CharField(read_only=True)
    user_agent = serializers.CharField(read_only=True)
    created_at = serializers.DateTimeField(read_only=True)
    last_active = serializers.DateTimeField(read_only=True)
    current = serializers.BooleanField(read_only=True)


class TotpEnrollConfirmSerializer(StrictSerializer):
    code = serializers.CharField(required=True, min_length=6, max_length=16)


class TotpDisableSerializer(StrictSerializer):
    current_password = serializers.CharField(
        required=True, write_only=True, max_length=128
    )


class TotpVerifySerializer(StrictSerializer):
    code = serializers.CharField(required=True, min_length=6, max_length=32)
    is_backup_code = serializers.BooleanField(required=False, default=False)
    challenge_token = serializers.CharField(
        required=False, allow_null=True, allow_blank=True, max_length=255
    )
    email = serializers.EmailField(
        required=False, allow_null=True, allow_blank=True, max_length=255
    )


class PasswordResetRequestSerializer(StrictSerializer):
    email = serializers.EmailField(required=True, max_length=255)


class PasswordResetConfirmSerializer(StrictSerializer):
    token = serializers.CharField(required=True, allow_blank=False, max_length=255)
    new_password = serializers.CharField(
        required=True,
        write_only=True,
        allow_blank=False,
        max_length=128,
    )
