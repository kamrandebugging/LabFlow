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

    return True, None, None
