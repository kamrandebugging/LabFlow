"""Result entry service — batch result entry (Doc 03 §5.5 RS-1/RS-2/RS-3/RS-V2,
§6.6, §8, KAN-150 / LAB-25, original LAB-30).

Thin-service pattern (same as billing/samples): error subclasses carry the
HTTP status + machine code; views only map them to responses. No business
logic in views.
"""

from __future__ import annotations

import uuid
from datetime import date
from typing import Any

from django.db import IntegrityError, transaction

from apps.accounts.models import AuditLog, Role, StaffUser
from apps.catalog.services import CatalogService, _to_range_row
from apps.results.engine import evaluate_result
from apps.results.models import Result
from apps.samples.models import Sample, SampleEvent, SampleTest, SampleTransfer

# Doc 03 §6.6: POST /api/v1/samples/{id}/results — roles cell is exactly "T P".
RESULT_ENTRY_ROLES = {Role.TECHNICIAN, Role.PATHOLOGIST}


class ResultError(Exception):
    """Base results error carrying an HTTP status + machine code."""

    __test__ = False
    status_code = 422
    error_code = "result_error"

    def __init__(self, message: str = "") -> None:
        super().__init__(message or self.error_code)


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
        patient = sample.invoice.patient
        collected_on = sample.collected_at.date()
        age_days = _age_in_days(patient.date_of_birth, collected_on)
        plans: list[dict[str, Any]] = []
        for row in rows:
            rr_model = CatalogService.resolve_reference_range(
                test_id=row["test_id"],
                patient_sex=patient.sex,
                patient_age_days=age_days,
                collection_date=sample.collected_at,
            )
            range_row = _to_range_row(rr_model) if rr_model is not None else None
            evaluation = evaluate_result(
                row["value"],
                range_row=range_row,
                patient_sex=patient.sex,
                age_in_days=age_days,
                collection_date=sample.collected_at,
                qualitative_values=None,
            )
            unit = row.get("unit") or (rr_model.unit if rr_model is not None else None)
            plans.append(
                {
                    "test_id": row["test_id"],
                    "value": row["value"],  # RS-2: stored EXACTLY as entered
                    "unit": unit,
                    "flag": (
                        evaluation.flag.value if evaluation.flag is not None else None
                    ),
                    "qualifier": evaluation.qualifier,
                    "needs_review": evaluation.needs_review,
                    "range_summary": _range_summary(rr_model),
                }
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
