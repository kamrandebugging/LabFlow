"""Strict serializers for the Results module (Doc 03 §5.5, KAN-150 / LAB-25).

- Unknown fields rejected (same pattern as billing/samples).
- result.value is accepted as free text and stored verbatim (RS-2).
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


class ResultRowSerializer(serializers.Serializer):
    """One row of POST /api/v1/samples/{id}/results."""

    test_id = serializers.UUIDField()
    value = serializers.CharField(min_length=1)
    unit = serializers.CharField(
        required=False, allow_null=True, allow_blank=True, max_length=64
    )

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        return _reject_unknown_fields(self, attrs)


class ResultEntrySerializer(serializers.Serializer):
    """POST /api/v1/samples/{id}/results — batch of result rows."""

    results = serializers.ListField(
        child=ResultRowSerializer(), min_length=1, max_length=500
    )

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        return _reject_unknown_fields(self, attrs)


class ResultApproveSerializer(serializers.Serializer):
    """POST /api/v1/results/{id}/approve — clinical verification (RS-5/RS-6/RS-7)."""

    decision = serializers.ChoiceField(choices=["approved", "rejected"])
    note = serializers.CharField(
        required=False, allow_null=True, allow_blank=True, max_length=2000
    )
    range_override = serializers.BooleanField(required=False, default=False)
    # D8: explicit reviewer attestation recorded on approval.
    attestation = serializers.BooleanField(required=False, default=False)

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        return _reject_unknown_fields(self, attrs)


class ResultAmendSerializer(serializers.Serializer):
    """POST /api/v1/results/{id}/amend — amendment of an approved result (RS-9).

    value: RS-V1 (required, max 500; non-empty-after-trim enforced in the
    service). reason: required non-empty (service trims and enforces).
    """

    value = serializers.CharField(max_length=500)
    unit = serializers.CharField(
        required=False, allow_null=True, allow_blank=True, max_length=64
    )
    reason = serializers.CharField(required=False, allow_blank=True, max_length=2000)

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        return _reject_unknown_fields(self, attrs)


class CriticalNotificationSerializer(serializers.Serializer):
    """POST /api/v1/results/{id}/critical-notifications (§8.5, §6.6).

    notified_name: required, non-empty after trim (service enforces),
    max 200. notified_at: required ISO 8601 datetime (future rejected in
    the service). read_back: required boolean.
    """

    notified_name = serializers.CharField(max_length=200)
    notified_at = serializers.DateTimeField()
    read_back = serializers.BooleanField()

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        return _reject_unknown_fields(self, attrs)
