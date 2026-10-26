from decimal import Decimal
from typing import Any

import pytest
from django.db import IntegrityError, connection, transaction
from django.db.models.deletion import ProtectedError
from django_tenants.utils import tenant_context

from apps.billing.models import Payment
from tests.factories.accounts import StaffUserFactory
from tests.factories.billing import InvoiceFactory, PaymentFactory


@pytest.mark.django_db
class TestPaymentModelSchemaAndConstraints:
    def test_payment_columns_indexes_and_append_only_shape(self, tenant_a: Any) -> None:
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
                WHERE table_schema = %s AND table_name = 'payment';
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
                "invoice_id",
                "kind",
                "method",
                "amount",
                "received_by",
                "reference",
                "idempotency_key",
                "created_at",
            }
            assert set(cols.keys()) == expected_cols
            assert "updated_at" not in cols
            assert "deleted_at" not in cols

            assert cols["amount"]["data_type"] == "numeric"
            assert cols["amount"]["precision"] == 12
            assert cols["amount"]["scale"] == 2
            assert cols["amount"]["nullable"] == "NO"
            assert cols["kind"]["nullable"] == "NO"
            assert cols["method"]["nullable"] == "NO"
            assert cols["received_by"]["nullable"] == "YES"

            cursor.execute(
                """
                SELECT indexname
                FROM pg_indexes
                WHERE schemaname = %s AND tablename = 'payment';
                """,
                [tenant_a.schema_name],
            )
            indexes = {r[0] for r in cursor.fetchall()}
            assert "uq_payment_idempotency_key" in indexes
            assert "idx_payment_invoice_id" in indexes
            assert "idx_payment_received_by" in indexes

    def test_payment_kind_and_method_check_constraints_enforced_by_db(
        self, tenant_a: Any
    ) -> None:
        with tenant_context(tenant_a):
            inv = InvoiceFactory()

            # All valid kinds and methods succeed
            for valid_kind in (Payment.Kind.PAYMENT, Payment.Kind.REFUND):
                for valid_method in (
                    Payment.Method.CASH,
                    Payment.Method.CARD,
                    Payment.Method.BANK_TRANSFER,
                    Payment.Method.EASYPAISA,
                    Payment.Method.JAZZCASH,
                    Payment.Method.OTHER,
                ):
                    p = PaymentFactory(
                        invoice=inv,
                        kind=valid_kind,
                        method=valid_method,
                        amount=Decimal("250.00"),
                    )
                    assert p.kind == valid_kind
                    assert p.method == valid_method

            # Invalid kind fails at DB -> chk_payment_kind
            with pytest.raises(IntegrityError), transaction.atomic():
                Payment.objects.create(
                    invoice=inv,
                    kind="chargeback_invalid",
                    method=Payment.Method.CASH,
                    amount=Decimal("100.00"),
                )

            # Invalid method (including 'refund' as method per OQ-23)
            # fails at DB -> chk_payment_method
            with pytest.raises(IntegrityError), transaction.atomic():
                Payment.objects.create(
                    invoice=inv,
                    kind=Payment.Kind.REFUND,
                    method="refund",
                    amount=Decimal("100.00"),
                )

    def test_payment_amount_strictly_positive_check_constraint(
        self, tenant_a: Any
    ) -> None:
        with tenant_context(tenant_a):
            inv = InvoiceFactory()

            # Zero amount rejected -> chk_payment_amount_pos
            with pytest.raises(IntegrityError), transaction.atomic():
                Payment.objects.create(
                    invoice=inv,
                    kind=Payment.Kind.PAYMENT,
                    method=Payment.Method.CASH,
                    amount=Decimal("0.00"),
                )

            # Negative amount rejected even for refund (kind supplies sign)
            # -> chk_payment_amount_pos
            with pytest.raises(IntegrityError), transaction.atomic():
                Payment.objects.create(
                    invoice=inv,
                    kind=Payment.Kind.REFUND,
                    method=Payment.Method.CASH,
                    amount=Decimal("-100.00"),
                )

    def test_payment_idempotency_key_partial_unique_and_fk_protect(
        self, tenant_a: Any, tenant_b: Any
    ) -> None:
        with tenant_context(tenant_a):
            staff = StaffUserFactory()
            inv = InvoiceFactory()

            # Multiple NULL idempotency_key rows allowed
            p1 = PaymentFactory(invoice=inv, received_by=staff, idempotency_key=None)
            p2 = PaymentFactory(invoice=inv, received_by=staff, idempotency_key=None)
            assert p1.id != p2.id

            # Duplicate non-null idempotency_key in same tenant fails at DB
            PaymentFactory(invoice=inv, idempotency_key="pay-idem-fixed-01")
            with pytest.raises(IntegrityError), transaction.atomic():
                PaymentFactory(invoice=inv, idempotency_key="pay-idem-fixed-01")

            # FKs protect on delete
            with pytest.raises(ProtectedError):
                inv.delete()
            with pytest.raises(ProtectedError):
                staff.delete()

        # Same idempotency_key in tenant_b succeeds
        with tenant_context(tenant_b):
            pb = PaymentFactory(idempotency_key="pay-idem-fixed-01")
            assert pb.idempotency_key == "pay-idem-fixed-01"
