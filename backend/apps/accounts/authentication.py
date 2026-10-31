"""DRF JWT Authentication Backend for LabFlow (Doc 08 §4.3 & §4.6).

Validates Bearer access JWTs, checks token denylist, checks user revocation marker,
and scopes staff user lookup to current tenant schema.
"""

import uuid
from typing import Any

from rest_framework import authentication, exceptions

from apps.accounts.jwt_engine import decode_jwt
from apps.accounts.models import StaffUser
from apps.accounts.session_registry import (
    get_user_revocation_marker,
    is_access_jti_denylisted,
    is_session_revoked,
)


class JWTAuthentication(authentication.BaseAuthentication):
    """DRF Authentication backend validating HS256 JWT access tokens."""

    keyword = "Bearer"

    def authenticate(self, request: Any) -> tuple[StaffUser, dict[str, Any]] | None:
        auth_header = authentication.get_authorization_header(request).decode("utf-8")
        if not auth_header:
            return None

        parts = auth_header.split()
        if len(parts) != 2 or parts[0].lower() != self.keyword.lower():
            return None

        raw_token = parts[1]
        try:
            payload = decode_jwt(raw_token, expected_type="access")
        except ValueError as exc:
            raise exceptions.AuthenticationFailed(str(exc)) from exc

        jti = payload.get("jti")
        if jti and is_access_jti_denylisted(jti):
            raise exceptions.AuthenticationFailed("Token has been revoked")

        user_id_str = payload.get("sub")
        if not user_id_str:
            raise exceptions.AuthenticationFailed("Invalid token: missing subject")

        try:
            user_id = uuid.UUID(user_id_str)
        except ValueError as exc:
            raise exceptions.AuthenticationFailed(
                "Invalid user identifier in token"
            ) from exc

        # Check per-user revocation marker (auth:revoked_before:<user_id>)
        marker = get_user_revocation_marker(user_id)
        if marker and payload.get("iat", 0) < marker:
            raise exceptions.AuthenticationFailed("Session has been revoked")

        # Check per-session revocation marker
        sid = payload.get("sid")
        if sid and is_session_revoked(sid):
            raise exceptions.AuthenticationFailed("Session has been revoked")

        # Validate token tenant against request tenant schema (SE-01 isolation)
        req_tenant = getattr(getattr(request, "tenant", None), "schema_name", None)
        token_tenant = payload.get("tenant")
        if req_tenant and token_tenant and token_tenant != req_tenant:
            raise exceptions.AuthenticationFailed("Token tenant mismatch")

        # Resolve user in active tenant schema
        tenant_to_use = req_tenant or token_tenant
        if tenant_to_use:
            from django_tenants.utils import schema_context

            with schema_context(tenant_to_use):
                user = StaffUser.objects.filter(id=user_id, is_active=True).first()
        else:
            user = StaffUser.objects.filter(id=user_id, is_active=True).first()
        if not user:
            raise exceptions.AuthenticationFailed("User not found or deactivated")

        return user, payload

    def authenticate_header(self, request: Any) -> str:
        return f'{self.keyword} realm="api"'
