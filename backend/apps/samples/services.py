"""Business logic for the Samples module — accessioning & labels
(Doc 03 §5.4 SM-1..SM-4, Doc 02 §9, KAN-137 / LAB-21, original LAB-23).

Sample collection (POST /api/v1/samples):
- SM-1: accession_id = {tenant_prefix:3}{YYYYMMDD}{seq:06d}, minted
  server-side only. Prefix derives from the tenant name (first 3 A-Z
  letters, uppercased). Sequence is per-tenant per-day via a date-keyed
  counter row locked with SELECT FOR UPDATE inside the creation
  transaction — concurrent collection cannot duplicate (Doc 02 §9).
- SM-2: one sample_test row per DISTINCT ordered test; panels expand via
  panel_test.
- SM-3: collected_at (server time), collected_by (authenticated user),
  status=collected, branch (caller's collecting branch), first
  sample_event (COLLECTED) — all in the same transaction.
- Guards: cancelled invoice -> 409 (BL-9); no untested items -> 422
  no_untested_items; retry over already-collected items -> 409
  items_already_collected naming the existing accession (natural
  idempotency — never a duplicate sample).
- Billing hold (BL-9): tenant_setting billing_hold_enabled does NOT block
  collection — the hold blocks report release, not collection.
- Audit: sample.collected row + COLLECTED sample_event in the same
  transaction. Event sample.collected rides on the audit row (no event
  bus exists yet — same pattern as billing).

Label (GET /api/v1/samples/{id}/label):
- SM-4: payload printed from STORED data only — no request body, no
  free-text endpoint. barcode = {symbology: code128, payload: accession}.
- Every print AND reprint is audited (sample.label_printed) — reprints
  matter in mislabelling investigations.
"""

import re
import uuid
from datetime import date, datetime
from typing import Any
from zoneinfo import ZoneInfo

from django.db import connection, transaction

from apps.accounts.models import AuditLog, Role, StaffUser
from apps.billing.models import Invoice, InvoiceItem
from apps.catalog.models import Panel, Test
from apps.samples.models import AccessionCounter, Sample, SampleEvent, SampleTest

KARACHI = ZoneInfo("Asia/Karachi")

SAMPLE_WRITE_ROLES = {Role.OWNER, Role.MANAGER, Role.RECEPTION}
SAMPLE_LABEL_ROLES = {Role.OWNER, Role.MANAGER, Role.RECEPTION, Role.TECHNICIAN}

# A sample still "live" for idempotency: cancelled/rejected samples do not
# block recollection of their items.
LIVE_SAMPLE_STATUSES = {
    Sample.Status.COLLECTED,
    Sample.Status.RECEIVED,
    Sample.Status.IN_PROCESS,
    Sample.Status.READY,
}


class SampleError(Exception):
    """Base samples error carrying an HTTP status + machine code."""

    __test__ = False
    status_code = 422
    error_code = "sample_error"

    def __init__(self, message: str = "") -> None:
        super().__init__(message or self.error_code)


class SampleNotFoundError(SampleError):
    status_code = 404
    error_code = "not_found"


class InvoiceCancelledError(SampleError):
    status_code = 409
    error_code = "invoice_cancelled"


class NoUntestedItemsError(SampleError):
    status_code = 422
    error_code = "no_untested_items"


class ItemsAlreadyCollectedError(SampleError):
    status_code = 409
    error_code = "items_already_collected"


def _tenant_prefix() -> str:
    """3-letter accession prefix from the tenant name (Doc 02 §9).

    No prefix column exists on the tenant model/docs — derive the first
    three A-Z letters of the tenant name, uppercased (e.g. "City
    Diagnostic Lab" -> "CIT", matching the Doc 02 example).
    """
    tenant = getattr(connection, "tenant", None)
    name = getattr(tenant, "name", "") or ""
    letters = re.sub(r"[^A-Z]", "", name.upper())
    return (letters + "XXX")[:3]


def _mint_accession_id() -> str:
    """Mint the next accession ID for today (Asia/Karachi), race-safe."""
    today: date = datetime.now(KARACHI).date()
    prefix = _tenant_prefix()
    with transaction.atomic():
        counter, _ = AccessionCounter.objects.select_for_update().get_or_create(
            date=today, defaults={"last_seq": 0}
        )
        counter.last_seq += 1
        counter.save(update_fields=["last_seq"])
        seq = counter.last_seq
    return f"{prefix}{today.strftime('%Y%m%d')}{seq:06d}"


def _expand_item_tests(item: InvoiceItem) -> list[Test]:
    """One Test per invoice item: direct test, or panel expanded via panel_test."""
    if item.test_id is not None:
        if item.test is None:
            raise SampleNotFoundError("Test not found.")
        return [item.test]
    if item.panel_id is None:
        raise SampleNotFoundError("Invoice item has neither test nor panel.")
    panel = Panel.objects.prefetch_related("panel_tests__test").get(pk=item.panel_id)
    return [pt.test for pt in panel.panel_tests.all()]


class SampleService:
    """Sample accessioning: collect + label."""

    @staticmethod
    def collect_sample(
        *,
        invoice_id: uuid.UUID,
        invoice_item_ids: list[uuid.UUID] | None,
        actor: StaffUser,
        ip: str | None = None,
        user_agent: str | None = None,
    ) -> Sample:
        """Collect a sample for an invoice's untested items (SM-1..SM-3)."""
        try:
            invoice = Invoice.objects.select_related("patient", "branch").get(
                pk=invoice_id
            )
        except Invoice.DoesNotExist:
            raise SampleNotFoundError("Invoice not found.") from None

        # BL-9: collection blocked while the invoice is cancelled.
        if invoice.status == Invoice.Status.CANCELLED:
            raise InvoiceCancelledError("Cannot collect against a cancelled invoice.")

        all_items = list(invoice.items.select_related("test", "panel"))
        if invoice_item_ids is not None:
            wanted = {str(i) for i in invoice_item_ids}
            by_id = {str(i.id): i for i in all_items}
            unknown = wanted - set(by_id)
            if unknown:
                raise SampleNotFoundError(
                    f"Invoice items not on this invoice: {sorted(unknown)[0]}."
                )
            requested = [by_id[str(i)] for i in invoice_item_ids]
        else:
            requested = all_items

        # Untested = no sample_test on a live sample for this item.
        # Single bulk query (no N+1): all live links for the requested items.
        live_links = (
            SampleTest.objects.filter(
                invoice_item__in=[item.id for item in requested],
                sample__status__in=LIVE_SAMPLE_STATUSES,
            )
            .select_related("sample")
            .order_by("created_at")
        )
        collected_by_item: dict[uuid.UUID, str] = {}
        for link in live_links:
            collected_by_item.setdefault(link.invoice_item_id, link.sample.accession_id)
        untested = [item for item in requested if item.id not in collected_by_item]

        if not untested:
            if requested:
                raise ItemsAlreadyCollectedError(
                    "These items were already collected on sample "
                    f"{collected_by_item[requested[0].id]}."
                )
            raise NoUntestedItemsError("No untested items left on this invoice.")

        # SM-2: expand to DISTINCT tests (a test and a panel containing it
        # may coexist on the invoice — one sample_test row per test).
        distinct_tests: dict[uuid.UUID, tuple[Test, InvoiceItem]] = {}
        for item in untested:
            for test in _expand_item_tests(item):
                distinct_tests.setdefault(test.id, (test, item))

        # Billing hold (BL-9): notes but never blocks collection.
        from apps.accounts.models import TenantSetting

        hold_row = TenantSetting.objects.filter(key="billing_hold_enabled").first()
        billing_hold = hold_row is not None and hold_row.value.lower() == "true"

        now = datetime.now(KARACHI)
        collecting_branch = actor.branch if actor.branch_id else None
        if collecting_branch is None:
            collecting_branch = invoice.branch

        with transaction.atomic():
            accession_id = _mint_accession_id()
            sample = Sample.objects.create(
                invoice=invoice,
                branch=collecting_branch,
                accession_id=accession_id,
                status=Sample.Status.COLLECTED,
                collected_at=now,
                collected_by=actor,
            )
            for _, (test, item) in distinct_tests.items():
                SampleTest.objects.create(sample=sample, invoice_item=item, test=test)
            SampleEvent.objects.create(
                sample=sample,
                event=SampleEvent.EventType.COLLECTED,
                actor=actor,
                branch=collecting_branch,
            )
            AuditLog.objects.create(
                actor_id=actor.id,
                action="sample.collected",
                entity_type="sample",
                entity_id=sample.id,
                before_jsonb=None,
                after_jsonb={
                    "accession_id": accession_id,
                    "invoice_id": str(invoice.id),
                    "patient_id": str(invoice.patient_id),
                    "branch_id": str(collecting_branch.id),
                    "collected_by": str(actor.id),
                    "test_count": len(distinct_tests),
                    "billing_hold_enabled": billing_hold,
                    "event": "sample.collected",
                },
                ip=ip,
                user_agent=user_agent,
            )
        return sample

    @staticmethod
    def get_label(
        *,
        sample_id: uuid.UUID,
        actor: StaffUser,
        ip: str | None = None,
        user_agent: str | None = None,
    ) -> dict[str, Any]:
        """Build the Code128 label payload from STORED data (SM-4).

        Every print AND reprint is audited.
        """
        try:
            sample = Sample.objects.select_related(
                "invoice__patient", "collected_by"
            ).get(pk=sample_id)
        except Sample.DoesNotExist:
            raise SampleNotFoundError("Sample not found.") from None

        patient = sample.invoice.patient
        dob = patient.date_of_birth.isoformat() if patient.date_of_birth else None
        collected_at = sample.collected_at.astimezone(KARACHI).isoformat()
        collector = sample.collected_by.email if sample.collected_by else None

        payload: dict[str, Any] = {
            "accession_id": sample.accession_id,
            "patient_name": patient.name,
            "mrn": patient.mrn,
            "date_of_birth": dob,
            "collected_at": collected_at,
            "collected_by": collector,
            "barcode": {
                "symbology": "code128",
                "payload": sample.accession_id,
            },
        }

        with transaction.atomic():
            AuditLog.objects.create(
                actor_id=actor.id,
                action="sample.label_printed",
                entity_type="sample",
                entity_id=sample.id,
                before_jsonb=None,
                after_jsonb={
                    "accession_id": sample.accession_id,
                    "printed_by": str(actor.id),
                },
                ip=ip,
                user_agent=user_agent,
            )
        return payload
