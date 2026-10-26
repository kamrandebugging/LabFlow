from datetime import date
from decimal import Decimal
from typing import Any

import pytest
from django.db import IntegrityError, connection, transaction
from django.db.models.deletion import ProtectedError
from django_tenants.utils import tenant_context

from apps.catalog.models import ReferenceRange
from tests.factories.catalog import ReferenceRangeFactory, TestFactory


@pytest.mark.django_db
class TestReferenceRangeSchemaAndConstraints:
    def test_reference_range_columns_and_numeric_10_3_precision(
        self, tenant_a: Any
    ) -> None:
        with tenant_context(tenant_a), connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT
                    column_name,
                    data_type,
                    numeric_precision,
                    numeric_scale,
                    is_nullable
                FROM information_schema.columns
                WHERE table_schema = %s AND table_name = 'reference_range';
                """,
                [tenant_a.schema_name],
            )
            cols = {
                row[0]: {
                    "data_type": row[1],
                    "precision": row[2],
                    "scale": row[3],
                    "nullable": row[4],
                }
                for row in cursor.fetchall()
            }

            expected_cols = {
                "id",
                "test_id",
                "sex",
                "age_min_days",
                "age_max_days",
                "low",
                "high",
                "critical_low",
                "critical_high",
                "unit",
                "effective_from",
                "effective_to",
                "created_at",
                "updated_at",
            }
            assert set(cols.keys()) == expected_cols
            assert "deleted_at" not in cols

            for bound_col in ("low", "high", "critical_low", "critical_high"):
                assert cols[bound_col]["data_type"] == "numeric"
                assert cols[bound_col]["precision"] == 10
                assert cols[bound_col]["scale"] == 3
                assert cols[bound_col]["nullable"] == "YES"

            assert cols["age_min_days"]["nullable"] == "NO"
            assert cols["age_max_days"]["nullable"] == "YES"
            assert cols["unit"]["nullable"] == "NO"
            assert cols["effective_from"]["data_type"] == "date"
            assert cols["effective_from"]["nullable"] == "NO"
            assert cols["effective_to"]["data_type"] == "date"
            assert cols["effective_to"]["nullable"] == "YES"

    def test_reference_range_fk_index_and_protect(self, tenant_a: Any) -> None:
        with tenant_context(tenant_a):
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT indexname
                    FROM pg_indexes
                    WHERE schemaname = %s AND tablename = 'reference_range';
                    """,
                    [tenant_a.schema_name],
                )
                indexes = {r[0] for r in cursor.fetchall()}
                assert "idx_reference_range_test_id" in indexes

            test_obj = TestFactory()
            rr = ReferenceRangeFactory(test=test_obj)
            assert rr.test_id == test_obj.id

            with pytest.raises(ProtectedError):
                test_obj.delete()

    def test_age_band_check_constraints(self, tenant_a: Any) -> None:
        with tenant_context(tenant_a):
            test_obj = TestFactory()

            # Valid: newborn 0..28 days
            rr_newborn = ReferenceRangeFactory(
                test=test_obj,
                age_min_days=0,
                age_max_days=28,
            )
            assert rr_newborn.age_min_days == 0
            assert rr_newborn.age_max_days == 28

            # Invalid: negative age_min_days -> chk_reference_range_age_min_non_neg
            with pytest.raises(IntegrityError), transaction.atomic():
                ReferenceRange.objects.create(
                    test=test_obj,
                    sex=ReferenceRange.Sex.BOTH,
                    age_min_days=-1,
                    age_max_days=100,
                    unit="mg/dL",
                    effective_from=date(2026, 1, 1),
                )

            # Invalid: age_max_days < age_min_days -> chk_reference_range_age_band_order
            with pytest.raises(IntegrityError), transaction.atomic():
                ReferenceRange.objects.create(
                    test=test_obj,
                    sex=ReferenceRange.Sex.BOTH,
                    age_min_days=100,
                    age_max_days=50,
                    unit="mg/dL",
                    effective_from=date(2026, 1, 1),
                )

    def test_normal_and_critical_bounds_check_constraints(self, tenant_a: Any) -> None:
        with tenant_context(tenant_a):
            test_obj = TestFactory()

            # Valid: qualitative test with all bounds NULL
            rr_qual = ReferenceRangeFactory(
                test=test_obj,
                low=None,
                high=None,
                critical_low=None,
                critical_high=None,
            )
            assert rr_qual.low is None
            assert rr_qual.critical_high is None

            # Invalid: low > high -> chk_reference_range_low_le_high
            with pytest.raises(IntegrityError), transaction.atomic():
                ReferenceRange.objects.create(
                    test=test_obj,
                    sex=ReferenceRange.Sex.FEMALE,
                    age_min_days=6570,
                    low=Decimal("15.000"),
                    high=Decimal("12.000"),
                    unit="g/dL",
                    effective_from=date(2026, 1, 1),
                )

            # Invalid: critical_low > critical_high ->
            # chk_reference_range_crit_low_le_crit_high
            with pytest.raises(IntegrityError), transaction.atomic():
                ReferenceRange.objects.create(
                    test=test_obj,
                    sex=ReferenceRange.Sex.MALE,
                    age_min_days=6570,
                    low=Decimal("13.000"),
                    high=Decimal("17.000"),
                    critical_low=Decimal("20.000"),
                    critical_high=Decimal("7.000"),
                    unit="g/dL",
                    effective_from=date(2026, 1, 1),
                )
