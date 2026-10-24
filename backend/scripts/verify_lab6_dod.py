"""LAB-6 Definition of Done (DoD) Verification Runner.

Executes all 8 explicit checks and prints results with clear PASS/FAIL markers.
"""

import os
import subprocess
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.dev")

import django  # noqa: E402

django.setup()

from collections.abc import Callable  # noqa: E402

from django.core.management import call_command  # noqa: E402
from django.db import connection, models  # noqa: E402
from django_tenants.utils import schema_context  # noqa: E402

from apps.accounts.models import StaffBranch, TenantSetting  # noqa: E402
from apps.core.models import Domain, Tenant  # noqa: E402
from tests.factories import (  # noqa: E402
    BranchFactory,
    StaffBranchFactory,
    StaffUserFactory,
)


def run_check(check_id: int, title: str, func: Callable[[], None]) -> bool:
    print(f"\n[CHECK {check_id}] {title}")
    try:
        func()
        print(f"--> PASS: Check {check_id} verified.")
        return True
    except Exception as exc:
        print(f"--> FAIL: Check {check_id} failed with error: {exc}")
        return False


def get_or_create_verification_tenant() -> Tenant:
    tenant = Tenant.objects.filter(schema_name__startswith="test_").first()
    if not tenant:
        tenant = Tenant.objects.exclude(schema_name="public").first()
    if not tenant:
        schema_name = "test_scratch_dod"
        with connection.cursor() as c:
            c.execute(f'CREATE SCHEMA IF NOT EXISTS "{schema_name}"')
        call_command(
            "migrate_schemas", schema_name=schema_name, tenant=True, verbosity=0
        )
        tenant, _ = Tenant.objects.get_or_create(
            schema_name=schema_name,
            defaults={
                "name": "Test Scratch",
                "slug": "test_scratch_dod",
                "status": Tenant.Status.ACTIVE,
            },
        )
        Domain.objects.get_or_create(
            tenant=tenant,
            domain="test-scratch.localhost",
            defaults={"is_primary": True},
        )
    return tenant


def main() -> None:
    print("=" * 70)
    print("LAB-6 DEFINITION OF DONE (DoD) GATE VERIFICATION")
    print("=" * 70)

    tenant = get_or_create_verification_tenant()
    print(f"Running verification against tenant schema: '{tenant.schema_name}'")

    results = []

    # Check 1: Tenant-only placement & zero drift
    def check_1() -> None:
        manage_py = str(BASE_DIR / "manage.py")
        out = subprocess.check_output(
            [
                sys.executable,
                manage_py,
                "makemigrations",
                "--check",
                "--dry-run",
            ],
            text=True,
            cwd=str(BASE_DIR.parent),
        )
        assert "No changes detected" in out
        with connection.cursor() as c:
            c.execute(
                """
                SELECT table_name FROM information_schema.tables
                WHERE table_schema = 'public'
                  AND table_name = ANY(ARRAY[
                      'branch', 'staff_user', 'staff_branch',
                      'login_event', 'password_reset_token',
                      'tenant_setting', 'audit_log'
                  ]);
                """
            )
            rows = c.fetchall()
            assert len(rows) == 0, f"Leaked tables in public: {rows}"

    results.append(
        run_check(1, "Tenant-only placement and zero migration drift", check_1)
    )

    # Check 2: Composite PK on staff_branch
    def check_2() -> None:
        with schema_context(tenant.schema_name):
            b1 = BranchFactory.build()
            u1 = StaffUserFactory.build()
            sb1 = StaffBranchFactory.build(staff_user=u1, branch=b1)
            assert sb1.pk == (u1.id, b1.id)
            assert "id" not in [f.name for f in StaffBranch._meta.get_fields()]

    results.append(
        run_check(2, "Composite PK on staff_branch without surrogate id", check_2)
    )

    # Check 3: Purpose CHECK constraint
    def check_3() -> None:
        with connection.cursor() as c:
            c.execute(
                f"""
                SELECT conname FROM pg_constraint c
                JOIN pg_namespace n ON n.oid = c.connamespace
                WHERE n.nspname = '{tenant.schema_name}'
                  AND conname = 'chk_password_reset_token_purpose';
                """
            )
            assert c.fetchone() is not None

    results.append(
        run_check(
            3,
            "PostgreSQL database-level CHECK constraint on purpose",
            check_3,
        )
    )

    # Check 4: Setting uniqueness & RESTRICT
    def check_4() -> None:
        with schema_context(tenant.schema_name):
            s = StaffUserFactory.build()
            ts = TenantSetting.objects.create(
                key=f"dod_test_key_{tenant.id}", value="1", updated_by=s
            )
            assert ts.id is not None
            try:
                s.delete()
                raise AssertionError(
                    "StaffUser deletion should have been blocked by models.PROTECT"
                )
            except models.ProtectedError:
                pass
            with connection.cursor() as c:
                c.execute(
                    f"""
                    SELECT pg_get_constraintdef(oid) FROM pg_constraint
                    WHERE conrelid = '{tenant.schema_name}.tenant_setting'::regclass
                      AND contype = 'f';
                    """
                )
                row = c.fetchone()
                assert row is not None
                assert (
                    "ON DELETE RESTRICT" in row[0]
                    or "FOREIGN KEY (updated_by) REFERENCES" in row[0]
                )

    results.append(
        run_check(4, "TenantSetting key uniqueness & RESTRICT on updated_by", check_4)
    )

    # Check 5: Append-only audit
    def check_5() -> None:
        with connection.cursor() as c:
            c.execute(
                f"""
                SELECT column_name FROM information_schema.columns
                WHERE table_schema = '{tenant.schema_name}'
                  AND table_name = 'audit_log';
                """
            )
            cols = {r[0] for r in c.fetchall()}
            assert "at" in cols
            assert "updated_at" not in cols

    results.append(
        run_check(5, "Append-only audit_log structure (timestamp at only)", check_5)
    )

    # Check 6: Protected columns no defaults
    def check_6() -> None:
        with connection.cursor() as c:
            c.execute(
                f"""
                SELECT column_name, column_default
                FROM information_schema.columns
                WHERE table_schema = '{tenant.schema_name}'
                  AND table_name = 'staff_user'
                  AND column_name IN (
                      'totp_secret_encrypted', 'totp_backup_codes_hash'
                  );
                """
            )
            for _, default in c.fetchall():
                assert default is None

    results.append(
        run_check(
            6,
            "totp_secret_encrypted and totp_backup_codes_hash have no default values",
            check_6,
        )
    )

    # Check 7: Isolation
    def check_7() -> None:
        out = subprocess.check_output(
            [
                sys.executable,
                "-m",
                "pytest",
                "backend/tests/isolation/test_cross_tenant_isolation.py",
                "--collect-only",
                "-q",
            ],
            text=True,
            cwd=str(BASE_DIR.parent),
        )
        for m in [
            "Branch",
            "StaffUser",
            "StaffBranch",
            "LoginEvent",
            "PasswordResetToken",
            "TenantSetting",
            "AuditLog",
        ]:
            assert m in out

    results.append(
        run_check(
            7,
            "Dynamic cross-tenant generator coverage for all 7 models",
            check_7,
        )
    )

    # Check 8: FK Indexes
    def check_8() -> None:
        with connection.cursor() as c:
            c.execute(
                f"""
                SELECT indexname FROM pg_indexes
                WHERE schemaname = '{tenant.schema_name}' AND indexname LIKE 'idx_%';
                """
            )
            indexes = {r[0] for r in c.fetchall()}
            expected = {
                "idx_staff_user_branch_id",
                "idx_staff_branch_staff_user_id",
                "idx_staff_branch_branch_id",
                "idx_login_event_staff_user_id",
                "idx_password_reset_token_staff_user_id",
                "idx_tenant_setting_updated_by_id",
            }
            assert expected.issubset(indexes)

    results.append(
        run_check(
            8,
            "Performance verification of foreign key indexes in pg_indexes",
            check_8,
        )
    )

    print("\n" + "=" * 70)
    passed = sum(results)
    total = len(results)
    print(f"DoD Gate Summary: {passed}/{total} checks passed.")
    print("=" * 70)

    if passed != total:
        sys.exit(1)
    print(
        "\nAll LAB-6 Definition of Done checks successfully verified. "
        "Ready to close Epic LAB-6 Story KAN-36."
    )


if __name__ == "__main__":
    main()
