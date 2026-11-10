"""Patient Service Layer (Doc 03 §5.1, §6.2, Doc 04 §8.5).

Implements:
- Server-assigned MRN sequence per branch (Doc 02 §9, PT-1).
- Duplicate check PT-3 (exact phone, pg_trgm name similarity + DOB).
- Multi-branch scoping BS-1 to BS-4 (query-level scoping, BS-4 identifiers-only).
- Optimistic concurrency If-Match (T-37) & PT-4 identity edit gate.
- Soft delete PT-5 with in-flight sample guard.
- AuditLog emission within database transactions.
"""

import re
import uuid
from datetime import date
from typing import Any

from django.contrib.postgres.search import TrigramSimilarity
from django.db import connection, transaction
from django.utils import timezone

from apps.accounts.models import AuditLog, Role, StaffBranch, StaffUser
from apps.branches.models import Branch
from apps.patients.models import Patient, PatientConsent, PatientContact
from apps.reports.models import Report


class PossibleDuplicateError(Exception):
    def __init__(self, candidates: list[Patient]) -> None:
        super().__init__("One or more potential duplicate patient records found.")
        self.candidates = candidates


class VersionConflictError(Exception):
    pass


class IdentityEditForbiddenError(Exception):
    pass


class SamplesInFlightError(Exception):
    pass


class BranchScopeDeniedError(Exception):
    pass


class PatientNotFoundError(Exception):
    pass


class PatientService:
    @staticmethod
    def get_caller_branch_scope(user: StaffUser) -> tuple[bool, set[uuid.UUID]]:
        """Return (is_tenant_wide, assigned_branch_ids) per BS-1, BS-2, and SB-3.

        Scope derives strictly from staff_branch join table on open branches.
        user.branch is a display default, never the scope source (Doc 04 §8.4 SB-3).
        """
        if user.role in (Role.OWNER, Role.PATHOLOGIST):
            return True, set()

        branch_ids = set(
            StaffBranch.objects.filter(
                staff_user=user,
                branch__deleted_at__isnull=True,
            ).values_list("branch_id", flat=True)
        )
        return False, branch_ids

    @staticmethod
    def generate_mrn(branch: Branch) -> str:
        """Mint sequential MRN-{branch_code:3}-{seq:06d} via safe DB sequence."""
        clean_code = re.sub(r"[^a-zA-Z0-9]", "", branch.code.lower())
        seq_name = f"seq_mrn_{clean_code}"
        with connection.cursor() as cursor:
            quoted_seq = connection.ops.quote_name(seq_name)
            cursor.execute(f"CREATE SEQUENCE IF NOT EXISTS {quoted_seq} START 1;")
            cursor.execute("SELECT nextval(%s);", [seq_name])
            seq = cursor.fetchone()[0]
        return f"MRN-{branch.code.upper()}-{seq:06d}"

    @classmethod
    def check_duplicates(
        cls,
        phone: str,
        name: str,
        date_of_birth: date | None = None,
    ) -> list[Patient]:
        """Check for duplicates: exact phone or trigram name + same DOB (PT-3)."""
        candidates: dict[uuid.UUID, Patient] = {}

        # 1. Exact phone match on active records
        phone_matches = Patient.objects.filter(
            phone=phone,
            deleted_at__isnull=True,
        )
        for p in phone_matches:
            candidates[p.id] = p

        # 2. pg_trgm name similarity (> 0.3) + same date_of_birth
        if date_of_birth:
            name_matches = (
                Patient.objects.filter(
                    date_of_birth=date_of_birth,
                    deleted_at__isnull=True,
                )
                .annotate(similarity=TrigramSimilarity("name", name))
                .filter(similarity__gt=0.3)
            )
            for p in name_matches:
                candidates[p.id] = p

        return list(candidates.values())

    @classmethod
    def register_patient(
        cls,
        actor: StaffUser,
        name: str,
        phone: str,
        sex: str,
        branch_id: uuid.UUID,
        date_of_birth: date | None = None,
        confirm_duplicate: bool = False,
        whatsapp_number: str | None = None,
        consent_reports: bool = False,
        ip: str | None = None,
        user_agent: str | None = None,
    ) -> Patient:
        """Register a patient, enforce PT-3, generate MRN, and log audit row.

        Digital delivery (PT-2): when the patient consents to report delivery,
        the WhatsApp destination and the consent grant are persisted here, in
        the same transaction as the patient row. Without both rows every later
        ``reports.deliver`` call fails its consent/contact checks, so the
        registration form's "Digital Delivery & Consent" section would be a
        no-op.
        """
        is_tenant_wide, assigned_branches = cls.get_caller_branch_scope(actor)
        if not is_tenant_wide and branch_id not in assigned_branches:
            raise BranchScopeDeniedError("Branch is outside caller scope.")

        try:
            branch = Branch.objects.get(id=branch_id, deleted_at__isnull=True)
        except Branch.DoesNotExist as exc:
            raise BranchScopeDeniedError("Invalid or inactive branch.") from exc

        # Duplicate check PT-3
        confirmed_candidate_mrns: list[str] = []
        if confirm_duplicate:
            candidates = cls.check_duplicates(
                phone=phone, name=name, date_of_birth=date_of_birth
            )
            confirmed_candidate_mrns = [c.mrn for c in candidates]
        else:
            candidates = cls.check_duplicates(
                phone=phone, name=name, date_of_birth=date_of_birth
            )
            if candidates:
                raise PossibleDuplicateError(candidates)

        with transaction.atomic():
            mrn = cls.generate_mrn(branch)
            patient = Patient.objects.create(
                mrn=mrn,
                name=name,
                phone=phone,
                sex=sex,
                date_of_birth=date_of_birth,
                branch=branch,
            )

            # Digital delivery destination. Only persisted when the operator
            # supplied a WhatsApp number or recorded delivery consent; the
            # registered phone is a valid WhatsApp destination when the
            # dedicated field is left blank.
            contact: PatientContact | None = None
            consent: PatientConsent | None = None
            if consent_reports or whatsapp_number:
                contact = PatientContact.objects.create(
                    patient=patient,
                    kind=PatientContact.Kind.WHATSAPP,
                    value=whatsapp_number or phone,
                    is_primary=True,
                )
            if consent_reports:
                consent = PatientConsent.objects.create(
                    patient=patient,
                    channel=PatientConsent.Channel.WHATSAPP,
                    granted_at=timezone.now(),
                    granted_by=actor,
                )

            # Audit log row
            AuditLog.objects.create(
                actor_id=actor.id,
                action="patient.registered",
                entity_type="patient",
                entity_id=patient.id,
                before_jsonb=None,
                after_jsonb={
                    "mrn": patient.mrn,
                    "name": patient.name,
                    "phone": patient.phone,
                    "sex": patient.sex,
                    "branch_id": str(patient.branch_id),
                    "duplicate_confirmed": confirm_duplicate,
                    "confirmed_duplicate_mrns": confirmed_candidate_mrns,
                    "whatsapp_contact_id": str(contact.id) if contact else None,
                    "report_delivery_consent": consent is not None,
                    "consent_channel": consent.channel if consent else None,
                },
                ip=ip or "",
                user_agent=user_agent or "",
            )

        return patient

    @classmethod
    def list_patients(
        cls,
        actor: StaffUser,
        q: str | None = None,
        branch_id: uuid.UUID | None = None,
        ip: str | None = None,
        user_agent: str | None = None,
    ) -> list[Patient]:
        """List/search patients respecting BS-1 to BS-4 multi-branch scoping."""
        is_tenant_wide, assigned_branches = cls.get_caller_branch_scope(actor)

        # BS-2: Unassigned staff gets empty list
        if not is_tenant_wide and not assigned_branches:
            return []

        if (
            branch_id is not None
            and not is_tenant_wide
            and branch_id not in assigned_branches
        ):
            return []

        filters: dict[str, Any] = {"deleted_at__isnull": True}
        if branch_id is not None:
            filters["branch_id"] = branch_id

        # Case 1: Search query provided (BS-4 applies — the one method
        # allowed to cross branch scope; deliberately NOT routed through
        # scoped_to).
        if q:
            clean_q = q.strip()[:120]
            annotated_qs = (
                Patient.objects.filter(**filters)
                .select_related("branch")
                .annotate(similarity=TrigramSimilarity("name", clean_q))
                .filter(models_q_filter(clean_q))
                .order_by("-similarity", "-created_at")
            )
            patients: list[Patient] = [p for p in annotated_qs[:100]]

            cross_branch_hit = False
            for p in patients:
                if is_tenant_wide or p.branch_id in assigned_branches:
                    p._is_cross_branch = False
                else:
                    p._is_cross_branch = True
                    cross_branch_hit = True

            # Audit cross-branch search hits if occurred
            if cross_branch_hit:
                AuditLog.objects.create(
                    actor_id=actor.id,
                    action="patient.cross_branch_searched",
                    entity_type="patient",
                    entity_id=uuid.UUID(int=0),
                    before_jsonb=None,
                    after_jsonb={"query": clean_q},
                    ip=ip or "",
                    user_agent=user_agent or "",
                )

            return patients

        # Case 2: Listing without search query — canonical §8.5 Layer-1
        # scope: the manager-level scoped_to() keeps the BranchScopedQuerySet
        # type through chaining (django-stubs resolves chained .filter() to
        # the plain QuerySet).
        qs = Patient.objects.scoped_to(actor).select_related("branch").filter(**filters)

        listed_patients: list[Patient] = [p for p in qs.order_by("-created_at")[:100]]
        for p in listed_patients:
            p._is_cross_branch = False
        return listed_patients

    @classmethod
    def get_patient_detail(
        cls,
        actor: StaffUser,
        patient_id: uuid.UUID,
        ip: str | None = None,
        user_agent: str | None = None,
    ) -> Patient:
        """Fetch patient detail enforcing BS-3 / P-7 anti-oracle 404."""
        try:
            patient = Patient.objects.get(id=patient_id, deleted_at__isnull=True)
        except Patient.DoesNotExist as exc:
            raise PatientNotFoundError() from exc

        is_tenant_wide, assigned_branches = cls.get_caller_branch_scope(actor)

        # P-7 & BS-3: Return 404 if out of branch scope for non-tenant-wide staff
        if not is_tenant_wide and patient.branch_id not in assigned_branches:
            raise PatientNotFoundError()

        # Audit cross-branch detail view if tenant-wide staff accesses another branch
        if is_tenant_wide and actor.branch_id and actor.branch_id != patient.branch_id:
            AuditLog.objects.create(
                actor_id=actor.id,
                action="patient.cross_branch_viewed",
                entity_type="patient",
                entity_id=patient.id,
                before_jsonb=None,
                after_jsonb={"branch_id": str(patient.branch_id)},
                ip=ip or "",
                user_agent=user_agent or "",
            )

        return patient

    @classmethod
    def update_patient(
        cls,
        actor: StaffUser,
        patient_id: uuid.UUID,
        data: dict[str, Any],
        if_match: str | None = None,
        ip: str | None = None,
        user_agent: str | None = None,
    ) -> Patient:
        """Update patient with If-Match check (T-37) and PT-4 identity edit rules."""
        patient = cls.get_patient_detail(actor, patient_id)

        # Optimistic concurrency check (T-37)
        if if_match:
            clean_if_match = if_match.strip().strip('"').strip("'")
            patient_updated = patient.updated_at.isoformat()
            if clean_if_match not in (patient_updated, str(patient.updated_at)):
                raise VersionConflictError("Resource modified since last fetch.")

        # PT-4 identity edit gate
        identity_fields = {"name", "sex", "date_of_birth"}
        touches_identity = any(k in data for k in identity_fields)

        if touches_identity:
            has_finalised_report = (
                Report.objects.filter(
                    sample__invoice__patient=patient,
                    status__in=[Report.Status.FINAL, Report.Status.AMENDED],
                ).exists()
                or Report.objects.filter(
                    sample__invoice__patient=patient,
                    finalised_at__isnull=False,
                ).exists()
            )
            if has_finalised_report and actor.role not in (Role.OWNER, Role.MANAGER):
                raise IdentityEditForbiddenError(
                    "Identity edits after finalised report require Owner or Manager."
                )

        before_values: dict[str, Any] = {}
        after_values: dict[str, Any] = {}

        with transaction.atomic():
            for field in ("name", "phone", "sex", "date_of_birth"):
                if field in data:
                    old_val = getattr(patient, field)
                    new_val = data[field]
                    if old_val != new_val:
                        before_values[field] = (
                            str(old_val) if old_val is not None else None
                        )
                        after_values[field] = (
                            str(new_val) if new_val is not None else None
                        )
                        setattr(patient, field, new_val)

            patient.save()

            if after_values:
                AuditLog.objects.create(
                    actor_id=actor.id,
                    action="patient.updated",
                    entity_type="patient",
                    entity_id=patient.id,
                    before_jsonb=before_values,
                    after_jsonb=after_values,
                    ip=ip or "",
                    user_agent=user_agent or "",
                )

        return patient

    @classmethod
    def soft_delete_patient(
        cls,
        actor: StaffUser,
        patient_id: uuid.UUID,
        ip: str | None = None,
        user_agent: str | None = None,
    ) -> None:
        """Soft delete patient per PT-5 with sample guard and idempotent 204."""
        if actor.role not in (Role.OWNER, Role.MANAGER):
            raise BranchScopeDeniedError("Only Owner or Manager may delete patients.")

        try:
            patient = Patient.objects.get(id=patient_id)
        except Patient.DoesNotExist as exc:
            raise PatientNotFoundError() from exc

        is_tenant_wide, assigned_branches = cls.get_caller_branch_scope(actor)
        if not is_tenant_wide and patient.branch_id not in assigned_branches:
            raise PatientNotFoundError()

        # Idempotent second delete returns 204
        if patient.deleted_at is not None:
            return

        # PT-5 sample guard: samples in flight block deletion
        from apps.samples.models import Sample

        in_flight = Sample.objects.filter(
            invoice__patient=patient,
            status__in=["collected", "received", "in_process"],
        ).exists()
        if in_flight:
            raise SamplesInFlightError("Cannot delete patient with samples in flight.")

        with transaction.atomic():
            now = timezone.now()
            patient.deleted_at = now
            patient.save(update_fields=["deleted_at", "updated_at"])

            AuditLog.objects.create(
                actor_id=actor.id,
                action="patient.soft_deleted",
                entity_type="patient",
                entity_id=patient.id,
                before_jsonb={"deleted_at": None},
                after_jsonb={"deleted_at": now.isoformat()},
                ip=ip or "",
                user_agent=user_agent or "",
            )


def models_q_filter(query: str) -> Any:
    """Build Q filter searching MRN, phone digits, or name trigram/icontains."""
    from django.db.models import Q

    return (
        Q(mrn__iexact=query)
        | Q(phone__icontains=query)
        | Q(name__icontains=query)
        | Q(similarity__gt=0.2)
    )
