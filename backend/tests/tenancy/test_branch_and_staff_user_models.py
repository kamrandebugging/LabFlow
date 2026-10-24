from typing import Any

import pytest
from django.db import IntegrityError, connection
from django_tenants.utils import schema_context

from apps.accounts.models import Role, StaffUser
from apps.branches.models import Branch
from tests.factories.branch import BranchFactory
from tests.factories.staff_user import StaffUserFactory


@pytest.mark.django_db
def test_branch_and_staff_user_fields_and_tables(tenant_a: Any) -> None:
    """Verifies Doc 02 §5.1 table names, constraints, and field defaults."""
    with schema_context(tenant_a.schema_name):
        branch = BranchFactory(
            code="KHI",
            name="Karachi Main Branch",
            is_collection_centre=True,
            result_entry_enabled=True,
        )
        assert branch.code == "KHI"
        assert branch.is_collection_centre is True
        assert branch.result_entry_enabled is True
        assert branch.deleted_at is None
        assert branch._meta.db_table == "branch"

        staff = StaffUserFactory(
            branch=branch,
            role=Role.MANAGER,
            email="manager.khi@labflow.app",
            totp_enabled=True,
            totp_secret_encrypted="fernet_ciphertext_sample",
            totp_backup_codes_hash=["argon2_hash_1", "argon2_hash_2"],
        )
        assert staff.branch == branch
        assert staff.role == "manager"
        assert staff.email == "manager.khi@labflow.app"
        assert staff.totp_enabled is True
        assert staff.totp_secret_encrypted == "fernet_ciphertext_sample"
        assert staff.totp_backup_codes_hash == ["argon2_hash_1", "argon2_hash_2"]
        assert staff._meta.db_table == "staff_user"


@pytest.mark.django_db
def test_branch_code_unique_constraint(tenant_a: Any) -> None:
    """Verifies uq_branch_code constraint per Doc 02 §7."""
    with schema_context(tenant_a.schema_name):
        BranchFactory(code="LHR")
        with pytest.raises(IntegrityError):
            BranchFactory(code="LHR")


@pytest.mark.django_db
def test_staff_user_email_unique_constraint(tenant_a: Any) -> None:
    """Verifies uq_staff_user_email constraint per Doc 02 §7."""
    with schema_context(tenant_a.schema_name):
        StaffUserFactory(email="tech@labflow.app")
        with pytest.raises(IntegrityError):
            StaffUserFactory(email="tech@labflow.app")


@pytest.mark.django_db
def test_tenant_wide_staff_user_null_branch(tenant_a: Any) -> None:
    """Verifies Doc 02 §5.1: Pathologists and Owners can have branch=None

    (tenant-wide).
    """
    with schema_context(tenant_a.schema_name):
        owner = StaffUserFactory(tenant_wide=True)
        assert owner.branch is None
        assert owner.role == Role.OWNER


@pytest.mark.django_db
def test_schema_isolation_for_branch_and_staff(tenant_a: Any, tenant_b: Any) -> None:
    """Verifies Doc 01 ADR-003, Doc 04 §6.1:

    Objects created in tenant_a schema do NOT leak into tenant_b.
    """
    with schema_context(tenant_a.schema_name):
        branch_a = BranchFactory(code="ISB", name="Islamabad Branch")
        staff_a = StaffUserFactory(branch=branch_a, email="staff.isb@labflow.app")
        assert Branch.objects.filter(id=branch_a.id).exists()
        assert StaffUser.objects.filter(id=staff_a.id).exists()

    with schema_context(tenant_b.schema_name):
        assert not Branch.objects.filter(id=branch_a.id).exists()
        assert not StaffUser.objects.filter(id=staff_a.id).exists()

        # Same code and email CAN exist in tenant_b (per-schema uniqueness)
        branch_b = BranchFactory(code="ISB", name="Islamabad Secondary Branch")
        staff_b = StaffUserFactory(branch=branch_b, email="staff.isb@labflow.app")
        assert Branch.objects.filter(id=branch_b.id).exists()
        assert StaffUser.objects.filter(id=staff_b.id).exists()


@pytest.mark.django_db
def test_tenant_tables_do_not_exist_in_public_schema() -> None:
    """Verifies that 'branch' and 'staff_user' tables never exist in public schema."""
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT table_name FROM information_schema.tables
            WHERE table_schema = 'public' AND table_name IN ('branch', 'staff_user');
            """
        )
        rows = cursor.fetchall()
        assert len(rows) == 0, f"Tenant tables found in public schema: {rows}"


def test_no_tenant_id_columns_in_models() -> None:
    """Verifies Non-Negotiable Invariant: Zero tenant or tenant_id columns

    in tenant models.
    """
    for model in [Branch, StaffUser]:
        field_names = [f.name for f in model._meta.get_fields()]
        assert "tenant" not in field_names, f"{model} has 'tenant' field"
        assert "tenant_id" not in field_names, f"{model} has 'tenant_id' field"
