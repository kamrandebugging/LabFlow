"""Hardening tests for LabFlow Samples module (Phases 1.1-1.7, D1-D12).

Tests:
- 1.1: Audit + transfer guards (D5, D4)
- 1.2: Recollection guard + lineage FK (D3, D1)
- 1.3: Collection notes (D6)
- 1.4: Billing guards exclude REJECTED (D2)
- 1.5: Label print endpoint (D8)
- 1.6: Branch membership + BS-2 (D9)
- 1.7: Completion guard + event constraint (D10, D11)
- D12: Transfers discovery endpoint (GET /api/v1/transfers)
"""

import uuid
from decimal import Decimal
from typing import Any, cast

import jwt
import pytest
from django.conf import settings
from django.utils import timezone
from django_tenants.utils import tenant_context
from rest_framework.test import APIClient

from apps.accounts.models import AuditLog, Role, StaffUser
from apps.billing.models import Invoice, Payment
from apps.billing.services import CreditNoteService, InvoiceQueryService
from apps.branches.models import StaffBranch
from apps.core.models import Tenant
from apps.results.models import Result
from apps.results.services import _maybe_complete_sample
from apps.samples.models import Sample, SampleEvent, SampleTransfer
from apps.samples.services import (
    BranchCannotReceiveError,
    InvalidStateTransitionError,
    SampleHasResultsError,
    SampleService,
    TransferAlreadyOpenError,
    TransferService,
)
from tests.factories.accounts import StaffUserFactory
from tests.factories.billing import InvoiceFactory, InvoiceItemFactory, PaymentFactory
from tests.factories.branches import BranchFactory
from tests.factories.catalog import TestFactory
from tests.factories.patients import PatientFactory
from tests.factories.results import ResultFactory
from tests.factories.samples import SampleFactory, SampleTestFactory


def _staff_user(role: str = Role.OWNER, branch: Any = None) -> StaffUser:
    return cast(StaffUser, StaffUserFactory(role=role, branch=branch))


def _mint_jwt(staff_id: uuid.UUID, tenant_slug: str, role: str) -> str:
    signing_key = getattr(
        settings, "JWT_SIGNING_KEY", getattr(settings, "SECRET_KEY", "test-secret")
    )
    now = int(timezone.now().timestamp())
    payload = {
        "sub": str(staff_id),
        "tenant": tenant_slug,
        "role": role,
        "typ": "access",
        "jti": uuid.uuid4().hex,
        "iat": now,
        "exp": now + 3600,
        "iss": "labflow",
        "aud": "labflow-api",
    }
    return str(jwt.encode(payload, str(signing_key), algorithm="HS256"))


def _authenticate_client(
    client: APIClient,
    staff: StaffUser,
    tenant: Tenant,
    role: str = Role.OWNER,
) -> None:
    token = _mint_jwt(staff.id, tenant.slug, role)
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")


@pytest.fixture
def api_client(tenant_a: Tenant) -> APIClient:
    client = APIClient()
    client.defaults["HTTP_HOST"] = "tenant-a.localhost"
    return client


@pytest.mark.django_db
class TestSamplesHardening11:
    """1.1 Transfer guards + audit true prior status (D4, D5)."""

    def test_cancel_sample_with_open_transfer_raises_409(
        self, tenant_a: Tenant
    ) -> None:
        with tenant_context(tenant_a):
            b1 = BranchFactory(name="B1")
            b2 = BranchFactory(name="B2", is_collection_centre=False)
            actor = _staff_user(role=Role.OWNER, branch=b1)
            sample = SampleFactory(branch=b1, status=Sample.Status.COLLECTED)
            SampleTransfer.objects.create(
                sample=sample,
                from_branch=b1,
                to_branch=b2,
                status=SampleTransfer.Status.OPEN,
            )

            with pytest.raises(TransferAlreadyOpenError):
                SampleService.cancel_sample(
                    sample_id=sample.id, reason="Patient request", actor=actor
                )

    def test_receive_sample_with_open_transfer_raises_409(
        self, tenant_a: Tenant
    ) -> None:
        with tenant_context(tenant_a):
            b1 = BranchFactory(name="B1")
            b2 = BranchFactory(name="B2", is_collection_centre=False)
            actor = _staff_user(role=Role.TECHNICIAN, branch=b1)
            StaffBranch.objects.create(staff_user=actor, branch=b1)
            sample = SampleFactory(branch=b1, status=Sample.Status.COLLECTED)
            SampleTransfer.objects.create(
                sample=sample,
                from_branch=b1,
                to_branch=b2,
                status=SampleTransfer.Status.OPEN,
            )

            with pytest.raises(TransferAlreadyOpenError):
                SampleService.receive_sample(sample_id=sample.id, actor=actor)

    def test_receive_transfer_on_cancelled_or_rejected_sample_raises_409(
        self, tenant_a: Tenant
    ) -> None:
        with tenant_context(tenant_a):
            b1 = BranchFactory(name="B1")
            b2 = BranchFactory(name="B2", is_collection_centre=False)
            actor = _staff_user(role=Role.TECHNICIAN, branch=b2)
            StaffBranch.objects.create(staff_user=actor, branch=b2)

            # Cancelled sample
            s_cancel = SampleFactory(branch=b1, status=Sample.Status.CANCELLED)
            t1 = SampleTransfer.objects.create(
                sample=s_cancel,
                from_branch=b1,
                to_branch=b2,
                status=SampleTransfer.Status.OPEN,
            )
            with pytest.raises(InvalidStateTransitionError):
                TransferService.receive_transfer(transfer_id=t1.id, actor=actor)

            # Rejected sample
            s_rej = SampleFactory(branch=b1, status=Sample.Status.REJECTED)
            t2 = SampleTransfer.objects.create(
                sample=s_rej,
                from_branch=b1,
                to_branch=b2,
                status=SampleTransfer.Status.OPEN,
            )
            with pytest.raises(InvalidStateTransitionError):
                TransferService.receive_transfer(transfer_id=t2.id, actor=actor)

    def test_create_transfer_self_transfer_raises_422(self, tenant_a: Tenant) -> None:
        with tenant_context(tenant_a):
            b1 = BranchFactory(name="B1", is_collection_centre=False)
            actor = _staff_user(role=Role.OWNER, branch=b1)
            sample = SampleFactory(branch=b1, status=Sample.Status.COLLECTED)

            with pytest.raises(BranchCannotReceiveError):
                TransferService.create_transfer(
                    sample_id=sample.id, to_branch_id=b1.id, actor=actor
                )

    def test_reception_cannot_receive_transfer_via_api(
        self, tenant_a: Tenant, api_client: APIClient
    ) -> None:
        with tenant_context(tenant_a):
            b1 = BranchFactory(name="B1")
            b2 = BranchFactory(name="B2", is_collection_centre=False)
            reception = _staff_user(role=Role.RECEPTION, branch=b2)
            StaffBranch.objects.create(staff_user=reception, branch=b2)
            _authenticate_client(api_client, reception, tenant_a, Role.RECEPTION)

            sample = SampleFactory(branch=b1, status=Sample.Status.COLLECTED)
            transfer = SampleTransfer.objects.create(
                sample=sample,
                from_branch=b1,
                to_branch=b2,
                status=SampleTransfer.Status.OPEN,
            )

        resp = api_client.post(f"/api/v1/transfers/{transfer.id}/receive")
        assert resp.status_code == 403

    def test_reject_audit_records_true_prior_status(self, tenant_a: Tenant) -> None:
        with tenant_context(tenant_a):
            b1 = BranchFactory(name="B1")
            actor = _staff_user(role=Role.OWNER, branch=b1)

            # 1. Reject from COLLECTED
            s1 = SampleFactory(branch=b1, status=Sample.Status.COLLECTED)
            SampleService.reject_sample(
                sample_id=s1.id,
                reason_code=Sample.RejectionReasonCode.CLOTTED,
                note=None,
                actor=actor,
            )
            audit1 = (
                AuditLog.objects.filter(entity_id=s1.id, action="sample.rejected")
                .order_by("-at")
                .first()
            )
            assert audit1 is not None
            assert isinstance(audit1.after_jsonb, dict)
            assert audit1.after_jsonb.get("from_status") == "collected"
            assert audit1.after_jsonb.get("to_status") == "rejected"

            # 2. Reject from RECEIVED
            s2 = SampleFactory(branch=b1, status=Sample.Status.RECEIVED)
            SampleService.reject_sample(
                sample_id=s2.id,
                reason_code=Sample.RejectionReasonCode.HEMUSHED,
                note=None,
                actor=actor,
            )
            audit2 = (
                AuditLog.objects.filter(entity_id=s2.id, action="sample.rejected")
                .order_by("-at")
                .first()
            )
            assert audit2 is not None
            assert isinstance(audit2.after_jsonb, dict)
            assert audit2.after_jsonb.get("from_status") == "received"
            assert audit2.after_jsonb.get("to_status") == "rejected"


@pytest.mark.django_db
class TestSamplesHardening12:
    """1.2 Recollection guard + lineage FK + results exclusion (D3, D1)."""

    def test_recollect_sequential_second_call_409(self, tenant_a: Tenant) -> None:
        with tenant_context(tenant_a):
            b1 = BranchFactory(name="B1")
            actor = _staff_user(role=Role.OWNER, branch=b1)
            sample = SampleFactory(branch=b1, status=Sample.Status.REJECTED)
            test = TestFactory()
            SampleTestFactory(
                sample=sample, test=test, invoice_item__invoice=sample.invoice
            )

            # First recollection succeeds
            new_s = SampleService.recollect_sample(sample_id=sample.id, actor=actor)
            assert new_s.status == Sample.Status.COLLECTED
            assert new_s.recollected_from_id == sample.id

            # Second recollection fails with 409
            with pytest.raises(InvalidStateTransitionError) as exc_info:
                SampleService.recollect_sample(sample_id=sample.id, actor=actor)
            assert "already recollected" in str(exc_info.value).lower()

    def test_recollect_lineage_serialized_on_detail(
        self, tenant_a: Tenant, api_client: APIClient
    ) -> None:
        with tenant_context(tenant_a):
            b1 = BranchFactory(name="B1")
            owner = _staff_user(role=Role.OWNER, branch=b1)
            _authenticate_client(api_client, owner, tenant_a, Role.OWNER)

            old_sample = SampleFactory(
                branch=b1, status=Sample.Status.REJECTED, accession_id="OLD-1001"
            )
            test = TestFactory()
            SampleTestFactory(
                sample=old_sample, test=test, invoice_item__invoice=old_sample.invoice
            )

            new_sample = SampleService.recollect_sample(
                sample_id=old_sample.id, actor=owner
            )

        resp = api_client.get(f"/api/v1/samples/{new_sample.id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data.get("recollected_from_id") == str(old_sample.id)
        assert data.get("recollected_from_accession") == "OLD-1001"

    def test_reject_from_in_process_with_only_withdrawn_results_succeeds(
        self, tenant_a: Tenant
    ) -> None:
        with tenant_context(tenant_a):
            b1 = BranchFactory(name="B1")
            actor = _staff_user(role=Role.OWNER, branch=b1)
            sample = SampleFactory(branch=b1, status=Sample.Status.IN_PROCESS)
            test = TestFactory()
            SampleTestFactory(
                sample=sample, test=test, invoice_item__invoice=sample.invoice
            )

            # Create a WITHDRAWN result
            ResultFactory(
                sample=sample,
                test=test,
                status=Result.Status.WITHDRAWN,
            )

            # Rejection should SUCCEED per D1
            SampleService.reject_sample(
                sample_id=sample.id,
                reason_code=Sample.RejectionReasonCode.CLOTTED,
                note=None,
                actor=actor,
            )
            sample.refresh_from_db()
            assert sample.status == Sample.Status.REJECTED

    def test_reject_with_entered_or_approved_result_raises_409(
        self, tenant_a: Tenant
    ) -> None:
        with tenant_context(tenant_a):
            b1 = BranchFactory(name="B1")
            actor = _staff_user(role=Role.OWNER, branch=b1)
            sample = SampleFactory(branch=b1, status=Sample.Status.IN_PROCESS)
            test = TestFactory()
            SampleTestFactory(
                sample=sample, test=test, invoice_item__invoice=sample.invoice
            )

            ResultFactory(
                sample=sample,
                test=test,
                status=Result.Status.ENTERED,
            )

            with pytest.raises(SampleHasResultsError):
                SampleService.reject_sample(
                    sample_id=sample.id,
                    reason_code=Sample.RejectionReasonCode.CLOTTED,
                    note=None,
                    actor=actor,
                )

    def test_recollect_copies_only_untested_or_withdrawn_tests(
        self, tenant_a: Tenant
    ) -> None:
        with tenant_context(tenant_a):
            b1 = BranchFactory(name="B1")
            actor = _staff_user(role=Role.OWNER, branch=b1)
            sample = SampleFactory(branch=b1, status=Sample.Status.REJECTED)
            test1 = TestFactory(name="T1")
            test2 = TestFactory(name="T2")
            SampleTestFactory(
                sample=sample, test=test1, invoice_item__invoice=sample.invoice
            )
            SampleTestFactory(
                sample=sample, test=test2, invoice_item__invoice=sample.invoice
            )

            # test1 has a WITHDRAWN result, test2 has no result
            ResultFactory(sample=sample, test=test1, status=Result.Status.WITHDRAWN)

            new_sample = SampleService.recollect_sample(
                sample_id=sample.id, actor=actor
            )
            copied_test_ids = set(
                new_sample.sample_tests.values_list("test_id", flat=True)
            )
            # Both T1 (withdrawn) and T2 (untested) are copied
            assert test1.id in copied_test_ids
            assert test2.id in copied_test_ids


@pytest.mark.django_db
class TestSamplesHardening13:
    """1.3 Collection notes (D6)."""

    def test_collection_notes_roundtrip_to_detail_and_events(
        self, tenant_a: Tenant, api_client: APIClient
    ) -> None:
        with tenant_context(tenant_a):
            b1 = BranchFactory(name="B1")
            owner = _staff_user(role=Role.OWNER, branch=b1)
            StaffBranch.objects.create(staff_user=owner, branch=b1)
            _authenticate_client(api_client, owner, tenant_a, Role.OWNER)

            patient = PatientFactory(branch=b1)
            invoice = InvoiceFactory(patient=patient, branch=b1)
            item = InvoiceItemFactory(invoice=invoice)

        payload = {
            "invoice_id": str(invoice.id),
            "invoice_item_ids": [str(item.id)],
            "notes": "Patient was fasting for 12 hours.",
        }
        resp = api_client.post("/api/v1/samples", payload, format="json")
        assert resp.status_code == 201
        sample_id = resp.json()["id"]

        detail_resp = api_client.get(f"/api/v1/samples/{sample_id}")
        assert detail_resp.status_code == 200
        data = detail_resp.json()
        assert data.get("collection_notes") == "Patient was fasting for 12 hours."

        # Verify initial COLLECTED event carries the note
        collected_event = next(
            (e for e in data.get("events", []) if e.get("event") == "COLLECTED"), None
        )
        assert collected_event is not None
        assert (
            collected_event.get("payload", {}).get("note")
            == "Patient was fasting for 12 hours."
        )

    def test_collection_notes_validation_and_unknown_fields(
        self, tenant_a: Tenant, api_client: APIClient
    ) -> None:
        with tenant_context(tenant_a):
            b1 = BranchFactory(name="B1")
            owner = _staff_user(role=Role.OWNER, branch=b1)
            StaffBranch.objects.create(staff_user=owner, branch=b1)
            _authenticate_client(api_client, owner, tenant_a, Role.OWNER)

            patient = PatientFactory(branch=b1)
            invoice = InvoiceFactory(patient=patient, branch=b1)
            InvoiceItemFactory(invoice=invoice)

        # > 500 chars 422
        long_notes = "a" * 501
        resp = api_client.post(
            "/api/v1/samples",
            {"invoice_id": str(invoice.id), "notes": long_notes},
            format="json",
        )
        assert resp.status_code == 422

        # Unknown fields 422
        resp = api_client.post(
            "/api/v1/samples",
            {"invoice_id": str(invoice.id), "random_field": "disallowed"},
            format="json",
        )
        assert resp.status_code == 422


@pytest.mark.django_db
class TestSamplesHardening14:
    """1.4 Billing guards exclude REJECTED (D2)."""

    def test_invoice_cancel_allowed_with_rejected_sample(
        self, tenant_a: Tenant
    ) -> None:
        with tenant_context(tenant_a):
            b1 = BranchFactory(name="B1")
            actor = _staff_user(role=Role.OWNER, branch=b1)
            invoice = InvoiceFactory(
                branch=b1, status=Invoice.Status.UNPAID, total=Decimal("1000.00")
            )
            SampleFactory(invoice=invoice, branch=b1, status=Sample.Status.REJECTED)

            # Invoice cancellation should succeed (does not raise
            # SampleAlreadyCollected)
            InvoiceQueryService.cancel_invoice(
                invoice_id=invoice.id, reason="Patient request", actor=actor
            )
            invoice.refresh_from_db()
            assert invoice.status == Invoice.Status.CANCELLED

    def test_line_cancel_allowed_with_rejected_sample(self, tenant_a: Tenant) -> None:
        with tenant_context(tenant_a):
            b1 = BranchFactory(name="B1")
            actor = _staff_user(role=Role.OWNER, branch=b1)
            invoice = InvoiceFactory(
                branch=b1, status=Invoice.Status.UNPAID, total=Decimal("1000.00")
            )
            item = InvoiceItemFactory(invoice=invoice, unit_price=Decimal("1000.00"))
            sample = SampleFactory(
                invoice=invoice, branch=b1, status=Sample.Status.REJECTED
            )
            test = TestFactory()
            SampleTestFactory(sample=sample, invoice_item=item, test=test)

            # Line cancellation should succeed
            InvoiceQueryService.cancel_line(
                invoice_id=invoice.id,
                item_id=item.id,
                reason="Line cancel",
                actor=actor,
            )
            item.refresh_from_db()
            assert item.is_cancelled is True

    def test_credit_note_allowed_with_rejected_sample(self, tenant_a: Tenant) -> None:
        with tenant_context(tenant_a):
            b1 = BranchFactory(name="B1")
            actor = _staff_user(role=Role.OWNER, branch=b1)
            invoice = InvoiceFactory(
                branch=b1, status=Invoice.Status.PAID, total=Decimal("1000.00")
            )
            InvoiceItemFactory(invoice=invoice, unit_price=Decimal("1000.00"))
            PaymentFactory(
                invoice=invoice,
                amount=Decimal("1000.00"),
                kind=Payment.Kind.PAYMENT,
                method=Payment.Method.CASH,
                received_by=actor,
            )
            SampleFactory(invoice=invoice, branch=b1, status=Sample.Status.REJECTED)

            # Credit note should succeed
            note, _ = CreditNoteService.issue(
                invoice_id=invoice.id,
                amount=Decimal("1000.00"),
                reason="Customer declined redraw",
                method=Payment.Method.CASH,
                idempotency_key=str(uuid.uuid4()),
                actor=actor,
            )
            assert note is not None
            invoice.refresh_from_db()
            assert invoice.credit_notes.exists()


@pytest.mark.django_db
class TestSamplesHardening15:
    """1.5 Label print endpoint + audit (D8)."""

    def test_get_label_writes_no_audit_post_print_writes_one(
        self, tenant_a: Tenant, api_client: APIClient
    ) -> None:
        with tenant_context(tenant_a):
            b1 = BranchFactory(name="B1")
            owner = _staff_user(role=Role.OWNER, branch=b1)
            StaffBranch.objects.create(staff_user=owner, branch=b1)
            _authenticate_client(api_client, owner, tenant_a, Role.OWNER)

            sample = SampleFactory(branch=b1, status=Sample.Status.COLLECTED)

            count_before = AuditLog.objects.filter(
                entity_id=sample.id, action="sample.label_printed"
            ).count()

        # GET /samples/{id}/label preview — NO audit row
        get_resp = api_client.get(f"/api/v1/samples/{sample.id}/label")
        assert get_resp.status_code == 200

        with tenant_context(tenant_a):
            count_after_get = AuditLog.objects.filter(
                entity_id=sample.id, action="sample.label_printed"
            ).count()
            assert count_after_get == count_before

        # POST /samples/{id}/label/print — exactly ONE audit row
        post_resp = api_client.post(f"/api/v1/samples/{sample.id}/label/print")
        assert post_resp.status_code == 200

        with tenant_context(tenant_a):
            count_after_post = AuditLog.objects.filter(
                entity_id=sample.id, action="sample.label_printed"
            ).count()
            assert count_after_post == count_before + 1

    def test_pathologist_label_endpoints_403(
        self, tenant_a: Tenant, api_client: APIClient
    ) -> None:
        with tenant_context(tenant_a):
            b1 = BranchFactory(name="B1")
            pathologist = _staff_user(role=Role.PATHOLOGIST, branch=b1)
            _authenticate_client(api_client, pathologist, tenant_a, Role.PATHOLOGIST)
            sample = SampleFactory(branch=b1, status=Sample.Status.COLLECTED)

        assert api_client.get(f"/api/v1/samples/{sample.id}/label").status_code == 403
        assert (
            api_client.post(f"/api/v1/samples/{sample.id}/label/print").status_code
            == 403
        )


@pytest.mark.django_db
class TestSamplesHardening16:
    """1.6 Branch membership + zero-assignment BS-2 (D9, D7)."""

    def test_two_branch_manager_acts_at_non_home_branch(
        self, tenant_a: Tenant, api_client: APIClient
    ) -> None:
        with tenant_context(tenant_a):
            b1 = BranchFactory(name="Home Branch B1")
            b2 = BranchFactory(name="Assigned Branch B2", is_collection_centre=False)
            manager = _staff_user(role=Role.MANAGER, branch=b1)
            # Assigned to b1 and b2
            StaffBranch.objects.create(staff_user=manager, branch=b1)
            StaffBranch.objects.create(staff_user=manager, branch=b2)
            _authenticate_client(api_client, manager, tenant_a, Role.MANAGER)

            # Sample held at B2 (non-home branch)
            sample = SampleFactory(branch=b2, status=Sample.Status.COLLECTED)

        # Receive sample held at B2 succeeds
        resp = api_client.post(f"/api/v1/samples/{sample.id}/receive")
        assert resp.status_code == 200
        sample.refresh_from_db()
        assert sample.status == Sample.Status.RECEIVED

    def test_zero_assignment_staff_gets_403_on_mutating_endpoints(
        self, tenant_a: Tenant, api_client: APIClient
    ) -> None:
        with tenant_context(tenant_a):
            b1 = BranchFactory(name="B1")
            # Technician with NO branch assignments
            tech = _staff_user(role=Role.TECHNICIAN, branch=None)
            _authenticate_client(api_client, tech, tenant_a, Role.TECHNICIAN)

            sample = SampleFactory(branch=b1, status=Sample.Status.COLLECTED)

        # All mutating actions return 403 branch_scope_denied
        assert (
            api_client.post(f"/api/v1/samples/{sample.id}/receive").status_code == 403
        )
        assert (
            api_client.post(
                f"/api/v1/samples/{sample.id}/reject",
                {"reason_code": "clotted"},
                format="json",
            ).status_code
            == 403
        )
        assert (
            api_client.post(
                f"/api/v1/samples/{sample.id}/cancel", {"reason": "Test"}
            ).status_code
            == 403
        )
        assert (
            api_client.post(f"/api/v1/samples/{sample.id}/recollect").status_code == 403
        )

    def test_reception_cannot_reject_received_sample(
        self, tenant_a: Tenant, api_client: APIClient
    ) -> None:
        with tenant_context(tenant_a):
            b1 = BranchFactory(name="B1")
            reception = _staff_user(role=Role.RECEPTION, branch=b1)
            StaffBranch.objects.create(staff_user=reception, branch=b1)
            _authenticate_client(api_client, reception, tenant_a, Role.RECEPTION)

            sample = SampleFactory(branch=b1, status=Sample.Status.RECEIVED)

        # Reception may only reject from collected (D7b) -> 403
        resp = api_client.post(
            f"/api/v1/samples/{sample.id}/reject",
            {"reason_code": "clotted"},
            format="json",
        )
        assert resp.status_code == 403


@pytest.mark.django_db
class TestSamplesHardening17:
    """1.7 Completion guard + event constraint (D10, D11)."""

    def test_maybe_complete_sample_excludes_rejected_and_cancelled(
        self, tenant_a: Tenant
    ) -> None:
        with tenant_context(tenant_a):
            b1 = BranchFactory(name="B1")
            actor = _staff_user(role=Role.OWNER, branch=b1)

            # Rejected sample
            s_rej = SampleFactory(branch=b1, status=Sample.Status.REJECTED)
            assert not _maybe_complete_sample(
                sample_id=s_rej.id, actor=actor, ip=None, user_agent=None
            )
            s_rej.refresh_from_db()
            assert s_rej.status == Sample.Status.REJECTED

            # Cancelled sample
            s_can = SampleFactory(branch=b1, status=Sample.Status.CANCELLED)
            assert not _maybe_complete_sample(
                sample_id=s_can.id, actor=actor, ip=None, user_agent=None
            )
            s_can.refresh_from_db()
            assert s_can.status == Sample.Status.CANCELLED

    def test_sample_event_append_only_guard(self, tenant_a: Tenant) -> None:
        with tenant_context(tenant_a):
            b1 = BranchFactory(name="B1")
            actor = _staff_user(role=Role.OWNER, branch=b1)
            sample = SampleFactory(branch=b1, status=Sample.Status.COLLECTED)

            event = SampleEvent.objects.create(
                sample=sample,
                event=SampleEvent.EventType.COLLECTED,
                actor=actor,
                branch=b1,
            )

            # Updating raises
            event.note = "Tampered note"
            with pytest.raises(RuntimeError):
                event.save()

            # Deleting raises
            with pytest.raises(RuntimeError):
                event.delete()


@pytest.mark.django_db
class TestTransfersDiscoveryD12:
    """D12: GET /api/v1/transfers list endpoint with scoping."""

    def test_transfers_list_incoming_outgoing_scoping(
        self, tenant_a: Tenant, api_client: APIClient
    ) -> None:
        with tenant_context(tenant_a):
            b1 = BranchFactory(name="Branch 1")
            b2 = BranchFactory(name="Branch 2", is_collection_centre=False)
            tech_b2 = _staff_user(role=Role.TECHNICIAN, branch=b2)
            StaffBranch.objects.create(staff_user=tech_b2, branch=b2)

            sample = SampleFactory(branch=b1, accession_id="TR-1001")
            transfer = SampleTransfer.objects.create(
                sample=sample,
                from_branch=b1,
                to_branch=b2,
                status=SampleTransfer.Status.OPEN,
                dispatched_at=timezone.now(),
            )
            _authenticate_client(api_client, tech_b2, tenant_a, Role.TECHNICIAN)

        # Tech at B2 queries incoming open transfers
        resp = api_client.get("/api/v1/transfers?status=open&direction=incoming")
        assert resp.status_code == 200
        results = resp.json().get("results", resp.json())
        assert any(t["id"] == str(transfer.id) for t in results)

    def test_invoice_reference_resolves_patient_mrn(self, tenant_a: Tenant) -> None:
        """Resolve invoice reference by patient MRN as well as INV-XXXXXXXX number."""
        from apps.billing.views import _resolve_invoice_reference

        with tenant_context(tenant_a):
            b1 = BranchFactory(name="Branch 1")
            owner = _staff_user(role=Role.OWNER, branch=b1)
            sample: Any = SampleFactory(branch=b1, accession_id="MRN-TEST-1")
            invoice: Any = sample.invoice
            assert invoice.patient is not None
            mrn = invoice.patient.mrn
            resolved_by_mrn = _resolve_invoice_reference(owner, mrn)
            assert resolved_by_mrn == invoice.id

            # Non-existent MRN returns None
            resolved_missing = _resolve_invoice_reference(owner, "MRN-NON-EXISTENT")
            assert resolved_missing is None
