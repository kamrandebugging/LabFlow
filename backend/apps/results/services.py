"""Result entry service — batch result entry (Doc 03 §5.5 RS-1/RS-2/RS-3/RS-V2,
§6.6, §8, KAN-150 / LAB-25, original LAB-30).

Thin-service pattern (same as billing/samples): error subclasses carry the
HTTP status + machine code; views only map them to responses. No business
logic in views.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any

from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.accounts.models import AuditLog, Role, StaffUser
from apps.catalog.models import ReferenceRange
from apps.catalog.services import CatalogService, _to_range_row
from apps.reports.models import Report
from apps.results.engine import evaluate_result, parse_result
from apps.results.models import CriticalNotification, Result, ResultApproval
from apps.samples.models import Sample, SampleEvent, SampleTest, SampleTransfer

# Doc 03 §6.6: POST /api/v1/samples/{id}/results — roles cell is exactly "T P".
RESULT_ENTRY_ROLES = {Role.TECHNICIAN, Role.PATHOLOGIST}
# Doc 03 §6.6: POST /api/v1/results/{id}/approve — roles cell is exactly "P".
RESULT_APPROVE_ROLES = {Role.PATHOLOGIST}
# Doc 03 §6.6: POST /api/v1/results/{id}/withdraw — roles cell "T P (author only)".
RESULT_WITHDRAW_ROLES = {Role.TECHNICIAN, Role.PATHOLOGIST}
# Doc 03 §6.6: POST /api/v1/results/{id}/amend — roles cell is exactly "T P".
RESULT_AMEND_ROLES = {Role.TECHNICIAN, Role.PATHOLOGIST}
# Doc 03 §6.6: POST /api/v1/results/{id}/critical-notifications —
# roles cell is exactly "M P" (Manager + Pathologist only).
RESULT_NOTIFY_ROLES = {Role.MANAGER, Role.PATHOLOGIST}


class ResultError(Exception):
    """Base results error carrying an HTTP status + machine code."""

    __test__ = False
    status_code = 422
    error_code = "result_error"

    def __init__(
        self, message: str = "", details: dict[str, Any] | None = None
    ) -> None:
        super().__init__(message or self.error_code)
        self.details = details


class ResultNotFoundError(ResultError):
    status_code = 404
    error_code = "not_found"


class InvalidStateTransitionError(ResultError):
    status_code = 409
    error_code = "invalid_state_transition"


class TransferAlreadyOpenError(ResultError):
    status_code = 409
    error_code = "transfer_already_open"


class SampleNotHereError(ResultError):
    status_code = 409
    error_code = "sample_not_here"


class ResultEntryDisabledAtBranchError(ResultError):
    status_code = 403
    error_code = "result_entry_disabled_at_branch"


class ResultAlreadyEnteredError(ResultError):
    """T-28 loser: a concurrent entry won; names the winning author."""

    status_code = 409
    error_code = "result_already_entered"

    def __init__(self, message: str = "", entered_by: str | None = None) -> None:
        super().__init__(message)
        self.entered_by = entered_by


class ResultBatchValidationError(ResultError):
    """RS-V2: per-row validation failures; nothing was saved."""

    status_code = 422
    error_code = "validation_failed"

    def __init__(self, rows: list[dict[str, Any]]) -> None:
        super().__init__("One or more result rows failed validation.")
        self.rows = rows


class ResultForbiddenError(ResultError):
    """Caller role may not perform this verification action."""

    status_code = 403
    error_code = "forbidden"


class SelfApprovalNotPermittedError(ResultError):
    """RS-6: a pathologist may not approve a result they entered."""

    status_code = 403
    error_code = "self_approval_not_permitted"


class WithdrawNotPermittedError(ResultError):
    """RS-4: only the author may withdraw their entered result."""

    status_code = 403
    error_code = "withdraw_not_permitted"


class NoteRequiredForRejectionError(ResultError):
    """RS-5: decision=rejected requires a non-empty note."""

    status_code = 422
    error_code = "note_required_for_rejection"


class OverrideNoteRequiredError(ResultError):
    """RS-7: range_override=true requires a non-empty note."""

    status_code = 422
    error_code = "override_note_required"


class NoteRequiredForUnparseableError(ResultError):
    """RS-10: numeric test with unparseable value requires a note to approve."""

    status_code = 422
    error_code = "note_required_for_unparseable"


class ValueRequiredError(ResultError):
    """RS-V1: value is required and non-empty after trim."""

    status_code = 422
    error_code = "value_required"


class AmendReasonRequiredError(ResultError):
    """RS-9: an amendment requires a non-empty reason."""

    status_code = 422
    error_code = "amend_reason_required"


class AmendmentAlreadyPendingError(ResultError):
    """An unapproved amendment already exists for this sample_test."""

    status_code = 409
    error_code = "amendment_already_pending"


class AmendmentApprovalNoteRequiredError(ResultError):
    """RS-9: approving an amendment requires its own note — the amend-time
    reason does not satisfy this."""

    status_code = 422
    error_code = "amendment_approval_note_required"


class NotCriticalError(ResultError):
    """§8.5: a critical notification may only be recorded on a critical
    result."""

    status_code = 409
    error_code = "not_critical"


class NotifiedNameRequiredError(ResultError):
    """§8.5: notified_name is required and non-empty after trim."""

    status_code = 422
    error_code = "notified_name_required"


class NotificationInFutureError(ResultError):
    """§8.5: notified_at cannot be in the future."""

    status_code = 422
    error_code = "notification_in_future"


def _get_sample(sample_id: uuid.UUID) -> Sample:
    """Fetch a tenant-scoped sample with patient + branch, or 404 (never 403)."""
    try:
        return Sample.objects.select_related("invoice__patient", "branch").get(
            pk=sample_id
        )
    except Sample.DoesNotExist:
        raise ResultNotFoundError("Sample not found.") from None


def _caller_branch(actor: StaffUser) -> Any:
    """The branch holding the caller — None for a branchless actor."""
    return actor.branch if actor.branch_id else None


def _age_in_days(dob: date | None, as_of: date) -> int | None:
    if dob is None:
        return None
    return (as_of - dob).days


def _range_summary(rr: Any) -> dict[str, Any] | None:
    if rr is None:
        return None
    return {
        "low": str(rr.low) if rr.low is not None else None,
        "high": str(rr.high) if rr.high is not None else None,
        "critical_low": str(rr.critical_low) if rr.critical_low is not None else None,
        "critical_high": (
            str(rr.critical_high) if rr.critical_high is not None else None
        ),
        "unit": rr.unit,
    }


def _evaluate_plan(
    *,
    sample: Sample,
    test_id: uuid.UUID,
    value: str,
    unit: str | None,
) -> dict[str, Any]:
    """Run one value through the LAB-24 pure engine (§8).

    Shared by batch entry (LAB-25) and amendments (LAB-27, RS-9): the
    amendment's new row goes through the same evaluation (flag/qualifier).
    The sample must carry invoice__patient (see _get_sample).
    """
    patient = sample.invoice.patient
    collected_on = sample.collected_at.date()
    age_days = _age_in_days(patient.date_of_birth, collected_on)
    rr_model = CatalogService.resolve_reference_range(
        test_id=test_id,
        patient_sex=patient.sex,
        patient_age_days=age_days,
        collection_date=sample.collected_at,
    )
    range_row = _to_range_row(rr_model) if rr_model is not None else None
    evaluation = evaluate_result(
        value,
        range_row=range_row,
        patient_sex=patient.sex,
        age_in_days=age_days,
        collection_date=sample.collected_at,
        qualitative_values=None,
    )
    return {
        "test_id": test_id,
        "value": value,
        "unit": unit or (rr_model.unit if rr_model is not None else None),
        "flag": evaluation.flag.value if evaluation.flag is not None else None,
        "qualifier": evaluation.qualifier,
        "needs_review": evaluation.needs_review,
        "range_summary": _range_summary(rr_model),
    }


class ResultService:
    """Batch result entry (RS-1/RS-2/RS-3/RS-V2, §8)."""

    @staticmethod
    def enter_results(
        *,
        sample_id: uuid.UUID,
        rows: list[dict[str, Any]],
        actor: StaffUser,
        ip: str | None = None,
        user_agent: str | None = None,
    ) -> dict[str, Any]:
        """Enter a batch of results for one sample — all-or-nothing (RS-V2).

        Phase 1 (guards, no writes): branch gate (RS-3, BEFORE the state
        rule), caller branch scope (BS-3), sample state, open transfer.
        Phase 2 (validation, no writes): every row checked; any failure
        raises with per-row errors and NOTHING is saved.
        Phase 3 (one transaction): all result rows + per-row audit rows +
        the IN_PROCESS event on first entry. A concurrent double entry for
        the same test is decided by the partial unique constraint
        (uq_result_sample_test_entered); the loser gets 409
        result_already_entered naming the winning author (T-28).
        """
        sample = _get_sample(sample_id)

        # RS-3 branch gate FIRST — regardless of sample state.
        branch = sample.branch
        if branch.is_collection_centre and not branch.result_entry_enabled:
            raise ResultEntryDisabledAtBranchError(
                "Result entry is disabled at this collection centre."
            )

        # BS-3: a technician enters only on the holding branch.
        caller_branch = _caller_branch(actor)
        if caller_branch is not None and caller_branch.id != sample.branch_id:
            raise SampleNotHereError("This branch does not hold the sample.")

        # RS-3 state rule.
        if sample.status not in (Sample.Status.RECEIVED, Sample.Status.IN_PROCESS):
            raise InvalidStateTransitionError(
                "Results can only be entered on a received or in-process sample."
            )

        # SM-7: an open transfer blocks entry.
        if SampleTransfer.objects.filter(
            sample=sample, status=SampleTransfer.Status.OPEN
        ).exists():
            raise TransferAlreadyOpenError(
                "Cannot enter results while a transfer is open."
            )

        # ---- Phase 2: validate EVERY row before saving anything (RS-V2).
        ordered_test_ids = set(
            SampleTest.objects.filter(sample=sample).values_list("test_id", flat=True)
        )
        seen: set[uuid.UUID] = set()
        row_errors: list[dict[str, Any]] = []
        for row in rows:
            test_id = row["test_id"]
            if test_id in seen:
                row_errors.append(
                    {
                        "test_id": str(test_id),
                        "code": "duplicate_test_in_batch",
                        "message": "Duplicate test_id within the same batch.",
                    }
                )
                continue
            seen.add(test_id)
            if test_id not in ordered_test_ids:
                row_errors.append(
                    {
                        "test_id": str(test_id),
                        "code": "test_not_ordered",
                        "message": "No sample_test row for this test on the sample.",
                    }
                )
        if row_errors:
            raise ResultBatchValidationError(row_errors)

        # ---- Phase 3: enrich every row via the LAB-24 pure engine (§8).
        plans: list[dict[str, Any]] = []
        for row in rows:
            plans.append(
                _evaluate_plan(
                    sample=sample,
                    test_id=row["test_id"],
                    value=row["value"],  # RS-2: stored EXACTLY as entered
                    unit=row.get("unit"),
                )
            )

        # ---- Phase 4: write everything in ONE transaction (RS-V2).
        created: list[tuple[Result, dict[str, Any]]] = []
        with transaction.atomic():
            locked = Sample.objects.select_for_update().get(pk=sample.pk)
            if locked.status not in (
                Sample.Status.RECEIVED,
                Sample.Status.IN_PROCESS,
            ):
                raise InvalidStateTransitionError(
                    "Sample state changed while entering results."
                )
            first_entry = locked.status == Sample.Status.RECEIVED

            for plan in plans:
                try:
                    # Savepoint per row: a concurrent winner aborts only its
                    # own savepoint; the outer transaction stays usable so we
                    # can name the author in the 409 (T-28).
                    with transaction.atomic():
                        result = Result.objects.create(
                            sample=locked,
                            test_id=plan["test_id"],
                            value=plan["value"],
                            unit=plan["unit"],
                            flag=plan["flag"],
                            status=Result.Status.ENTERED,
                            entered_by=actor,
                        )
                except IntegrityError:
                    winner = (
                        Result.objects.select_related("entered_by")
                        .filter(
                            sample=locked,
                            test_id=plan["test_id"],
                            status=Result.Status.ENTERED,
                        )
                        .order_by("created_at")
                        .first()
                    )
                    author = (
                        winner.entered_by.email if winner is not None else "unknown"
                    )
                    raise ResultAlreadyEnteredError(
                        f"Result for this test was already entered by {author}.",
                        entered_by=author,
                    ) from None
                AuditLog.objects.create(
                    actor_id=actor.id,
                    action="result.entered",
                    entity_type="result",
                    entity_id=result.id,
                    before_jsonb=None,
                    after_jsonb={
                        "sample_id": str(locked.id),
                        "test_id": str(plan["test_id"]),
                        "value": plan["value"],
                        "unit": plan["unit"],
                        "flag": plan["flag"],
                        "entered_by": str(actor.id),
                        "event": "result.entered",
                    },
                    ip=ip,
                    user_agent=user_agent,
                )
                created.append((result, plan))

            if first_entry:
                # RS-3: entry IS the start of processing (SM-5: event + audit
                # in the same transaction as the status change).
                locked.status = Sample.Status.IN_PROCESS
                locked.save(update_fields=["status", "updated_at"])
                SampleEvent.objects.create(
                    sample=locked,
                    event=SampleEvent.EventType.IN_PROCESS,
                    actor=actor,
                    branch=locked.branch,
                )
                AuditLog.objects.create(
                    actor_id=actor.id,
                    action="sample.in_process",
                    entity_type="sample",
                    entity_id=locked.id,
                    before_jsonb=None,
                    after_jsonb={
                        "accession_id": locked.accession_id,
                        "from_status": "received",
                        "to_status": "in_process",
                        "event": "sample.in_process",
                    },
                    ip=ip,
                    user_agent=user_agent,
                )

        return {
            "sample_id": str(locked.id),
            "sample_status": locked.status,
            "results": [
                {
                    "id": str(result.id),
                    "test_id": str(plan["test_id"]),
                    "value": result.value,
                    "unit": result.unit,
                    "flag": result.flag,
                    "qualifier": plan["qualifier"],
                    "needs_review": plan["needs_review"],
                    "status": result.status,
                    "matched_range": plan["range_summary"],
                    "entered_by": str(actor.id),
                }
                for result, plan in created
            ],
        }

    # ---- Clinical verification (RS-4/RS-5/RS-6/RS-7/RS-8/RS-10, §6.6, §10) ----

    @staticmethod
    def approve_result(
        *,
        result_id: uuid.UUID,
        decision: str,
        note: str | None,
        range_override: bool,
        actor: StaffUser,
        ip: str | None = None,
        user_agent: str | None = None,
    ) -> dict[str, Any]:
        """Pathologist approval / rejection of one entered result (RS-5).

        Concurrency (§10, T-31): the result row is locked with
        SELECT FOR UPDATE inside the transaction — two concurrent approvals
        serialize; the loser sees a non-entered status and gets 409
        invalid_state_transition naming the winner. Single-winner, no lost
        updates.
        """
        clean_note = (note or "").strip()
        if decision == ResultApproval.Decision.REJECTED and not clean_note:
            raise NoteRequiredForRejectionError(
                "A rejection decision requires a non-empty note."
            )
        if range_override and not clean_note:
            raise OverrideNoteRequiredError(
                "A range override requires a non-empty note."
            )

        with transaction.atomic():
            try:
                result = (
                    Result.objects.select_for_update()
                    .select_related("sample")
                    .get(pk=result_id)
                )
            except Result.DoesNotExist:
                raise ResultNotFoundError("Result not found.") from None

            if result.status != Result.Status.ENTERED:
                raise InvalidStateTransitionError(
                    "Only an entered result can be decided.",
                    details=_winner_details(result),
                )

            # RS-6 self-approval: the entering pathologist may not approve,
            # unless this tenant has exactly one active pathologist account.
            # The exception is recorded visibly in audit, never silent.
            audit_note: str | None = None
            if result.entered_by_id == actor.id:
                active_pathologists = StaffUser.objects.filter(
                    role=Role.PATHOLOGIST, is_active=True
                ).count()
                if active_pathologists != 1:
                    raise SelfApprovalNotPermittedError(
                        "A pathologist may not approve a result they entered."
                    )
                audit_note = "single_pathologist_self_approval"

            # RS-10: NULL flag on a numeric test with an unparseable value
            # requires a note; qualitative NULL-flag results do not.
            if (
                result.flag is None
                and _is_numeric_unparseable(result)
                and not clean_note
            ):
                raise NoteRequiredForUnparseableError(
                    "Approval of an unparseable numeric value requires a note."
                )

            # RS-9: an amendment carries its own approval note — the
            # amend-time reason does NOT satisfy this.
            supersedes_id = result.supersedes_id
            if supersedes_id is not None and not clean_note:
                raise AmendmentApprovalNoteRequiredError(
                    "Approving an amendment requires a non-empty note."
                )

            new_status = (
                Result.Status.APPROVED
                if decision == ResultApproval.Decision.APPROVED
                else Result.Status.REJECTED
            )
            result.status = new_status
            result.save(update_fields=["status", "updated_at"])
            approval = ResultApproval.objects.create(
                result=result,
                pathologist=actor,
                decision=decision,
                note=clean_note or None,
                range_override=range_override,
            )

            action = (
                "result.approved"
                if decision == ResultApproval.Decision.APPROVED
                else "result.rejected"
            )
            after: dict[str, Any] = {
                "decision": decision,
                "note": clean_note or None,
                "range_override": range_override,
                "pathologist_id": str(actor.id),
                "approval_id": str(approval.id),
                "event": action,
            }
            if audit_note is not None:
                after["audit_note"] = audit_note

            amended_result_id: str | None = None
            report_version_requested = False
            if (
                supersedes_id is not None
                and decision == ResultApproval.Decision.APPROVED
            ):
                # RS-9: the old row becomes amended IN THE SAME TRANSACTION.
                # The old row is never edited otherwise (DoD: no row ever
                # edited — only its status flips here).
                old_row = Result.objects.select_for_update().get(pk=supersedes_id)
                old_row.status = Result.Status.AMENDED
                old_row.save(update_fields=["status", "updated_at"])
                amended_result_id = str(old_row.id)
                # §5.6 RP-4: a FINAL report already exists for the sample ->
                # the reports module (later LAB) must cut a new version.
                # Cross-module trigger pattern (no event bus yet): flag on
                # the audit row, like sample.ready / sample.collected.
                report_version_requested = Report.objects.filter(
                    sample_id=result.sample_id, status=Report.Status.FINAL
                ).exists()
                # result.amended fires at the amendment's approval.
                after["event"] = "result.amended"
                after["amendment_of"] = amended_result_id
                if report_version_requested:
                    after["report_version_requested"] = True

            AuditLog.objects.create(
                actor_id=actor.id,
                action=action,
                entity_type="result",
                entity_id=result.id,
                before_jsonb={"status": "entered"},
                after_jsonb=after,
                ip=ip,
                user_agent=user_agent,
            )

            # RS-8: completing the last pending test moves the sample to
            # ready (SM-5: READY event in the same transaction). Partial
            # approval is a normal stable state — the sample waits.
            sample_ready = False
            if new_status == Result.Status.APPROVED:
                sample_ready = _maybe_complete_sample(
                    sample_id=result.sample_id,
                    actor=actor,
                    ip=ip,
                    user_agent=user_agent,
                )

        payload: dict[str, Any] = {
            "id": str(result.id),
            "status": result.status,
            "decision": decision,
            "note": clean_note or None,
            "range_override": range_override,
            "approved_by": str(actor.id),
            "sample_ready": sample_ready,
        }
        if amended_result_id is not None:
            payload["amended_result_id"] = amended_result_id
            payload["report_version_requested"] = report_version_requested
        return payload

    @staticmethod
    def withdraw_result(
        *,
        result_id: uuid.UUID,
        actor: StaffUser,
        ip: str | None = None,
        user_agent: str | None = None,
    ) -> dict[str, Any]:
        """Author withdrawal of an entered result (RS-4).

        Sets status=withdrawn, writes NO result_approval row — the withdrawal
        is recorded in audit_log only. The row is read-only afterwards.
        """
        with transaction.atomic():
            try:
                result = Result.objects.select_for_update().get(pk=result_id)
            except Result.DoesNotExist:
                raise ResultNotFoundError("Result not found.") from None

            if result.entered_by_id != actor.id:
                raise WithdrawNotPermittedError(
                    "Only the author may withdraw this result."
                )
            if (
                result.status != Result.Status.ENTERED
                or ResultApproval.objects.filter(result=result).exists()
            ):
                raise InvalidStateTransitionError(
                    "Only an entered result with no approval decision can be withdrawn."
                )

            result.status = Result.Status.WITHDRAWN
            result.save(update_fields=["status", "updated_at"])
            AuditLog.objects.create(
                actor_id=actor.id,
                action="result.withdrawn",
                entity_type="result",
                entity_id=result.id,
                before_jsonb={"status": "entered"},
                after_jsonb={
                    "status": "withdrawn",
                    "withdrawn_by": str(actor.id),
                    "event": "result.withdrawn",
                },
                ip=ip,
                user_agent=user_agent,
            )

        return {"id": str(result.id), "status": result.status}

    # ---- Amendments (RS-9, §6.6, §5.6 RP-4) ----

    @staticmethod
    def amend_result(
        *,
        result_id: uuid.UUID,
        value: str | None,
        unit: str | None,
        reason: str | None,
        actor: StaffUser,
        ip: str | None = None,
        user_agent: str | None = None,
    ) -> dict[str, Any]:
        """Create an amendment of an approved result (RS-9).

        RS-9: an approved result is never changed. The correction is a NEW
        result row for the same sample_test with status entered, linked via
        supersedes; the old row becomes amended only when the new row is
        approved (see approve_result). 409 amendment_already_pending when an
        unapproved amendment exists. The new row runs through the LAB-24
        engine like a fresh entry.
        """
        clean_value = (value or "").strip()
        if not clean_value:
            raise ValueRequiredError("A non-empty value is required.")
        clean_reason = (reason or "").strip()
        if not clean_reason:
            raise AmendReasonRequiredError("An amendment requires a non-empty reason.")

        with transaction.atomic():
            try:
                old = (
                    Result.objects.select_for_update()
                    .select_related("sample__invoice__patient", "sample__branch")
                    .get(pk=result_id)
                )
            except Result.DoesNotExist:
                raise ResultNotFoundError("Result not found.") from None

            if old.status != Result.Status.APPROVED:
                raise InvalidStateTransitionError(
                    "Only an approved result can be amended."
                )

            # The old row is approved, so any other ENTERED row for the same
            # sample_test is a pending amendment (the LAB-25 partial unique
            # constraint guarantees at most one).
            if (
                Result.objects.filter(
                    sample_id=old.sample_id,
                    test_id=old.test_id,
                    status=Result.Status.ENTERED,
                )
                .exclude(pk=old.pk)
                .exists()
            ):
                raise AmendmentAlreadyPendingError(
                    "An unapproved amendment already exists for this result."
                )

            plan = _evaluate_plan(
                sample=old.sample,
                test_id=old.test_id,
                # RS-V1: stored verbatim, only leading/trailing whitespace
                # trimmed.
                value=clean_value,
                unit=(unit or "").strip() or None,
            )
            try:
                # Savepoint: a concurrent amendment racing us loses the
                # partial unique constraint and gets 409 naming the winner.
                with transaction.atomic():
                    new = Result.objects.create(
                        sample=old.sample,
                        test_id=old.test_id,
                        value=plan["value"],
                        unit=plan["unit"],
                        flag=plan["flag"],
                        status=Result.Status.ENTERED,
                        entered_by=actor,
                        supersedes=old,
                        amend_reason=clean_reason,
                    )
            except IntegrityError:
                winner = (
                    Result.objects.select_related("entered_by")
                    .filter(
                        sample_id=old.sample_id,
                        test_id=old.test_id,
                        status=Result.Status.ENTERED,
                    )
                    .exclude(pk=old.pk)
                    .order_by("created_at")
                    .first()
                )
                author = winner.entered_by.email if winner is not None else "unknown"
                raise AmendmentAlreadyPendingError(
                    f"An amendment was already created by {author}.",
                ) from None

            AuditLog.objects.create(
                actor_id=actor.id,
                action="result.amendment_created",
                entity_type="result",
                entity_id=new.id,
                before_jsonb={"old_result_id": str(old.id), "old_status": "approved"},
                after_jsonb={
                    "old_result_id": str(old.id),
                    "new_result_id": str(new.id),
                    "sample_id": str(old.sample_id),
                    "test_id": str(old.test_id),
                    "value": plan["value"],
                    "unit": plan["unit"],
                    "flag": plan["flag"],
                    "reason": clean_reason,
                    "entered_by": str(actor.id),
                    "event": "result.entered",
                },
                ip=ip,
                user_agent=user_agent,
            )

        return {
            "id": str(new.id),
            "test_id": str(plan["test_id"]),
            "value": new.value,
            "unit": new.unit,
            "flag": new.flag,
            "qualifier": plan["qualifier"],
            "needs_review": plan["needs_review"],
            "status": new.status,
            "matched_range": plan["range_summary"],
            "entered_by": str(actor.id),
            "supersedes": str(old.id),
            "amend_reason": clean_reason,
        }

    # ---- Critical notifications (§8.5, §6.6, Doc 02 §5.6 v1.2) ----

    @staticmethod
    def record_critical_notification(
        *,
        result_id: uuid.UUID,
        notified_name: str | None,
        notified_at: datetime,
        read_back: bool,
        actor: StaffUser,
        ip: str | None = None,
        user_agent: str | None = None,
    ) -> dict[str, Any]:
        """Record a critical-result notification (LAB-28 / KAN-153, §8.5).

        Only Manager or Pathologist may record (§4.3, §6.6 — enforced in the
        view); only on a result flagged critical. Append-only: each call
        creates a new critical_notification row; the DB-level P-5 REVOKE set
        (UPDATE/DELETE/TRUNCATE revoked on critical_notification) forbids
        mutation. Audit result.critical_notified carries the event flag
        result.critical_notified. The §11 exceptions list clears by derived
        state: a critical result with a notification record no longer
        qualifies as "unnotified".
        """
        clean_name = (notified_name or "").strip()
        if not clean_name:
            raise NotifiedNameRequiredError(
                "notified_name is required and non-empty after trim."
            )
        if notified_at > timezone.now():
            raise NotificationInFutureError("notified_at cannot be in the future.")

        with transaction.atomic():
            try:
                result = Result.objects.get(pk=result_id)
            except Result.DoesNotExist:
                raise ResultNotFoundError("Result not found.") from None

            if result.flag != Result.Flag.CRITICAL:
                raise NotCriticalError(
                    "A critical notification may only be recorded on a critical result."
                )

            notification = CriticalNotification.objects.create(
                result=result,
                notified_name=clean_name,
                notified_at=notified_at,
                read_back=read_back,
                recorded_by=actor,
            )
            AuditLog.objects.create(
                actor_id=actor.id,
                action="result.critical_notified",
                entity_type="result",
                entity_id=result.id,
                before_jsonb={"notified": False},
                after_jsonb={
                    "notified": True,
                    "notification_id": str(notification.id),
                    "notified_name": clean_name,
                    "notified_at": notification.notified_at.isoformat(),
                    "read_back": read_back,
                    "recorded_by": str(actor.id),
                    "event": "result.critical_notified",
                },
                ip=ip,
                user_agent=user_agent,
            )

        return {
            "id": str(notification.id),
            "result_id": str(result.id),
            "notified_name": clean_name,
            "notified_at": notification.notified_at.isoformat(),
            "read_back": notification.read_back,
            "recorded_by": str(actor.id),
            "created_at": notification.created_at.isoformat(),
        }


def _winner_details(result: Result) -> dict[str, Any] | None:
    """T-31: the loser of a concurrent decision names the winner."""
    winner = (
        ResultApproval.objects.select_related("pathologist")
        .filter(result=result)
        .order_by("created_at")
        .first()
    )
    if winner is None:
        return None
    return {
        "decision": winner.decision,
        "decided_by": winner.pathologist.email,
        "approval_id": str(winner.id),
    }


def _is_numeric_unparseable(result: Result) -> bool:
    """RS-10: True when the test is numeric-kind but the value is unparseable.

    Numeric-kind follows the engine (§8.1): a reference range row with low
    and high NOT NULL. parse_result decides unparseability.
    """
    if parse_result(result.value).value is not None:
        return False
    return ReferenceRange.objects.filter(
        test_id=result.test_id, low__isnull=False, high__isnull=False
    ).exists()


def _maybe_complete_sample(
    *,
    sample_id: uuid.UUID,
    actor: StaffUser,
    ip: str | None,
    user_agent: str | None,
) -> bool:
    """RS-8: move the sample to ready once every sample_test is approved.

    Returns True when the transition happened. SM-5: the READY sample_event
    is written in the same transaction as the status update; the audit row
    carries the sample.ready event flag (cross-module trigger pattern —
    there is no event bus yet).
    """
    test_ids = set(
        SampleTest.objects.filter(sample_id=sample_id).values_list("test_id", flat=True)
    )
    if not test_ids:
        return False
    approved_ids = set(
        Result.objects.filter(
            sample_id=sample_id, status=Result.Status.APPROVED
        ).values_list("test_id", flat=True)
    )
    if not test_ids <= approved_ids:
        return False

    sample = Sample.objects.select_for_update().get(pk=sample_id)
    if sample.status == Sample.Status.READY:
        return False
    before_status = sample.status
    sample.status = Sample.Status.READY
    sample.save(update_fields=["status", "updated_at"])
    SampleEvent.objects.create(
        sample=sample,
        event=SampleEvent.EventType.READY,
        actor=actor,
        branch=sample.branch,
    )
    AuditLog.objects.create(
        actor_id=actor.id,
        action="sample.ready",
        entity_type="sample",
        entity_id=sample.id,
        before_jsonb={"status": before_status},
        after_jsonb={
            "accession_id": sample.accession_id,
            "to_status": "ready",
            "event": "sample.ready",
        },
        ip=ip,
        user_agent=user_agent,
    )
    return True
