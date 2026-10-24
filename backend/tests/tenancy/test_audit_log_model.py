import uuid
from typing import Any

import pytest
from django.db import connection
from django_tenants.utils import schema_context

from apps.accounts.models import AuditLog
from tests.factories.audit_log import AuditLogFactory


@pytest.mark.django_db
def test_audit_log_fields_and_append_only_shape(tenant_a: Any) -> None:
    """Verifies Doc 02 §5.11 & §13: AuditLog fields, table name, and append-only

    timestamp.
    """
    with schema_context(tenant_a.schema_name):
        log = AuditLogFactory(
            action="invoice.created",
            entity_type="invoice",
            before_jsonb=None,
            after_jsonb={"total": "1250.00", "status": "unpaid"},
            ip="192.168.1.100",
            user_agent="Chrome/120.0",
        )

        assert log._meta.db_table == "audit_log"
        assert log.action == "invoice.created"
        assert log.entity_type == "invoice"
        assert log.after_jsonb == {"total": "1250.00", "status": "unpaid"}
        assert log.ip == "192.168.1.100"
        assert log.user_agent == "Chrome/120.0"
        assert log.at is not None

        # Verify strict append-only shape: zero updated_at and zero deleted_at
        field_names = [f.name for f in AuditLog._meta.get_fields()]
        assert "updated_at" not in field_names, "AuditLog must not possess 'updated_at'"
        assert "deleted_at" not in field_names, "AuditLog must not possess 'deleted_at'"
        assert "at" in field_names, "AuditLog must use 'at' as timestamp"


@pytest.mark.django_db
def test_audit_log_actor_id_plain_uuid_and_nullable_for_system_events(
    tenant_a: Any,
) -> None:
    """Verifies Doc 02 §17: actor_id is plain UUID without FK and nullable for

    system events.
    """
    with schema_context(tenant_a.schema_name):
        # 1. System event with actor_id=None
        system_log = AuditLogFactory(system_event=True)
        assert system_log.actor_id is None

        # 2. Random UUID not corresponding to StaffUser MUST NOT raise FK error
        random_uuid = uuid.uuid4()
        user_log = AuditLogFactory(actor_id=random_uuid)
        assert user_log.actor_id == random_uuid


@pytest.mark.django_db
def test_audit_log_entity_id_plain_uuid_and_non_fk(tenant_a: Any) -> None:
    """Verifies Doc 02 §17: entity_id is plain UUID without foreign key constraint."""
    with schema_context(tenant_a.schema_name):
        random_entity_uuid = uuid.uuid4()
        log = AuditLogFactory(entity_type="sample", entity_id=random_entity_uuid)
        assert log.entity_id == random_entity_uuid


@pytest.mark.django_db
def test_audit_log_indexes_present(tenant_a: Any) -> None:
    """Verifies Doc 02 §7 & §18: idx_audit_log_at,

    idx_audit_log_entity_type_entity_id, idx_audit_log_actor_id.
    """
    index_names = [idx.name for idx in AuditLog._meta.indexes]
    assert "idx_audit_log_at" in index_names
    assert "idx_audit_log_entity_type_entity_id" in index_names
    assert "idx_audit_log_actor_id" in index_names


@pytest.mark.django_db
def test_audit_log_isolation_and_public_exclusion(tenant_a: Any, tenant_b: Any) -> None:
    """Verifies Doc 01 ADR-003, Doc 04 §6.1: Isolation across schemas and absence

    from public schema.
    """
    with schema_context(tenant_a.schema_name):
        log_a = AuditLogFactory()
        assert AuditLog.objects.filter(id=log_a.id).exists()

    with schema_context(tenant_b.schema_name):
        assert not AuditLog.objects.filter(id=log_a.id).exists()

    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT table_name FROM information_schema.tables
            WHERE table_schema = 'public' AND table_name = 'audit_log';
            """
        )
        rows = cursor.fetchall()
        assert len(rows) == 0, f"'audit_log' table found in public schema: {rows}"


def test_no_tenant_id_columns_in_audit_log() -> None:
    """Verifies Non-Negotiable Invariant: Zero tenant or tenant_id columns in

    tenant models.
    """
    field_names = [f.name for f in AuditLog._meta.get_fields()]
    assert "tenant" not in field_names, "AuditLog has 'tenant' field"
    assert "tenant_id" not in field_names, "AuditLog has 'tenant_id' field"
