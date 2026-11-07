from decimal import Decimal
from typing import Any

from rest_framework import serializers


class TenantProvisionRequestSerializer(serializers.Serializer[dict[str, Any]]):
    name = serializers.CharField(
        required=True,
        allow_blank=True,
        trim_whitespace=False,
    )
    slug = serializers.CharField(
        required=True,
        allow_blank=True,
        trim_whitespace=False,
    )
    plan_id = serializers.UUIDField(required=True)
    owner_email = serializers.CharField(
        required=False,
        allow_blank=True,
        trim_whitespace=False,
    )
    owner_name = serializers.CharField(
        required=False,
        allow_blank=True,
        trim_whitespace=False,
    )
    owner = serializers.DictField(
        child=serializers.CharField(allow_blank=True, trim_whitespace=False),
        required=False,
    )
    city = serializers.CharField(
        required=False,
        allow_blank=True,
        default="",
    )
    province = serializers.CharField(
        required=False,
        allow_blank=True,
        default="",
    )
    phone = serializers.CharField(
        required=False,
        allow_blank=True,
        default="",
    )
    whatsapp = serializers.CharField(
        required=False,
        allow_blank=True,
        default="",
    )
    staff_seats = serializers.IntegerField(
        required=False,
        allow_null=True,
        default=None,
    )
    branch_count = serializers.IntegerField(
        required=False,
        default=1,
    )
    enabled_roles = serializers.ListField(
        child=serializers.CharField(),
        required=False,
        default=list,
    )

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        owner_dict = attrs.get("owner") or {}
        email = attrs.get("owner_email")
        if not email and isinstance(owner_dict, dict):
            email = owner_dict.get("email", "")
        owner_name = attrs.get("owner_name")
        if not owner_name and isinstance(owner_dict, dict):
            owner_name = owner_dict.get("name", "")

        phone = attrs.get("phone") or attrs.get("whatsapp")
        if not phone and isinstance(owner_dict, dict):
            phone = owner_dict.get("phone", "")

        attrs["resolved_owner_email"] = email if isinstance(email, str) else ""
        attrs["resolved_owner_name"] = owner_name if isinstance(owner_name, str) else ""
        attrs["resolved_owner_phone"] = phone if isinstance(phone, str) else ""
        return attrs


class PlanCreateSerializer(serializers.Serializer[dict[str, Any]]):
    """POST /platform/plans body (Doc 04 §15.1). Price is a Decimal string."""

    name = serializers.CharField(required=True, max_length=100)
    price = serializers.CharField(required=True)
    max_branches = serializers.IntegerField(required=False, allow_null=True)

    def validate_price(self, value: str) -> Decimal:
        if not isinstance(value, str):
            raise serializers.ValidationError("money_must_be_string")
        try:
            amount = Decimal(value)
        except Exception as err:
            raise serializers.ValidationError("invalid_money_format") from err
        if amount < Decimal("0.00"):
            raise serializers.ValidationError("price_must_be_non_negative")
        return amount

    def validate_name(self, value: str) -> str:
        if not value or not value.strip():
            raise serializers.ValidationError("name_required")
        return value.strip()


class SubscriptionChangeSerializer(serializers.Serializer[dict[str, Any]]):
    """POST /platform/tenants/{id}/subscription body (Doc 04 §15.1)."""

    plan_id = serializers.UUIDField(required=True)
    status = serializers.ChoiceField(
        required=True,
        choices=["active", "past_due", "cancelled", "expired"],
    )
    ends_at = serializers.DateTimeField(required=False, allow_null=True)


class TenantSuspendSerializer(serializers.Serializer[dict[str, Any]]):
    """POST /platform/tenants/{id}/suspend — reason required (Doc 04 §15.1)."""

    reason = serializers.CharField(
        required=True,
        allow_blank=False,
        trim_whitespace=True,
        max_length=500,
    )


class TenantOffboardCompleteSerializer(serializers.Serializer[dict[str, Any]]):
    """POST /platform/tenants/{id}/complete-offboarding.

    confirm_schema_drop must be explicitly true (Doc 04 §15.1) — this
    cannot fire from a generic form post.
    """

    confirm_schema_drop = serializers.BooleanField(required=True)
    waive_grace = serializers.BooleanField(required=False, default=False)
    waive_reason = serializers.CharField(
        required=False,
        allow_blank=True,
        trim_whitespace=True,
        max_length=500,
    )

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        if attrs.get("confirm_schema_drop") is not True:
            raise serializers.ValidationError(
                {"confirm_schema_drop": ["Must be true to drop the tenant schema."]}
            )
        return attrs


class PlatformAuditFilterSerializer(serializers.Serializer[dict[str, Any]]):
    """GET /platform/audit — filter params (Doc 04 §15.1)."""

    action = serializers.CharField(required=False, allow_blank=True)
    entity_type = serializers.CharField(required=False, allow_blank=True)
    tenant_id = serializers.UUIDField(required=False)
    date_from = serializers.DateTimeField(required=False)
    date_to = serializers.DateTimeField(required=False)
    start_date = serializers.DateTimeField(required=False)
    end_date = serializers.DateTimeField(required=False)
