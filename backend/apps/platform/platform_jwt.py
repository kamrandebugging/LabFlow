"""Platform JWT engine for PlatformUser auth (Doc 08 §4.3).

Platform tokens have NO 'tenant' claim — sub is platform_user UUID,
role is 'super_admin'. typ rules identical to tenant tokens.
"""

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any, Final

import jwt
from django.conf import settings

PLATFORM_JWT_ALGORITHM: Final[str] = "HS256"
PLATFORM_ACCESS_LIFETIME_SECONDS: Final[int] = 900  # 15 minutes
PLATFORM_REFRESH_LIFETIME_SECONDS: Final[int] = 7 * 86400  # 7 days
PLATFORM_REFRESH_COOKIE_NAME: Final[str] = "labflow_refresh"
PLATFORM_COOKIE_PATH: Final[str] = "/api/v1/platform/auth"


def _get_signing_key() -> str:
    key = getattr(settings, "JWT_SIGNING_KEY", None) or settings.SECRET_KEY
    return str(key)


def platform_mint_access_token(
    platform_user_id: uuid.UUID,
    role: str,
    jti: str | None = None,
    session_id: uuid.UUID | str | None = None,
) -> tuple[str, str, int]:
    """Mint a 15-minute platform access JWT.

    Returns (encoded_jwt, jti, exp_timestamp).
    No 'tenant' claim — a platform token presented to tenant endpoints is rejected
    by _authenticate_jwt_header which checks decoded.get('tenant') is not None.
    """
    token_jti = jti or str(uuid.uuid4())
    now = datetime.now(UTC)
    exp = now + timedelta(seconds=PLATFORM_ACCESS_LIFETIME_SECONDS)
    exp_int = int(exp.timestamp())

    payload: dict[str, Any] = {
        "sub": str(platform_user_id),
        "role": role,
        "jti": token_jti,
        "iat": int(now.timestamp()),
        "exp": exp_int,
        "typ": "access",
    }
    if session_id:
        payload["sid"] = str(session_id)

    token = jwt.encode(payload, _get_signing_key(), algorithm=PLATFORM_JWT_ALGORITHM)
    return token, token_jti, exp_int


def platform_mint_refresh_token(
    platform_user_id: uuid.UUID,
    family_id: uuid.UUID,
    family_expires_at: int | None = None,
    jti: str | None = None,
    session_id: uuid.UUID | str | None = None,
) -> tuple[str, str, int]:
    """Mint a 7-day platform refresh JWT with family binding.

    Returns (encoded_jwt, jti, exp_timestamp).
    """
    token_jti = jti or str(uuid.uuid4())
    now = datetime.now(UTC)
    now_int = int(now.timestamp())

    max_exp_int = now_int + PLATFORM_REFRESH_LIFETIME_SECONDS
    exp_int = min(max_exp_int, family_expires_at) if family_expires_at else max_exp_int

    payload: dict[str, Any] = {
        "sub": str(platform_user_id),
        "fid": str(family_id),
        "jti": token_jti,
        "iat": now_int,
        "exp": exp_int,
        "typ": "refresh",
    }
    if session_id:
        payload["sid"] = str(session_id)

    token = jwt.encode(payload, _get_signing_key(), algorithm=PLATFORM_JWT_ALGORITHM)
    return token, token_jti, exp_int


def platform_decode_jwt(
    raw_token: str, expected_type: str = "access"
) -> dict[str, Any]:
    """Decode and strictly validate a platform JWT (RFC 8725).

    Raises ValueError on any validation failure.
    """
    try:
        payload = jwt.decode(
            raw_token,
            _get_signing_key(),
            algorithms=[PLATFORM_JWT_ALGORITHM],
            options={"require": ["sub", "jti", "iat", "exp", "typ"]},
        )
    except jwt.PyJWTError as exc:
        raise ValueError(f"Invalid platform JWT: {exc}") from exc

    if payload.get("typ") != expected_type:
        raise ValueError(
            f"Invalid token typ: expected {expected_type}, got {payload.get('typ')}"
        )

    # Reject tenant-scoped tokens — platform tokens have no 'tenant' claim
    if "tenant" in payload:
        raise ValueError("Token carries 'tenant' claim; not a platform token")

    return payload
