"""Shared TokenService interface for password reset, email verification,

and activation (KAN-102).

Per Doc 08 §4.5, §4.7 & Doc 02 §5.11:
- Tokens are single-use, cryptographically secure 32-byte strings.
- Only the Argon2id hash is stored in `password_reset_token.token_hash`.
- Zero leakage: raw tokens never appear in database, audit logs, or server logs.
- Default TTLs:
  - password_reset: 3600 seconds (60 minutes)
  - email_verification: 86400 seconds (24 hours)
  - activation: 259200 seconds (72 hours)
"""

import logging
import secrets
from datetime import timedelta
from typing import Any, Final

from django.contrib.auth.hashers import check_password, make_password
from django.db import transaction
from django.utils import timezone

from apps.accounts.models import PasswordResetToken, StaffUser

logger = logging.getLogger(__name__)

DEFAULT_TTLS: Final[dict[str, int]] = {
    PasswordResetToken.Purpose.PASSWORD_RESET: 3600,  # 60 minutes
    PasswordResetToken.Purpose.EMAIL_VERIFICATION: 86400,  # 24 hours
    PasswordResetToken.Purpose.ACTIVATION: 259200,  # 72 hours
}


class InvalidResetTokenError(Exception):
    """Raised when token is invalid, expired, used, or purpose mismatch."""


class TokenService:
    """Token generation, lookup, and atomic consumption service."""

    @classmethod
    def generate(
        cls,
        user: StaffUser,
        purpose: str,
        expiry_seconds: int | None = None,
    ) -> str:
        """Issue a 32-byte cryptographically secure token, store only its Argon2 hash,

        invalidate any active predecessor tokens for (user, purpose), and return the
        raw plain token.
        """
        now = timezone.now()
        ttl = (
            expiry_seconds
            if expiry_seconds is not None
            else DEFAULT_TTLS.get(purpose, 3600)
        )
        expires_at = now + timedelta(seconds=ttl)

        # Invalidate existing active tokens for this user and purpose (Doc 08 §4.5)
        PasswordResetToken.objects.filter(
            staff_user=user,
            purpose=purpose,
            used_at__isnull=True,
        ).update(used_at=now)

        raw_token = secrets.token_urlsafe(32)
        token_hash = make_password(raw_token)

        PasswordResetToken.objects.create(
            staff_user=user,
            token_hash=token_hash,
            purpose=purpose,
            expires_at=expires_at,
            used_at=None,
        )
        return raw_token

    @classmethod
    def find_valid_token(
        cls,
        token: str,
        purpose: str,
        user: StaffUser | None = None,
    ) -> PasswordResetToken | None:
        """Look up an unused, unexpired row matching token and purpose.

        Returns None if not found, expired, already used, or purpose mismatch.
        """
        if not token:
            return None

        now = timezone.now()
        qs = PasswordResetToken.objects.filter(
            purpose=purpose,
            used_at__isnull=True,
            expires_at__gt=now,
        ).select_related("staff_user")

        if user is not None:
            qs = qs.filter(staff_user=user)

        # Check candidate rows against plain token
        for candidate in qs.order_by("-created_at"):
            if check_password(token, candidate.token_hash):
                return candidate

        return None

    @classmethod
    def consume(
        cls,
        token: str,
        purpose: str,
        user: StaffUser | None = None,
        candidate_id: Any | None = None,
    ) -> StaffUser:
        """Atomically verify and consume token by setting used_at = now.

        Raises InvalidResetTokenError on any failure mode.
        """
        with transaction.atomic():
            if candidate_id is not None:
                locked = (
                    PasswordResetToken.objects.select_for_update()
                    .filter(id=candidate_id, purpose=purpose, used_at__isnull=True)
                    .first()
                )
                if locked is None or not check_password(token, locked.token_hash):
                    raise InvalidResetTokenError("Invalid or expired reset token")
            else:
                candidate = cls.find_valid_token(token, purpose, user=user)
                if candidate is None:
                    raise InvalidResetTokenError("Invalid or expired reset token")

                # Lock row for update to prevent concurrent double-consumption
                locked = (
                    PasswordResetToken.objects.select_for_update()
                    .filter(id=candidate.id, used_at__isnull=True)
                    .first()
                )
                if locked is None:
                    raise InvalidResetTokenError("Invalid or expired reset token")

            now = timezone.now()
            if locked.expires_at <= now or locked.purpose != purpose:
                raise InvalidResetTokenError("Invalid or expired reset token")

            locked.used_at = now
            locked.save(update_fields=["used_at", "updated_at"])
            return locked.staff_user

    @classmethod
    def invalidate(
        cls,
        user: StaffUser,
        purpose: str,
    ) -> int:
        """Mark all unconsumed tokens of this purpose for user as used."""
        return PasswordResetToken.objects.filter(
            staff_user=user,
            purpose=purpose,
            used_at__isnull=True,
        ).update(used_at=timezone.now())
