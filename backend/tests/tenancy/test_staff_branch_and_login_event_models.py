from typing import Any

import pytest
from django.db import IntegrityError, connection, transaction
from django_tenants.utils import schema_context

from apps.accounts.models import LoginEvent, StaffBranch
from tests.factories.branch import BranchFactory
from tests.factories.login_event import LoginEventFactory
from tests.factories.staff_branch import StaffBranchFactory
from tests.factories.staff_user import StaffUserFactory


@pytest.mark.django_db
def test_staff_branch_composite_pk_and_fields(tenant_a: Any) -> None:
    """Verifies Doc 02 §5.1: staff_branch has no surrogate id and composite PK

    (staff_user_id, branch_id).
    """
    with schema_context(tenant_a.schema_name):
        staff = StaffUserFactory()
        branch_1 = BranchFactory(code="B01")
        branch_2 = BranchFactory(code="B02")

        sb1 = StaffBranchFactory(staff_user=staff, branch=branch_1, is_primary=True)
        assert sb1.is_primary is True
        assert sb1.created_at is not None
        assert sb1._meta.db_table == "staff_branch"
        assert sb1.pk == (staff.id, branch_1.id)

        # Duplicate (staff_user, branch) pair must fail via Composite PK constraint
        with pytest.raises(IntegrityError), transaction.atomic():
            StaffBranch.objects.create(
                staff_user=staff, branch=branch_1, is_primary=False
            )

        # Same staff user with different branch MUST succeed
        sb2 = StaffBranchFactory(staff_user=staff, branch=branch_2, is_primary=False)
        assert sb2.pk == (staff.id, branch_2.id)


@pytest.mark.django_db
def test_staff_branch_has_no_surrogate_id_field() -> None:
    """Verifies Doc 02 §5.1 invariant: staff_branch has composite PK with no

    surrogate id field.
    """
    field_names = [f.name for f in StaffBranch._meta.get_fields()]
    assert "id" not in field_names, (
        "StaffBranch must not possess a surrogate 'id' field"
    )
    assert hasattr(StaffBranch._meta, "pk"), "StaffBranch must possess primary key"


@pytest.mark.django_db
def test_login_event_fields_and_table(tenant_a: Any) -> None:
    """Verifies Doc 02 §5.11: login_event fields, nullable staff_user, append-only

    shape.
    """
    with schema_context(tenant_a.schema_name):
        staff = StaffUserFactory(email="technician@labflow.app")

        # Successful login event with resolved staff_user
        event_ok = LoginEventFactory(
            staff_user=staff,
            email_attempted="technician@labflow.app",
            success=True,
            ip="10.0.0.1",
            user_agent="Firefox/120.0",
        )
        assert event_ok.staff_user == staff
        assert event_ok.email_attempted == "technician@labflow.app"
        assert event_ok.success is True
        assert event_ok.ip == "10.0.0.1"
        assert event_ok.user_agent == "Firefox/120.0"
        assert event_ok.created_at is not None
        assert not hasattr(event_ok, "updated_at")
        assert event_ok._meta.db_table == "login_event"

        # Failed login event with staff_user=None (unmatched account)
        event_fail = LoginEventFactory(failed=True)
        assert event_fail.staff_user is None
        assert event_fail.success is False
        assert event_fail.email_attempted == "invalid@labflow.app"


@pytest.mark.django_db
def test_staff_branch_and_login_event_isolation(tenant_a: Any, tenant_b: Any) -> None:
    """Verifies Doc 01 ADR-003, Doc 04 §6.1:

    Objects created in tenant_a schema do NOT leak into tenant_b schema.
    """
    with schema_context(tenant_a.schema_name):
        sb_a = StaffBranchFactory()
        event_a = LoginEventFactory()
        assert StaffBranch.objects.filter(pk=sb_a.pk).exists()
        assert LoginEvent.objects.filter(id=event_a.id).exists()

    with schema_context(tenant_b.schema_name):
        assert not StaffBranch.objects.filter(pk=sb_a.pk).exists()
        assert not LoginEvent.objects.filter(id=event_a.id).exists()


@pytest.mark.django_db
def test_tables_do_not_exist_in_public_schema() -> None:
    """Verifies tenant tables never exist in PostgreSQL public schema."""
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT table_name FROM information_schema.tables
            WHERE table_schema = 'public'
              AND table_name IN ('staff_branch', 'login_event');
            """
        )
        rows = cursor.fetchall()
        assert len(rows) == 0, f"Tenant tables found in public schema: {rows}"


def test_no_tenant_id_columns_in_models() -> None:
    """Verifies Non-Negotiable Invariant: Zero tenant or tenant_id columns

    in tenant models.
    """
    for model in [StaffBranch, LoginEvent]:
        field_names = [f.name for f in model._meta.get_fields()]
        assert "tenant" not in field_names, f"{model} has 'tenant' field"
        assert "tenant_id" not in field_names, f"{model} has 'tenant_id' field"
