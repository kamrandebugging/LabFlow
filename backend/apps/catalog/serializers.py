"""Serializers for Diagnostic Catalog (Doc 03 §5.2, §6.3, KAN-118).

Enforces:
- CT-V1 & T-12: Money values must be decimal strings with at most 2 decimal places.
- CT-V3: Panels cannot be empty or contain inactive tests.
"""

import re
import uuid
from decimal import Decimal, InvalidOperation
from typing import Any, cast

from rest_framework import serializers

from apps.branches.models import Branch
from apps.catalog.models import Panel, Test, TestPrice


class MoneyField(serializers.Field):
    """Field for monetary amounts enforcing CT-V1 and T-12.

    Rejects non-string representations and values with > 2 decimal places.
    """

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
        # Verify decimal format: digits, optional decimal point and 1-2 digits
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


class TestSerializer(serializers.ModelSerializer[Test]):
    class Meta:
        model = Test
        fields = [
            "id",
            "code",
            "name",
            "category",
            "unit",
            "is_active",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]


class TestCreateSerializer(serializers.Serializer):
    code = serializers.CharField(max_length=64, required=True)
    name = serializers.CharField(max_length=255, required=True)
    category = serializers.CharField(
        max_length=128, required=False, allow_null=True, allow_blank=True
    )
    unit = serializers.CharField(
        max_length=64, required=False, allow_null=True, allow_blank=True
    )
    is_active = serializers.BooleanField(required=False, default=True)

    def validate_code(self, value: str) -> str:
        code = value.strip().upper()
        if not code:
            raise serializers.ValidationError("Code cannot be empty.")
        if Test.objects.filter(code=code).exists():
            raise serializers.ValidationError(
                f"Test with code '{code}' already exists."
            )
        return code

    def validate_name(self, value: str) -> str:
        name = value.strip()
        if not name:
            raise serializers.ValidationError("Name cannot be empty.")
        return name


class TestUpdateSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=255, required=False)
    category = serializers.CharField(
        max_length=128, required=False, allow_null=True, allow_blank=True
    )
    unit = serializers.CharField(
        max_length=64, required=False, allow_null=True, allow_blank=True
    )
    is_active = serializers.BooleanField(required=False)

    def validate_name(self, value: str) -> str:
        name = value.strip()
        if not name:
            raise serializers.ValidationError("Name cannot be empty.")
        return name


class PanelTestComponentSerializer(serializers.ModelSerializer[Test]):
    class Meta:
        model = Test
        fields = ["id", "code", "name", "category", "unit", "is_active"]


class PanelSerializer(serializers.ModelSerializer[Panel]):
    test_ids = serializers.SerializerMethodField()
    tests = serializers.SerializerMethodField()

    class Meta:
        model = Panel
        fields = [
            "id",
            "code",
            "name",
            "is_active",
            "test_ids",
            "tests",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]

    def get_test_ids(self, obj: Panel) -> list[str]:
        return [str(pt.test_id) for pt in obj.panel_tests.all()]

    def get_tests(self, obj: Panel) -> list[dict[str, Any]]:
        tests = [pt.test for pt in obj.panel_tests.select_related("test").all()]
        return cast(
            list[dict[str, Any]],
            PanelTestComponentSerializer(tests, many=True).data,
        )


class PanelCreateSerializer(serializers.Serializer):
    code = serializers.CharField(max_length=64, required=True)
    name = serializers.CharField(max_length=255, required=True)
    test_ids = serializers.ListField(
        child=serializers.UUIDField(), required=True, allow_empty=True
    )
    is_active = serializers.BooleanField(required=False, default=True)

    def validate_code(self, value: str) -> str:
        code = value.strip().upper()
        if not code:
            raise serializers.ValidationError("Code cannot be empty.")
        if Panel.objects.filter(code=code).exists():
            raise serializers.ValidationError(
                f"Panel with code '{code}' already exists."
            )
        return code

    def validate_name(self, value: str) -> str:
        name = value.strip()
        if not name:
            raise serializers.ValidationError("Name cannot be empty.")
        return name

    def validate_test_ids(self, value: list[uuid.UUID]) -> list[uuid.UUID]:
        if not value:
            # CT-V3: empty_panel error code
            raise serializers.ValidationError("empty_panel")

        # Deduplicate preserving order
        deduped: list[uuid.UUID] = list(dict.fromkeys(value))

        tests = Test.objects.filter(id__in=deduped)
        found_ids = {t.id for t in tests}
        missing_ids = set(deduped) - found_ids
        if missing_ids:
            raise serializers.ValidationError(
                f"Tests not found: {[str(i) for i in missing_ids]}"
            )

        inactive_tests = [t.code for t in tests if not t.is_active]
        if inactive_tests:
            # CT-V3: inactive_component error code
            raise serializers.ValidationError("inactive_component")

        return deduped


class PanelUpdateSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=255, required=False)
    test_ids = serializers.ListField(
        child=serializers.UUIDField(), required=False, allow_empty=True
    )
    is_active = serializers.BooleanField(required=False)

    def validate_name(self, value: str) -> str:
        name = value.strip()
        if not name:
            raise serializers.ValidationError("Name cannot be empty.")
        return name

    def validate_test_ids(self, value: list[uuid.UUID]) -> list[uuid.UUID]:
        if not value:
            raise serializers.ValidationError("empty_panel")

        deduped: list[uuid.UUID] = list(dict.fromkeys(value))

        tests = Test.objects.filter(id__in=deduped)
        found_ids = {t.id for t in tests}
        missing_ids = set(deduped) - found_ids
        if missing_ids:
            raise serializers.ValidationError(
                f"Tests not found: {[str(i) for i in missing_ids]}"
            )

        inactive_tests = [t.code for t in tests if not t.is_active]
        if inactive_tests:
            raise serializers.ValidationError("inactive_component")

        return deduped


class TestPriceSerializer(serializers.ModelSerializer[TestPrice]):
    price = serializers.SerializerMethodField()

    class Meta:
        model = TestPrice
        fields = [
            "id",
            "test_id",
            "panel_id",
            "branch_id",
            "price",
            "effective_from",
            "effective_to",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]

    def get_price(self, obj: TestPrice) -> str:
        return f"{obj.price:.2f}"


class TestPriceCreateSerializer(serializers.Serializer):
    amount = MoneyField(required=True)
    effective_from = serializers.DateTimeField(required=False)
    branch_id = serializers.UUIDField(required=False, allow_null=True)

    def validate_branch_id(self, value: uuid.UUID | None) -> uuid.UUID | None:
        if value is not None and not Branch.objects.filter(id=value).exists():
            raise serializers.ValidationError("Branch does not exist.")
        return value
