"""Strict serializers for the Reports public portal (KAN-156 / LAB-31).

Unknown fields rejected (same pattern as samples/billing).
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


class TokenRevokeSerializer(serializers.Serializer):
    """POST /api/v1/reports/{id}/revoke-token — §6.7.

    Exactly one of: token_id (UUID) or all=true. Anything else -> 422 via
    the view's validation handler.
    """

    token_id = serializers.UUIDField(required=False, allow_null=True, default=None)
    all = serializers.BooleanField(required=False, default=False)

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        attrs = _reject_unknown_fields(self, attrs)
        token_id = attrs.get("token_id")
        revoke_all = attrs.get("all", False)
        if (token_id is None) == (not revoke_all):
            # both empty or both set
            raise serializers.ValidationError(
                "Provide exactly one of 'token_id' or 'all': true."
            )
        return attrs
