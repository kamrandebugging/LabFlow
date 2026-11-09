"""Strict serializers for the Samples module (Doc 03 §5.4, KAN-137 / LAB-21,
KAN-138 / LAB-22).

- Unknown fields rejected (same pattern as billing).
- accession_id is never accepted from the client (SM-1: server-minted).
"""

from typing import Any

from django.utils import timezone
from rest_framework import serializers

from apps.samples.models import Sample, SampleTest


def _reject_unknown_fields(
    serializer: serializers.Serializer, attrs: dict[str, Any]
) -> dict[str, Any]:
    """Strict request serialization: unknown parameters are rejected."""
    initial = getattr(serializer, "initial_data", None)
    if not isinstance(initial, dict):
        return attrs
    known = set(serializer.fields)
    unknown = set(initial.keys()) - known
    if unknown:
        raise serializers.ValidationError(
            f"Unknown fields: {', '.join(sorted(str(u) for u in unknown))}."
        )
    return attrs


class SampleCreateSerializer(serializers.Serializer):
    """POST /api/v1/samples — invoice_id required, optional item subset."""

    invoice_id = serializers.UUIDField()
    invoice_item_ids = serializers.ListField(
        child=serializers.UUIDField(), required=False, allow_empty=True
    )

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        return _reject_unknown_fields(self, attrs)


class SampleSerializer(serializers.Serializer):
    """Sample summary for the 201 response."""

    id = serializers.UUIDField()
    accession_id = serializers.CharField()
    invoice_id = serializers.UUIDField(source="invoice.id")
    branch_id = serializers.UUIDField(source="branch.id")
    status = serializers.CharField()
    collected_at = serializers.DateTimeField()
    collected_by = serializers.EmailField(
        source="collected_by.email", allow_null=True, default=None
    )


class SampleListSerializer(serializers.Serializer):
    """List serializer for GET /api/v1/samples satisfying SampleSummary."""

    id = serializers.UUIDField(read_only=True)
    accession_id = serializers.CharField(read_only=True)
    invoice_id = serializers.UUIDField(source="invoice.id", read_only=True)
    patient_id = serializers.UUIDField(source="invoice.patient.id", read_only=True)
    patient_name = serializers.CharField(source="invoice.patient.name", read_only=True)
    patient_mrn = serializers.CharField(source="invoice.patient.mrn", read_only=True)
    patient_sex = serializers.CharField(
        source="invoice.patient.sex", allow_null=True, required=False, read_only=True
    )
    patient_age_years = serializers.SerializerMethodField()
    branch_id = serializers.UUIDField(source="branch.id", read_only=True)
    branch_name = serializers.CharField(source="branch.name", read_only=True)
    status = serializers.CharField(read_only=True)
    tests = serializers.SerializerMethodField()
    collected_at = serializers.DateTimeField(read_only=True)
    age_display = serializers.SerializerMethodField()
    rejection_reason_code = serializers.CharField(
        allow_null=True, required=False, read_only=True
    )
    rejection_note = serializers.CharField(
        allow_null=True, required=False, read_only=True
    )

    def get_patient_age_years(self, obj: Sample) -> int | None:
        patient = getattr(getattr(obj, "invoice", None), "patient", None)
        if not patient or not patient.date_of_birth:
            return None
        today = timezone.localdate()
        dob = patient.date_of_birth
        return today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))

    def get_age_display(self, obj: Sample) -> str | None:
        patient = getattr(getattr(obj, "invoice", None), "patient", None)
        if not patient or not patient.date_of_birth:
            return None
        collected_on = (
            timezone.localtime(obj.collected_at).date()
            if obj.collected_at
            else timezone.localdate()
        )
        days = (collected_on - patient.date_of_birth).days
        if days < 0:
            return None
        if days < 30:
            return f"{days}d"
        months = days // 30
        if months < 24:
            return f"{months}m"
        return f"{months // 12}y"

    def get_tests(self, obj: Sample) -> list[str]:
        return [
            st.test.name
            for st in obj.sample_tests.all()  # type: ignore[attr-defined]
            if getattr(st, "test", None) and getattr(st.test, "name", None)
        ]


class SampleTestItemSerializer(serializers.ModelSerializer[SampleTest]):
    test_id = serializers.UUIDField(source="test.id")
    test_name = serializers.CharField(source="test.name")
    test_code = serializers.CharField(source="test.code")
    invoice_item_id = serializers.UUIDField(source="invoice_item.id")
    category = serializers.CharField(source="test.category", allow_null=True)
    unit = serializers.SerializerMethodField()
    reference_range = serializers.SerializerMethodField()
    panel_codes = serializers.SerializerMethodField()

    class Meta:
        model = SampleTest
        fields = [
            "id",
            "test_id",
            "test_name",
            "test_code",
            "invoice_item_id",
            "category",
            "unit",
            "reference_range",
            "panel_codes",
        ]

    def _resolve_range(self, obj: SampleTest) -> Any:
        from apps.catalog.services import CatalogService

        sample = obj.sample
        patient = sample.invoice.patient
        dob = patient.date_of_birth
        age_days = (
            (sample.collected_at.date() - dob).days if dob is not None else None
        )
        return CatalogService.resolve_reference_range(
            test_id=obj.test_id,
            patient_sex=patient.sex,
            patient_age_days=age_days,
            collection_date=sample.collected_at,
        )

    def get_unit(self, obj: SampleTest) -> str | None:
        resolved = self._resolve_range(obj)
        return resolved.unit if resolved is not None else obj.test.unit

    def get_reference_range(self, obj: SampleTest) -> dict[str, Any] | None:
        resolved = self._resolve_range(obj)
        if resolved is None:
            return None
        return {
            "low": str(resolved.low) if resolved.low is not None else None,
            "high": str(resolved.high) if resolved.high is not None else None,
            "unit": resolved.unit,
            "critical_low": (
                str(resolved.critical_low)
                if resolved.critical_low is not None
                else None
            ),
            "critical_high": (
                str(resolved.critical_high)
                if resolved.critical_high is not None
                else None
            ),
        }

    def get_panel_codes(self, obj: SampleTest) -> list[str]:
        from apps.catalog.models import Panel

        return sorted(
            Panel.objects.filter(panel_tests__test_id=obj.test_id).values_list(
                "code", flat=True
            )
        )


class SampleDetailSerializer(SampleListSerializer):
    patient_dob = serializers.DateField(
        source="invoice.patient.date_of_birth", allow_null=True, required=False
    )
    collected_by = serializers.CharField(
        source="collected_by.email", allow_null=True, required=False
    )
    sample_tests = SampleTestItemSerializer(many=True, read_only=True)


class SampleLabelSerializer(serializers.Serializer):
    """GET /api/v1/samples/{id}/label — stored-data payload (SM-4)."""

    accession_id = serializers.CharField()
    patient_name = serializers.CharField()
    mrn = serializers.CharField()
    date_of_birth = serializers.CharField(allow_null=True)
    collected_at = serializers.CharField()
    collected_by = serializers.EmailField(allow_null=True)
    branch_name = serializers.CharField()
    tests = serializers.ListField(child=serializers.CharField())
    barcode = serializers.DictField()


class SampleRejectSerializer(serializers.Serializer):
    """POST /api/v1/samples/{id}/reject — SM-8 reason code + note (KAN-138).

    Unknown reason codes -> 422 via the view's validation handler. The
    `other`-requires-note rule lives in the service (422
    reject_note_required).
    """

    reason_code = serializers.ChoiceField(choices=Sample.RejectionReasonCode.choices)
    note = serializers.CharField(required=False, allow_blank=True, default="")

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        return _reject_unknown_fields(self, attrs)


class SampleCancelSerializer(serializers.Serializer):
    """POST /api/v1/samples/{id}/cancel — SM-11 (KAN-138).

    reason is optional at the serializer level so an empty/missing reason
    surfaces as the domain-coded 422 cancel_reason_required from the
    service instead of a generic validation error.
    """

    reason = serializers.CharField(required=False, allow_blank=True, default="")

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        return _reject_unknown_fields(self, attrs)


class TransferCreateSerializer(serializers.Serializer):
    """POST /api/v1/samples/{id}/transfer — SM-7 (KAN-143).

    to_branch_id is required; unknown fields rejected. Destination
    eligibility (open processing branch) is enforced in the service
    (422 branch_cannot_receive).
    """

    to_branch_id = serializers.UUIDField()

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        return _reject_unknown_fields(self, attrs)


class TransferMarkLostSerializer(serializers.Serializer):
    """POST /api/v1/transfers/{id}/mark-lost (KAN-143).

    note is optional at the serializer level so a missing/blank note
    surfaces as the domain-coded 422 mark_lost_note_required from the
    service instead of a generic validation error.
    """

    note = serializers.CharField(required=False, allow_blank=True, default="")

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        return _reject_unknown_fields(self, attrs)


class BranchRefSerializer(serializers.Serializer):
    """Branch reference for transfer responses."""

    id = serializers.UUIDField()
    code = serializers.CharField()
    name = serializers.CharField()


class TransferSerializer(serializers.Serializer):
    """SampleTransfer summary for transfer responses (KAN-143)."""

    id = serializers.UUIDField()
    sample_id = serializers.UUIDField(source="sample.id")
    accession_id = serializers.CharField(source="sample.accession_id")
    from_branch = BranchRefSerializer()
    to_branch = BranchRefSerializer()
    status = serializers.CharField()
    dispatched_at = serializers.DateTimeField(allow_null=True)
    received_at = serializers.DateTimeField(allow_null=True)
    transferred_by = serializers.EmailField(
        source="transferred_by.email", allow_null=True, default=None
    )
    received_by = serializers.EmailField(
        source="received_by.email", allow_null=True, default=None
    )
