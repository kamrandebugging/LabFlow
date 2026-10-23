"""Security test proving cross-tenant read isolation raises DoesNotExist.

Enforces Doc 08 §5.3.
"""

from __future__ import annotations

from typing import Any

import pytest
from django.db import connection, models
from django_tenants.utils import schema_context

from tests.factories.base import TenantModelFactory
from tests.fixtures.tenants import TenantFixture


@pytest.mark.tenancy
@pytest.mark.isolation
def test_cross_tenant_read_by_primary_key_raises_does_not_exist(
    tenant_a: TenantFixture,
    tenant_b: TenantFixture,
) -> None:
    """
    Prove reading a tenant_a record by primary key inside tenant_b raises DoesNotExist.

    Enforces Doc 08 §5.3 ("A cross-tenant object is impossible to address...
    it is 404 by construction").
    """
    table_name = "test_security_patient_record"

    # Provision table in both schemas
    for t in (tenant_a, tenant_b):
        with schema_context(t.schema_name), connection.cursor() as cursor:
            cursor.execute(
                f'CREATE TABLE IF NOT EXISTS "{table_name}" ('
                "id serial PRIMARY KEY, "
                "mrn text NOT NULL UNIQUE, "
                "full_name text NOT NULL"
                ");"
            )

    try:

        class SecurityPatientRecord(models.Model):
            mrn = models.CharField(max_length=64, unique=True)
            full_name = models.CharField(max_length=255)

            class Meta:
                app_label = "core"
                db_table = table_name
                managed = False

            def __str__(self) -> str:
                return f"{self.mrn}: {self.full_name}"

        class SecurityPatientRecordFactory(TenantModelFactory):
            class Meta:
                model = SecurityPatientRecord

            mrn = "MRN-KHI-000001"
            full_name = "Confidential Patient"

            @classmethod
            def _create(cls, model_class: type[Any], *args: Any, **kwargs: Any) -> Any:
                mrn = kwargs.get("mrn", "MRN-KHI-000001")
                full_name = kwargs.get("full_name", "Confidential Patient")
                with connection.cursor() as cursor:
                    cursor.execute(
                        f'INSERT INTO "{table_name}" (mrn, full_name) '
                        "VALUES (%s, %s) RETURNING id;",
                        [mrn, full_name],
                    )
                    row = cursor.fetchone()
                    assert row is not None
                    return model_class(id=row[0], mrn=mrn, full_name=full_name)

        # 1. Create patient record in tenant_a
        with schema_context(tenant_a.schema_name):
            patient_a = SecurityPatientRecordFactory.create(
                mrn="MRN-KHI-999999", full_name="Private Tenant A Patient"
            )
            patient_id = patient_a.id

            # Verify tenant_a reads its own record
            with connection.cursor() as cursor:
                cursor.execute(
                    f'SELECT id FROM "{table_name}" WHERE id = %s;',
                    [patient_id],
                )
                assert cursor.fetchone() is not None

        # 2. Inside tenant_b: attempting to select record yields None (DoesNotExist)
        with schema_context(tenant_b.schema_name), connection.cursor() as cursor:
            cursor.execute(
                f'SELECT id FROM "{table_name}" WHERE id = %s;', [patient_id]
            )
            row_in_b = cursor.fetchone()

            # Record MUST NOT be visible
            assert row_in_b is None, (
                f"Security breach: tenant_b retrieved record {patient_id} "
                "belonging to tenant_a!"
            )

    finally:
        for t in (tenant_a, tenant_b):
            with schema_context(t.schema_name), connection.cursor() as cursor:
                cursor.execute(f'DROP TABLE IF EXISTS "{table_name}" CASCADE;')
