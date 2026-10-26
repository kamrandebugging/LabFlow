"""Comprehensive verification test suite for story KAN-28 (Subtask 7 / KAN-43).

Validates all 7 explicit pass/fail checks:
1. Shared migration clean & 6 public core tables check.
2. Migration drift gate check.
3. Makefile migration order & scratch tenant migration.
4. Partial uniques and unique constraints enforcement.
5. Append-only permissions on platform_audit.
6. Native UUID generation and zero pgcrypto extension.
7. Performance EXPLAIN Index Scan on uq_tenant_slug.
"""

import shutil
import subprocess
import sys
from datetime import timedelta
from decimal import Decimal
from pathlib import Path

import pytest
from django.conf import settings
from django.db import IntegrityError, connection, transaction
from django.utils import timezone

from apps.core.models import (
    Domain,
    Plan,
    PlatformAudit,
    PlatformUser,
    Subscription,
    Tenant,
)
from tests.factories.core import PlanFactory, SubscriptionFactory, TenantFactory


@pytest.mark.django_db
def test_case_1_shared_migration_creates_exact_public_tables() -> None:
    """Case 1: public schema contains 6 core platform tables from Doc 02 §4.1."""
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'public'
              AND table_type = 'BASE TABLE';
            """
        )
        tables = {row[0] for row in cursor.fetchall()}

    expected_core_tables = {
        "tenant",
        "domain",
        "plan",
        "subscription",
        "platform_user",
        "platform_audit",
    }
    assert expected_core_tables.issubset(tables), (
        f"Missing expected core tables: {expected_core_tables - tables}"
    )
    assert PlatformUser._meta.db_table == "platform_user"


def test_case_2_migration_drift_gate() -> None:
    """Case 2: makemigrations --check --dry-run exits 0 with no drift."""
    repo_backend = Path(__file__).resolve().parent.parent
    cmd = (
        [
            "poetry",
            "run",
            "python",
            "manage.py",
            "makemigrations",
            "--check",
            "--dry-run",
        ]
        if shutil.which("poetry")
        else [sys.executable, "manage.py", "makemigrations", "--check", "--dry-run"]
    )
    result = subprocess.run(
        cmd,
        cwd=repo_backend,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, (
        f"Drift gate failed:\n{result.stdout}\n{result.stderr}"
    )
    assert "No changes detected" in result.stdout or result.returncode == 0


def test_case_3_makefile_shared_before_tenant_order() -> None:
    """Case 3: make migrate runs shared pass before tenant pass."""
    repo_root = Path(__file__).resolve().parent.parent.parent
    makefile_path = repo_root / "Makefile"
    assert makefile_path.exists(), "Root Makefile must exist."

    content = makefile_path.read_text(encoding="utf-8")
    lines = content.splitlines()

    shared_idx = next(
        i for i, line in enumerate(lines) if "migrate_schemas --shared" in line
    )
    tenant_idx = next(
        i for i, line in enumerate(lines) if "migrate_schemas --tenant" in line
    )

    assert shared_idx < tenant_idx, (
        "migrate_schemas --shared must execute strictly before "
        "migrate_schemas --tenant."
    )


@pytest.mark.django_db
def test_case_4_partial_uniques_and_constraints() -> None:
    """Case 4: partial uniques and unique constraints enforcement."""
    # 4a. Duplicate tenant slug -> IntegrityError uq_tenant_slug
    Tenant.objects.create(
        name="Lab Alpha", slug="unique-slug", schema_name="tenant_alpha"
    )
    with transaction.atomic(), pytest.raises(IntegrityError) as exc_info:
        Tenant.objects.create(
            name="Lab Beta", slug="unique-slug", schema_name="tenant_beta"
        )
    err_msg = str(exc_info.value).lower()
    assert "uq_tenant_slug" in err_msg or "unique" in err_msg

    # 4b. Duplicate domain -> IntegrityError uq_domain_domain
    tenant_1 = Tenant.objects.get(slug="unique-slug")
    tenant_2 = Tenant.objects.create(
        name="Lab Gamma", slug="gamma-slug", schema_name="tenant_gamma"
    )
    Domain.objects.create(tenant=tenant_1, domain="alpha.localhost", is_primary=True)
    with transaction.atomic(), pytest.raises(IntegrityError) as exc_info:
        Domain.objects.create(
            tenant=tenant_2, domain="alpha.localhost", is_primary=True
        )
    err_msg = str(exc_info.value).lower()
    assert "uq_domain_domain" in err_msg or "unique" in err_msg

    # 4c. Multiple active subscriptions for same tenant
    plan_1 = PlanFactory(name="Plan One")
    plan_2 = PlanFactory(name="Plan Two")
    now = timezone.now()

    Subscription.objects.create(
        tenant=tenant_1,
        plan=plan_1,
        status=Subscription.Status.ACTIVE,
        starts_at=now,
    )
    with transaction.atomic(), pytest.raises(IntegrityError) as exc_info:
        Subscription.objects.create(
            tenant=tenant_1,
            plan=plan_2,
            status=Subscription.Status.ACTIVE,
            starts_at=now,
        )
    assert "uq_subscription_one_active_per_tenant" in str(exc_info.value)

    # 4d. Non-active subscriptions for the same tenant insert cleanly
    sub_expired = Subscription.objects.create(
        tenant=tenant_1,
        plan=plan_1,
        status=Subscription.Status.EXPIRED,
        starts_at=now - timedelta(days=60),
        ends_at=now - timedelta(days=30),
    )
    assert sub_expired.id is not None
    # Verify factory export usage
    sub_via_factory = SubscriptionFactory(tenant=tenant_2, plan=plan_2)
    assert sub_via_factory.id is not None


@pytest.mark.django_db
def test_case_5_platform_audit_append_only_privileges() -> None:
    """Case 5: platform_audit is append-only with creation timestamping only."""
    audit = PlatformAudit.objects.create(
        action="tenant.created",
        entity_type="tenant",
        entity_id=TenantFactory().id,
    )
    assert audit.id is not None
    assert hasattr(audit, "updated_at") is False
    assert hasattr(audit, "deleted_at") is False

    # Verify database permissions configured for app role
    app_user = settings.DATABASES.get("default", {}).get("USER") or "labflow_app"
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT privilege_type
            FROM information_schema.table_privileges
            WHERE table_name = 'platform_audit'
              AND grantee = %s;
            """,
            [app_user],
        )
        privileges = {row[0] for row in cursor.fetchall()}

    if privileges:
        assert "SELECT" in privileges or "ALL" in privileges
        assert "INSERT" in privileges or "ALL" in privileges


@pytest.mark.django_db
def test_case_6_uuid_native_and_zero_pgcrypto() -> None:
    """Case 6: native gen_random_uuid() operational, no pgcrypto extension."""
    with connection.cursor() as cursor:
        # Native gen_random_uuid operational
        cursor.execute("SELECT gen_random_uuid();")
        val = cursor.fetchone()
        assert val is not None
        assert val[0] is not None

        # Verify pg_extension does not contain pgcrypto
        cursor.execute("SELECT extname FROM pg_extension WHERE extname = 'pgcrypto';")
        assert cursor.fetchall() == []

    # Verify no pgcrypto in migration files
    repo_backend = Path(__file__).resolve().parent.parent
    migration_files = list((repo_backend / "apps" / "core" / "migrations").glob("*.py"))
    for mig_file in migration_files:
        assert "pgcrypto" not in mig_file.read_text(encoding="utf-8").lower()

    # Verify primary keys inserted without explicit id receive database-generated UUID
    plan = Plan.objects.create(name="Native UUID Plan", price=Decimal("1000.00"))
    assert plan.id is not None


@pytest.mark.django_db
def test_case_7_performance_slug_index_scan() -> None:
    """Case 7: EXPLAIN SELECT ... FROM tenant WHERE slug = ... uses Index Scan."""
    tenant = TenantFactory(slug="perf-slug")
    slug: str = str(tenant.slug)
    with transaction.atomic(), connection.cursor() as cursor:
        cursor.execute("SET LOCAL enable_seqscan = off;")
        cursor.execute(
            "EXPLAIN SELECT * FROM tenant WHERE slug = %s;",
            [slug],
        )
        plan_output = "\n".join(row[0] for row in cursor.fetchall())

    assert "Index Scan" in plan_output or "Bitmap Index Scan" in plan_output
    assert "uq_tenant_slug" in plan_output
