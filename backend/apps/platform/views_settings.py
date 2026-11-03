"""DRF views for Tenant Settings — GET/PATCH /settings (Doc 04 §10, KAN-160 / LAB-35).

GET /api/v1/settings — all settings with parsed values (any authenticated staff).
PATCH /api/v1/settings — update settings (Owner, Manager only).
    Body: {"settings": {"key": "raw_value", ...}}
    422 unknown_setting_key for unknown keys.
    422 invalid_setting_value for per-key validation failures.
    One audit row per key changed (in settings_accessor.set_setting).

Thin views: business logic lives in settings_registry / settings_accessor.
"""

from typing import Any, cast

from rest_framework import permissions, status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import Role, StaffUser
from apps.platform.settings_accessor import (
    UnknownSettingKeyError,
    get_setting,
    set_setting,
)
from apps.platform.settings_registry import SETTING_REGISTRY, get_default

SETTINGS_WRITE_ROLES = {Role.OWNER, Role.MANAGER}


def _get_client_ip(request: Request) -> str:
    x_forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
    if x_forwarded_for:
        return x_forwarded_for.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR", "")


def _format_error(code: str, message: str) -> dict[str, Any]:
    return {"code": code, "message": message}


class SettingsView(APIView):
    """GET /api/v1/settings — return all settings with parsed values.

    PATCH /api/v1/settings — update one or more settings (Owner/Manager only).
    """

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request: Request) -> Response:
        settings: dict[str, dict[str, Any]] = {}
        for key, spec in SETTING_REGISTRY.items():
            settings[key] = {
                "value": get_setting(key),
                "default": spec.validator(get_default(key)),
                "type": spec.type_name,
                "description": spec.description,
            }
        return Response({"settings": settings}, status=status.HTTP_200_OK)

    def patch(self, request: Request) -> Response:
        user = cast(StaffUser, request.user)
        if user.role not in SETTINGS_WRITE_ROLES:
            return Response(
                _format_error(
                    "forbidden",
                    "Only owners and managers may update settings.",
                ),
                status=status.HTTP_403_FORBIDDEN,
            )

        body = request.data
        if not isinstance(body, dict) or not isinstance(body.get("settings"), dict):
            return Response(
                _format_error(
                    "invalid_request",
                    'Body must be {"settings": {"key": "value", ...}}.',
                ),
                status=status.HTTP_400_BAD_REQUEST,
            )

        updates: dict[str, str] = body["settings"]
        results: dict[str, dict[str, Any]] = {}
        ip = _get_client_ip(request)
        user_agent = request.META.get("HTTP_USER_AGENT", "")

        for key, raw_value in updates.items():
            if not isinstance(raw_value, str):
                return Response(
                    _format_error(
                        "invalid_setting_value",
                        f"Value for {key!r} must be a string.",
                    ),
                    status=status.HTTP_422_UNPROCESSABLE_ENTITY,
                )
            try:
                parsed = set_setting(
                    key,
                    raw_value,
                    user.id,
                    actor_ip=ip,
                    user_agent=user_agent,
                )
            except UnknownSettingKeyError:
                return Response(
                    _format_error(
                        "unknown_setting_key",
                        f"Unknown setting key: {key!r}.",
                    ),
                    status=status.HTTP_422_UNPROCESSABLE_ENTITY,
                )
            except ValueError as exc:
                return Response(
                    _format_error("invalid_setting_value", str(exc)),
                    status=status.HTTP_422_UNPROCESSABLE_ENTITY,
                )
            results[key] = {"value": parsed}

        return Response({"settings": results}, status=status.HTTP_200_OK)
