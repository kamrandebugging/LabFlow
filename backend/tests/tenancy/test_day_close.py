"""Day Close — shift reconciliation for one branch and one completed business day.

Closing is built only from the append-only Payment / Invoice / CreditNote rows
by PKT business_date, requires all active payment methods to be counted, blocks
mid-day closes of the current day, requires reason + second approver on any
discrepancy, and supports Owner-only append-only reopen for corrections.
"""

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any, cast
from unittest.mock import patch

import pytest
from django.test import Client
from django.utils import timezone
from django_tenants.utils import tenant_context

from apps.accounts.auth_service import AuthService
from apps.accounts.models import AuditLog, Role, StaffBranch
from apps.billing.models import DayClose, DayCloseReopen, Invoice, Payment
from apps.billing.services import BillingService
from tests.factories.billing import InvoiceFactory, PaymentFactory
from tests.factories.branches import BranchFactory
from tests.factories.catalog import TestFactory, TestPriceFactory
from tests.factories.patients import PatientFactory
from tests.factories.staff_user import StaffUserFactory

DAY_CLOSE_URL = "/api/v1/day-close"
DAY_CLOSE_REOPEN_URL = "/api/v1/day-close/reopen"
DAY_CLOSE_APPROVE_URL = "/api/v1/day-close/approve"
INVOICES_URL = "/api/v1/invoices"

APPROVER_PASSWORD = "ManagerClosePass2026!"


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
        owner = StaffUserFactory(
            role=Role.OWNER,
            branch=None,
            email="dc_owner@t.com",
            password=APPROVER_PASSWORD,
        )
        manager = StaffUserFactory(
            role=Role.MANAGER,
            branch=branch,
            email="dc_manager@t.com",
            password=APPROVER_PASSWORD,
        )
        StaffBranch.objects.create(staff_user=manager, branch=branch, is_primary=True)
        receptionist = StaffUserFactory(
            role=Role.RECEPTION, branch=branch, email="dc_recep@t.com"
        )
        StaffBranch.objects.create(
            staff_user=receptionist, branch=branch, is_primary=True
        )
        patient = PatientFactory(branch=branch)
        return {
            "branch": branch,
            "owner": owner,
            "manager": manager,
            "receptionist": receptionist,
            "patient": patient,
        }


def _day_money(setup: dict[str, Any], day: date) -> Invoice:
    """Cash 1000 in, card 500 in, cash refund 200 out (all on ``day``)."""
    invoice = InvoiceFactory(
        patient=setup["patient"],
        branch=setup["branch"],
        status=Invoice.Status.PARTIAL,
        subtotal=Decimal("1500.00"),
        total=Decimal("1500.00"),
        business_date=day,
    )
    PaymentFactory(
        invoice=invoice,
        kind=Payment.Kind.PAYMENT,
        method=Payment.Method.CASH,
        amount=Decimal("1000.00"),
        received_by=setup["owner"],
        business_date=day,
    )
    PaymentFactory(
        invoice=invoice,
        kind=Payment.Kind.PAYMENT,
        method=Payment.Method.CARD,
        amount=Decimal("500.00"),
        received_by=setup["owner"],
        business_date=day,
    )
    PaymentFactory(
        invoice=invoice,
        kind=Payment.Kind.REFUND,
        method=Payment.Method.CASH,
        amount=Decimal("200.00"),
        received_by=setup["owner"],
        business_date=day,
    )
    return cast(Invoice, invoice)


@pytest.mark.django_db
def test_mid_day_close_of_today_rejected_422(
    tenant_a: Any, dc_setup: dict[str, Any], auth_headers: Any
) -> None:
    """Closing the current business day before it ends must return 422."""
    today = timezone.localdate()
    with tenant_context(tenant_a):
        branch_id = dc_setup["branch"].id

    resp = Client().post(
        DAY_CLOSE_URL,
        data={
            "branch_id": str(branch_id),
            "date": today.isoformat(),
            "counted_cash": "0.00",
        },
        content_type="application/json",
        headers=auth_headers(dc_setup["owner"]),
    )
    assert resp.status_code == 422, resp.content
    assert resp.json()["error"]["code"] == "day_close_invalid_date"


@pytest.mark.django_db
def test_day_close_totals_non_cash_and_second_approver(
    tenant_a: Any, dc_setup: dict[str, Any], auth_headers: Any
) -> None:
    """Reconciles cash + non-cash methods; discrepancy needs note + 2nd approver."""
    client = Client()
    owner_headers = auth_headers(dc_setup["owner"])
    manager_headers = auth_headers(dc_setup["manager"])
    day = timezone.localdate() - timedelta(days=1)

    with tenant_context(tenant_a):
        branch_id = dc_setup["branch"].id
        _day_money(dc_setup, day)

    preview = client.get(
        f"{DAY_CLOSE_URL}?branch={branch_id}&date={day.isoformat()}",
        headers=owner_headers,
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

    # Omitting active non-cash method (card) -> 422
    missing_card = client.post(
        DAY_CLOSE_URL,
        data={
            "branch_id": str(branch_id),
            "date": day.isoformat(),
            "counted_cash": "800.00",
        },
        content_type="application/json",
        headers=owner_headers,
    )
    assert missing_card.status_code == 422
    assert missing_card.json()["error"]["code"] == "day_close_counted_methods_required"

    # A difference needs a written note first.
    missing_note = client.post(
        DAY_CLOSE_URL,
        data={
            "branch_id": str(branch_id),
            "date": day.isoformat(),
            "counted_cash": "750.00",
            "counted_methods": {"cash": "750.00", "card": "500.00"},
        },
        content_type="application/json",
        headers=owner_headers,
    )
    assert missing_note.status_code == 422
    assert missing_note.json()["error"]["code"] == "day_close_note_required"

    # A difference with a note but NO second approver -> 403 owner_approval_required
    missing_approver = client.post(
        DAY_CLOSE_URL,
        data={
            "branch_id": str(branch_id),
            "date": day.isoformat(),
            "counted_cash": "750.00",
            "counted_methods": {"cash": "750.00", "card": "500.00"},
            "difference_note": "PKR 50 short — tea money",
        },
        content_type="application/json",
        headers=owner_headers,
    )
    assert missing_approver.status_code == 403
    assert missing_approver.json()["error"]["code"] == "owner_approval_required"

    # Self-approval is rejected (403).
    self_approve = client.post(
        DAY_CLOSE_URL,
        data={
            "branch_id": str(branch_id),
            "date": day.isoformat(),
            "counted_cash": "750.00",
            "counted_methods": {"cash": "750.00", "card": "500.00"},
            "difference_note": "PKR 50 short — tea money",
            "approver_email": dc_setup["owner"].email,
            "approver_password": APPROVER_PASSWORD,
        },
        content_type="application/json",
        headers=owner_headers,
    )
    assert self_approve.status_code == 403
    assert self_approve.json()["error"]["code"] == "owner_approval_required"

    # Non-cash discrepancy also requires note + second approver; manager closes,
    # owner approves via credentials.
    closed = client.post(
        DAY_CLOSE_URL,
        data={
            "branch_id": str(branch_id),
            "date": day.isoformat(),
            "counted_cash": "750.00",
            "counted_methods": {"cash": "750.00", "card": "490.00"},
            "difference_note": "PKR 50 cash short + PKR 10 card fee",
            "approver_email": dc_setup["owner"].email,
            "approver_password": APPROVER_PASSWORD,
        },
        content_type="application/json",
        headers=manager_headers,
    )
    assert closed.status_code == 201, closed.content
    close = closed.json()["close"]
    assert close["expected_cash"] == "800.00"
    assert close["counted_cash"] == "750.00"
    assert close["difference"] == "-50.00"
    assert close["counted_methods"]["card"] == "490.00"
    assert close["method_differences"]["card"] == "-10.00"
    assert close["approved_by"] == str(dc_setup["owner"].id)
    assert close["closed_by_name"]


@pytest.mark.django_db
def test_closed_day_cannot_close_again_and_reopen_re_derives(
    tenant_a: Any, dc_setup: dict[str, Any], auth_headers: Any
) -> None:
    """Double close -> 409; Owner reopen is append-only, re-derives, and visible."""
    client = Client()
    owner_headers = auth_headers(dc_setup["owner"])
    manager_headers = auth_headers(dc_setup["manager"])
    day = timezone.localdate() - timedelta(days=1)

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
        "counted_methods": {"cash": "800.00", "card": "500.00"},
    }
    first = client.post(
        DAY_CLOSE_URL,
        data=payload,
        content_type="application/json",
        headers=owner_headers,
    )
    assert first.status_code == 201, first.content

    second = client.post(
        DAY_CLOSE_URL,
        data=payload,
        content_type="application/json",
        headers=owner_headers,
    )
    assert second.status_code == 409
    assert second.json()["error"]["code"] == "day_close_exists"

    # Non-Owner cannot reopen (403)
    mgr_reopen = client.post(
        DAY_CLOSE_REOPEN_URL,
        data={
            "branch_id": str(branch_id),
            "date": day.isoformat(),
            "reason": "Manager attempt",
        },
        content_type="application/json",
        headers=manager_headers,
    )
    assert mgr_reopen.status_code == 403

    # Blank reason -> 422
    no_reason = client.post(
        DAY_CLOSE_REOPEN_URL,
        data={"branch_id": str(branch_id), "date": day.isoformat(), "reason": "  "},
        content_type="application/json",
        headers=owner_headers,
    )
    assert no_reason.status_code == 422

    # Owner reopens with reason -> 200
    reopened = client.post(
        DAY_CLOSE_REOPEN_URL,
        data={
            "branch_id": str(branch_id),
            "date": day.isoformat(),
            "reason": "Missed late evening cash settlement",
        },
        content_type="application/json",
        headers=owner_headers,
    )
    assert reopened.status_code == 200, reopened.content
    r_body = reopened.json()
    assert r_body["closed"] is False
    assert r_body["is_corrected"] is True
    assert len(r_body["reopens"]) == 1
    assert r_body["reopens"][0]["reason"] == "Missed late evening cash settlement"

    # Add a payment on that reopened business day and verify live re-derivation
    with tenant_context(tenant_a):
        PaymentFactory(
            invoice_id=invoice_id,
            kind=Payment.Kind.PAYMENT,
            method=Payment.Method.CASH,
            amount=Decimal("200.00"),
            received_by=dc_setup["owner"],
            business_date=day,
        )
        assert DayCloseReopen.objects.filter(branch_id=branch_id).count() == 1
        assert AuditLog.objects.filter(action="day_close.reopened").exists()

    read_after_reopen = client.get(
        f"{DAY_CLOSE_URL}?branch={branch_id}&date={day.isoformat()}",
        headers=owner_headers,
    )
    assert read_after_reopen.status_code == 200
    assert read_after_reopen.json()["closed"] is False
    assert read_after_reopen.json()["is_corrected"] is True
    assert read_after_reopen.json()["totals"]["expected_cash"] == "1000.00"

    # Re-close with corrected counted cash (1000.00) using approval token from manager
    token_resp = client.post(
        DAY_CLOSE_APPROVE_URL,
        data={"branch_id": str(branch_id), "date": day.isoformat()},
        content_type="application/json",
        headers=manager_headers,
    )
    assert token_resp.status_code == 200
    assert token_resp.json()["approval_token"]

    reclosed = client.post(
        DAY_CLOSE_URL,
        data={
            "branch_id": str(branch_id),
            "date": day.isoformat(),
            "counted_cash": "1000.00",
            "counted_methods": {"cash": "1000.00", "card": "500.00"},
        },
        content_type="application/json",
        headers=owner_headers,
    )
    assert reclosed.status_code == 201, reclosed.content
    assert reclosed.json()["is_corrected"] is True
    assert len(reclosed.json()["reopens"]) == 1

    with tenant_context(tenant_a):
        after = list(
            Payment.objects.filter(invoice_id=invoice_id).order_by("id").values("id")
        )
        assert len(after) == len(before) + 1
        # Append-only: both DayClose rows exist (first superseded, second active)
        assert (
            DayClose.objects.filter(branch_id=branch_id, business_date=day).count() == 2
        )


@pytest.mark.django_db
def test_pkt_00_to_05_boundary_counts_toward_pkt_business_date(
    tenant_a: Any, dc_setup: dict[str, Any], auth_headers: Any
) -> None:
    """Invoices created 00:00-05:00 PKT (19:00-23:59 UTC prev day) use PKT date."""
    client = Client()
    headers = auth_headers(dc_setup["owner"])

    # 2026-11-24 20:30 UTC == 2026-11-25 01:30 PKT
    utc_late = datetime(2026, 11, 24, 20, 30, 0, tzinfo=UTC)
    pkt_day = date(2026, 11, 25)
    utc_day = date(2026, 11, 24)

    with tenant_context(tenant_a):
        test_obj = TestFactory(name="PKT Boundary Test", code="PKT01")
        TestPriceFactory(test=test_obj, panel=None, price=Decimal("1000.00"))

        with (
            patch("django.utils.timezone.now", return_value=utc_late),
            patch("django.utils.timezone.localdate", return_value=pkt_day),
        ):
            inv, _ = BillingService.create_invoice(
                patient_id=dc_setup["patient"].id,
                branch_id=dc_setup["branch"].id,
                referral_partner_id=None,
                items=[{"test_id": test_obj.id, "qty": 1}],
                discount_amount=Decimal("100.00"),
                discount_reason="Night shift discount",
                idempotency_key="pkt-boundary-1",
                actor=dc_setup["owner"],
            )
            # Simulate DB created_at in UTC prev day
            Invoice.objects.filter(pk=inv.pk).update(created_at=utc_late)
            inv.refresh_from_db()
            assert inv.business_date == pkt_day

        branch_id = dc_setup["branch"].id

    # Day Close for PKT day (2026-11-25) sees the invoice & discount;
    # UTC day (11-24) does not.
    pkt_read = client.get(
        f"{DAY_CLOSE_URL}?branch={branch_id}&date={pkt_day.isoformat()}",
        headers=headers,
    ).json()
    assert pkt_read["totals"]["total_invoices"] == 1
    assert pkt_read["totals"]["total_discount"] == "100.00"

    utc_read = client.get(
        f"{DAY_CLOSE_URL}?branch={branch_id}&date={utc_day.isoformat()}",
        headers=headers,
    ).json()
    assert utc_read["totals"]["total_invoices"] == 0
    assert utc_read["totals"]["total_discount"] == "0.00"

    # Invoice list daily_total uses PKT business_date too
    with patch("django.utils.timezone.localdate", return_value=pkt_day):
        list_resp = client.get(INVOICES_URL, headers=headers).json()
        assert list_resp["daily_total"] == "900.00"


@pytest.mark.django_db
def test_day_close_is_owner_manager_only(
    tenant_a: Any, dc_setup: dict[str, Any], auth_headers: Any
) -> None:
    day = timezone.localdate() - timedelta(days=1)
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
