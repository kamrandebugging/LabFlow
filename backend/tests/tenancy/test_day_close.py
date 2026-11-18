"""Day Close — shift reconciliation for one branch and one day.

Closing is built only from the append-only Payment / Invoice / CreditNote rows,
records the reconciliation, and never changes money that was already recorded.
"""

from datetime import date
from decimal import Decimal
from typing import Any

import pytest
from django.test import Client
from django.utils import timezone
from django_tenants.utils import tenant_context

from apps.accounts.auth_service import AuthService
from apps.accounts.models import Role
from apps.billing.models import DayClose, Invoice, Payment
from tests.factories.billing import InvoiceFactory, PaymentFactory
from tests.factories.branches import BranchFactory
from tests.factories.patients import PatientFactory
from tests.factories.staff_user import StaffUserFactory

DAY_CLOSE_URL = "/api/v1/day-close"


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
def dc_setup(tenant_a: Any) -> dict[str, Any]:
    with tenant_context(tenant_a):
        branch = BranchFactory(code="DC1", name="Day Close Lab")
        owner = StaffUserFactory(role=Role.OWNER, branch=None, email="dc_owner@t.com")
        receptionist = StaffUserFactory(
            role=Role.RECEPTION, branch=branch, email="dc_recep@t.com"
        )
        patient = PatientFactory(branch=branch)
        return {
            "branch": branch,
            "owner": owner,
            "receptionist": receptionist,
            "patient": patient,
        }


def _day_money(setup: dict[str, Any], day: date) -> Any:
    """Cash 1000 in, card 500 in, cash refund 200 out (all on ``day``)."""
    invoice = InvoiceFactory(
        patient=setup["patient"],
        branch=setup["branch"],
        status=Invoice.Status.PARTIAL,
        subtotal=Decimal("1500.00"),
        total=Decimal("1500.00"),
    )
    PaymentFactory(
        invoice=invoice,
        kind=Payment.Kind.PAYMENT,
        method=Payment.Method.CASH,
        amount=Decimal("1000.00"),
        received_by=setup["owner"],
    )
    PaymentFactory(
        invoice=invoice,
        kind=Payment.Kind.PAYMENT,
        method=Payment.Method.CARD,
        amount=Decimal("500.00"),
        received_by=setup["owner"],
    )
    PaymentFactory(
        invoice=invoice,
        kind=Payment.Kind.REFUND,
        method=Payment.Method.CASH,
        amount=Decimal("200.00"),
        received_by=setup["owner"],
    )
    # Payments are append-only, so the business day is the day they are made.
    return invoice


@pytest.mark.django_db
def test_day_close_totals_and_cash_difference(
    tenant_a: Any, dc_setup: dict[str, Any], auth_headers: Any
) -> None:
    client = Client()
    headers = auth_headers(dc_setup["owner"])
    day = timezone.localdate()

    with tenant_context(tenant_a):
        branch_id = dc_setup["branch"].id
        _day_money(dc_setup, day)

    preview = client.get(
        f"{DAY_CLOSE_URL}?branch={branch_id}&date={day.isoformat()}",
        headers=headers,
    )
    assert preview.status_code == 200, preview.content
    body = preview.json()
    assert body["closed"] is False
    totals = body["totals"]
    assert totals["method_totals"]["cash"] == {
        "in": "1000.00",
        "out": "200.00",
        "net": "800.00",
    }
    assert totals["method_totals"]["card"] == {
        "in": "500.00",
        "out": "0.00",
        "net": "500.00",
    }
    assert totals["net_total"] == "1300.00"
    assert totals["expected_cash"] == "800.00"
    assert totals["total_invoices"] == 1

    # A difference needs a written note.
    missing_note = client.post(
        DAY_CLOSE_URL,
        data={
            "branch_id": str(branch_id),
            "date": day.isoformat(),
            "counted_cash": "750.00",
        },
        content_type="application/json",
        headers=headers,
    )
    assert missing_note.status_code == 422
    assert missing_note.json()["error"]["code"] == "day_close_note_required"

    closed = client.post(
        DAY_CLOSE_URL,
        data={
            "branch_id": str(branch_id),
            "date": day.isoformat(),
            "counted_cash": "750.00",
            "difference_note": "PKR 50 short — tea money",
        },
        content_type="application/json",
        headers=headers,
    )
    assert closed.status_code == 201, closed.content
    close = closed.json()["close"]
    assert close["expected_cash"] == "800.00"
    assert close["counted_cash"] == "750.00"
    assert close["difference"] == "-50.00"
    assert close["difference_note"] == "PKR 50 short — tea money"
    assert close["method_totals"]["cash"]["net"] == "800.00"
    assert close["closed_by_name"]


@pytest.mark.django_db
def test_closed_day_cannot_close_again_and_money_is_untouched(
    tenant_a: Any, dc_setup: dict[str, Any], auth_headers: Any
) -> None:
    client = Client()
    headers = auth_headers(dc_setup["owner"])
    day = timezone.localdate()

    with tenant_context(tenant_a):
        branch_id = dc_setup["branch"].id
        invoice = _day_money(dc_setup, day)
        invoice_id = invoice.id
        before = list(
            Payment.objects.filter(invoice=invoice)
            .order_by("id")
            .values_list("id", "amount", "kind")
        )

    payload = {
        "branch_id": str(branch_id),
        "date": day.isoformat(),
        "counted_cash": "800.00",
    }
    first = client.post(
        DAY_CLOSE_URL,
        data=payload,
        content_type="application/json",
        headers=headers,
    )
    assert first.status_code == 201, first.content

    second = client.post(
        DAY_CLOSE_URL,
        data=payload,
        content_type="application/json",
        headers=headers,
    )
    assert second.status_code == 409
    assert second.json()["error"]["code"] == "day_close_exists"

    read = client.get(
        f"{DAY_CLOSE_URL}?branch={branch_id}&date={day.isoformat()}",
        headers=headers,
    )
    assert read.status_code == 200
    assert read.json()["closed"] is True
    assert read.json()["close"]["difference"] == "0.00"

    with tenant_context(tenant_a):
        after = list(
            Payment.objects.filter(invoice_id=invoice_id)
            .order_by("id")
            .values_list("id", "amount", "kind")
        )
        assert before == after
        assert DayClose.objects.filter(branch_id=branch_id).count() == 1
        invoice = Invoice.objects.get(pk=invoice_id)
        assert invoice.total == Decimal("1500.00")


@pytest.mark.django_db
def test_day_close_is_owner_manager_only(
    tenant_a: Any, dc_setup: dict[str, Any], auth_headers: Any
) -> None:
    day = timezone.localdate()
    with tenant_context(tenant_a):
        branch_id = dc_setup["branch"].id

    response = Client().post(
        DAY_CLOSE_URL,
        data={
            "branch_id": str(branch_id),
            "date": day.isoformat(),
            "counted_cash": "0.00",
        },
        content_type="application/json",
        headers=auth_headers(dc_setup["receptionist"]),
    )
    assert response.status_code == 403
