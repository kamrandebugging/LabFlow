"""Shared strict serializers (LAB-49 Phase 5.1, API3 A3-1).

DRF silently drops unknown fields. That is a mass-assignment regression waiting
to happen the day a serializer is used as a write DTO. These bases reject any
key that is not an explicit field with a 422 ``ValidationError``.

Existing per-app ``_reject_unknown_fields`` helpers stay valid; new code should
inherit from these bases.
"""

from __future__ import annotations

from typing import Any

from rest_framework import serializers


def reject_unknown_fields(
    serializer: serializers.Serializer, attrs: dict[str, Any]
) -> dict[str, Any]:
    """Raise when ``initial_data`` carries keys the serializer does not declare."""
    initial = getattr(serializer, "initial_data", None)
    if not isinstance(initial, dict):
        return attrs
    unknown = set(initial.keys()) - set(serializer.fields)
    if unknown:
        raise serializers.ValidationError(
            f"Unknown fields: {', '.join(sorted(str(u) for u in unknown))}."
        )
    return attrs


class StrictFieldsMixin:
    """Mixin that rejects unknown input fields in ``validate``."""

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        attrs = super().validate(attrs)  # type: ignore[misc]
        return reject_unknown_fields(self, attrs)  # type: ignore[arg-type]


class StrictSerializer(StrictFieldsMixin, serializers.Serializer):
    """Explicit-field serializer that rejects unknown input."""


class StrictModelSerializer(StrictFieldsMixin, serializers.ModelSerializer):
    """Explicit-field model serializer that rejects unknown input."""
