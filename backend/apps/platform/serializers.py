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

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        owner_dict = attrs.get("owner") or {}
        email = attrs.get("owner_email")
        if not email and isinstance(owner_dict, dict):
            email = owner_dict.get("email", "")
        owner_name = attrs.get("owner_name")
        if not owner_name and isinstance(owner_dict, dict):
            owner_name = owner_dict.get("name", "")

        attrs["resolved_owner_email"] = email if isinstance(email, str) else ""
        attrs["resolved_owner_name"] = owner_name if isinstance(owner_name, str) else ""
        return attrs
