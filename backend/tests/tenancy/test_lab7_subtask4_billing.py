from decimal import Decimal
from typing import Any

import pytest
from django.db import IntegrityError, connection, transaction
from django.db.models.deletion import ProtectedError
from django_tenants.utils import tenant_context

from apps.billing.models import Invoice, InvoiceItem
from tests.factories.billing import InvoiceFactory, InvoiceItemFactory
from tests.factories.branches import BranchFactory
from tests.factories.catalog import PanelFactory, TestFactory, TestPriceFactory
from tests.factories.partners import ReferralPartnerFactory
from tests.factories.patients import PatientFactory


@pytest.mark.django_db
class TestBillingInvoiceModelsSchemaAndConstraints:
    def test_invoice_and_invoice_item_indexes_and_numeric_12_2(
        self, tenant_a: Any
    ) -> None:
        expected_indexes = {
            "invoice": {
                "uq_invoice_idempotency_key",
                "idx_invoice_patient_id",
                "idx_invoice_branch_id",
                "idx_invoice_referral_partner_id",
            },
            "invoice_item": {
                "idx_invoice_item_invoice_id",
                "idx_invoice_item_test_id",
                "idx_invoice_item_panel_id",
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

            # Verify numeric(12,2) on all money columns
            for table_name, money_cols in [
                ("invoice", ("subtotal", "discount_amount", "total")),
                ("invoice_item", ("unit_price", "line_total")),
            ]:
                for col in money_cols:
                    cursor.execute(
                        """
                        SELECT data_type, numeric_precision, numeric_scale
                        FROM information_schema.columns
                        WHERE table_schema = %s
                          AND table_name = %s
                          AND column_name = %s;
                        """,
                        [tenant_a.schema_name, table_name, col],
                    )
                    assert cursor.fetchone() == ("numeric", 12, 2)

            # Verify neither table has deleted_at
            for table_name in ("invoice", "invoice_item"):
                cursor.execute(
                    """
                    SELECT column_name
                    FROM information_schema.columns
                    WHERE table_schema = %s AND table_name = %s;
                    """,
                    [tenant_a.schema_name, table_name],
                )
                cols = {r[0] for r in cursor.fetchall()}
                assert "deleted_at" not in cols

    def test_invoice_idempotency_key_partial_unique_constraint(
        self, tenant_a: Any, tenant_b: Any
    ) -> None:
        with tenant_context(tenant_a):
            # Multiple NULL idempotency_key rows are permitted by partial index
            inv_null_1 = InvoiceFactory(idempotency_key=None)
            inv_null_2 = InvoiceFactory(idempotency_key=None)
            assert inv_null_1.id != inv_null_2.id

            # Duplicate non-null idempotency_key in same tenant fails at DB
            InvoiceFactory(idempotency_key="idem-fixed-001")
            with pytest.raises(IntegrityError), transaction.atomic():
                InvoiceFactory(idempotency_key="idem-fixed-001")

        # Same idempotency_key in another tenant succeeds (schema isolation)
        with tenant_context(tenant_b):
            inv_b = InvoiceFactory(idempotency_key="idem-fixed-001")
            assert inv_b.idempotency_key == "idem-fixed-001"

    def test_invoice_status_and_money_check_constraints(self, tenant_a: Any) -> None:
        with tenant_context(tenant_a):
            patient = PatientFactory()
            branch = BranchFactory()

            for valid_status in (
                Invoice.Status.UNPAID,
                Invoice.Status.PARTIAL,
                Invoice.Status.PAID,
                Invoice.Status.REFUNDED,
                Invoice.Status.CANCELLED,
            ):
                inv = InvoiceFactory(
                    patient=patient,
                    branch=branch,
                    status=valid_status,
                )
                assert inv.status == valid_status

            # Invalid status rejected by chk_invoice_status
            with pytest.raises(IntegrityError), transaction.atomic():
                Invoice.objects.create(
                    patient=patient,
                    branch=branch,
                    status="voided_invalid",
                )

            # Negative total rejected by chk_invoice_total_non_neg
            with pytest.raises(IntegrityError), transaction.atomic():
                Invoice.objects.create(
                    patient=patient,
                    branch=branch,
                    subtotal=Decimal("100.00"),
                    discount_amount=Decimal("0.00"),
                    total=Decimal("-10.00"),
                )

    def test_invoice_item_xor_and_snapshot_independence(self, tenant_a: Any) -> None:
        with tenant_context(tenant_a):
            inv = InvoiceFactory()
            test_obj = TestFactory(name="HbA1c")
            panel_obj = PanelFactory(name="Lipid Profile")
            tp = TestPriceFactory(
                test=test_obj,
                panel=None,
                price=Decimal("1500.00"),
            )

            # 1. Valid: test item with snapshot price
            item_test = InvoiceItemFactory(
                invoice=inv,
                test=test_obj,
                panel=None,
                description=test_obj.name,
                unit_price=tp.price,
                quantity=1,
                line_total=tp.price,
            )
            # Changing catalog price later never mutates billed item snapshot
            tp.price = Decimal("2200.00")
            tp.save()
            item_test.refresh_from_db()
            assert item_test.unit_price == Decimal("1500.00")

            # 2. Valid: panel item
            item_panel = InvoiceItemFactory(
                invoice=inv,
                test=None,
                panel=panel_obj,
                description=panel_obj.name,
                unit_price=Decimal("2000.00"),
                quantity=2,
                line_total=Decimal("4000.00"),
            )
            assert item_panel.panel_id == panel_obj.id

            # 3. Invalid: both test and panel set -> chk_invoice_item_test_xor_panel
            with pytest.raises(IntegrityError), transaction.atomic():
                InvoiceItem.objects.create(
                    invoice=inv,
                    test=test_obj,
                    panel=panel_obj,
                    description="Invalid Both",
                    unit_price=Decimal("500.00"),
                    quantity=1,
                    line_total=Decimal("500.00"),
                )

            # 4. Invalid: neither test nor panel set -> chk_invoice_item_test_xor_panel
            with pytest.raises(IntegrityError), transaction.atomic():
                InvoiceItem.objects.create(
                    invoice=inv,
                    test=None,
                    panel=None,
                    description="Invalid Neither",
                    unit_price=Decimal("500.00"),
                    quantity=1,
                    line_total=Decimal("500.00"),
                )

            # 5. Invalid: quantity <= 0 -> chk_invoice_item_quantity_pos
            with pytest.raises(IntegrityError), transaction.atomic():
                InvoiceItem.objects.create(
                    invoice=inv,
                    test=test_obj,
                    panel=None,
                    description="Zero Qty",
                    unit_price=Decimal("500.00"),
                    quantity=0,
                    line_total=Decimal("0.00"),
                )

    def test_invoice_and_invoice_item_fks_protect_on_delete(
        self, tenant_a: Any
    ) -> None:
        with tenant_context(tenant_a):
            branch = BranchFactory()
            patient = PatientFactory(branch=branch)
            partner = ReferralPartnerFactory()
            test_obj = TestFactory()
            inv = InvoiceFactory(
                patient=patient,
                branch=branch,
                referral_partner=partner,
            )
            InvoiceItemFactory(invoice=inv, test=test_obj, panel=None)

            with pytest.raises(ProtectedError):
                patient.delete()
            with pytest.raises(ProtectedError):
                branch.delete()
            with pytest.raises(ProtectedError):
                partner.delete()
            with pytest.raises(ProtectedError):
                inv.delete()
            with pytest.raises(ProtectedError):
                test_obj.delete()
