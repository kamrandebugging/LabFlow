"""Strict serializers for the Billing module (Doc 03 §5.3, §6.4, KAN-124 / LAB-18).

- MoneyField: Decimal strings only, max 2 decimals (BL-V1, money_must_be_string).
- Unknown fields rejected (KAN-119 strict pattern).
- Client-sent totals (total/subtotal) are accepted but IGNORED (BL-2).
"""

import re
from decimal import Decimal, InvalidOperation
from typing import Any

from rest_framework import serializers


class MoneyField(serializers.Field):
    """Monetary amount: Decimal string, max 2 decimals, >= 0 (BL-V1)."""

    default_error_messages = {
        "invalid": "Amount must be a valid decimal string.",
        "not_a_string": "Amount must be a string.",
        "max_two_decimals": "Amount must have at most 2 decimal places.",
        "negative": "Amount cannot be negative.",
    }

    def to_internal_value(self, data: Any) -> Decimal:
        if not isinstance(data, str):
            self.fail("not_a_string")
        trimmed = data.strip()
        if not re.match(r"^\d+(\.\d{1,2})?$", trimmed):
            if re.match(r"^\d+\.\d{3,}$", trimmed):
                self.fail("max_two_decimals")
            if trimmed.startswith("-"):
                self.fail("negative")
            self.fail("invalid")
        try:
            val = Decimal(trimmed)
        except InvalidOperation:
            self.fail("invalid")
        if val < Decimal("0.00"):
            self.fail("negative")
        return val

    def to_representation(self, value: Any) -> str:
        if isinstance(value, Decimal):
            return f"{value:.2f}"
        return str(value)


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


class InvoiceItemInputSerializer(serializers.Serializer):
    """One billed line: test_id XOR panel_id, qty >= 1 (BL-1, BL-V2)."""

    test_id = serializers.UUIDField(required=False, allow_null=True, default=None)
    panel_id = serializers.UUIDField(required=False, allow_null=True, default=None)
    qty = serializers.IntegerField(min_value=1)

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        attrs = _reject_unknown_fields(self, attrs)
        has_test = attrs.get("test_id") is not None
        has_panel = attrs.get("panel_id") is not None
        if has_test == has_panel:
            raise serializers.ValidationError(
                "Exactly one of test_id or panel_id is required."
            )
        return attrs


class InvoiceCreateSerializer(serializers.Serializer):
    """POST /api/v1/invoices body (BL-1..BL-4, BL-V1..BL-V3)."""

    patient_id = serializers.UUIDField()
    branch_id = serializers.UUIDField()
    referral_partner_id = serializers.UUIDField(
        required=False, allow_null=True, default=None
    )
    items = serializers.ListField(
        child=InvoiceItemInputSerializer(), min_length=1, allow_empty=False
    )
    discount_amount = MoneyField(required=False, default=Decimal("0.00"))
    discount_reason = serializers.CharField(
        required=False, allow_null=True, allow_blank=True, default=None
    )
    # BL-2: client-sent totals are accepted but IGNORED — server computes.
    total = serializers.CharField(required=False, write_only=True)
    subtotal = serializers.CharField(required=False, write_only=True)

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        return _reject_unknown_fields(self, attrs)


class InvoiceItemSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    test_id = serializers.UUIDField(allow_null=True)
    panel_id = serializers.UUIDField(allow_null=True)
    description = serializers.CharField()
    unit_price = MoneyField()
    quantity = serializers.IntegerField()
    line_total = MoneyField()


class InvoiceSerializer(serializers.Serializer):
    """Response shape for a created / replayed invoice."""

    id = serializers.UUIDField()
    patient_id = serializers.UUIDField()
    branch_id = serializers.UUIDField()
    referral_partner_id = serializers.UUIDField(allow_null=True)
    status = serializers.CharField()
    subtotal = MoneyField()
    discount_amount = MoneyField()
    discount_reason = serializers.CharField(allow_null=True)
    total = MoneyField()
    items = InvoiceItemSerializer(many=True)


class PositiveMoneyField(MoneyField):
    """MoneyField variant requiring >= 0.01 (BL-V1 for payments/refunds)."""

    default_error_messages = {
        **MoneyField.default_error_messages,
        "too_small": "Amount must be at least 0.01.",
    }

    def to_internal_value(self, data: Any) -> Decimal:
        val = super().to_internal_value(data)
        if val < Decimal("0.01"):
            self.fail("too_small")
        return val


class PaymentCreateSerializer(serializers.Serializer):
    """POST /api/v1/invoices/{id}/payments body (BL-5, BL-7, BL-10, BL-V1)."""

    kind = serializers.ChoiceField(choices=["payment", "refund"])
    method = serializers.ChoiceField(
        choices=["cash", "card", "bank_transfer", "easypaisa", "jazzcash", "other"]
    )
    amount = PositiveMoneyField()
    reference = serializers.CharField(
        required=False, allow_null=True, allow_blank=True, default=None
    )

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        return _reject_unknown_fields(self, attrs)


class PaymentSerializer(serializers.Serializer):
    """Response shape for a recorded / replayed payment."""

    id = serializers.UUIDField()
    invoice_id = serializers.UUIDField()
    kind = serializers.CharField()
    method = serializers.CharField()
    amount = MoneyField()
    reference = serializers.CharField(allow_null=True)
    received_by = serializers.SerializerMethodField()
    created_at = serializers.DateTimeField()

    def get_received_by(self, obj: Any) -> str | None:
        """Operator display name; the raw staff UUID is unreadable in the UI."""
        staff = getattr(obj, "received_by", None)
        if staff is None:
            return None
        return getattr(staff, "name", None) or getattr(staff, "email", None)


class InvoiceCancelSerializer(serializers.Serializer):
    """Body for POST /invoices/{id}/cancel — reason required (BL-8)."""

    reason = serializers.CharField(
        required=True, allow_blank=False, trim_whitespace=True
    )

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        return _reject_unknown_fields(self, attrs)


class InvoiceSummarySerializer(serializers.Serializer):
    """List row for GET /invoices (cursor page)."""

    id = serializers.UUIDField()
    patient_id = serializers.UUIDField()
    branch_id = serializers.UUIDField()
    status = serializers.CharField()
    subtotal = MoneyField()
    discount_amount = MoneyField()
    total = MoneyField()
    created_at = serializers.DateTimeField()


class InvoiceDetailSerializer(serializers.Serializer):
    """Detail for GET /invoices/{id} — items + payments + net_paid."""

    id = serializers.UUIDField()
    invoice_number = serializers.CharField()
    patient_id = serializers.UUIDField()
    patient_name = serializers.CharField()
    patient_mrn = serializers.CharField()
    patient_sex = serializers.CharField(allow_null=True)
    patient_age = serializers.CharField(allow_null=True)
    patient_phone = serializers.CharField(allow_null=True)
    branch_id = serializers.UUIDField()
    branch_name = serializers.CharField()
    referral_partner_id = serializers.UUIDField(allow_null=True)
    status = serializers.CharField()
    subtotal = MoneyField()
    discount_amount = MoneyField()
    discount_reason = serializers.CharField(allow_null=True)
    total = MoneyField()
    items = InvoiceItemSerializer(many=True)
    payments = PaymentSerializer(many=True)
    net_paid = MoneyField()
    created_at = serializers.DateTimeField()
