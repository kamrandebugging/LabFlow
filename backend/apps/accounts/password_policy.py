"""Password policy validation per Doc 08 §4.5.

Rules:
- Minimum length 12 characters, maximum 128 characters.
- No composition rules (no required digit/capital/symbol mix).
- Must not equal account email.
- Must not appear in bundled common-password blocklist (422 password_too_common).
"""

from typing import Final

from django.contrib.auth.password_validation import CommonPasswordValidator
from django.core.exceptions import ValidationError

MIN_PASSWORD_LENGTH: Final[int] = 12
MAX_PASSWORD_LENGTH: Final[int] = 128

_common_validator = CommonPasswordValidator()


def validate_password_policy(
    password: str,
    user_email: str,
) -> tuple[bool, str | None, str | None]:
    """Validate password per Doc 08 §4.5 requirements.

    Returns:
        (is_valid, error_code, error_message)
    """
    if len(password) < MIN_PASSWORD_LENGTH:
        return (
            False,
            "password_too_short",
            f"Password must be at least {MIN_PASSWORD_LENGTH} characters long",
        )

    if len(password) > MAX_PASSWORD_LENGTH:
        return (
            False,
            "password_too_long",
            f"Password cannot exceed {MAX_PASSWORD_LENGTH} characters",
        )

    clean_email = user_email.strip().lower()
    if password.strip().lower() == clean_email:
        return (
            False,
            "password_matches_email",
            "Password cannot match account email",
        )

    try:
        _common_validator.validate(password)
    except ValidationError:
        return (
            False,
            "password_too_common",
            "Password is too common and easily guessable",
        )

    if is_breached_password(password):
        return (
            False,
            "password_breached",
            "This password has appeared in a known data breach",
        )

    return True, None, None


def is_breached_password(password: str) -> bool:
    """HIBP k-anonymity check (API2 A2-6).

    Only the first five SHA-1 characters leave the process; the provider never
    sees the password or the full hash. Disabled unless ``HIBP_ENABLED`` is on,
    and fail-open on any network/provider error so a provider outage cannot
    lock every user out of password changes.
    """
    from django.conf import settings

    if not getattr(settings, "HIBP_ENABLED", False):
        return False
    import hashlib

    import requests

    digest = hashlib.sha1(password.encode("utf-8")).hexdigest().upper()
    prefix, suffix = digest[:5], digest[5:]
    url = f"https://api.pwnedpasswords.com/range/{prefix}"
    try:
        response = requests.get(url, timeout=3)
        response.raise_for_status()
    except Exception:
        return False
    for line in response.text.splitlines():
        candidate, _, _count = line.partition(":")
        if candidate.strip().upper() == suffix:
            return True
    return False
