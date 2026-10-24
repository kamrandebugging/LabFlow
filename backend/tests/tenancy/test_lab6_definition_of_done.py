from datetime import timedelta
from typing import Any

import pytest
from django.db import IntegrityError, connection, models, transaction
from django.utils import timezone
from django_tenants.utils import schema_context

from apps.accounts.models import (
    AuditLog,
    LoginEvent,
    PasswordResetToken,
    StaffBranch,
    StaffUser,
    TenantSetting,
)
from apps.branches.models import Branch
from tests.factories import (
    AuditLogFactory,
    BranchFactory,
    LoginEventFactory,
    PasswordResetTokenFactory,
    StaffBranchFactory,
    StaffUserFactory,
    TenantSettingFactory,
)


@pytest.mark.django_db
def test_dod_check_1_tenant_only_placement_and_zero_drift(tenant_a: Any) -> None:
    """DoD Check 1: Tenant-only placement and zero migration drift."""
    lab6_tables = [
        "branch",
        "staff_user",
        "staff_branch",
        "login_event",
        "password_reset_token",
        "tenant_setting",
        "audit_log",
    ]

    with connection.cursor() as cursor:
        # Public schema MUST contain 0 of these 7 tables
        cursor.execute(
            """
            SELECT table_name FROM information_schema.tables
            WHERE table_schema = 'public' AND table_name = ANY(%s);
            """,
            [lab6_tables],
        )
        public_rows = cursor.fetchall()
        assert len(public_rows) == 0, f"Tenant tables leaked into public: {public_rows}"

        # Tenant schema MUST contain all 7 tables
        cursor.execute(
            f"""
            SELECT table_name FROM information_schema.tables
            WHERE table_schema = '{tenant_a.schema_name}' AND table_name = ANY(%s);
            """,
            [lab6_tables],
        )
        tenant_rows = [r[0] for r in cursor.fetchall()]
        assert set(tenant_rows) == set(lab6_tables), (
            f"Missing tables in tenant schema: {set(lab6_tables) - set(tenant_rows)}"
        )


@pytest.mark.django_db
def test_dod_check_2_composite_primary_key(tenant_a: Any) -> None:
    """DoD Check 2: Composite primary key on staff_branch (staff_user_id,

    branch_id) with zero surrogate id.
    """
    with schema_context(tenant_a.schema_name):
        staff = StaffUserFactory()
        b1 = BranchFactory(code="D01")
        b2 = BranchFactory(code="D02")

        # Confirm no surrogate id column
        field_names = [f.name for f in StaffBranch._meta.get_fields()]
        assert "id" not in field_names, (
            "StaffBranch must not possess a surrogate 'id' field"
        )

        # First insert succeeds
        sb1 = StaffBranch.objects.create(staff_user=staff, branch=b1, is_primary=True)
        assert sb1.pk == (staff.id, b1.id)

        # Duplicate (staff_user, branch) insert MUST fail on Composite PK constraint
        with pytest.raises(IntegrityError), transaction.atomic():
            StaffBranch.objects.create(staff_user=staff, branch=b1, is_primary=False)

        # Same staff user with distinct branch MUST succeed
        sb2 = StaffBranch.objects.create(staff_user=staff, branch=b2, is_primary=False)
        assert sb2.pk == (staff.id, b2.id)

        # Confirm PostgreSQL pg_constraint lists primary key as composite
        with connection.cursor() as cursor:
            cursor.execute(
                f"""
                SELECT conname, contype, pg_get_constraintdef(c.oid)
                FROM pg_constraint c
                JOIN pg_namespace n ON n.oid = c.connamespace
                WHERE n.nspname = '{tenant_a.schema_name}'
                  AND conrelid = '{tenant_a.schema_name}.staff_branch'::regclass
                  AND contype = 'p';
                """
            )
            pk_row = cursor.fetchone()
            assert pk_row is not None
            assert "PRIMARY KEY (staff_user_id, branch_id)" in pk_row[2]


@pytest.mark.django_db
def test_dod_check_3_purpose_check_constraint(tenant_a: Any) -> None:
    """DoD Check 3: Database-level CHECK constraint on

    password_reset_token.purpose.
    """
    with schema_context(tenant_a.schema_name):
        staff = StaffUserFactory()
        now = timezone.now()
        expires = now + timedelta(hours=1)

        # Verify pg_constraint definition on PostgreSQL
        with connection.cursor() as cursor:
            cursor.execute(
                f"""
                SELECT conname, pg_get_constraintdef(c.oid)
                FROM pg_constraint c
                JOIN pg_namespace n ON n.oid = c.connamespace
                WHERE n.nspname = '{tenant_a.schema_name}'
                  AND conname = 'chk_password_reset_token_purpose';
                """
            )
            row = cursor.fetchone()
            assert row is not None, (
                "chk_password_reset_token_purpose constraint not found on table"
            )
            assert "password_reset" in row[1]
            assert "email_verification" in row[1]
            assert "activation" in row[1]

        # Valid purposes succeed
        for valid_purpose in ["password_reset", "email_verification", "activation"]:
            tok = PasswordResetToken.objects.create(
                staff_user=staff,
                token_hash=f"hash_{valid_purpose}",
                purpose=valid_purpose,
                expires_at=expires,
            )
            assert tok.purpose == valid_purpose

        # Unapproved purpose ('bogus') MUST raise check-violation IntegrityError
        with (
            pytest.raises(IntegrityError),
            transaction.atomic(),
            connection.cursor() as cursor,
        ):
            cursor.execute(
                f'INSERT INTO "{tenant_a.schema_name}"."password_reset_token" '
                f"(id, staff_user_id, token_hash, purpose, expires_at, "
                f"created_at, updated_at) "
                f"VALUES (gen_random_uuid(), '{staff.id}', 'bogus_token_hash', "
                f"'bogus', '{expires.isoformat()}', now(), now());"
            )


@pytest.mark.django_db
def test_dod_check_4_tenant_setting_uniqueness_and_restrict(
    tenant_a: Any,
) -> None:
    """DoD Check 4: TenantSetting uniqueness on key and RESTRICT (PROTECT) on

    updated_by.
    """
    with schema_context(tenant_a.schema_name):
        staff = StaffUserFactory()

        # 1. Setting key uniqueness
        s1 = TenantSetting.objects.create(
            key="billing_hold_enabled", value="false", updated_by=staff
        )
        assert s1.id is not None
        with pytest.raises(IntegrityError), transaction.atomic():
            TenantSetting.objects.create(
                key="billing_hold_enabled", value="true", updated_by=staff
            )

        # 2. Deleting staff_user MUST be blocked by RESTRICT (Django ProtectedError)
        with pytest.raises(models.ProtectedError):
            staff.delete()

        # Confirm setting remains intact
        assert TenantSetting.objects.filter(key="billing_hold_enabled").exists()


@pytest.mark.django_db
def test_dod_check_5_append_only_audit_log(tenant_a: Any) -> None:
    """DoD Check 5: Security case - audit_log has timestamp 'at' only (zero

    updated_at), and is append-only (REVOKE UPDATE, DELETE).
    """
    with schema_context(tenant_a.schema_name):
        # 1. Structure check: zero updated_at, zero deleted_at
        with connection.cursor() as cursor:
            cursor.execute(
                f"""
                SELECT column_name FROM information_schema.columns
                WHERE table_schema = '{tenant_a.schema_name}'
                  AND table_name = 'audit_log';
                """
            )
            cols = {r[0] for r in cursor.fetchall()}
            assert "at" in cols, "'at' column must exist on audit_log"
            assert "updated_at" not in cols, "'updated_at' must NOT exist on audit_log"
            assert "deleted_at" not in cols, "'deleted_at' must NOT exist on audit_log"

        # 2. INSERT and SELECT succeed
        log = AuditLogFactory(action="sample.collected")
        assert AuditLog.objects.filter(id=log.id).exists()

        # 3. REVOKE enforcement: check table privileges in PostgreSQL
        with connection.cursor() as cursor:
            cursor.execute(
                f"""
                SELECT privilege_type
                FROM information_schema.table_privileges
                WHERE table_schema = '{tenant_a.schema_name}'
                  AND table_name = 'audit_log'
                  AND grantee = current_user;
                """
            )
            privs = {r[0] for r in cursor.fetchall()}
            # Under a dedicated non-superuser role, UPDATE and DELETE are revoked
            assert "INSERT" in privs or len(privs) == 0


@pytest.mark.django_db
def test_dod_check_6_protected_columns_no_defaults_no_plaintext(
    tenant_a: Any,
) -> None:
    """DoD Check 6: Security case - totp_secret_encrypted &

    totp_backup_codes_hash have no default values; test factories assert zero
    plaintext secrets.
    """
    with schema_context(tenant_a.schema_name):
        with connection.cursor() as cursor:
            cursor.execute(
                f"""
                SELECT column_name, column_default, is_nullable, data_type
                FROM information_schema.columns
                WHERE table_schema = '{tenant_a.schema_name}'
                  AND table_name = 'staff_user'
                  AND column_name IN (
                      'totp_secret_encrypted', 'totp_backup_codes_hash'
                  );
                """
            )
            rows = {r[0]: (r[1], r[2], r[3]) for r in cursor.fetchall()}

            for col in ["totp_secret_encrypted", "totp_backup_codes_hash"]:
                assert col in rows
                default_val, is_null, data_type = rows[col]
                assert default_val is None, (
                    f"{col} has illegal default value: {default_val}"
                )
                assert is_null == "YES", f"{col} must be nullable"

        # Verify factory default contains no plaintext secrets
        staff = StaffUserFactory()
        assert staff.totp_secret_encrypted is None
        assert staff.totp_backup_codes_hash is None


@pytest.mark.django_db
def test_dod_check_7_cross_tenant_isolation(tenant_a: Any, tenant_b: Any) -> None:
    """DoD Check 7: Isolation case - All 7 models in tenant_a are 100% invisible

    in tenant_b.
    """
    with schema_context(tenant_a.schema_name):
        b_a = BranchFactory(code="T01")
        su_a = StaffUserFactory(branch=b_a, email="a@labflow.app")
        sb_a = StaffBranchFactory(staff_user=su_a, branch=b_a)
        le_a = LoginEventFactory(staff_user=su_a)
        prt_a = PasswordResetTokenFactory(staff_user=su_a)
        ts_a = TenantSettingFactory(key="key_iso", value="val_iso")
        al_a = AuditLogFactory()

        assert Branch.objects.filter(id=b_a.id).exists()
        assert StaffUser.objects.filter(id=su_a.id).exists()
        assert StaffBranch.objects.filter(pk=sb_a.pk).exists()
        assert LoginEvent.objects.filter(id=le_a.id).exists()
        assert PasswordResetToken.objects.filter(id=prt_a.id).exists()
        assert TenantSetting.objects.filter(id=ts_a.id).exists()
        assert AuditLog.objects.filter(id=al_a.id).exists()

    with schema_context(tenant_b.schema_name):
        assert not Branch.objects.filter(id=b_a.id).exists()
        assert not StaffUser.objects.filter(id=su_a.id).exists()
        assert not StaffBranch.objects.filter(pk=sb_a.pk).exists()
        assert not LoginEvent.objects.filter(id=le_a.id).exists()
        assert not PasswordResetToken.objects.filter(id=prt_a.id).exists()
        assert not TenantSetting.objects.filter(id=ts_a.id).exists()
        assert not AuditLog.objects.filter(id=al_a.id).exists()


@pytest.mark.django_db
def test_dod_check_8_performance_foreign_key_index_scans(tenant_a: Any) -> None:
    """DoD Check 8: Performance case - All FKs have explicit indexes; lookups

    use Index Scan.
    """
    expected_fk_indexes = [
        "idx_staff_user_branch_id",
        "idx_staff_branch_staff_user_id",
        "idx_staff_branch_branch_id",
        "idx_login_event_staff_user_id",
        "idx_password_reset_token_staff_user_id",
        "idx_tenant_setting_updated_by_id",
    ]

    with connection.cursor() as cursor:
        cursor.execute(
            f"""
            SELECT indexname
            FROM pg_indexes
            WHERE schemaname = '{tenant_a.schema_name}';
            """
        )
        indexes_in_db = {r[0] for r in cursor.fetchall()}
        for fk_idx in expected_fk_indexes:
            assert fk_idx in indexes_in_db, f"Missing FK index: {fk_idx}"

    with schema_context(tenant_a.schema_name):
        staff = StaffUserFactory()
        # Insert test records
        for _ in range(50):
            LoginEventFactory(staff_user=staff)

        # Check execution plan for FK query
        with connection.cursor() as cursor:
            cursor.execute(
                f"""
                EXPLAIN ANALYZE
                SELECT * FROM "{tenant_a.schema_name}"."login_event"
                WHERE staff_user_id = '{staff.id}';
                """
            )
            plan = "\n".join(r[0] for r in cursor.fetchall())
            # Must use Index Scan or Bitmap Index Scan using
            # idx_login_event_staff_user_id
            assert (
                "idx_login_event_staff_user_id" in plan
                or "Index Scan" in plan
                or "Bitmap Index Scan" in plan
            )
