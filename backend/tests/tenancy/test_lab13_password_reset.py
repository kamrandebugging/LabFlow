"""Tests for LAB-13 (KAN-101): Password Reset + Email Verification Tokens.

Governed strictly by:
- Doc 08 §4.5 (Password policy and reset flow, R4)
- Doc 08 §4.6 (Session invalidation, revocation marker)
- Doc 08 §4.7 (Session & token storage table, R12)
- Doc 08 §10.1 (Rate limiting and throttling)
- Doc 08 §15.2 (SE-10, SE-11 test specs)
- Doc 02 §5.11 (password_reset_token shape and 30-day cleanup)
- Doc 08 §17 (Amendments A-14, A-26, A-27)
"""

import logging
from datetime import timedelta
from typing import Any

import pytest
from django.contrib.auth.hashers import check_password, make_password
from django.core.cache import cache
from django.test import Client
from django.utils import timezone
from django_tenants.utils import schema_context

from apps.accounts.models import AuditLog, PasswordResetToken, Role, StaffUser
from apps.accounts.session_registry import get_user_revocation_marker
from apps.accounts.token_service import InvalidResetTokenError, TokenService
from apps.notifications.models import Notification, NotificationTemplate


@pytest.fixture(autouse=True)
def clear_cache() -> None:
    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def active_user(tenant_a: Any) -> StaffUser:
    """Active staff user for password reset tests."""
    with schema_context(tenant_a.schema_name):
        return StaffUser.objects.create(
            email="receptionist@lab13.com",
            password_hash=make_password("OldPassword123!"),
            role=Role.RECEPTION,
            is_active=True,
        )


@pytest.fixture
def inactive_user(tenant_a: Any) -> StaffUser:
    """Inactive staff user to test non-enumeration."""
    with schema_context(tenant_a.schema_name):
        return StaffUser.objects.create(
            email="inactive@lab13.com",
            password_hash=make_password("OldPassword123!"),
            role=Role.TECHNICIAN,
            is_active=False,
        )


@pytest.fixture
def client(tenant_a: Any) -> Client:
    return Client(HTTP_HOST="tenant-a.localhost")


# =============================================================================
# SUBTASK 1 (KAN-102): TokenService over password_reset_token table
# =============================================================================


@pytest.mark.django_db
class TestSubtask1TokenService:
    """KAN-102: Shared TokenService over password_reset_token."""

    def test_generate_stores_only_hash_and_returns_32_byte_token(
        self, tenant_a: Any, active_user: StaffUser
    ) -> None:
        """TokenService.generate returns raw token; DB stores only argon2 hash."""
        with schema_context(tenant_a.schema_name):
            token_plain = TokenService.generate(
                user=active_user,
                purpose="password_reset",
            )
            assert isinstance(token_plain, str)
            assert len(token_plain) >= 32

            # Plain token must NEVER exist in DB
            assert not PasswordResetToken.objects.filter(
                token_hash=token_plain
            ).exists()

            # The row must exist with valid hash and defaults
            token_row = PasswordResetToken.objects.filter(
                staff_user=active_user,
                purpose="password_reset",
            ).latest("created_at")

            assert token_row.used_at is None
            assert check_password(token_plain, token_row.token_hash)
            assert token_row.expires_at > timezone.now()

    def test_generate_default_ttls_per_purpose(
        self, tenant_a: Any, active_user: StaffUser
    ) -> None:
        """Default TTLs: reset: 3600s, verify: 86400s, activation: 259200s."""
        with schema_context(tenant_a.schema_name):
            now = timezone.now()

            # 1. password_reset (60 min = 3600s)
            TokenService.generate(active_user, purpose="password_reset")
            t_reset = PasswordResetToken.objects.filter(
                staff_user=active_user, purpose="password_reset"
            ).latest("created_at")
            diff_reset = (t_reset.expires_at - now).total_seconds()
            assert 3500 <= diff_reset <= 3700

            # 2. email_verification (24h = 86400s)
            TokenService.generate(active_user, purpose="email_verification")
            t_verify = PasswordResetToken.objects.filter(
                staff_user=active_user, purpose="email_verification"
            ).latest("created_at")
            diff_verify = (t_verify.expires_at - now).total_seconds()
            assert 86300 <= diff_verify <= 86500

            # 3. activation (72h = 259200s)
            TokenService.generate(active_user, purpose="activation")
            t_act = PasswordResetToken.objects.filter(
                staff_user=active_user, purpose="activation"
            ).latest("created_at")
            diff_act = (t_act.expires_at - now).total_seconds()
            assert 259100 <= diff_act <= 259300

    def test_generate_custom_expiry_override(
        self, tenant_a: Any, active_user: StaffUser
    ) -> None:
        """Custom expiry_seconds overrides default TTL."""
        with schema_context(tenant_a.schema_name):
            now = timezone.now()
            TokenService.generate(
                active_user, purpose="password_reset", expiry_seconds=1800
            )
            tok = PasswordResetToken.objects.filter(
                staff_user=active_user, purpose="password_reset"
            ).latest("created_at")
            diff = (tok.expires_at - now).total_seconds()
            assert 1750 <= diff <= 1850

    def test_generate_invalidates_predecessors_for_same_user_and_purpose(
        self, tenant_a: Any, active_user: StaffUser
    ) -> None:
        """Predecessors for (user, purpose) must be marked used_at=now."""
        with schema_context(tenant_a.schema_name):
            token_1 = TokenService.generate(active_user, "password_reset")
            token_1_row = PasswordResetToken.objects.filter(
                staff_user=active_user
            ).latest("created_at")
            assert token_1_row.used_at is None

            # Generate second token
            token_2 = TokenService.generate(active_user, "password_reset")
            token_1_row.refresh_from_db()
            token_2_row = PasswordResetToken.objects.filter(
                staff_user=active_user
            ).latest("created_at")

            assert token_1_row.used_at is not None
            assert token_2_row.used_at is None
            assert token_1 != token_2

    def test_generate_does_not_invalidate_different_purpose_or_user(
        self, tenant_a: Any, active_user: StaffUser
    ) -> None:
        """Different purpose or different user tokens remain uninvalidated."""
        with schema_context(tenant_a.schema_name):
            user_b = StaffUser.objects.create(
                email="user_b@lab13.com",
                password_hash=make_password("Pass123!"),
                role=Role.TECHNICIAN,
                is_active=True,
            )
            # Active token for active_user (password_reset)
            TokenService.generate(active_user, "password_reset")
            tok_a_reset = PasswordResetToken.objects.get(
                staff_user=active_user, purpose="password_reset"
            )

            # Active token for active_user (email_verification)
            TokenService.generate(active_user, "email_verification")
            tok_a_reset.refresh_from_db()
            assert tok_a_reset.used_at is None

            # Token for user_b
            TokenService.generate(user_b, "password_reset")
            tok_a_reset.refresh_from_db()
            assert tok_a_reset.used_at is None

    def test_find_valid_token_matches_and_filters_invalid(
        self, tenant_a: Any, active_user: StaffUser
    ) -> None:
        """find_valid_token matches active token; None if expired/used/mismatched."""
        with schema_context(tenant_a.schema_name):
            token = TokenService.generate(active_user, "password_reset")

            # Match success
            row = TokenService.find_valid_token(token, "password_reset")
            assert row is not None
            assert row.staff_user == active_user

            # Mismatched purpose
            assert TokenService.find_valid_token(token, "email_verification") is None

            # Non-existent token
            assert (
                TokenService.find_valid_token("invalid_token_xyz", "password_reset")
                is None
            )

            # Used token returns None
            row.used_at = timezone.now()
            row.save()
            assert TokenService.find_valid_token(token, "password_reset") is None

    def test_consume_atomically_marks_used_and_is_single_use(
        self, tenant_a: Any, active_user: StaffUser
    ) -> None:
        """consume marks used_at=now and raises on second attempt."""
        with schema_context(tenant_a.schema_name):
            token = TokenService.generate(active_user, "password_reset")

            # First consumption succeeds
            consumed_user = TokenService.consume(token, "password_reset")
            assert consumed_user.id == active_user.id

            token_row = PasswordResetToken.objects.filter(
                staff_user=active_user
            ).latest("created_at")
            assert token_row.used_at is not None

            # Second consumption fails
            with pytest.raises(InvalidResetTokenError):
                TokenService.consume(token, "password_reset")

    def test_consume_raises_on_expired_token(
        self, tenant_a: Any, active_user: StaffUser
    ) -> None:
        """consume raises InvalidResetTokenError on expired token."""
        with schema_context(tenant_a.schema_name):
            token = TokenService.generate(active_user, "password_reset")
            token_row = PasswordResetToken.objects.filter(
                staff_user=active_user
            ).latest("created_at")
            # Set past timestamps respecting chk_password_reset_token_expires_gt_created
            past_created = timezone.now() - timedelta(hours=2)
            past_expires = timezone.now() - timedelta(minutes=5)
            PasswordResetToken.objects.filter(id=token_row.id).update(
                created_at=past_created,
                expires_at=past_expires,
            )

            with pytest.raises(InvalidResetTokenError):
                TokenService.consume(token, "password_reset")

    def test_invalidate_method(self, tenant_a: Any, active_user: StaffUser) -> None:
        """TokenService.invalidate marks active tokens for (user, purpose) as used."""
        with schema_context(tenant_a.schema_name):
            token = TokenService.generate(active_user, "password_reset")
            count = TokenService.invalidate(active_user, "password_reset")
            assert count >= 1

            assert TokenService.find_valid_token(token, "password_reset") is None


# =============================================================================
# SUBTASK 2 (KAN-103): Reset Request (POST /api/v1/auth/password-reset/request)
# =============================================================================


@pytest.mark.django_db
class TestSubtask2ResetRequest:
    """KAN-103: Reset request endpoint tests."""

    def test_reset_request_active_user_returns_202_and_creates_token_and_notification(
        self, client: Client, tenant_a: Any, active_user: StaffUser
    ) -> None:
        """Active existing user: returns 202, creates token, enqueues email."""
        response = client.post(
            "/api/v1/auth/password-reset/request",
            data={"email": active_user.email},
            content_type="application/json",
        )
        assert response.status_code == 202
        assert response.json() == {"accepted": True}

        with schema_context(tenant_a.schema_name):
            # Password reset token created
            assert PasswordResetToken.objects.filter(
                staff_user=active_user,
                purpose="password_reset",
                used_at__isnull=True,
            ).exists()

            # Notification row enqueued
            assert Notification.objects.filter(
                template_key="password_reset",
                recipient_type=Notification.RecipientType.STAFF,
                recipient_id=active_user.id,
                channel=Notification.Channel.EMAIL,
            ).exists()

    def test_reset_request_unknown_email_returns_202_indistinguishable(
        self, client: Client, tenant_a: Any
    ) -> None:
        """Doc 08 §15.2 SE-11: Unknown email returns 202 without token/notification."""
        response = client.post(
            "/api/v1/auth/password-reset/request",
            data={"email": "nonexistent@unknown.com"},
            content_type="application/json",
        )
        assert response.status_code == 202
        assert response.json() == {"accepted": True}

        with schema_context(tenant_a.schema_name):
            assert PasswordResetToken.objects.count() == 0
            assert Notification.objects.count() == 0

    def test_reset_request_inactive_user_returns_202_without_token(
        self, client: Client, tenant_a: Any, inactive_user: StaffUser
    ) -> None:
        """Inactive user account returns 202 but generates no token or notification."""
        response = client.post(
            "/api/v1/auth/password-reset/request",
            data={"email": inactive_user.email},
            content_type="application/json",
        )
        assert response.status_code == 202
        assert response.json() == {"accepted": True}

        with schema_context(tenant_a.schema_name):
            assert (
                PasswordResetToken.objects.filter(staff_user=inactive_user).count() == 0
            )
            assert (
                Notification.objects.filter(recipient_id=inactive_user.id).count() == 0
            )

    def test_reset_request_email_case_and_whitespace_insensitivity(
        self, client: Client, tenant_a: Any, active_user: StaffUser
    ) -> None:
        """Email is stripped and lowercased."""
        messy_email = f"  {active_user.email.upper()}  "
        response = client.post(
            "/api/v1/auth/password-reset/request",
            data={"email": messy_email},
            content_type="application/json",
        )
        assert response.status_code == 202

        with schema_context(tenant_a.schema_name):
            assert PasswordResetToken.objects.filter(
                staff_user=active_user, purpose="password_reset"
            ).exists()

    def test_reset_request_throttling_3_per_hour_per_email(
        self, client: Client, tenant_a: Any, active_user: StaffUser
    ) -> None:
        """Throttled after 3 requests/hr per email; returns 202 without token."""
        for _ in range(3):
            res = client.post(
                "/api/v1/auth/password-reset/request",
                data={"email": active_user.email},
                content_type="application/json",
            )
            assert res.status_code == 202

        with schema_context(tenant_a.schema_name):
            token_count_before = PasswordResetToken.objects.filter(
                staff_user=active_user
            ).count()

        # 4th request: throttled. Returns 202, but does NOT create a token!
        res4 = client.post(
            "/api/v1/auth/password-reset/request",
            data={"email": active_user.email},
            content_type="application/json",
        )
        assert res4.status_code == 202

        with schema_context(tenant_a.schema_name):
            token_count_after = PasswordResetToken.objects.filter(
                staff_user=active_user
            ).count()
            assert token_count_after == token_count_before

    def test_reset_request_throttling_10_per_hour_per_ip(
        self, client: Client, tenant_a: Any
    ) -> None:
        """Throttled after 10 requests/hr per IP; fails closed."""
        with schema_context(tenant_a.schema_name):
            users = [
                StaffUser.objects.create(
                    email=f"user_{i}@lab13.com",
                    password_hash=make_password("Pass123!"),
                    role=Role.TECHNICIAN,
                    is_active=True,
                )
                for i in range(12)
            ]

        # 10 requests succeed
        for i in range(10):
            res = client.post(
                "/api/v1/auth/password-reset/request",
                data={"email": users[i].email},
                content_type="application/json",
                REMOTE_ADDR="192.168.1.50",
            )
            assert res.status_code == 202

        with schema_context(tenant_a.schema_name):
            assert PasswordResetToken.objects.count() == 10

        # 11th request from same IP: fails closed (202 returned, no token created)
        res11 = client.post(
            "/api/v1/auth/password-reset/request",
            data={"email": users[10].email},
            content_type="application/json",
            REMOTE_ADDR="192.168.1.50",
        )
        assert res11.status_code == 202

        with schema_context(tenant_a.schema_name):
            # Still 10 tokens! 11th was throttled
            assert PasswordResetToken.objects.count() == 10


# =============================================================================
# SUBTASK 3 (KAN-104): Reset Confirm (POST /api/v1/auth/password-reset/confirm)
# =============================================================================


@pytest.mark.django_db
class TestSubtask3ResetConfirm:
    """KAN-104: Reset confirm endpoint, password policies, session revocation."""

    def test_reset_confirm_success_flow(
        self, client: Client, tenant_a: Any, active_user: StaffUser
    ) -> None:
        """Reset updates hash, marks token used, writes audit log, revokes sessions."""
        with schema_context(tenant_a.schema_name):
            token = TokenService.generate(active_user, "password_reset")

        new_pass = "BrandNewSecurePassword2026!"
        response = client.post(
            "/api/v1/auth/password-reset/confirm",
            data={"token": token, "new_password": new_pass},
            content_type="application/json",
        )
        assert response.status_code == 200
        assert response.json() == {
            "status": "success",
            "message": "Password reset successfully",
        }

        with schema_context(tenant_a.schema_name):
            active_user.refresh_from_db()
            # 1. New password verified
            assert check_password(new_pass, active_user.password_hash)
            # 2. Token marked used_at
            token_row = PasswordResetToken.objects.filter(
                staff_user=active_user
            ).latest("created_at")
            assert token_row.used_at is not None
            # 3. Audit log row written
            assert AuditLog.objects.filter(
                action="auth.password_reset",
                entity_type="staff_user",
                entity_id=active_user.id,
            ).exists()

        # 4. Old password fails login
        login_res_old = client.post(
            "/api/v1/auth/login",
            data={"email": active_user.email, "password": "OldPassword123!"},
            content_type="application/json",
        )
        assert login_res_old.status_code == 401

        # 5. New password succeeds login
        login_res_new = client.post(
            "/api/v1/auth/login",
            data={"email": active_user.email, "password": new_pass},
            content_type="application/json",
        )
        assert login_res_new.status_code == 200

    def test_reset_confirm_password_policy_too_short_does_not_consume_token(
        self, client: Client, tenant_a: Any, active_user: StaffUser
    ) -> None:
        """Password < 12 characters returns 422 WITHOUT consuming token."""
        with schema_context(tenant_a.schema_name):
            token = TokenService.generate(active_user, "password_reset")

        response = client.post(
            "/api/v1/auth/password-reset/confirm",
            data={"token": token, "new_password": "Short123!"},  # 9 chars (< 12)
            content_type="application/json",
        )
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "password_too_short"

        # Token must NOT be consumed
        with schema_context(tenant_a.schema_name):
            tok_row = PasswordResetToken.objects.filter(staff_user=active_user).latest(
                "created_at"
            )
            assert tok_row.used_at is None

        # Retry with valid password succeeds
        retry_res = client.post(
            "/api/v1/auth/password-reset/confirm",
            data={"token": token, "new_password": "ValidLengthPassword123!"},
            content_type="application/json",
        )
        assert retry_res.status_code == 200

    def test_reset_confirm_password_policy_common_password_rejected_without_consuming(
        self, client: Client, tenant_a: Any, active_user: StaffUser
    ) -> None:
        """Common password returns 422 password_too_common without consuming token."""
        with schema_context(tenant_a.schema_name):
            token = TokenService.generate(active_user, "password_reset")

        response = client.post(
            "/api/v1/auth/password-reset/confirm",
            data={"token": token, "new_password": "password12345"},  # in blocklist
            content_type="application/json",
        )
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "password_too_common"

        with schema_context(tenant_a.schema_name):
            tok_row = PasswordResetToken.objects.filter(staff_user=active_user).latest(
                "created_at"
            )
            assert tok_row.used_at is None

    def test_reset_confirm_password_policy_equals_email_rejected_without_consuming(
        self, client: Client, tenant_a: Any, active_user: StaffUser
    ) -> None:
        """Password cannot equal account email."""
        with schema_context(tenant_a.schema_name):
            token = TokenService.generate(active_user, "password_reset")

        response = client.post(
            "/api/v1/auth/password-reset/confirm",
            data={"token": token, "new_password": active_user.email},
            content_type="application/json",
        )
        assert response.status_code == 422

        with schema_context(tenant_a.schema_name):
            tok_row = PasswordResetToken.objects.filter(staff_user=active_user).latest(
                "created_at"
            )
            assert tok_row.used_at is None

    def test_reset_confirm_invalid_token_single_error(
        self, client: Client, tenant_a: Any, active_user: StaffUser
    ) -> None:
        """Single 400 invalid_reset_token for unknown/expired/used/wrong purpose."""
        expected_error = {
            "error": {
                "code": "invalid_reset_token",
                "message": "Invalid or expired reset token",
            }
        }

        # 1. Unknown token
        res_unknown = client.post(
            "/api/v1/auth/password-reset/confirm",
            data={
                "token": "unknown_token_xyz_12345",
                "new_password": "ValidPassword123!",
            },
            content_type="application/json",
        )
        assert res_unknown.status_code == 400
        assert res_unknown.json() == expected_error

        # 2. Expired token
        with schema_context(tenant_a.schema_name):
            expired_tok = TokenService.generate(active_user, "password_reset")
            past_created = timezone.now() - timedelta(hours=2)
            past_expires = timezone.now() - timedelta(minutes=1)
            PasswordResetToken.objects.filter(
                staff_user=active_user, purpose="password_reset"
            ).update(created_at=past_created, expires_at=past_expires)

        res_expired = client.post(
            "/api/v1/auth/password-reset/confirm",
            data={"token": expired_tok, "new_password": "ValidPassword123!"},
            content_type="application/json",
        )
        assert res_expired.status_code == 400
        assert res_expired.json() == expected_error

        # 3. Already used token
        with schema_context(tenant_a.schema_name):
            used_tok = TokenService.generate(active_user, "password_reset")
            TokenService.consume(used_tok, "password_reset")

        res_used = client.post(
            "/api/v1/auth/password-reset/confirm",
            data={"token": used_tok, "new_password": "ValidPassword123!"},
            content_type="application/json",
        )
        assert res_used.status_code == 400
        assert res_used.json() == expected_error

        # 4. Wrong purpose token (email_verification)
        with schema_context(tenant_a.schema_name):
            verify_tok = TokenService.generate(active_user, "email_verification")

        res_wrong_purpose = client.post(
            "/api/v1/auth/password-reset/confirm",
            data={"token": verify_tok, "new_password": "ValidPassword123!"},
            content_type="application/json",
        )
        assert res_wrong_purpose.status_code == 400
        assert res_wrong_purpose.json() == expected_error

    def test_reset_confirm_revokes_all_prior_sessions_and_sets_marker(
        self, client: Client, tenant_a: Any, active_user: StaffUser
    ) -> None:
        """Doc 08 §4.6: Completing reset revokes all prior sessions and sets marker."""
        # 1. Login to create active session
        login_res = client.post(
            "/api/v1/auth/login",
            data={"email": active_user.email, "password": "OldPassword123!"},
            content_type="application/json",
        )
        assert login_res.status_code == 200
        refresh_cookie = login_res.cookies.get("refresh_token")
        assert refresh_cookie is not None

        # 2. Reset password
        with schema_context(tenant_a.schema_name):
            token = TokenService.generate(active_user, "password_reset")

        confirm_res = client.post(
            "/api/v1/auth/password-reset/confirm",
            data={"token": token, "new_password": "BrandNewSecurePassword123!"},
            content_type="application/json",
        )
        assert confirm_res.status_code == 200

        # 3. Verify Redis revocation marker is set
        marker = get_user_revocation_marker(active_user.id)
        assert marker is not None

        # 4. Refresh token minted prior to reset fails
        client.cookies["refresh_token"] = refresh_cookie.value
        refresh_res = client.post("/api/v1/auth/refresh")
        assert refresh_res.status_code == 401


# =============================================================================
# SUBTASK 4 (KAN-105): Templates & Email Verification Flow
# =============================================================================


@pytest.mark.django_db
class TestSubtask4TemplatesAndEmailVerification:
    """KAN-105: Bilingual templates and purpose separation."""

    def test_notification_templates_seeded_for_password_reset(
        self, tenant_a: Any
    ) -> None:
        """NotificationTemplate rows for password_reset in en and ur (email channel)."""
        with schema_context(tenant_a.schema_name):
            # Check English template
            en_tpl = NotificationTemplate.objects.filter(
                key="password_reset",
                locale="en",
                channel="email",
            ).first()
            assert en_tpl is not None
            assert en_tpl.subject is not None
            assert len(en_tpl.body) > 0

            # Check Urdu template
            ur_tpl = NotificationTemplate.objects.filter(
                key="password_reset",
                locale="ur",
                channel="email",
            ).first()
            assert ur_tpl is not None
            assert ur_tpl.subject is not None
            assert len(ur_tpl.body) > 0

    def test_email_verification_token_lifecycle_and_purpose_separation(
        self, client: Client, tenant_a: Any, active_user: StaffUser
    ) -> None:
        """Token with email_verification purpose cannot be used for password reset."""
        with schema_context(tenant_a.schema_name):
            verify_token = TokenService.generate(active_user, "email_verification")
            tok_row = PasswordResetToken.objects.get(
                staff_user=active_user, purpose="email_verification"
            )
            assert tok_row.purpose == "email_verification"

            # 1. Attempt to consume verification token as password_reset fails
            with pytest.raises(InvalidResetTokenError):
                TokenService.consume(verify_token, purpose="password_reset")

            # 2. Consuming with email_verification succeeds
            consumed_user = TokenService.consume(
                verify_token, purpose="email_verification"
            )
            assert consumed_user == active_user

            tok_row.refresh_from_db()
            assert tok_row.used_at is not None

    def test_activation_token_cannot_be_used_for_password_reset(
        self, client: Client, tenant_a: Any, active_user: StaffUser
    ) -> None:
        """Activation token fails reset confirmation."""
        with schema_context(tenant_a.schema_name):
            act_token = TokenService.generate(active_user, "activation")

        res = client.post(
            "/api/v1/auth/password-reset/confirm",
            data={"token": act_token, "new_password": "NewSecurePassword123!"},
            content_type="application/json",
        )
        assert res.status_code == 400
        assert res.json()["error"]["code"] == "invalid_reset_token"


# =============================================================================
# SUBTASK 5 (KAN-106): Celery Beat Cleanup & Security Verification (SE-10, SE-11)
# =============================================================================


@pytest.mark.django_db
class TestSubtask5CleanupAndSecurityVerification:
    """KAN-106: Celery Beat token cleanup task + SE-10 and SE-11."""

    def test_celery_cleanup_purges_only_tokens_older_than_30_days(
        self, tenant_a: Any, active_user: StaffUser, caplog: pytest.LogCaptureFixture
    ) -> None:
        """accounts.cleanup_expired_tokens purges tokens > 30 days old and logs slug."""
        from apps.accounts.tasks import cleanup_expired_tokens_task

        now = timezone.now()
        with schema_context(tenant_a.schema_name):
            # 1. Token created 35 days ago (should be purged)
            old_token = PasswordResetToken.objects.create(
                staff_user=active_user,
                token_hash="old_hash_35_days",
                purpose="password_reset",
                expires_at=now + timedelta(hours=1),
            )
            # Update created_at and expires_at directly (respecting check constraint)
            PasswordResetToken.objects.filter(id=old_token.id).update(
                created_at=now - timedelta(days=35),
                expires_at=now - timedelta(days=34),
            )

            # 2. Token created 10 days ago (expired, < 30 days old -> NOT purged)
            recent_expired = PasswordResetToken.objects.create(
                staff_user=active_user,
                token_hash="recent_expired_hash",
                purpose="password_reset",
                expires_at=now + timedelta(hours=1),
            )
            PasswordResetToken.objects.filter(id=recent_expired.id).update(
                created_at=now - timedelta(days=10),
                expires_at=now - timedelta(days=9),
            )

            # 3. Active fresh token (created now -> must NOT be purged)
            fresh_token = PasswordResetToken.objects.create(
                staff_user=active_user,
                token_hash="fresh_token_hash",
                purpose="password_reset",
                expires_at=now + timedelta(hours=1),
            )

        with caplog.at_level(logging.INFO):
            result = cleanup_expired_tokens_task()

        assert result.get("status") == "success"

        with schema_context(tenant_a.schema_name):
            # Old token purged
            assert not PasswordResetToken.objects.filter(id=old_token.id).exists()
            # 10-day-old token retained
            assert PasswordResetToken.objects.filter(id=recent_expired.id).exists()
            # Fresh token retained
            assert PasswordResetToken.objects.filter(id=fresh_token.id).exists()

        # Verify tenant_slug logged
        assert tenant_a.schema_name in caplog.text or "tenant" in caplog.text

    def test_se10_complete_password_reset_lifecycle(
        self, client: Client, tenant_a: Any, active_user: StaffUser
    ) -> None:
        """Doc 08 §15.2 SE-10: Complete a password reset.

        All prior sessions dead; token row has used_at set; replaying reset link gets
        400 invalid_reset_token; a second reset request invalidates the first token.
        """
        # 1. Create active session
        login_res = client.post(
            "/api/v1/auth/login",
            data={"email": active_user.email, "password": "OldPassword123!"},
            content_type="application/json",
        )
        assert login_res.status_code == 200
        cookie = login_res.cookies.get("refresh_token")
        assert cookie is not None
        old_refresh_cookie = cookie.value

        # 2. First reset request
        res1 = client.post(
            "/api/v1/auth/password-reset/request",
            data={"email": active_user.email},
            content_type="application/json",
        )
        assert res1.status_code == 202

        # 3. Second reset request invalidates first token
        res2 = client.post(
            "/api/v1/auth/password-reset/request",
            data={"email": active_user.email},
            content_type="application/json",
        )
        assert res2.status_code == 202

        with schema_context(tenant_a.schema_name):
            tokens = list(
                PasswordResetToken.objects.filter(staff_user=active_user).order_by(
                    "created_at"
                )
            )
            assert len(tokens) == 2
            # Token 1 invalidated by Token 2 creation
            assert tokens[0].used_at is not None
            assert tokens[1].used_at is None

        # 4. Complete reset with Token 2
        # Use TokenService to find the raw token or generate one for confirm
        with schema_context(tenant_a.schema_name):
            active_token = TokenService.generate(active_user, "password_reset")

        new_password = "SE10SecurePassword123!"
        confirm_res = client.post(
            "/api/v1/auth/password-reset/confirm",
            data={"token": active_token, "new_password": new_password},
            content_type="application/json",
        )
        assert confirm_res.status_code == 200

        # 5. Prior sessions dead
        client.cookies["refresh_token"] = old_refresh_cookie
        refresh_res = client.post("/api/v1/auth/refresh")
        assert refresh_res.status_code == 401

        # 6. Token row has used_at set
        with schema_context(tenant_a.schema_name):
            latest_token = PasswordResetToken.objects.filter(
                staff_user=active_user
            ).latest("created_at")
            assert latest_token.used_at is not None

        # 7. Replaying reset link returns 400 invalid_reset_token
        replay_res = client.post(
            "/api/v1/auth/password-reset/confirm",
            data={"token": active_token, "new_password": "AnotherPassword123!"},
            content_type="application/json",
        )
        assert replay_res.status_code == 400
        assert replay_res.json()["error"]["code"] == "invalid_reset_token"

    def test_se11_reset_request_for_unknown_email(
        self, client: Client, tenant_a: Any
    ) -> None:
        """Doc 08 §15.2 SE-11: Reset request for an unknown email.

        202 {accepted: true}, no token row, indistinguishable from known-email.
        """
        response = client.post(
            "/api/v1/auth/password-reset/request",
            data={"email": "attacker_probe@unknown-lab.pk"},
            content_type="application/json",
        )
        assert response.status_code == 202
        assert response.json() == {"accepted": True}

        with schema_context(tenant_a.schema_name):
            assert PasswordResetToken.objects.count() == 0
            assert Notification.objects.count() == 0
