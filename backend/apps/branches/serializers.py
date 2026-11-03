"""Strict serializers for the Branches module (Doc 04 §8.2, §8.3, KAN-158 / LAB-33).

- Unknown fields rejected (same pattern as samples/billing).
- Branch code format is validated in the service so the machine-stable
  error code is invalid_branch_code (Doc 03 §6.1), not a generic
  validation_error.
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


class BranchSerializer(serializers.Serializer):
    """Branch read shape (Doc 04 §15 table)."""

    id = serializers.UUIDField()
    code = serializers.CharField()
    name = serializers.CharField()
    address = serializers.CharField(allow_null=True)
    phone = serializers.CharField(allow_null=True)
    is_collection_centre = serializers.BooleanField()
    result_entry_enabled = serializers.BooleanField()
    deleted_at = serializers.DateTimeField(allow_null=True)


class BranchCreateSerializer(serializers.Serializer):
    """POST /api/v1/branches — Doc 04 §15 body."""

    # allow_blank + trim_whitespace=False: every malformed code reaches the
    # service so the machine code is always invalid_branch_code (§8.2).
    code = serializers.CharField(allow_blank=True, trim_whitespace=False)
    name = serializers.CharField()
    address = serializers.CharField(required=False, allow_null=True, default=None)
    phone = serializers.CharField(required=False, allow_null=True, default=None)
    is_collection_centre = serializers.BooleanField(required=False, default=False)

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        return _reject_unknown_fields(self, attrs)


class BranchUpdateSerializer(serializers.Serializer):
    """PATCH /api/v1/branches/{id} — Doc 04 §15 body + code (§8.2 rule).

    code is accepted by the serializer but gated in the service:
    422 branch_code_immutable once referenced, allowed (validated) while
    unreferenced (TN-18).
    """

    name = serializers.CharField(required=False)
    address = serializers.CharField(required=False, allow_null=True)
    phone = serializers.CharField(required=False, allow_null=True)
    is_collection_centre = serializers.BooleanField(required=False)
    code = serializers.CharField(
        required=False, allow_blank=True, trim_whitespace=False
    )

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        return _reject_unknown_fields(self, attrs)
