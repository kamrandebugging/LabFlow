"""RFC 8725 compliant JWT Engine for LabFlow (Doc 08 §4.3).

Access tokens: 15 minutes (900s), HS256 algorithm allowlist of exactly one.
Refresh tokens: 7 days, fid (family id), typ="refresh", family cap enforced.
"""

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any, Final

import jwt
from django.conf import settings

JWT_ALGORITHM: Final[str] = "HS256"
ACCESS_TOKEN_LIFETIME_SECONDS: Final[int] = 900  # 15 minutes
REFRESH_TOKEN_LIFETIME_SECONDS: Final[int] = 7 * 86400  # 7 days


def get_jwt_signing_key() -> str:
    key = getattr(settings, "JWT_SIGNING_KEY", None) or settings.SECRET_KEY
    return str(key)


def mint_access_token(
    staff_user_id: uuid.UUID,
    tenant_slug: str,
    role: str,
    jti: str | None = None,
    session_id: uuid.UUID | str | None = None,
) -> tuple[str, str, int]:
    """Mint a 15-minute access JWT (Doc 08 §4.3).

    Returns (encoded_jwt, jti, exp_timestamp).
    """
    token_jti = jti or str(uuid.uuid4())
    now = datetime.now(UTC)
    exp = now + timedelta(seconds=ACCESS_TOKEN_LIFETIME_SECONDS)
    exp_int = int(exp.timestamp())

    payload = {
        "sub": str(staff_user_id),
        "tenant": tenant_slug,
        "role": role,
        "jti": token_jti,
        "iat": int(now.timestamp()),
        "exp": exp_int,
        "typ": "access",
    }
    if session_id:
        payload["sid"] = str(session_id)

    token = jwt.encode(payload, get_jwt_signing_key(), algorithm=JWT_ALGORITHM)
    return token, token_jti, exp_int


def mint_refresh_token(
    staff_user_id: uuid.UUID,
    tenant_slug: str,
    family_id: uuid.UUID,
    family_expires_at: int | None = None,
    jti: str | None = None,
    session_id: uuid.UUID | str | None = None,
) -> tuple[str, str, int]:
    """Mint a 7-day refresh JWT with family binding (Doc 08 §4.3).

    Returns (encoded_jwt, jti, exp_timestamp).
    """
    token_jti = jti or str(uuid.uuid4())
    now = datetime.now(UTC)
    now_int = int(now.timestamp())

    # Absolute family cap: refresh token cannot exceed original family exp
    max_exp_int = now_int + REFRESH_TOKEN_LIFETIME_SECONDS
    exp_int = min(max_exp_int, family_expires_at) if family_expires_at else max_exp_int

    payload = {
        "sub": str(staff_user_id),
        "tenant": tenant_slug,
        "fid": str(family_id),
        "jti": token_jti,
        "iat": now_int,
        "exp": exp_int,
        "typ": "refresh",
    }
    if session_id:
        payload["sid"] = str(session_id)

    token = jwt.encode(payload, get_jwt_signing_key(), algorithm=JWT_ALGORITHM)
    return token, token_jti, exp_int


def decode_jwt(
    raw_token: str,
    expected_type: str = "access",
) -> dict[str, Any]:
    """Decode and strictly validate JWT per RFC 8725 (Doc 08 §4.3).

    Enforces algorithm allowlist of exactly one (HS256), signature, and exp.
    """
    try:
        payload = jwt.decode(
            raw_token,
            get_jwt_signing_key(),
            algorithms=[JWT_ALGORITHM],  # RFC 8725: single algorithm allowlist
            options={"require": ["sub", "jti", "iat", "exp", "typ"]},
        )
    except jwt.PyJWTError as exc:
        raise ValueError(f"Invalid JWT: {exc}") from exc

    if payload.get("typ") != expected_type:
        raise ValueError(
            f"Invalid token typ: expected {expected_type}, got {payload.get('typ')}"
        )

    return payload
