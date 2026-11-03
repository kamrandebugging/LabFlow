"""Report service — async PDF pipeline orchestration (KAN-155 / LAB-30)
and public report portal: access-token mint / redeem / revoke
(KAN-156 / LAB-31).

Doc 03 §5.6 (RP-1, RP-2, RP-3, RP-8, RP-9, RP-V2, RP-V3), §6.7, §6.8, §10.
Thin orchestration only: the actual rendering lives in apps/reports/pdf/,
the Celery task in apps/reports/tasks.py.

Concurrency model (§10):
- reports.generate_pdf is idempotent: deterministic pdf_key
  (reports/{report_id}/{version}.pdf) + existence check for the target
  version — a repeat run that finds the version row exits as success.
- In-flight guard: Report.generation_status (idle|running|failed). The
  request-side claim (SELECT ... FOR UPDATE inside a transaction) runs BEFORE
  enqueueing, so a second enqueue while one is in flight -> 409
  generation_already_running. The worker re-checks under its own lock.

Public portal (LAB-31) token design (RP-8):
- Token = 32 random bytes, urlsafe-base64 encoded (44 chars). Only the
  argon2 hash is stored (ReportAccessToken.token_hash); the plain token is
  returned ONCE in the 201 mint response and never stored, logged or
  audited.
- Redemption scans stored hashes with argon2 verify (hashes cannot be
  looked up directly). Live tokens are verified first, then dead
  (expired/revoked) tokens so the response can distinguish 404 (unknown)
  from 410 (expired/revoked). The scan is linear per tenant — acceptable
  because the live token set is small, and the public endpoint is
  rate-limited (see apps/reports/throttling.py) so an attacker cannot
  turn the ~100ms-per-row verify cost into a DoS.
"""

from __future__ import annotations

import base64
import secrets
import uuid
from datetime import timedelta
from typing import Any

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from django.db import connection, transaction
from django.db.models import Q
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import AuditLog, Role, StaffUser, TenantSetting
from apps.reports.models import (
    Report,
    ReportAccessToken,
    ReportDelivery,
    ReportVersion,
)
from apps.reports.storage import ReportStorage

# Doc 03 §6.7: POST /api/v1/reports/{id}/regenerate — roles cell "O M P".
REPORT_REGENERATE_ROLES = {Role.OWNER, Role.MANAGER, Role.PATHOLOGIST}
# Doc 03 §6.7: POST /api/v1/reports/{id}/access-token — roles cell "O M R".
REPORT_ACCESS_TOKEN_ROLES = {Role.OWNER, Role.MANAGER, Role.RECEPTION}
# Doc 03 §6.7: POST /api/v1/reports/{id}/revoke-token — roles cell "O M".
REPORT_REVOKE_TOKEN_ROLES = {Role.OWNER, Role.MANAGER}

# Doc 03 §5.6 RP-8: tenant_setting key + platform default for new tokens.
TOKEN_VALIDITY_SETTING_KEY = "report_link_validity_days"
DEFAULT_TOKEN_VALIDITY_DAYS = 7
# Doc 01 §14 / RP-8: pre-signed storage URL lifetime, ~15 minutes.
FILE_URL_VALIDITY_SECONDS = 15 * 60

_ph = PasswordHasher()


class ReportError(Exception):
    error_code = "report_error"
    status_code = 400

    def __init__(self, message: str = "", details: Any = None) -> None:
        super().__init__(message)
        self.details = details


class ReportNotFoundError(ReportError):
    error_code = "not_found"
    status_code = 404


class ReportVoidError(ReportError):
    error_code = "report_void"
    status_code = 409


class GenerationAlreadyRunningError(ReportError):
    error_code = "generation_already_running"
    status_code = 409


class ReportNotFinalError(ReportError):
    """RP-V2: token issue/delivery needs status final|amended, version >= 1."""

    error_code = "report_not_final"
    status_code = 409


class AccessTokenNotFoundError(ReportError):
    """Public portal: presented token matches no stored hash."""

    error_code = "token_not_found"
    status_code = 404


class AccessTokenExpiredError(ReportError):
    error_code = "link_expired"
    status_code = 410


class AccessTokenRevokedError(ReportError):
    error_code = "link_revoked"
    status_code = 410


class ReportVersionMissingError(ReportError):
    """Current version has no stored PDF — data inconsistency, 500."""

    error_code = "report_version_missing"
    status_code = 500


def _schema_name() -> str:
    tenant = getattr(connection, "tenant", None)
    return getattr(tenant, "schema_name", "public")


def _enqueue_generate_pdf(
    report_id: uuid.UUID, triggered_by: uuid.UUID | None, target_version: int
) -> None:
    """Enqueue reports.generate_pdf AFTER the caller's transaction commits."""
    schema_name = _schema_name()
    report_pk = str(report_id)
    actor_pk = str(triggered_by) if triggered_by is not None else None

    def _enqueue() -> None:
        from apps.reports.tasks import generate_pdf_task

        generate_pdf_task.delay(schema_name, report_pk, actor_pk, target_version)

    transaction.on_commit(_enqueue)


class ReportService:
    """Orchestration for the async report PDF pipeline."""

    @staticmethod
    def _get_report(report_id: uuid.UUID) -> Report:
        try:
            return Report.objects.get(pk=report_id)
        except (Report.DoesNotExist, ValueError, TypeError) as exc:
            raise ReportNotFoundError("Report not found.") from exc

    @staticmethod
    def _claim_generation(report: Report) -> Report | None:
        """Atomically claim the in-flight slot.

        Returns the locked report when this caller won the claim (status was
        idle or failed -> now running), or None when another generation is
        already running. Must be called inside a transaction.
        """
        locked = Report.objects.select_for_update().get(pk=report.pk)
        if locked.generation_status == Report.GenerationStatus.RUNNING:
            return None
        locked.generation_status = Report.GenerationStatus.RUNNING
        locked.generation_error = None
        locked.save(
            update_fields=["generation_status", "generation_error", "updated_at"]
        )
        return locked

    @staticmethod
    def ensure_report_for_sample(*, sample_id: uuid.UUID) -> Report:
        """RP-1: get-or-create the draft report row for a ready sample."""
        report, _ = Report.objects.get_or_create(
            sample_id=sample_id,
            defaults={
                "status": Report.Status.DRAFT,
                "current_version": 0,
            },
        )
        return report

    @staticmethod
    def enqueue_generation_for_sample(
        *, sample_id: uuid.UUID, actor: StaffUser
    ) -> bool:
        """RP-1 hook: sample just became ready -> ensure the draft report row
        and enqueue reports.generate_pdf (exactly-once per ready transition).

        Returns True when a generation was enqueued.
        """
        with transaction.atomic():
            report = ReportService.ensure_report_for_sample(sample_id=sample_id)
            if report.status == Report.Status.VOID:
                return False
            locked = ReportService._claim_generation(report)
            if locked is None:
                return False
            _enqueue_generate_pdf(locked.id, actor.id, locked.current_version + 1)
            return True

    @staticmethod
    def regenerate_report(
        *,
        report_id: uuid.UUID,
        actor: StaffUser,
        ip: str | None = None,
        user_agent: str | None = None,
    ) -> dict[str, Any]:
        """POST /api/v1/reports/{id}/regenerate (§6.7).

        Enqueues reports.generate_pdf for a new version from the current
        approved results. -> 202 with the report state. 409 report_void;
        409 generation_already_running. The named user is recorded as the
        generated_by trigger in audit.
        """
        with transaction.atomic():
            report = ReportService._get_report(report_id)
            if report.status == Report.Status.VOID:
                raise ReportVoidError("Report is void and cannot be regenerated.")
            locked = ReportService._claim_generation(report)
            if locked is None:
                raise GenerationAlreadyRunningError(
                    "A PDF generation is already in flight for this report."
                )
            AuditLog.objects.create(
                actor_id=actor.id,
                action="report.regenerate_requested",
                entity_type="report",
                entity_id=locked.id,
                before_jsonb={
                    "status": locked.status,
                    "current_version": locked.current_version,
                },
                after_jsonb={
                    "generated_by": str(actor.id),
                    "generated_by_email": actor.email,
                    "generation_status": Report.GenerationStatus.RUNNING,
                },
                ip=ip,
                user_agent=user_agent,
            )
            _enqueue_generate_pdf(locked.id, actor.id, locked.current_version + 1)
            return {
                "id": str(locked.id),
                "sample_id": str(locked.sample_id),
                "status": locked.status,
                "current_version": locked.current_version,
                "generation_status": Report.GenerationStatus.RUNNING,
            }


class ReportAccessService:
    """Public report portal: access-token mint / redeem / revoke
    (Doc 03 §5.6 RP-8/RP-9/RP-V2/RP-V3, §6.7, §6.8; KAN-156 / LAB-31).

    Security notes:
    - The plain token exists only in memory during issue and once in the
      201 response body. It is never persisted, never logged and never
      written to audit_jsonb — audit rows carry the token ROW id only.
    - Redemption verifies the presented token against stored argon2 hashes
      (see _find_token for the two-pass scan and its documented limits).
    - RP-V3: the token is the ONLY credential accepted; the public view
      takes no patient ID, MRN or report ID.
    """

    @staticmethod
    def _validity_days() -> int:
        """New-token lifetime from the tenant setting, default 7 days."""
        row = TenantSetting.objects.filter(key=TOKEN_VALIDITY_SETTING_KEY).first()
        if row is None:
            return DEFAULT_TOKEN_VALIDITY_DAYS
        try:
            days = int(row.value)
        except (TypeError, ValueError):
            return DEFAULT_TOKEN_VALIDITY_DAYS
        return days if days > 0 else DEFAULT_TOKEN_VALIDITY_DAYS

    @staticmethod
    def _branch_phone(report_id: uuid.UUID) -> str | None:
        report = (
            Report.objects.select_related("sample__branch")
            .only("sample__branch__phone")
            .get(pk=report_id)
        )
        branch = report.sample.branch
        return branch.phone if branch is not None else None

    @staticmethod
    def _find_token(plain: str) -> tuple[ReportAccessToken | None, str | None]:
        """Locate the token row matching `plain` via argon2 verify.

        Two passes: live tokens first (non-revoked, non-expired, newest
        first), then dead tokens so the caller can distinguish unknown
        (404) from expired/revoked (410). Returns (row, reason) where
        reason is None for a live token, else "expired" or "revoked".

        Limits, by design: the scan is linear in the tenant's token rows
        because salted argon2 hashes cannot be indexed or looked up
        directly. This is acceptable because (a) the live set stays small —
        tokens expire in days and dead rows are never re-scanned for
        success, and (b) the public endpoint is rate-limited per IP (see
        apps/reports/throttling.py) so the ~100ms-per-row verify cost
        cannot be weaponised into a cheap DoS.
        """
        now = timezone.now()
        live = (
            ReportAccessToken.objects.filter(
                revoked_at__isnull=True, expires_at__gt=now
            )
            .order_by("-created_at")
            .iterator()
        )
        for row in live:
            try:
                if _ph.verify(row.token_hash, plain):
                    return row, None
            except VerifyMismatchError:
                continue
        dead = (
            ReportAccessToken.objects.filter(
                Q(revoked_at__isnull=False) | Q(expires_at__lte=now)
            )
            .order_by("-created_at")
            .iterator()
        )
        for row in dead:
            try:
                if _ph.verify(row.token_hash, plain):
                    reason = "revoked" if row.revoked_at is not None else "expired"
                    return row, reason
            except VerifyMismatchError:
                continue
        return None, None

    @staticmethod
    def issue_access_token(
        *,
        report_id: uuid.UUID,
        actor: StaffUser,
        ip: str | None = None,
        user_agent: str | None = None,
    ) -> dict[str, Any]:
        """POST /api/v1/reports/{id}/access-token (§6.7).

        Mints a fresh patient link WITHOUT sending (phone read-out / manual
        WhatsApp). RP-V2: 409 report_not_final unless status is final|amended
        with current_version >= 1; void -> 409 report_void; unknown -> 404.
        -> 201 payload {token_id, link, expires_at}; the plain token appears
        only inside `link`, once. Audit: report.token_issued (token row id).
        Event: none (delivery/access events cover use).
        """
        with transaction.atomic():
            report = ReportService._get_report(report_id)
            if report.status == Report.Status.VOID:
                raise ReportVoidError("Report is void; its patient links are revoked.")
            if (
                report.status not in (Report.Status.FINAL, Report.Status.AMENDED)
                or report.current_version < 1
            ):
                raise ReportNotFinalError(
                    "Report is not finalised; no patient link may be issued."
                )
            plain = base64.urlsafe_b64encode(secrets.token_bytes(32)).decode("ascii")
            token_hash = _ph.hash(plain)
            expires_at = timezone.now() + timedelta(
                days=ReportAccessService._validity_days()
            )
            row = ReportAccessToken.objects.create(
                report=report,
                token_hash=token_hash,
                expires_at=expires_at,
            )
            AuditLog.objects.create(
                actor_id=actor.id,
                action="report.token_issued",
                entity_type="report_access_token",
                entity_id=row.id,
                after_jsonb={
                    "token_id": str(row.id),
                    "report_id": str(report.id),
                    "expires_at": row.expires_at.isoformat(),
                },
                ip=ip,
                user_agent=user_agent,
            )
            return {
                "token_id": str(row.id),
                # reverse() keeps this in sync with the URL route; the
                # plain token appears here exactly once (ECC: no hardcoded
                # URL, no logging of this dict anywhere).
                "link": reverse("report-access", kwargs={"token": plain}),
                "expires_at": row.expires_at.isoformat(),
            }

    @staticmethod
    def redeem_access_token(
        *,
        token: str,
        ip: str | None = None,
        user_agent: str | None = None,
    ) -> dict[str, Any]:
        """GET /api/v1/report-access/{token} — PUBLIC, no auth (§6.8, RP-V3).

        On success: sets last_accessed_at, marks the latest PENDING/SENT
        delivery OPENED, audits report.accessed with the event flag, and
        returns redirect_url — a short-lived (~15 min) pre-signed URL for
        the CURRENT version's pdf_key (RP-8: an amended report's old link
        serves the corrected PDF). The token is reusable inside its
        validity period.
        Failures: unknown -> 404 token_not_found; expired/revoked -> 410
        link_expired/link_revoked (details carry the lab phone for the 410
        page). EVERY attempt is audited, success and failure, without
        ever recording the presented token.
        """
        row, reason = ReportAccessService._find_token(token)
        if row is None:
            with transaction.atomic():
                AuditLog.objects.create(
                    actor_id=None,
                    action="report.access_failed",
                    entity_type="public_access_attempt",
                    entity_id=uuid.uuid4(),
                    after_jsonb={"reason": "unknown"},
                    ip=ip,
                    user_agent=user_agent,
                )
            raise AccessTokenNotFoundError("Report link not found.")
        phone = ReportAccessService._branch_phone(row.report_id)
        if reason is not None:
            with transaction.atomic():
                AuditLog.objects.create(
                    actor_id=None,
                    action="report.access_failed",
                    entity_type="report_access_token",
                    entity_id=row.id,
                    after_jsonb={
                        "reason": reason,
                        "token_id": str(row.id),
                        "report_id": str(row.report_id),
                    },
                    ip=ip,
                    user_agent=user_agent,
                )
            if reason == "revoked":
                raise AccessTokenRevokedError(
                    "This report link has been revoked.",
                    details={"phone": phone},
                )
            raise AccessTokenExpiredError(
                "This report link has expired.",
                details={"phone": phone},
            )
        with transaction.atomic():
            now = timezone.now()
            row.last_accessed_at = now
            row.save(update_fields=["last_accessed_at", "updated_at"])
            # RP-8: patient links always resolve to the CURRENT version —
            # after an amendment the old link serves the corrected PDF.
            report = ReportService._get_report(row.report_id)
            version = ReportVersion.objects.filter(
                report=report, version=report.current_version
            ).first()
            if version is None:
                raise ReportVersionMissingError(
                    "Report has no stored PDF for its current version."
                )
            delivery = (
                ReportDelivery.objects.filter(
                    report_id=row.report_id,
                    status__in=[
                        ReportDelivery.Status.PENDING,
                        ReportDelivery.Status.SENT,
                    ],
                )
                .order_by("-created_at")
                .first()
            )
            if delivery is not None:
                delivery.status = ReportDelivery.Status.OPENED
                delivery.save(update_fields=["status", "updated_at"])
            redirect_url = ReportStorage().presigned_url(
                version.pdf_key, expires_seconds=FILE_URL_VALIDITY_SECONDS
            )
            AuditLog.objects.create(
                actor_id=None,
                action="report.accessed",
                entity_type="report_access_token",
                entity_id=row.id,
                after_jsonb={
                    "token_id": str(row.id),
                    "report_id": str(row.report_id),
                    "pdf_key": version.pdf_key,
                    "event": "report.accessed",
                },
                ip=ip,
                user_agent=user_agent,
            )
            return {
                "token_id": str(row.id),
                "report_id": str(row.report_id),
                "redirect_url": redirect_url,
            }

    @staticmethod
    def revoke_access_token(
        *,
        report_id: uuid.UUID,
        actor: StaffUser,
        token_id: uuid.UUID | None = None,
        revoke_all: bool = False,
        ip: str | None = None,
        user_agent: str | None = None,
    ) -> dict[str, Any]:
        """POST /api/v1/reports/{id}/revoke-token (§6.7).

        token_id (one row) or revoke_all (every live token of the report).
        Sets revoked_at=now. Idempotent: revoking twice -> 200 with
        revoked_count 0. Unknown report or token row -> 404 (tenant-scoped).
        Audit: report.token_revoked. Event flag: report.token_revoked.
        """
        with transaction.atomic():
            report = ReportService._get_report(report_id)
            live = ReportAccessToken.objects.filter(
                report=report, revoked_at__isnull=True
            )
            if token_id is not None:
                # Idempotent: an already-revoked row still exists for this
                # report -> 200 with revoked_count 0. Only a row that never
                # existed (or belongs to another report) is a 404.
                if not ReportAccessToken.objects.filter(
                    report=report, pk=token_id
                ).exists():
                    raise AccessTokenNotFoundError("Access token not found.")
                target = live.filter(pk=token_id)
            elif revoke_all:
                target = live
            else:  # pragma: no cover - the serializer enforces one-of.
                raise AccessTokenNotFoundError("Access token not found.")
            revoked_count = target.update(revoked_at=timezone.now())
            AuditLog.objects.create(
                actor_id=actor.id,
                action="report.token_revoked",
                entity_type="report",
                entity_id=report.id,
                after_jsonb={
                    "token_id": str(token_id) if token_id is not None else None,
                    "all": revoke_all,
                    "revoked_count": revoked_count,
                    "event": "report.token_revoked",
                },
                ip=ip,
                user_agent=user_agent,
            )
            return {"revoked_count": revoked_count}
