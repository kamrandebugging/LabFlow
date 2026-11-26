"""DRF Serializers for Patient Management (Doc 03 §5.1, §6.2, Doc 04 §8.5).

Validation rules:
- PT-V1: Name 2-120 chars; phone 10-15 digits normalised; sex M|F; date_of_birth valid.
- BS-4: Out-of-branch search projections restrict strictly to identifiers only.
"""

import re
from datetime import date
from typing import Any

from django.utils import timezone
from rest_framework import serializers

from apps.core.serializers import StrictSerializer
from apps.patients.models import Patient, PatientConsent, PatientContact


def normalize_phone(value: str) -> str:
    """Normalise phone to digits only (strip spaces, dashes, parentheses, +).

    Standardises Pakistani country code (0092/92) to 03xx local format.
    """
    cleaned = re.sub(r"[\s\-()+]", "", value or "")
    if cleaned.startswith("0092") and len(cleaned) == 14:
        cleaned = "0" + cleaned[4:]
    elif cleaned.startswith("92") and len(cleaned) == 12:
        cleaned = "0" + cleaned[2:]
    return cleaned


class PatientValidationMixin:
    """Reusable PT-V1 field validation logic for Patient create and update."""

    def validate_name(self, value: str) -> str:
        trimmed = (value or "").strip()
        if len(trimmed) < 2 or len(trimmed) > 120:
            raise serializers.ValidationError(
                "Name must be between 2 and 120 characters."
            )
        return trimmed

    def validate_phone(self, value: str) -> str:
        normalized = normalize_phone(value)
        if not (10 <= len(normalized) <= 15 and normalized.isdigit()):
            raise serializers.ValidationError("Phone must be between 10 and 15 digits.")
        return normalized

    def validate_date_of_birth(self, value: date | None) -> date | None:
        if value is None:
            return None
        today = timezone.now().date()
        if value > today:
            raise serializers.ValidationError("Date of birth cannot be in the future.")
        if (today.year - value.year) > 120:
            raise serializers.ValidationError(
                "Date of birth cannot be more than 120 years ago."
            )
        return value


class PatientCreateSerializer(PatientValidationMixin, StrictSerializer):
    """Registration serializer enforcing PT-V1 validation."""

    name = serializers.CharField(required=True)
    phone = serializers.CharField(required=True)
    sex = serializers.ChoiceField(choices=Patient.Sex.choices, required=True)
    date_of_birth = serializers.DateField(required=False, allow_null=True)
    referral_partner_id = serializers.UUIDField(
        required=False, allow_null=True, default=None
    )
    branch_id = serializers.UUIDField(required=True)
    whatsapp_number = serializers.CharField(
        required=False, allow_blank=True, allow_null=True, default=None
    )
    consent_reports = serializers.BooleanField(required=False, default=False)
    confirm_duplicate = serializers.BooleanField(required=False, default=False)

    def validate_whatsapp_number(self, value: str | None) -> str | None:
        if not value:
            return None
        normalized = normalize_phone(value)
        if not (10 <= len(normalized) <= 15 and normalized.isdigit()):
            raise serializers.ValidationError(
                "WhatsApp number must be between 10 and 15 digits."
            )
        return normalized


class PatientUpdateSerializer(PatientValidationMixin, StrictSerializer):
    """Update serializer supporting partial PATCH."""

    name = serializers.CharField(required=False)
    phone = serializers.CharField(required=False)
    sex = serializers.ChoiceField(choices=Patient.Sex.choices, required=False)
    date_of_birth = serializers.DateField(required=False, allow_null=True)


class PatientCandidateSerializer(serializers.Serializer):
    """Candidate representation for duplicate checks and BS-4 identifiers-only."""

    id = serializers.UUIDField(read_only=True)
    mrn = serializers.CharField(read_only=True)
    name = serializers.CharField(read_only=True)
    sex = serializers.CharField(read_only=True)
    year_of_birth = serializers.SerializerMethodField()
    branch_id = serializers.UUIDField(read_only=True)

    def get_year_of_birth(self, obj: Patient) -> int | None:
        return obj.date_of_birth.year if obj.date_of_birth else None


class PatientContactSerializer(serializers.ModelSerializer[PatientContact]):
    class Meta:
        model = PatientContact
        fields = ["id", "kind", "value", "is_primary", "created_at"]


class PatientConsentSerializer(serializers.ModelSerializer[PatientConsent]):
    class Meta:
        model = PatientConsent
        fields = ["id", "channel", "granted_at", "granted_by", "revoked_at"]


class PatientSummarySerializer(serializers.Serializer):
    """Patient summary serializer handling both in-scope and BS-4 cross-branch views.

    LAB-49 Phase 5.2: the same per-role PII allowlist as the detail serializer,
    so listing patients cannot bypass the masking.
    """

    _PII_RESTRICTED_ROLES = frozenset({"technician", "pathologist"})

    id = serializers.UUIDField(read_only=True)
    mrn = serializers.CharField(read_only=True)
    name = serializers.CharField(read_only=True)
    sex = serializers.CharField(read_only=True)
    phone = serializers.SerializerMethodField()
    date_of_birth = serializers.SerializerMethodField()
    year_of_birth = serializers.SerializerMethodField()
    branch_id = serializers.UUIDField(read_only=True)
    branch_name = serializers.SerializerMethodField()
    referral_partner_id = serializers.SerializerMethodField()
    referral_partner_name = serializers.SerializerMethodField()
    last_visit = serializers.SerializerMethodField()
    created_at = serializers.SerializerMethodField()
    updated_at = serializers.SerializerMethodField()
    version = serializers.SerializerMethodField()
    is_cross_branch = serializers.SerializerMethodField()

    def get_branch_name(self, obj: Patient) -> str | None:
        """Registering branch name; hidden for BS-4 cross-branch projections."""
        if getattr(obj, "_is_cross_branch", False):
            return None
        branch = getattr(obj, "branch", None)
        return branch.name if branch is not None else None

    def get_referral_partner_id(self, obj: Patient) -> str | None:
        return str(obj.referral_partner_id) if obj.referral_partner_id else None

    def get_referral_partner_name(self, obj: Patient) -> str | None:
        partner = getattr(obj, "referral_partner", None)
        return partner.name if partner is not None else None

    def get_is_cross_branch(self, obj: Patient) -> bool:
        return getattr(obj, "_is_cross_branch", False)

    def get_phone(self, obj: Patient) -> str | None:
        if getattr(obj, "_is_cross_branch", False):
            return None
        return obj.phone

    def get_date_of_birth(self, obj: Patient) -> str | None:
        if getattr(obj, "_is_cross_branch", False):
            return None
        return obj.date_of_birth.isoformat() if obj.date_of_birth else None

    def get_year_of_birth(self, obj: Patient) -> int | None:
        return obj.date_of_birth.year if obj.date_of_birth else None

    def get_created_at(self, obj: Patient) -> str | None:
        if getattr(obj, "_is_cross_branch", False):
            return None
        return obj.created_at.isoformat() if obj.created_at else None

    def get_updated_at(self, obj: Patient) -> str | None:
        if getattr(obj, "_is_cross_branch", False):
            return None
        return obj.updated_at.isoformat() if obj.updated_at else None

    def get_version(self, obj: Patient) -> str | None:
        if getattr(obj, "_is_cross_branch", False):
            return None
        return obj.updated_at.isoformat() if obj.updated_at else None

    def get_last_visit(self, obj: Patient) -> str | None:
        if getattr(obj, "_is_cross_branch", False):
            return None
        if hasattr(obj, "last_visit_at"):
            val = getattr(obj, "last_visit_at", None)
            return val.isoformat() if val is not None else None
        from apps.billing.models import Invoice

        latest = (
            Invoice.objects.filter(patient=obj)
            .exclude(status__in=[Invoice.Status.CANCELLED, Invoice.Status.VOIDED])
            .order_by("-created_at")
            .values_list("created_at", flat=True)
            .first()
        )
        return latest.isoformat() if latest is not None else None

    def to_representation(self, instance: Patient) -> dict[str, Any]:
        data = super().to_representation(instance)
        request = self.context.get("request")
        role = getattr(getattr(request, "user", None), "role", None)
        if role in self._PII_RESTRICTED_ROLES:
            data["phone"] = None
            data["date_of_birth"] = None
            data["year_of_birth"] = None
        return data


class PatientDetailSerializer(serializers.ModelSerializer[Patient]):
    """Detailed patient representation including contacts and consents.

    LAB-49 Phase 5.2: per-role output allowlist. Technician and Pathologist
    keep the clinical identifiers they need but lose phone, DOB, contacts and
    consents. ``deleted_at`` is never exposed (A3-3).
    """

    _PII_RESTRICTED_ROLES = frozenset({"technician", "pathologist"})

    contacts = PatientContactSerializer(many=True, read_only=True)
    consents = PatientConsentSerializer(many=True, read_only=True)
    referral_partner_id = serializers.SerializerMethodField()
    referral_partner_name = serializers.SerializerMethodField()
    last_visit = serializers.SerializerMethodField()
    version = serializers.SerializerMethodField()
    invoices = serializers.SerializerMethodField()
    samples = serializers.SerializerMethodField()

    class Meta:
        model = Patient
        fields = [
            "id",
            "mrn",
            "name",
            "phone",
            "sex",
            "date_of_birth",
            "branch_id",
            "referral_partner_id",
            "referral_partner_name",
            "last_visit",
            "version",
            "created_at",
            "updated_at",
            "contacts",
            "consents",
            "invoices",
            "samples",
        ]

    def _caller_branch_scope(self) -> tuple[bool, set[uuid.UUID]]:
        from apps.accounts.models import StaffUser
        from apps.patients.services import PatientService

        request = self.context.get("request")
        user = getattr(request, "user", None)
        if not isinstance(user, StaffUser):
            return False, set()
        return PatientService.get_caller_branch_scope(user)

    def get_version(self, instance: Patient) -> str | None:
        return instance.updated_at.isoformat() if instance.updated_at else None

    def get_last_visit(self, instance: Patient) -> str | None:
        from apps.billing.models import Invoice

        is_tenant_wide, assigned_branches = self._caller_branch_scope()
        qs = Invoice.objects.filter(patient=instance).exclude(
            status__in=[Invoice.Status.CANCELLED, Invoice.Status.VOIDED]
        )
        if not is_tenant_wide:
            if not assigned_branches:
                return None
            qs = qs.filter(branch_id__in=assigned_branches)
        latest = qs.order_by("-created_at").values_list("created_at", flat=True).first()
        return latest.isoformat() if latest is not None else None

    def get_referral_partner_id(self, instance: Patient) -> str | None:
        return (
            str(instance.referral_partner_id) if instance.referral_partner_id else None
        )

    def get_referral_partner_name(self, instance: Patient) -> str | None:
        partner = getattr(instance, "referral_partner", None)
        return partner.name if partner is not None else None

    def to_representation(self, instance: Patient) -> dict[str, Any]:
        data = super().to_representation(instance)
        request = self.context.get("request")
        role = getattr(getattr(request, "user", None), "role", None)
        if role in self._PII_RESTRICTED_ROLES:
            data["phone"] = None
            data["date_of_birth"] = None
            data["contacts"] = []
            data["consents"] = []
        return data

    def get_invoices(self, obj: Patient) -> list[dict[str, Any]]:
        from apps.accounts.models import Role
        from apps.billing.models import Invoice

        is_tenant_wide, assigned_branches = self._caller_branch_scope()
        if not is_tenant_wide and not assigned_branches:
            return []
        qs = (
            Invoice.objects.filter(patient=obj)
            .select_related("branch")
            .order_by("-created_at")
        )
        if not is_tenant_wide:
            qs = qs.filter(branch_id__in=assigned_branches)
        request = self.context.get("request")
        user = getattr(request, "user", None)
        hide_prices = False
        if getattr(user, "role", None) == Role.TECHNICIAN:
            from apps.platform.settings_accessor import get_setting

            hide_prices = bool(get_setting("hide_prices_for_technicians"))
        return [
            {
                "id": str(inv.id),
                "invoice_number": f"INV-{str(inv.id)[:8].upper()}",
                "status": inv.status,
                "total": None if hide_prices else f"{inv.total:.2f}",
                "branch_id": str(inv.branch_id),
                "branch_name": inv.branch.name,
                "created_at": inv.created_at.isoformat(),
            }
            for inv in qs[:25]
        ]

    def get_samples(self, obj: Patient) -> list[dict[str, Any]]:
        from apps.samples.models import Sample

        is_tenant_wide, assigned_branches = self._caller_branch_scope()
        if not is_tenant_wide and not assigned_branches:
            return []
        qs = Sample.objects.filter(invoice__patient=obj).order_by("-created_at")
        if not is_tenant_wide:
            qs = qs.filter(branch_id__in=assigned_branches)
        # Summary of recent samples via invoice relationship (Doc 02 §5.5)
        samples = qs[:10]
        return [
            {
                "id": str(s.id),
                "accession_id": s.accession_id,
                "status": s.status,
                "created_at": s.created_at.isoformat(),
            }
            for s in samples
        ]
