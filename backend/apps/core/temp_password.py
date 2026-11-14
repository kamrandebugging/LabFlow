"""The single temporary-password generator (Doc 08 §4.4).

Every one-time credential — platform provisioning, Platform Owner reset, and
Owner/Manager-issued staff resets — uses this format so operators and support
scripts only ever see one shape:

``LBF-XXXX-XX#`` (12 chars: uppercase, digits, two separators)

The value is generated with ``secrets`` (CSPRNG), returned exactly once, and
stored only as an Argon2 hash. Online guessing is bounded by the login
throttle/lockout and the 24-hour expiry.
"""

from __future__ import annotations

import secrets

TEMP_PASSWORD_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


def generate_temp_password() -> str:
    """Return a CSPRNG ``LBF-XXXX-XX#`` temporary password."""
    part1 = "".join(secrets.choice(TEMP_PASSWORD_ALPHABET) for _ in range(4))
    part2 = "".join(secrets.choice(TEMP_PASSWORD_ALPHABET) for _ in range(2))
    return f"LBF-{part1}-{part2}#"
