"""Strict serializers for the Samples module (Doc 03 §5.4, KAN-137 / LAB-21).

- Unknown fields rejected (same pattern as billing).
- accession_id is never accepted from the client (SM-1: server-minted).
"""

from typing import Any

from rest_framework import serializers


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


class SampleLabelSerializer(serializers.Serializer):
    """GET /api/v1/samples/{id}/label — stored-data payload (SM-4)."""

    accession_id = serializers.CharField()
    patient_name = serializers.CharField()
    mrn = serializers.CharField()
    date_of_birth = serializers.CharField(allow_null=True)
    collected_at = serializers.CharField()
    collected_by = serializers.EmailField(allow_null=True)
    barcode = serializers.DictField()
