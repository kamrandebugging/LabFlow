from datetime import timedelta
from typing import Any

import pytest
from django.db import IntegrityError, connection, models, transaction
from django.utils import timezone
from django_tenants.utils import schema_context

from apps.accounts.models import PasswordResetToken, TenantSetting
from tests.factories.password_reset_token import PasswordResetTokenFactory
from tests.factories.staff_user import StaffUserFactory
from tests.factories.tenant_setting import TenantSettingFactory


@pytest.mark.django_db
def test_password_reset_token_fields_and_defaults(tenant_a: Any) -> None:
    """Verifies Doc 02 §5.11: PasswordResetToken fields, types, and defaults."""
    with schema_context(tenant_a.schema_name):
        token = PasswordResetTokenFactory()
        assert token.purpose == "password_reset"
        assert token.used_at is None
        assert token._meta.db_table == "password_reset_token"
        assert token.created_at is not None
        assert token.updated_at is not None
        assert token.expires_at > token.created_at


@pytest.mark.django_db
def test_password_reset_token_purpose_check_constraint(tenant_a: Any) -> None:
    """Verifies Doc 02 §8: chk_password_reset_token_purpose rejects unapproved

    purposes at PostgreSQL level.
    """
    with schema_context(tenant_a.schema_name):
        staff = StaffUserFactory()
        now = timezone.now()
        expires = now + timedelta(hours=1)

        # 1. Allowed purposes MUST succeed
        for valid_purpose in ["password_reset", "email_verification", "activation"]:
            tok = PasswordResetToken.objects.create(
                staff_user=staff,
                token_hash=f"hash_{valid_purpose}",
                purpose=valid_purpose,
                expires_at=expires,
            )
            assert tok.purpose == valid_purpose

        # 2. Invalid purpose MUST fail via PostgreSQL database CHECK constraint
        with (
            pytest.raises(IntegrityError),
            transaction.atomic(),
            connection.cursor() as cursor,
        ):
            cursor.execute(
                f'INSERT INTO "{tenant_a.schema_name}"."password_reset_token" '
                f"(id, staff_user_id, token_hash, purpose, expires_at, "
                f"created_at, updated_at) "
                f"VALUES (gen_random_uuid(), '{staff.id}', 'unapproved_hash', "
                f"'session_auth', '{expires.isoformat()}', now(), now());"
            )


@pytest.mark.django_db
def test_password_reset_token_expires_gt_created_constraint(tenant_a: Any) -> None:
    """Verifies Doc 02 §8: chk_password_reset_token_expires_gt_created rejects

    past/equal expiration.
    """
    with schema_context(tenant_a.schema_name):
        staff = StaffUserFactory()
        now = timezone.now()
        past_expires = now - timedelta(hours=1)

        with (
            pytest.raises(IntegrityError),
            transaction.atomic(),
            connection.cursor() as cursor,
        ):
            cursor.execute(
                f'INSERT INTO "{tenant_a.schema_name}"."password_reset_token" '
                f"(id, staff_user_id, token_hash, purpose, expires_at, "
                f"created_at, updated_at) "
                f"VALUES (gen_random_uuid(), '{staff.id}', 'expired_hash', "
                f"'password_reset', '{past_expires.isoformat()}', now(), now());"
            )


@pytest.mark.django_db
def test_password_reset_token_cascade_delete(tenant_a: Any) -> None:
    """Verifies Doc 02 §17: staff_user_id CASCADE deletion for token rows."""
    with schema_context(tenant_a.schema_name):
        staff = StaffUserFactory()
        token = PasswordResetTokenFactory(staff_user=staff)
        token_id = token.id

        staff.delete()
        assert not PasswordResetToken.objects.filter(id=token_id).exists()


@pytest.mark.django_db
def test_password_reset_token_unique_hash(tenant_a: Any) -> None:
    """Verifies Doc 02 §7: uq_password_reset_token_token_hash unique constraint."""
    with schema_context(tenant_a.schema_name):
        PasswordResetTokenFactory(token_hash="unique_hash_123")
        with pytest.raises(IntegrityError), transaction.atomic():
            PasswordResetTokenFactory(token_hash="unique_hash_123")


@pytest.mark.django_db
def test_tenant_setting_fields_and_uniqueness(tenant_a: Any) -> None:
    """Verifies Doc 02 §5.12: TenantSetting fields, table name, and

    uq_tenant_setting_key.
    """
    with schema_context(tenant_a.schema_name):
        setting = TenantSettingFactory(key="billing_hold_enabled", value="false")
        assert setting.key == "billing_hold_enabled"
        assert setting.value == "false"
        assert setting._meta.db_table == "tenant_setting"

        with pytest.raises(IntegrityError), transaction.atomic():
            TenantSettingFactory(key="billing_hold_enabled", value="true")


@pytest.mark.django_db
def test_tenant_setting_updated_by_protect_restrict(tenant_a: Any) -> None:
    """Verifies Doc 02 §5.12, §17: updated_by foreign key uses ON DELETE RESTRICT

    (Django PROTECT).
    """
    with schema_context(tenant_a.schema_name):
        staff = StaffUserFactory()
        TenantSettingFactory(
            key="report_default_language", value="en", updated_by=staff
        )

        with pytest.raises(models.ProtectedError):
            staff.delete()


@pytest.mark.django_db
def test_tenant_setting_updated_by_nullable_for_provisioning(
    tenant_a: Any,
) -> None:
    """Verifies Doc 02 §5.12: updated_by can be NULL for settings set by system

    at provisioning.
    """
    with schema_context(tenant_a.schema_name):
        setting = TenantSettingFactory(
            key="report_link_validity_days", value="7", updated_by=None
        )
        assert setting.updated_by is None


@pytest.mark.django_db
def test_models_isolation_and_public_exclusion(tenant_a: Any, tenant_b: Any) -> None:
    """Verifies Doc 01 ADR-003, Doc 04 §6.1: Isolation across schemas and absence

    from public.
    """
    with schema_context(tenant_a.schema_name):
        t_a = PasswordResetTokenFactory()
        s_a = TenantSettingFactory(key="shared_key_name", value="val_a")
        assert PasswordResetToken.objects.filter(id=t_a.id).exists()
        assert TenantSetting.objects.filter(id=s_a.id).exists()

    with schema_context(tenant_b.schema_name):
        assert not PasswordResetToken.objects.filter(id=t_a.id).exists()
        assert not TenantSetting.objects.filter(id=s_a.id).exists()

        # Per-tenant uniqueness for setting key
        s_b = TenantSettingFactory(key="shared_key_name", value="val_b")
        assert TenantSetting.objects.filter(id=s_b.id).exists()

    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT table_name FROM information_schema.tables
            WHERE table_schema = 'public'
              AND table_name IN ('password_reset_token', 'tenant_setting');
            """
        )
        rows = cursor.fetchall()
        assert len(rows) == 0, f"Tenant tables found in public schema: {rows}"


def test_no_tenant_id_columns_in_models() -> None:
    """Verifies Non-Negotiable Invariant: Zero tenant or tenant_id columns

    in tenant models.
    """
    for model in [PasswordResetToken, TenantSetting]:
        field_names = [f.name for f in model._meta.get_fields()]
        assert "tenant" not in field_names, f"{model} has 'tenant' field"
        assert "tenant_id" not in field_names, f"{model} has 'tenant_id' field"
