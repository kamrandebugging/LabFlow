from decimal import Decimal
from typing import Any

import pytest
from django.db import IntegrityError, connection, transaction
from django.db.models.deletion import ProtectedError
from django.utils import timezone
from django_tenants.utils import tenant_context

from apps.catalog.models import PanelTest, TestPrice
from tests.factories.branches import BranchFactory
from tests.factories.catalog import (
    PanelFactory,
    PanelTestFactory,
    TestFactory,
    TestPriceFactory,
)


@pytest.mark.django_db
class TestCatalogModelsSchemaAndConstraints:
    def test_catalog_tables_and_indexes_exist(self, tenant_a: Any) -> None:
        expected_indexes = {
            "test": {"uq_test_code"},
            "panel": {"uq_panel_code"},
            "panel_test": {
                "idx_panel_test_panel_id",
                "idx_panel_test_test_id",
            },
            "test_price": {
                "idx_test_price_branch_id",
                "idx_test_price_test_id",
                "idx_test_price_panel_id",
            },
        }
        with tenant_context(tenant_a), connection.cursor() as cursor:
            for table_name, idx_set in expected_indexes.items():
                cursor.execute(
                    """
                    SELECT indexname
                    FROM pg_indexes
                    WHERE schemaname = %s AND tablename = %s;
                    """,
                    [tenant_a.schema_name, table_name],
                )
                present = {r[0] for r in cursor.fetchall()}
                for expected_idx in idx_set:
                    assert expected_idx in present, (
                        f"Missing index {expected_idx} on {table_name}"
                    )

    def test_panel_test_has_composite_pk_and_no_surrogate_id(
        self, tenant_a: Any
    ) -> None:
        with tenant_context(tenant_a):
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT column_name
                    FROM information_schema.columns
                    WHERE table_schema = %s AND table_name = 'panel_test';
                    """,
                    [tenant_a.schema_name],
                )
                cols = {r[0] for r in cursor.fetchall()}
                assert cols == {"panel_id", "test_id"}

            pt = PanelTestFactory()
            with pytest.raises(IntegrityError), transaction.atomic():
                PanelTest.objects.create(panel=pt.panel, test=pt.test)

    def test_panel_test_cascades_on_delete(self, tenant_a: Any) -> None:
        with tenant_context(tenant_a):
            pt = PanelTestFactory()
            panel_id = pt.panel_id
            pt.panel.delete()
            assert not PanelTest.objects.filter(panel_id=panel_id).exists()

    def test_test_price_xor_check_constraint_enforced_by_db(
        self, tenant_a: Any
    ) -> None:
        with tenant_context(tenant_a):
            test_obj = TestFactory()
            panel_obj = PanelFactory()
            now = timezone.now()

            # 1. Valid: test only
            tp_test = TestPriceFactory(
                test=test_obj,
                panel=None,
                price=Decimal("800.00"),
                effective_from=now,
            )
            assert tp_test.test_id == test_obj.id
            assert tp_test.panel_id is None

            # 2. Valid: panel only
            tp_panel = TestPriceFactory(
                test=None,
                panel=panel_obj,
                price=Decimal("1800.00"),
                effective_from=now,
            )
            assert tp_panel.panel_id == panel_obj.id
            assert tp_panel.test_id is None

            # 3. Invalid: both set -> violates chk_test_price_test_xor_panel
            with pytest.raises(IntegrityError), transaction.atomic():
                TestPrice.objects.create(
                    test=test_obj,
                    panel=panel_obj,
                    price=Decimal("1000.00"),
                    effective_from=now,
                )

            # 4. Invalid: both null -> violates chk_test_price_test_xor_panel
            with pytest.raises(IntegrityError), transaction.atomic():
                TestPrice.objects.create(
                    test=None,
                    panel=None,
                    price=Decimal("1000.00"),
                    effective_from=now,
                )

    def test_test_price_non_negative_and_numeric_12_2(self, tenant_a: Any) -> None:
        with tenant_context(tenant_a):
            test_obj = TestFactory()
            now = timezone.now()

            # Zero price is allowed by schema (Doc 03 CT-V1)
            zero_price = TestPriceFactory(
                test=test_obj,
                panel=None,
                price=Decimal("0.00"),
                effective_from=now,
            )
            assert zero_price.price == Decimal("0.00")

            # Negative price rejected by DB CHECK constraint
            with pytest.raises(IntegrityError), transaction.atomic():
                TestPrice.objects.create(
                    test=test_obj,
                    panel=None,
                    price=Decimal("-0.01"),
                    effective_from=now,
                )

            # Verify column type in PostgreSQL is numeric(12,2)
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT data_type, numeric_precision, numeric_scale
                    FROM information_schema.columns
                    WHERE table_schema = %s
                      AND table_name = 'test_price'
                      AND column_name = 'price';
                    """,
                    [tenant_a.schema_name],
                )
                row = cursor.fetchone()
                assert row == ("numeric", 12, 2)

    def test_test_price_fks_protect_on_delete(self, tenant_a: Any) -> None:
        with tenant_context(tenant_a):
            branch = BranchFactory()
            test_obj = TestFactory()
            panel_obj = PanelFactory()
            TestPriceFactory(branch=branch, test=test_obj, panel=None)
            TestPriceFactory(branch=branch, test=None, panel=panel_obj)

            with pytest.raises(ProtectedError):
                branch.delete()
            with pytest.raises(ProtectedError):
                test_obj.delete()
            with pytest.raises(ProtectedError):
                panel_obj.delete()
