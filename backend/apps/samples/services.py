"""Business logic for the Samples module — accessioning, labels & lifecycle
(Doc 03 §5.4 SM-1..SM-11, Doc 02 §9, KAN-137 / LAB-21, KAN-138 / LAB-22).

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

Lifecycle (KAN-138 / LAB-22):
- receive (SM-7): collected -> received only; 409 sample_not_here when the
  caller branch does not hold the sample. A branchless Owner is tenant-wide
  and skips the branch check.
- reject (SM-8): reason_code from the v1 list (422 on unknown); note
  mandatory for `other` (422 reject_note_required); 409 sample_has_results;
  409 transfer_already_open; 409 invalid_state_transition from
  rejected/cancelled/ready. Stores code+note (A-2), REJECTED event, audit,
  and enqueues samples.notify_rejection via transaction.on_commit.
- recollect (SM-9): only on rejected -> 201 new sample, fresh accession via
  the shared _mint_accession_id helper, untested sample_test rows copied,
  audit links old -> new accession. Never touches the invoice (no double
  billing).
- cancel (SM-11): O/M only, reason required (422 cancel_reason_required),
  only from collected|received, 409 once any result exists.
- SM-5: EVERY status change writes its sample_event in the SAME transaction
  as the status update. Every state-changing request writes an audit_log row
  in the same transaction.
"""

import re
import uuid
from datetime import date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from django.db import connection, transaction
from django.db.models import Q

from apps.accounts.models import AuditLog, Role, StaffUser, TenantSetting
from apps.billing.models import Invoice, InvoiceItem
from apps.branches.models import Branch
from apps.catalog.models import Panel, Test
from apps.results.models import Result
from apps.samples.models import (
    AccessionCounter,
    Sample,
    SampleEvent,
    SampleTest,
    SampleTransfer,
)

KARACHI = ZoneInfo("Asia/Karachi")

SAMPLE_WRITE_ROLES = {Role.OWNER, Role.MANAGER, Role.RECEPTION}
SAMPLE_LABEL_ROLES = {Role.OWNER, Role.MANAGER, Role.RECEPTION, Role.TECHNICIAN}
SAMPLE_RECEIVE_ROLES = {Role.OWNER, Role.MANAGER, Role.TECHNICIAN}
SAMPLE_REJECT_ROLES = {Role.OWNER, Role.MANAGER, Role.RECEPTION, Role.TECHNICIAN}
SAMPLE_RECOLLECT_ROLES = {Role.OWNER, Role.MANAGER, Role.RECEPTION}
SAMPLE_CANCEL_ROLES = {Role.OWNER, Role.MANAGER}

TRANSFER_CREATE_ROLES = {Role.OWNER, Role.MANAGER, Role.RECEPTION, Role.TECHNICIAN}
TRANSFER_RECEIVE_ROLES = {Role.OWNER, Role.MANAGER, Role.RECEPTION, Role.TECHNICIAN}
TRANSFER_CANCEL_ROLES = {Role.OWNER, Role.MANAGER}
TRANSFER_MARK_LOST_ROLES = {Role.OWNER, Role.MANAGER}
SAMPLE_EVENTS_ROLES = {
    Role.OWNER,
    Role.MANAGER,
    Role.RECEPTION,
    Role.TECHNICIAN,
    Role.PATHOLOGIST,
}
SAMPLE_READ_ROLES = {
    Role.OWNER,
    Role.MANAGER,
    Role.RECEPTION,
    Role.TECHNICIAN,
    Role.PATHOLOGIST,
    "owner",
    "manager",
    "reception",
    "receptionist",
    "technician",
    "pathologist",
}
TRANSFER_EXCEPTIONS_ROLES = {Role.OWNER, Role.MANAGER}

# tenant_setting key for the late-transfer threshold (Doc 04 §9.4).
TRANSFER_LATE_SETTING = "transfer_late_after_hours"
TRANSFER_LATE_DEFAULT_HOURS = 24

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


class InvalidStateTransitionError(SampleError):
    status_code = 409
    error_code = "invalid_state_transition"


class SampleNotHereError(SampleError):
    status_code = 409
    error_code = "sample_not_here"


class SampleHasResultsError(SampleError):
    status_code = 409
    error_code = "sample_has_results"


class TransferAlreadyOpenError(SampleError):
    status_code = 409
    error_code = "transfer_already_open"


class RejectNoteRequiredError(SampleError):
    status_code = 422
    error_code = "reject_note_required"


class CancelReasonRequiredError(SampleError):
    status_code = 422
    error_code = "cancel_reason_required"


class TransferNotFoundError(SampleError):
    status_code = 404
    error_code = "not_found"


class BranchCannotReceiveError(SampleError):
    status_code = 422
    error_code = "branch_cannot_receive"


class MarkLostNoteRequiredError(SampleError):
    status_code = 422
    error_code = "mark_lost_note_required"


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


def _get_sample(sample_id: uuid.UUID) -> Sample:
    """Fetch a tenant-scoped sample or 404 (never 403)."""
    try:
        return Sample.objects.select_related("invoice", "branch").get(pk=sample_id)
    except Sample.DoesNotExist:
        raise SampleNotFoundError("Sample not found.") from None


def _caller_branch(actor: StaffUser) -> Any:
    """The branch holding the caller — None for a branchless Owner."""
    return actor.branch if actor.branch_id else None


def _write_event_and_audit(
    *,
    sample: Sample,
    event: str,
    actor: StaffUser,
    branch: Any,
    action: str,
    after_jsonb: dict[str, Any],
    note: str | None = None,
    ip: str | None = None,
    user_agent: str | None = None,
) -> SampleEvent:
    """SM-5: status change + sample_event + audit_log in ONE transaction."""
    event_row = SampleEvent.objects.create(
        sample=sample,
        event=event,
        actor=actor,
        branch=branch,
        note=note,
    )
    AuditLog.objects.create(
        actor_id=actor.id,
        action=action,
        entity_type="sample",
        entity_id=sample.id,
        before_jsonb=None,
        after_jsonb=after_jsonb,
        ip=ip,
        user_agent=user_agent,
    )
    return event_row


class SampleService:
    """Sample accessioning: collect + label."""

    @staticmethod
    def list_samples(
        *,
        actor: StaffUser,
        status: str | None = None,
        branch_id: str | None = None,
        q: str | None = None,
        limit: int | None = None,
    ) -> tuple[list[Sample], int]:
        """List samples with search and filters, bounded to prevent DoS."""
        qs = (
            Sample.objects.scoped_to(actor)
            .select_related("invoice__patient", "branch")
            .prefetch_related("sample_tests__test")
            .order_by("-collected_at", "-created_at")
        )

        if status and status != "all":
            qs = qs.filter(status=status.strip().lower())

        if branch_id and branch_id != "all":
            b_uuid = uuid.UUID(str(branch_id).strip())
            qs = qs.filter(branch_id=b_uuid)

        if q:
            term = q.strip()[:100]
            if term:
                qs = qs.filter(
                    Q(accession_id__icontains=term)
                    | Q(invoice__patient__name__icontains=term)
                    | Q(invoice__patient__mrn__icontains=term)
                )

        total = qs.count()
        limit_val = max(1, min(int(limit), 200)) if limit is not None else 100
        return list(qs[:limit_val]), total

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

    # ------------------------------------------------------------------
    # Lifecycle (KAN-138 / LAB-22)
    # ------------------------------------------------------------------

    @staticmethod
    def receive_sample(
        *,
        sample_id: uuid.UUID,
        actor: StaffUser,
        ip: str | None = None,
        user_agent: str | None = None,
    ) -> Sample:
        """collected -> received (SM-7). No body.

        409 invalid_state_transition from any other state; 409
        sample_not_here when the caller branch does not hold the sample.
        A branchless Owner is tenant-wide and skips the branch check.
        """
        sample = _get_sample(sample_id)
        if sample.status != Sample.Status.COLLECTED:
            raise InvalidStateTransitionError(
                "Only a collected sample can be received."
            )
        branch = _caller_branch(actor)
        if branch is not None and branch.id != sample.branch_id:
            raise SampleNotHereError("This branch does not hold the sample.")
        with transaction.atomic():
            sample.status = Sample.Status.RECEIVED
            sample.save(update_fields=["status", "updated_at"])
            _write_event_and_audit(
                sample=sample,
                event=SampleEvent.EventType.RECEIVED,
                actor=actor,
                branch=sample.branch,
                action="sample.received",
                after_jsonb={
                    "accession_id": sample.accession_id,
                    "from_status": "collected",
                    "to_status": "received",
                    "branch_id": str(sample.branch_id),
                    "received_by": str(actor.id),
                    "event": "sample.received",
                },
                ip=ip,
                user_agent=user_agent,
            )
        return sample

    @staticmethod
    def reject_sample(
        *,
        sample_id: uuid.UUID,
        reason_code: str,
        note: str | None,
        actor: StaffUser,
        ip: str | None = None,
        user_agent: str | None = None,
    ) -> Sample:
        """Reject for quality (SM-8). Stores code + note (A-2).

        Guards: 409 invalid_state_transition from rejected/cancelled/ready;
        409 sample_has_results when any result exists; 409
        transfer_already_open when an open transfer exists; 422
        reject_note_required when code is `other` without a note.
        Enqueues samples.notify_rejection via transaction.on_commit.
        """
        sample = _get_sample(sample_id)
        clean_note = (note or "").strip()
        if reason_code == Sample.RejectionReasonCode.OTHER and not clean_note:
            raise RejectNoteRequiredError(
                "A note is required when the reason code is 'other'."
            )
        if sample.status in (
            Sample.Status.REJECTED,
            Sample.Status.CANCELLED,
            Sample.Status.READY,
        ):
            raise InvalidStateTransitionError(
                f"A sample in status '{sample.status}' cannot be rejected."
            )
        if Result.objects.filter(sample=sample).exists():
            raise SampleHasResultsError(
                "Cannot reject a sample that already has results."
            )
        if SampleTransfer.objects.filter(
            sample=sample, status=SampleTransfer.Status.OPEN
        ).exists():
            raise TransferAlreadyOpenError(
                "Cannot reject a sample with an open transfer."
            )

        with transaction.atomic():
            sample.status = Sample.Status.REJECTED
            sample.rejection_reason_code = reason_code
            sample.rejection_note = clean_note or None
            sample.save(
                update_fields=[
                    "status",
                    "rejection_reason_code",
                    "rejection_note",
                    "updated_at",
                ]
            )
            event_row = _write_event_and_audit(
                sample=sample,
                event=SampleEvent.EventType.REJECTED,
                actor=actor,
                branch=sample.branch,
                action="sample.rejected",
                after_jsonb={
                    "accession_id": sample.accession_id,
                    "from_status": "collected",
                    "to_status": "rejected",
                    "rejection_reason_code": reason_code,
                    "rejection_note": clean_note or None,
                    "rejected_by": str(actor.id),
                    "event": "sample.rejected",
                },
                note=reason_code,
                ip=ip,
                user_agent=user_agent,
            )
            # Enqueue after commit (repo pattern: apps/platform/provisioning.py).
            tenant = getattr(connection, "tenant", None)
            schema_name = getattr(tenant, "schema_name", "public")
            event_pk = str(event_row.id)

            def _enqueue() -> None:
                from apps.samples.tasks import notify_rejection_task

                notify_rejection_task.delay(schema_name, event_pk)

            transaction.on_commit(_enqueue)
        return sample

    @staticmethod
    def recollect_sample(
        *,
        sample_id: uuid.UUID,
        actor: StaffUser,
        ip: str | None = None,
        user_agent: str | None = None,
    ) -> Sample:
        """Recollect after rejection (SM-9) -> 201 new sample.

        Only on a rejected sample. Mints a fresh accession via the shared
        _mint_accession_id helper (per-tenant-per-day + SELECT FOR UPDATE —
        not duplicated). Copies the still-untested sample_test rows (tests
        with no result row). Never touches the invoice (no double billing).
        Audit links old accession -> new accession.
        """
        old = _get_sample(sample_id)
        if old.status != Sample.Status.REJECTED:
            raise InvalidStateTransitionError(
                "Only a rejected sample can be recollected."
            )

        # Still-untested = sample_test rows with no result row yet. Single
        # bulk query (no N+1).
        old_links = list(
            SampleTest.objects.filter(sample=old).select_related("test", "invoice_item")
        )
        tested_test_ids = set(
            Result.objects.filter(sample=old).values_list("test_id", flat=True)
        )
        untested = [link for link in old_links if link.test_id not in tested_test_ids]
        if not untested:
            raise InvalidStateTransitionError(
                "Nothing left to recollect on this sample."
            )

        now = datetime.now(KARACHI)
        with transaction.atomic():
            new_accession = _mint_accession_id()
            new_sample = Sample.objects.create(
                invoice=old.invoice,
                branch=old.branch,
                accession_id=new_accession,
                status=Sample.Status.COLLECTED,
                collected_at=now,
                collected_by=actor,
            )
            for link in untested:
                SampleTest.objects.create(
                    sample=new_sample,
                    invoice_item=link.invoice_item,
                    test=link.test,
                )
            SampleEvent.objects.create(
                sample=new_sample,
                event=SampleEvent.EventType.COLLECTED,
                actor=actor,
                branch=old.branch,
            )
            AuditLog.objects.create(
                actor_id=actor.id,
                action="sample.collected",
                entity_type="sample",
                entity_id=new_sample.id,
                before_jsonb=None,
                after_jsonb={
                    "accession_id": new_accession,
                    "invoice_id": str(old.invoice_id),
                    "recollected_from": str(old.id),
                    "old_accession_id": old.accession_id,
                    "test_count": len(untested),
                    "event": "sample.collected",
                },
                ip=ip,
                user_agent=user_agent,
            )
            # Link old -> new on the OLD sample's audit row (SM-9).
            AuditLog.objects.create(
                actor_id=actor.id,
                action="sample.recollected",
                entity_type="sample",
                entity_id=old.id,
                before_jsonb=None,
                after_jsonb={
                    "old_accession_id": old.accession_id,
                    "new_accession_id": new_accession,
                    "new_sample_id": str(new_sample.id),
                    "recollected_by": str(actor.id),
                    "event": "sample.recollected",
                },
                ip=ip,
                user_agent=user_agent,
            )
        return new_sample

    @staticmethod
    def cancel_sample(
        *,
        sample_id: uuid.UUID,
        reason: str | None,
        actor: StaffUser,
        ip: str | None = None,
        user_agent: str | None = None,
    ) -> Sample:
        """Cancel a sample (SM-11): O/M only, reason required.

        Allowed only from collected|received; 409 invalid_state_transition
        otherwise; 409 sample_has_results once any result exists (even
        entered); 422 cancel_reason_required on empty reason.
        """
        sample = _get_sample(sample_id)
        clean_reason = (reason or "").strip()
        if not clean_reason:
            raise CancelReasonRequiredError("A cancellation reason is required.")
        if sample.status not in (Sample.Status.COLLECTED, Sample.Status.RECEIVED):
            raise InvalidStateTransitionError(
                f"A sample in status '{sample.status}' cannot be cancelled."
            )
        if Result.objects.filter(sample=sample).exists():
            raise SampleHasResultsError(
                "Cannot cancel a sample that already has results."
            )
        from_status = sample.status
        with transaction.atomic():
            sample.status = Sample.Status.CANCELLED
            sample.save(update_fields=["status", "updated_at"])
            _write_event_and_audit(
                sample=sample,
                event=SampleEvent.EventType.CANCELLED,
                actor=actor,
                branch=sample.branch,
                action="sample.cancelled",
                after_jsonb={
                    "accession_id": sample.accession_id,
                    "from_status": from_status,
                    "to_status": "cancelled",
                    "reason": clean_reason,
                    "cancelled_by": str(actor.id),
                    "event": "sample.cancelled",
                },
                note=clean_reason,
                ip=ip,
                user_agent=user_agent,
            )
        return sample


# ----------------------------------------------------------------------
# Transfers (KAN-143 / LAB-23)
# ----------------------------------------------------------------------


def _get_transfer(transfer_id: uuid.UUID) -> SampleTransfer:
    """Fetch a tenant-scoped transfer or 404 (never 403)."""
    try:
        return SampleTransfer.objects.select_related(
            "sample", "from_branch", "to_branch"
        ).get(pk=transfer_id)
    except SampleTransfer.DoesNotExist:
        raise TransferNotFoundError("Transfer not found.") from None


def _open_transfer_for(sample: Sample) -> SampleTransfer | None:
    """The sample's open transfer, if any (single bulk-safe query)."""
    return SampleTransfer.objects.filter(
        sample=sample, status=SampleTransfer.Status.OPEN
    ).first()


def _destination_eligible(branch: Branch) -> bool:
    """An open processing branch can receive transfers (Doc 04 §9.2).

    Collection centres only collect — they never receive for processing.
    Soft-deleted branches are closed.
    """
    return branch.deleted_at is None and not branch.is_collection_centre


def _write_transfer_audit(
    *,
    transfer: SampleTransfer,
    actor: StaffUser,
    action: str,
    after_jsonb: dict[str, Any],
    ip: str | None = None,
    user_agent: str | None = None,
) -> None:
    AuditLog.objects.create(
        actor_id=actor.id,
        action=action,
        entity_type="transfer",
        entity_id=transfer.id,
        before_jsonb=None,
        after_jsonb=after_jsonb,
        ip=ip,
        user_agent=user_agent,
    )


def _branch_ref(branch: Branch | None) -> dict[str, Any] | None:
    if branch is None:
        return None
    return {"id": str(branch.id), "code": branch.code, "name": branch.name}


def _late_threshold_hours() -> float:
    row = TenantSetting.objects.filter(key=TRANSFER_LATE_SETTING).first()
    if row is None:
        return float(TRANSFER_LATE_DEFAULT_HOURS)
    try:
        return float(row.value)
    except (TypeError, ValueError):
        return float(TRANSFER_LATE_DEFAULT_HOURS)


class TransferService:
    """Inter-branch sample transfers: custody, receipt, exceptions (SM-7)."""

    @staticmethod
    def create_transfer(
        *,
        sample_id: uuid.UUID,
        to_branch_id: uuid.UUID,
        actor: StaffUser,
        ip: str | None = None,
        user_agent: str | None = None,
    ) -> SampleTransfer:
        """Dispatch a sample to another branch (SM-7, Doc 04 §9.2).

        Only from collected|received — an in_process sample can never
        transfer (409 invalid_state_transition). One open transfer per
        sample (409 transfer_already_open). Destination must be an open
        processing branch (422 branch_cannot_receive). The caller must
        hold the sample (409 sample_not_here) — a branchless Owner is
        tenant-wide and skips the check.
        SM-7: the sample's own status does NOT change while open.
        """
        sample = _get_sample(sample_id)
        if sample.status not in (Sample.Status.COLLECTED, Sample.Status.RECEIVED):
            raise InvalidStateTransitionError(
                f"A sample in status '{sample.status}' cannot be transferred."
            )
        branch = _caller_branch(actor)
        if branch is not None and branch.id != sample.branch_id:
            raise SampleNotHereError("This branch does not hold the sample.")
        if _open_transfer_for(sample) is not None:
            raise TransferAlreadyOpenError(
                "A transfer is already open for this sample."
            )
        try:
            dest = Branch.objects.get(pk=to_branch_id)
        except Branch.DoesNotExist:
            raise TransferNotFoundError("Destination branch not found.") from None
        if not _destination_eligible(dest):
            raise BranchCannotReceiveError(
                "The destination branch cannot receive transfers."
            )

        now = datetime.now(KARACHI)
        with transaction.atomic():
            transfer = SampleTransfer.objects.create(
                sample=sample,
                from_branch=sample.branch,
                to_branch=dest,
                transferred_by=actor,
                status=SampleTransfer.Status.OPEN,
                dispatched_at=now,
            )
            SampleEvent.objects.create(
                sample=sample,
                event=SampleEvent.EventType.TRANSFERRED_OUT,
                actor=actor,
                branch=sample.branch,
            )
            _write_transfer_audit(
                transfer=transfer,
                actor=actor,
                action="transfer.created",
                after_jsonb={
                    "transfer_id": str(transfer.id),
                    "sample_id": str(sample.id),
                    "accession_id": sample.accession_id,
                    "from_branch_id": str(sample.branch_id),
                    "to_branch_id": str(dest.id),
                    "dispatched_by": str(actor.id),
                    "event": "sample.transferred_out",
                },
                ip=ip,
                user_agent=user_agent,
            )
        return transfer

    @staticmethod
    def receive_transfer(
        *,
        transfer_id: uuid.UUID,
        actor: StaffUser,
        ip: str | None = None,
        user_agent: str | None = None,
    ) -> SampleTransfer:
        """Receive at the destination branch (SM-7).

        Caller must be scoped to the destination branch (404 otherwise) —
        a branchless Owner is tenant-wide. Only an open transfer can be
        received (409). Moves sample.branch_id, sets sample status to
        received, writes TRANSFERRED_IN + RECEIVED events — all in the
        same transaction.
        """
        transfer = _get_transfer(transfer_id)
        branch = _caller_branch(actor)
        if branch is not None and branch.id != transfer.to_branch_id:
            raise TransferNotFoundError("Transfer not found.") from None
        if transfer.status != SampleTransfer.Status.OPEN:
            raise InvalidStateTransitionError(
                f"A transfer in status '{transfer.status}' cannot be received."
            )

        now = datetime.now(KARACHI)
        with transaction.atomic():
            transfer.status = SampleTransfer.Status.RECEIVED
            transfer.received_at = now
            transfer.received_by = actor
            transfer.save(update_fields=["status", "received_at", "received_by"])
            sample = transfer.sample
            sample.branch = transfer.to_branch
            sample.status = Sample.Status.RECEIVED
            sample.save(update_fields=["branch", "status", "updated_at"])
            SampleEvent.objects.create(
                sample=sample,
                event=SampleEvent.EventType.TRANSFERRED_IN,
                actor=actor,
                branch=transfer.to_branch,
            )
            SampleEvent.objects.create(
                sample=sample,
                event=SampleEvent.EventType.RECEIVED,
                actor=actor,
                branch=transfer.to_branch,
            )
            _write_transfer_audit(
                transfer=transfer,
                actor=actor,
                action="transfer.received",
                after_jsonb={
                    "transfer_id": str(transfer.id),
                    "sample_id": str(sample.id),
                    "accession_id": sample.accession_id,
                    "to_branch_id": str(transfer.to_branch_id),
                    "received_by": str(actor.id),
                    "events": ["sample.transferred_in", "sample.received"],
                },
                ip=ip,
                user_agent=user_agent,
            )
        return transfer

    @staticmethod
    def cancel_transfer(
        *,
        transfer_id: uuid.UUID,
        actor: StaffUser,
        ip: str | None = None,
        user_agent: str | None = None,
    ) -> SampleTransfer:
        """Cancel an open transfer — sending-branch scope only (Doc 04 §9.2).

        The receiver can never cancel. Only open transfers (409
        otherwise). The sample stays at the sender in its prior status —
        transferable again or processed locally.
        """
        transfer = _get_transfer(transfer_id)
        branch = _caller_branch(actor)
        if branch is not None and branch.id != transfer.from_branch_id:
            raise TransferNotFoundError("Transfer not found.") from None
        if transfer.status != SampleTransfer.Status.OPEN:
            raise InvalidStateTransitionError(
                f"A transfer in status '{transfer.status}' cannot be cancelled."
            )
        with transaction.atomic():
            transfer.status = SampleTransfer.Status.CANCELLED
            transfer.save(update_fields=["status", "updated_at"])
            SampleEvent.objects.create(
                sample=transfer.sample,
                event=SampleEvent.EventType.TRANSFER_CANCELLED,
                actor=actor,
                branch=transfer.from_branch,
            )
            _write_transfer_audit(
                transfer=transfer,
                actor=actor,
                action="transfer.cancelled",
                after_jsonb={
                    "transfer_id": str(transfer.id),
                    "sample_id": str(transfer.sample_id),
                    "cancelled_by": str(actor.id),
                    "event": "sample.transfer_cancelled",
                },
                ip=ip,
                user_agent=user_agent,
            )
        return transfer

    @staticmethod
    def mark_lost_transfer(
        *,
        transfer_id: uuid.UUID,
        note: str | None,
        actor: StaffUser,
        ip: str | None = None,
        user_agent: str | None = None,
    ) -> SampleTransfer:
        """Mark an open transfer lost — sending-branch scope only.

        Note is required (422 mark_lost_note_required). SM-7: a lost
        transfer does NOT change sample.status — the sample is resolved
        later through reject + recollect.
        """
        transfer = _get_transfer(transfer_id)
        branch = _caller_branch(actor)
        if branch is not None and branch.id != transfer.from_branch_id:
            raise TransferNotFoundError("Transfer not found.") from None
        clean_note = (note or "").strip()
        if not clean_note:
            raise MarkLostNoteRequiredError(
                "A note is required when marking a transfer lost."
            )
        if transfer.status != SampleTransfer.Status.OPEN:
            raise InvalidStateTransitionError(
                f"A transfer in status '{transfer.status}' cannot be marked lost."
            )
        with transaction.atomic():
            transfer.status = SampleTransfer.Status.LOST
            transfer.save(update_fields=["status", "updated_at"])
            SampleEvent.objects.create(
                sample=transfer.sample,
                event=SampleEvent.EventType.TRANSFER_LOST,
                actor=actor,
                branch=transfer.from_branch,
                note=clean_note,
            )
            _write_transfer_audit(
                transfer=transfer,
                actor=actor,
                action="transfer.marked_lost",
                after_jsonb={
                    "transfer_id": str(transfer.id),
                    "sample_id": str(transfer.sample_id),
                    "note": clean_note,
                    "marked_by": str(actor.id),
                    "event": "sample.transfer_marked_lost",
                },
                ip=ip,
                user_agent=user_agent,
            )
        return transfer

    # ------------------------------------------------------------------
    # Reads: events timeline + exceptions (KAN-143 / LAB-23)
    # ------------------------------------------------------------------

    @staticmethod
    def get_events(*, sample_id: uuid.UUID, actor: StaffUser) -> list[dict[str, Any]]:
        """Read-only chain-of-custody timeline (R-5, Doc 03 §6.5).

        Event type, actor, branch, timestamp, payload (rejection code,
        transfer branches). No audit row — read-only.
        """
        sample = _get_sample(sample_id)
        events = list(
            SampleEvent.objects.filter(sample=sample)
            .select_related("actor", "branch")
            .order_by("created_at", "id")
        )
        transfers = list(
            SampleTransfer.objects.filter(sample=sample)
            .select_related("from_branch", "to_branch")
            .order_by("created_at")
        )
        out: list[dict[str, Any]] = []
        for ev in events:
            out.append(
                {
                    "id": str(ev.id),
                    "event": ev.event,
                    "actor": ev.actor.email if ev.actor else None,
                    "branch": _branch_ref(ev.branch),
                    "timestamp": ev.created_at.astimezone(KARACHI).isoformat(),
                    "payload": _event_payload(ev, transfers),
                }
            )
        return out

    @staticmethod
    def get_exceptions(
        *,
        actor: StaffUser,
        report: str | None = None,
        from_date: date | None = None,
        to_date: date | None = None,
        month: str | None = None,
    ) -> dict[str, Any]:
        """Transfer exception reports (Doc 04 §9.4, Doc 03 §11).

        late: open transfers older than transfer_late_after_hours
        (default 24) — REPORT ONLY, no state moves. lost: status=lost
        with from/to period filter on the loss event. route_health: per
        from->to pair counts with month filter. Managers see only pairs
        touching their branches; a branchless Owner sees all. Read-only.
        """
        branch = _caller_branch(actor)
        qs = SampleTransfer.objects.select_related(
            "sample", "from_branch", "to_branch"
        ).order_by("-dispatched_at")
        if branch is not None:
            qs = qs.filter(Q(from_branch=branch) | Q(to_branch=branch))
        transfers = list(qs)

        sections: dict[str, Any] = {}
        if report is None or report == "late":
            sections["late"] = _late_report(transfers)
        if report is None or report == "lost":
            sections["lost"] = _lost_report(transfers, from_date, to_date)
        if report is None or report == "route_health":
            sections["route_health"] = _route_health_report(transfers, month)
        return sections


def _event_payload(ev: SampleEvent, transfers: list[SampleTransfer]) -> dict[str, Any]:
    """Payload for the timeline: rejection code, transfer branches (R-5)."""
    if ev.event == SampleEvent.EventType.REJECTED:
        return {"rejection_code": ev.note}
    if ev.event in (
        SampleEvent.EventType.TRANSFERRED_OUT,
        SampleEvent.EventType.TRANSFERRED_IN,
        SampleEvent.EventType.TRANSFER_CANCELLED,
        SampleEvent.EventType.TRANSFER_LOST,
    ):
        transfer = _transfer_for_event(ev, transfers)
        payload: dict[str, Any] = {
            "from_branch": _branch_ref(transfer.from_branch) if transfer else None,
            "to_branch": _branch_ref(transfer.to_branch) if transfer else None,
        }
        if ev.event == SampleEvent.EventType.TRANSFER_LOST:
            payload["note"] = ev.note
        return payload
    return {}


def _transfer_for_event(
    ev: SampleEvent, transfers: list[SampleTransfer]
) -> SampleTransfer | None:
    """The transfer an event belongs to: latest created at/before the event.

    Transfers are sequential per sample (a new one cannot open while one
    is open), so this match is deterministic.
    """
    best: SampleTransfer | None = None
    for t in transfers:
        if t.created_at <= ev.created_at and (
            best is None or t.created_at >= best.created_at
        ):
            best = t
    return best


def _transfer_row(t: SampleTransfer) -> dict[str, Any]:
    return {
        "transfer_id": str(t.id),
        "sample_id": str(t.sample_id),
        "accession_id": t.sample.accession_id,
        "from_branch": _branch_ref(t.from_branch),
        "to_branch": _branch_ref(t.to_branch),
        "status": t.status,
        "dispatched_at": t.dispatched_at.astimezone(KARACHI).isoformat()
        if t.dispatched_at
        else None,
        "received_at": t.received_at.astimezone(KARACHI).isoformat()
        if t.received_at
        else None,
    }


def _late_report(transfers: list[SampleTransfer]) -> list[dict[str, Any]]:
    """Open transfers past the late threshold — report only, no state moves."""
    threshold = _late_threshold_hours()
    now = datetime.now(KARACHI)
    cutoff = now - timedelta(hours=threshold)
    rows = []
    for t in transfers:
        if (
            t.status == SampleTransfer.Status.OPEN
            and t.dispatched_at is not None
            and t.dispatched_at < cutoff
        ):
            hours = (now - t.dispatched_at).total_seconds() / 3600
            row = _transfer_row(t)
            row["hours_in_transit"] = round(hours, 1)
            rows.append(row)
    return rows


def _lost_report(
    transfers: list[SampleTransfer],
    from_date: date | None,
    to_date: date | None,
) -> list[dict[str, Any]]:
    """Lost transfers with a from/to period filter on the loss event."""
    lost = [t for t in transfers if t.status == SampleTransfer.Status.LOST]
    sample_ids = [t.sample_id for t in lost]
    lost_events = SampleEvent.objects.filter(
        sample_id__in=sample_ids, event=SampleEvent.EventType.TRANSFER_LOST
    ).order_by("created_at")
    lost_at: dict[Any, Any] = {}
    notes: dict[Any, str | None] = {}
    for ev in lost_events:
        lost_at[ev.sample_id] = ev.created_at
        notes[ev.sample_id] = ev.note
    rows = []
    for t in lost:
        la = lost_at.get(t.sample_id)
        if from_date is not None and (la is None or la.date() < from_date):
            continue
        if to_date is not None and (la is None or la.date() > to_date):
            continue
        row = _transfer_row(t)
        row["lost_at"] = la.astimezone(KARACHI).isoformat() if la else None
        row["note"] = notes.get(t.sample_id)
        rows.append(row)
    return rows


def _route_health_report(
    transfers: list[SampleTransfer], month: str | None
) -> list[dict[str, Any]]:
    """Per from->to pair counts (open/late/received/lost) with month filter."""
    now = datetime.now(KARACHI)
    if month is None:
        year, mon = now.year, now.month
    else:
        year_s, mon_s = month.split("-")
        year, mon = int(year_s), int(mon_s)
    threshold = _late_threshold_hours()
    cutoff = now - timedelta(hours=threshold)
    pairs: dict[tuple[Any, Any], dict[str, Any]] = {}
    for t in transfers:
        if t.dispatched_at is None:
            continue
        local = t.dispatched_at.astimezone(KARACHI)
        if local.year != year or local.month != mon:
            continue
        key = (t.from_branch_id, t.to_branch_id)
        cell = pairs.get(key)
        if cell is None:
            cell = {
                "from_branch": _branch_ref(t.from_branch),
                "to_branch": _branch_ref(t.to_branch),
                "open": 0,
                "late": 0,
                "received": 0,
                "lost": 0,
            }
            pairs[key] = cell
        if t.status == SampleTransfer.Status.OPEN:
            cell["open"] += 1
            if t.dispatched_at < cutoff:
                cell["late"] += 1
        elif t.status == SampleTransfer.Status.RECEIVED:
            cell["received"] += 1
        elif t.status == SampleTransfer.Status.LOST:
            cell["lost"] += 1
    return sorted(
        pairs.values(),
        key=lambda r: (r["from_branch"]["code"], r["to_branch"]["code"]),
    )
