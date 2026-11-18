"""Credit-note cancellation for paid / partially paid invoices.

Append-only reversal documents: the original invoice, its items and its
payments are never modified, and the credit note is the reversal record.
"""

import itertools
from decimal import Decimal
from typing import Any

import pytest
from django.test import Client
from django_tenants.utils import tenant_context

from apps.accounts.auth_service import AuthService
from apps.accounts.models import Role
from apps.billing.models import CreditNote, Invoice, Payment
from tests.factories.billing import InvoiceFactory, PaymentFactory
from tests.factories.branches import BranchFactory
from tests.factories.patients import PatientFactory
from tests.factories.staff_user import StaffUserFactory

INVOICES_URL = "/api/v1/invoices"
_key_counter = itertools.count(1)


def _next_key() -> str:
    return f"cn-test-key-{next(_key_counter)}"


@pytest.fixture
def auth_headers() -> Any:
    def _make_headers(staff_user: Any, tenant_id: str = "tenant_a") -> dict[str, str]:
        slug = str(tenant_id).replace("_", "-")
        session = AuthService.create_session(user=staff_user, tenant_id=tenant_id)
        return {
            "Authorization": f"Bearer {session['access']}",
            "Host": f"{slug}.localhost",
        }

    return _make_headers


@pytest.fixture
def cn_setup(tenant_a: Any) -> dict[str, Any]:
    with tenant_context(tenant_a):
        branch = BranchFactory(code="CN1", name="Credit Note Lab")
        owner = StaffUserFactory(role=Role.OWNER, branch=None, email="cn_owner@t.com")
        manager = StaffUserFactory(
            role=Role.MANAGER, branch=branch, email="cn_manager@t.com"
        )
        receptionist = StaffUserFactory(
            role=Role.RECEPTION, branch=branch, email="cn_recep@t.com"
        )
        patient = PatientFactory(branch=branch)
        return {
            "branch": branch,
            "owner": owner,
            "manager": manager,
            "receptionist": receptionist,
            "patient": patient,
        }


def _paid_invoice(setup: dict[str, Any], amount: str = "1500.00") -> Invoice:
    invoice = InvoiceFactory(
        patient=setup["patient"],
        branch=setup["branch"],
        status=Invoice.Status.PAID,
        subtotal=Decimal(amount),
        total=Decimal(amount),
    )
    PaymentFactory(
        invoice=invoice,
        kind=Payment.Kind.PAYMENT,
        method=Payment.Method.CASH,
        amount=Decimal(amount),
        received_by=setup["owner"],
    )
    return invoice


@pytest.mark.django_db
def test_credit_note_is_sequential_append_only_and_visible_in_history(
    tenant_a: Any, cn_setup: dict[str, Any], auth_headers: Any
) -> None:
    client = Client()
    headers = auth_headers(cn_setup["owner"])

    with tenant_context(tenant_a):
        invoice = _paid_invoice(cn_setup)
        first_id = invoice.id
        second = _paid_invoice(cn_setup, "900.00")

    response = client.post(
        f"{INVOICES_URL}/{first_id}/credit-notes",
        data={"amount": "1500.00", "reason": "Invoice raised twice"},
        content_type="application/json",
        HTTP_IDEMPOTENCY_KEY=_next_key(),
        **headers,
    )
    assert response.status_code == 201, response.content
    body = response.json()
    assert body["number"] == "CN-000001"
    assert body["amount"] == "1500.00"
    assert body["reason"] == "Invoice raised twice"

    second_response = client.post(
        f"{INVOICES_URL}/{second.id}/credit-notes",
        data={"amount": "900.00", "reason": "Duplicate charge"},
        content_type="application/json",
        HTTP_IDEMPOTENCY_KEY=_next_key(),
        **headers,
    )
    assert second_response.status_code == 201, second_response.content
    assert second_response.json()["number"] == "CN-000002"

    with tenant_context(tenant_a):
        invoice = Invoice.objects.get(pk=first_id)
        # Money fields and payment rows are untouched; only status moves to
        # reflect the full reversal (credit notes feed the BL-6 derivation).
        assert invoice.status == Invoice.Status.REFUNDED
        assert invoice.total == Decimal("1500.00")
        assert invoice.payments.count() == 1
        assert CreditNote.objects.filter(invoice=invoice).count() == 1

    detail = client.get(f"{INVOICES_URL}/{first_id}", **headers)
    assert detail.status_code == 200
    assert len(detail.json()["credit_notes"]) == 1
    assert detail.json()["status"] == "refunded"
    # Net revenue = payments - refunds - credit notes.
    assert detail.json()["net_paid"] == "1500.00"
    assert detail.json()["net_revenue"] == "0.00"

    history = client.get(f"{INVOICES_URL}/{first_id}/history", **headers)
    assert history.status_code == 200
    events = history.json()["events"]
    notes = [e for e in events if e["event"] == "credit_note"]
    assert len(notes) == 1
    assert notes[0]["amount"] == "1500.00"
    assert notes[0]["reason"] == "Invoice raised twice"
    assert notes[0]["number"] == "CN-000001"


@pytest.mark.django_db
def test_credit_note_rejects_amount_above_net_paid(
    tenant_a: Any, cn_setup: dict[str, Any], auth_headers: Any
) -> None:
    with tenant_context(tenant_a):
        invoice = _paid_invoice(cn_setup)
        invoice_id = invoice.id

    response = Client().post(
        f"{INVOICES_URL}/{invoice_id}/credit-notes",
        data={"amount": "1500.01", "reason": "Too much"},
        content_type="application/json",
        HTTP_IDEMPOTENCY_KEY=_next_key(),
        **auth_headers(cn_setup["owner"]),
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "credit_note_exceeds_net_paid"


@pytest.mark.django_db
def test_credit_note_requires_full_reversal(
    tenant_a: Any, cn_setup: dict[str, Any], auth_headers: Any
) -> None:
    with tenant_context(tenant_a):
        invoice = _paid_invoice(cn_setup)
        invoice_id = invoice.id

    response = Client().post(
        f"{INVOICES_URL}/{invoice_id}/credit-notes",
        data={"amount": "500.00", "reason": "Partial"},
        content_type="application/json",
        HTTP_IDEMPOTENCY_KEY=_next_key(),
        **auth_headers(cn_setup["owner"]),
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "credit_note_amount_mismatch"


@pytest.mark.django_db
def test_credit_note_reason_is_mandatory(
    tenant_a: Any, cn_setup: dict[str, Any], auth_headers: Any
) -> None:
    with tenant_context(tenant_a):
        invoice = _paid_invoice(cn_setup)
        invoice_id = invoice.id

    response = Client().post(
        f"{INVOICES_URL}/{invoice_id}/credit-notes",
        data={"amount": "1500.00", "reason": "   "},
        content_type="application/json",
        HTTP_IDEMPOTENCY_KEY=_next_key(),
        **auth_headers(cn_setup["owner"]),
    )
    assert response.status_code == 422


@pytest.mark.django_db
def test_credit_note_requires_paid_invoice(
    tenant_a: Any, cn_setup: dict[str, Any], auth_headers: Any
) -> None:
    with tenant_context(tenant_a):
        invoice = InvoiceFactory(
            patient=cn_setup["patient"],
            branch=cn_setup["branch"],
            status=Invoice.Status.UNPAID,
        )
        invoice_id = invoice.id

    response = Client().post(
        f"{INVOICES_URL}/{invoice_id}/credit-notes",
        data={"amount": "1500.00", "reason": "Not paid"},
        content_type="application/json",
        HTTP_IDEMPOTENCY_KEY=_next_key(),
        **auth_headers(cn_setup["owner"]),
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "invalid_state_transition"


@pytest.mark.django_db
def test_credit_note_forbidden_for_reception(
    tenant_a: Any, cn_setup: dict[str, Any], auth_headers: Any
) -> None:
    with tenant_context(tenant_a):
        invoice = _paid_invoice(cn_setup)
        invoice_id = invoice.id

    response = Client().post(
        f"{INVOICES_URL}/{invoice_id}/credit-notes",
        data={"amount": "1500.00", "reason": "Front desk"},
        content_type="application/json",
        **auth_headers(cn_setup["receptionist"]),
    )
    assert response.status_code == 403


@pytest.mark.django_db
def test_unpaid_cancel_path_is_unchanged(
    tenant_a: Any, cn_setup: dict[str, Any], auth_headers: Any
) -> None:
    with tenant_context(tenant_a):
        invoice = InvoiceFactory(
            patient=cn_setup["patient"],
            branch=cn_setup["branch"],
            status=Invoice.Status.UNPAID,
        )
        invoice_id = invoice.id

    response = Client().post(
        f"{INVOICES_URL}/{invoice_id}/cancel",
        data={"reason": "Patient left"},
        content_type="application/json",
        **auth_headers(cn_setup["receptionist"]),
    )
    assert response.status_code == 200
    with tenant_context(tenant_a):
        assert Invoice.objects.get(pk=invoice_id).status == Invoice.Status.CANCELLED


@pytest.mark.django_db
def test_full_credit_note_refunds_status_and_zeroes_revenue(
    tenant_a: Any, cn_setup: dict[str, Any], auth_headers: Any
) -> None:
    """PKR 2400 paid + PKR 2400 credit note -> refunded, net revenue 0."""
    client = Client()
    headers = auth_headers(cn_setup["owner"])

    with tenant_context(tenant_a):
        invoice = _paid_invoice(cn_setup, "2400.00")
        invoice_id = invoice.id

    response = client.post(
        f"{INVOICES_URL}/{invoice_id}/credit-notes",
        data={"amount": "2400.00", "reason": "Treatment cancelled"},
        content_type="application/json",
        HTTP_IDEMPOTENCY_KEY=_next_key(),
        **headers,
    )
    assert response.status_code == 201, response.content

    detail = client.get(f"{INVOICES_URL}/{invoice_id}", **headers)
    assert detail.status_code == 200
    body = detail.json()
    assert body["status"] == "refunded"
    assert body["total"] == "2400.00"
    assert body["net_paid"] == "2400.00"
    assert body["net_revenue"] == "0.00"
    assert len(body["credit_notes"]) == 1

    listing = client.get(INVOICES_URL, **headers)
    assert listing.status_code == 200
    rows = listing.json()["results"]
    row = next(r for r in rows if r["id"] == str(invoice_id))
    assert row["status"] == "refunded"
    assert row["net_revenue"] == "0.00"
    # Daily total is billed - refunds - credit notes, computed server-side.
    assert listing.json()["daily_total"] == "0.00"

    # A fully credited invoice cannot be reversed twice.
    second = client.post(
        f"{INVOICES_URL}/{invoice_id}/credit-notes",
        data={"amount": "2400.00", "reason": "Again"},
        content_type="application/json",
        HTTP_IDEMPOTENCY_KEY=_next_key(),
        **headers,
    )
    assert second.status_code == 409
    assert second.json()["error"]["code"] == "invalid_state_transition"

    with tenant_context(tenant_a):
        assert CreditNote.objects.filter(invoice_id=invoice_id).count() == 1


def test_partial_reversal_derives_partial_status() -> None:
    """A credit note smaller than net_paid keeps the partial status value."""
    from apps.billing.services import _derive_invoice_status

    assert (
        _derive_invoice_status(
            total=Decimal("1000.00"),
            paid_sum=Decimal("1000.00"),
            refund_sum=Decimal("0.00"),
            credit_sum=Decimal("400.00"),
        )
        == Invoice.Status.PARTIAL
    )
    assert (
        _derive_invoice_status(
            total=Decimal("1000.00"),
            paid_sum=Decimal("1000.00"),
            refund_sum=Decimal("0.00"),
            credit_sum=Decimal("1000.00"),
        )
        == Invoice.Status.REFUNDED
    )


@pytest.mark.django_db
def test_payment_rejected_after_full_credit_note(
    tenant_a: Any, cn_setup: dict[str, Any], auth_headers: Any
) -> None:
    """A fully reversed invoice cannot collect more money afterwards."""
    client = Client()
    headers = auth_headers(cn_setup["owner"])

    with tenant_context(tenant_a):
        invoice = _paid_invoice(cn_setup, "2400.00")
        invoice_id = invoice.id

    note = client.post(
        f"{INVOICES_URL}/{invoice_id}/credit-notes",
        data={"amount": "2400.00", "reason": "Double entry"},
        content_type="application/json",
        HTTP_IDEMPOTENCY_KEY=_next_key(),
        **headers,
    )
    assert note.status_code == 201, note.content

    payment = client.post(
        f"{INVOICES_URL}/{invoice_id}/payments",
        data={
            "kind": "payment",
            "method": "cash",
            "amount": "700.00",
            "reference": "Late cash",
        },
        content_type="application/json",
        HTTP_IDEMPOTENCY_KEY="cn-after-reversal-1",
        **headers,
    )
    assert payment.status_code == 409
    assert payment.json()["error"]["code"] == "invalid_state_transition"

    detail = client.get(f"{INVOICES_URL}/{invoice_id}", **headers).json()
    assert detail["status"] == "refunded"
    assert detail["net_paid"] == "2400.00"
    assert len(detail["payments"]) == 1


@pytest.mark.django_db
def test_credit_note_idempotent_replay_and_tier(
    tenant_a: Any, cn_setup: dict[str, Any], auth_headers: Any
) -> None:
    """Same key + payload replays the original; >PKR 5,000 needs the Owner."""
    client = Client()
    headers = auth_headers(cn_setup["owner"])
    manager_headers = auth_headers(cn_setup["manager"])

    with tenant_context(tenant_a):
        invoice = _paid_invoice(cn_setup, "6000.00")
        invoice_id = invoice.id

    # A Manager cannot reverse more than the PKR 5,000 ceiling.
    blocked = client.post(
        f"{INVOICES_URL}/{invoice_id}/credit-notes",
        data={"amount": "6000.00", "reason": "Big reversal"},
        content_type="application/json",
        HTTP_IDEMPOTENCY_KEY="cn-tier-1",
        **manager_headers,
    )
    assert blocked.status_code == 403
    assert blocked.json()["error"]["code"] == "owner_approval_required"

    payload = {"amount": "6000.00", "reason": "Big reversal", "method": "cash"}
    first = client.post(
        f"{INVOICES_URL}/{invoice_id}/credit-notes",
        data=payload,
        content_type="application/json",
        HTTP_IDEMPOTENCY_KEY="cn-idem-1",
        **headers,
    )
    assert first.status_code == 201, first.content

    replay = client.post(
        f"{INVOICES_URL}/{invoice_id}/credit-notes",
        data=payload,
        content_type="application/json",
        HTTP_IDEMPOTENCY_KEY="cn-idem-1",
        **headers,
    )
    assert replay.status_code == 200
    assert replay.json()["id"] == first.json()["id"]

    different = client.post(
        f"{INVOICES_URL}/{invoice_id}/credit-notes",
        data={"amount": "6000.00", "reason": "Other reason"},
        content_type="application/json",
        HTTP_IDEMPOTENCY_KEY="cn-idem-1",
        **headers,
    )
    assert different.status_code == 409
    assert different.json()["error"]["code"] == "idempotency_key_reused"


@pytest.mark.django_db
def test_void_restores_revenue_without_deleting_rows(
    tenant_a: Any, cn_setup: dict[str, Any], auth_headers: Any
) -> None:
    """Owner void is append-only: the CN row stays, revenue comes back."""
    client = Client()
    headers = auth_headers(cn_setup["owner"])

    with tenant_context(tenant_a):
        invoice = _paid_invoice(cn_setup, "10700.00")
        invoice_id = invoice.id

    issued = client.post(
        f"{INVOICES_URL}/{invoice_id}/credit-notes",
        data={"amount": "10700.00", "reason": "Double entry", "method": "cash"},
        content_type="application/json",
        HTTP_IDEMPOTENCY_KEY="cn-void-1",
        **headers,
    )
    assert issued.status_code == 201, issued.content
    note_id = issued.json()["id"]

    detail = client.get(f"{INVOICES_URL}/{invoice_id}", **headers).json()
    assert detail["status"] == "refunded"
    assert detail["net_revenue"] == "0.00"

    # A partial note of PKR 10,000 on net paid 10,700 is rejected.
    with tenant_context(tenant_a):
        partial_invoice = _paid_invoice(cn_setup, "10700.00")
        partial_id = partial_invoice.id
    other = client.post(
        f"{INVOICES_URL}/{partial_id}/credit-notes",
        data={"amount": "10000.00", "reason": "Partial"},
        content_type="application/json",
        HTTP_IDEMPOTENCY_KEY="cn-void-2",
        **headers,
    )
    assert other.status_code == 422
    assert other.json()["error"]["code"] == "credit_note_amount_mismatch"

    voided = client.post(
        f"{INVOICES_URL}/{invoice_id}/credit-notes/{note_id}/void",
        data={"reason": "Issued by mistake"},
        content_type="application/json",
        **headers,
    )
    assert voided.status_code == 200, voided.content
    assert voided.json()["voided_at"]
    assert voided.json()["number"] == issued.json()["number"]

    detail = client.get(f"{INVOICES_URL}/{invoice_id}", **headers).json()
    assert detail["status"] == "paid"
    assert detail["net_revenue"] == "10700.00"
    assert len(detail["credit_notes"]) == 1
    assert detail["credit_notes"][0]["voided_at"]

    history = client.get(f"{INVOICES_URL}/{invoice_id}/history", **headers).json()
    events = [e["event"] for e in history["events"]]
    assert "credit_note" in events
    assert "credit_note_voided" in events

    with tenant_context(tenant_a):
        assert CreditNote.objects.filter(invoice_id=invoice_id).count() == 1
