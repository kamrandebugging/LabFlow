"""DRF serializers for the referral-partner registry (Doc 05 §5.1–§5.4,
KAN-164 / LAB-39).

Strict input: unknown fields are rejected. Money/percent values are
Decimal strings (Doc 02 §12 — money is never float).
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any

from django.core.validators import EmailValidator
from rest_framework import serializers
from rest_framework.exceptions import ErrorDetail


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


class PercentField(serializers.Field):
    """Revenue-share percent: Decimal string, max 2 decimals, 0–100."""

    def to_internal_value(self, data: Any) -> Decimal:
        if not isinstance(data, str):
            raise serializers.ValidationError(
                "percent_must_be_string",
                code="percent_must_be_string",
            )
        trimmed = data.strip()
        try:
            val = Decimal(trimmed)
        except InvalidOperation as exc:
            raise serializers.ValidationError(
                "validation_error", code="validation_error"
            ) from exc
        exponent = val.as_tuple().exponent
        if isinstance(exponent, int) and exponent < -2:
            raise serializers.ValidationError(
                "validation_error", code="validation_error"
            )
        if val < Decimal("0") or val > Decimal("100"):
            raise serializers.ValidationError(
                "validation_error", code="validation_error"
            )
        return val

    def to_representation(self, value: Any) -> str:
        if isinstance(value, Decimal):
            return f"{value:.2f}"
        return str(value)


class PartnerCreateSerializer(serializers.Serializer):
    name = serializers.CharField(required=True, allow_blank=False, max_length=500)
    organisation = serializers.CharField(
        required=False, allow_blank=True, allow_null=True, max_length=500
    )
    phone = serializers.CharField(
        required=False, allow_blank=True, allow_null=True, max_length=50
    )
    email = serializers.CharField(
        required=False, allow_blank=True, allow_null=True, max_length=255
    )
    is_active = serializers.BooleanField(required=False, default=True)

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        attrs = _reject_unknown_fields(self, attrs)
        email = attrs.get("email")
        if email:
            try:
                EmailValidator()(email)
            except Exception as exc:
                raise serializers.ValidationError(
                    {"email": ErrorDetail("validation_error", code="validation_error")}
                ) from exc
        return attrs


class PartnerUpdateSerializer(serializers.Serializer):
    name = serializers.CharField(required=False, allow_blank=False, max_length=500)
    organisation = serializers.CharField(
        required=False, allow_blank=True, allow_null=True, max_length=500
    )
    phone = serializers.CharField(
        required=False, allow_blank=True, allow_null=True, max_length=50
    )
    email = serializers.CharField(
        required=False, allow_blank=True, allow_null=True, max_length=255
    )
    is_active = serializers.BooleanField(required=False)

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        attrs = _reject_unknown_fields(self, attrs)
        if "email" in attrs and attrs["email"]:
            try:
                EmailValidator()(attrs["email"])
            except Exception as exc:
                raise serializers.ValidationError(
                    {"email": ErrorDetail("validation_error", code="validation_error")}
                ) from exc
        return attrs


class RuleCreateSerializer(serializers.Serializer):
    branch_id = serializers.UUIDField(required=False, allow_null=True, default=None)
    test_category = serializers.CharField(
        required=False,
        allow_blank=False,
        allow_null=True,
        default=None,
        max_length=200,
    )
    percent = PercentField(required=True)
    effective_from = serializers.DateField(required=True)

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        return _reject_unknown_fields(self, attrs)


class RuleUpdateSerializer(serializers.Serializer):
    """PATCH /revenue-share-rules/{id}: close-old + insert-new (RR-3).

    Accepts a new percent and/or a new effective_from. The old row is
    closed (effective_to = new effective_from - 1 day) and a new row is
    inserted; the old row's percent and effective_from are never mutated.
    """

    percent = PercentField(required=False)
    effective_from = serializers.DateField(required=False)

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        return _reject_unknown_fields(self, attrs)


def format_rule(rule: Any) -> dict[str, Any]:
    return {
        "id": str(rule.id),
        "referral_partner_id": str(rule.referral_partner_id),
        "branch_id": str(rule.branch_id) if rule.branch_id else None,
        "test_category": rule.test_category,
        "percent": f"{rule.percent:.2f}",
        "effective_from": rule.effective_from.isoformat(),
        "effective_to": rule.effective_to.isoformat() if rule.effective_to else None,
        "created_at": rule.created_at.isoformat(),
    }


def format_partner(partner: Any) -> dict[str, Any]:
    return {
        "id": str(partner.id),
        "name": partner.name,
        "organisation": partner.organisation,
        "phone": partner.phone,
        "email": partner.email,
        "is_active": partner.is_active,
        "created_at": partner.created_at.isoformat(),
        "updated_at": partner.updated_at.isoformat(),
    }
