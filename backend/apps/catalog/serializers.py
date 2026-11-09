"""Serializers for Diagnostic Catalog (Doc 03 §5.2, §6.3, KAN-118, KAN-119).

Enforces:
- CT-V1 & T-12: Money values must be decimal strings with at most 2 decimal places.
- CT-V3: Panels cannot be empty or contain inactive tests.
- KAN-119: Reference range stratification fields, cross-field validation and
  strict unknown-field rejection.
"""

import re
import uuid
from decimal import Decimal, InvalidOperation
from typing import Any, cast

from django.db.models import Q
from django.utils import timezone
from rest_framework import serializers

from apps.branches.models import Branch
from apps.catalog.models import Panel, ReferenceRange, Test, TestPrice


def _effective_tenant_price(
    *, test_id: uuid.UUID | None = None, panel_id: uuid.UUID | None = None
) -> Decimal | None:
    """Current tenant-wide effective price for a test or panel (read view)."""
    now = timezone.now()
    queryset = TestPrice.objects.filter(branch_id__isnull=True, effective_from__lte=now)
    if test_id is not None:
        queryset = queryset.filter(test_id=test_id)
    elif panel_id is not None:
        queryset = queryset.filter(panel_id=panel_id)
    else:
        return None
    row = (
        queryset.filter(Q(effective_to__isnull=True) | Q(effective_to__gt=now))
        .order_by("-effective_from")
        .first()
    )
    return row.price if row is not None else None


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
    price = serializers.SerializerMethodField()
    panel_codes = serializers.SerializerMethodField()
    is_panel_only = serializers.SerializerMethodField()

    class Meta:
        model = Test
        fields = [
            "id",
            "code",
            "name",
            "category",
            "unit",
            "is_active",
            "price",
            "panel_codes",
            "is_panel_only",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]

    def get_price(self, obj: Test) -> str | None:
        """Effective standalone price, or null when only a panel is priced."""
        price = _effective_tenant_price(test_id=obj.id)
        return f"{price:.2f}" if price is not None else None

    def get_panel_codes(self, obj: Test) -> list[str]:
        return sorted(
            Panel.objects.filter(
                panel_tests__test_id=obj.id, is_active=True
            ).values_list("code", flat=True)
        )

    def get_is_panel_only(self, obj: Test) -> bool:
        if _effective_tenant_price(test_id=obj.id) is not None:
            return False
        return Panel.objects.filter(panel_tests__test_id=obj.id).exists()


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
    price = serializers.SerializerMethodField()

    class Meta:
        model = Panel
        fields = [
            "id",
            "code",
            "name",
            "is_active",
            "test_ids",
            "tests",
            "price",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]

    def get_price(self, obj: Panel) -> str | None:
        price = _effective_tenant_price(panel_id=obj.id)
        return f"{price:.2f}" if price is not None else None

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


class ReferenceRangeSerializer(serializers.ModelSerializer[ReferenceRange]):
    """Read serializer for reference ranges (KAN-119).

    Decimal bounds render as 3-decimal strings; nulls stay null.
    """

    low = serializers.DecimalField(
        max_digits=10, decimal_places=3, coerce_to_string=True, allow_null=True
    )
    high = serializers.DecimalField(
        max_digits=10, decimal_places=3, coerce_to_string=True, allow_null=True
    )
    critical_low = serializers.DecimalField(
        max_digits=10, decimal_places=3, coerce_to_string=True, allow_null=True
    )
    critical_high = serializers.DecimalField(
        max_digits=10, decimal_places=3, coerce_to_string=True, allow_null=True
    )

    class Meta:
        model = ReferenceRange
        fields = [
            "id",
            "test_id",
            "sex",
            "age_min_days",
            "age_max_days",
            "low",
            "high",
            "critical_low",
            "critical_high",
            "unit",
            "effective_from",
            "effective_to",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields


def _reject_unknown_fields(
    serializer: serializers.Serializer, attrs: dict[str, Any]
) -> dict[str, Any]:
    """Strict request serialization: unknown parameters are rejected (KAN-119)."""
    initial = serializer.initial_data
    known = set(serializer.fields)
    unknown = set(initial.keys()) - known if isinstance(initial, dict) else set()
    if unknown:
        raise serializers.ValidationError(
            f"Unknown fields: {', '.join(sorted(str(u) for u in unknown))}."
        )
    return attrs


def _validate_range_cross_fields(attrs: dict[str, Any]) -> dict[str, Any]:
    """Cross-field validation shared by range create/update (KAN-119)."""
    age_min = attrs.get("age_min_days")
    age_max = attrs.get("age_max_days")
    if age_min is not None and age_max is not None and age_max < age_min:
        raise serializers.ValidationError(
            {"age_max_days": "age_max_days cannot be less than age_min_days."}
        )

    low = attrs.get("low")
    high = attrs.get("high")
    if low is not None and high is not None and low > high:
        raise serializers.ValidationError({"low": "low cannot be greater than high."})

    critical_low = attrs.get("critical_low")
    critical_high = attrs.get("critical_high")
    if (
        critical_low is not None
        and critical_high is not None
        and critical_low > critical_high
    ):
        raise serializers.ValidationError(
            {"critical_low": "critical_low cannot be greater than critical_high."}
        )

    effective_from = attrs.get("effective_from")
    effective_to = attrs.get("effective_to")
    if (
        effective_from is not None
        and effective_to is not None
        and effective_to < effective_from
    ):
        raise serializers.ValidationError(
            {"effective_to": "effective_to cannot be before effective_from."}
        )
    return attrs


class ReferenceRangeCreateSerializer(serializers.Serializer):
    sex = serializers.ChoiceField(choices=["M", "F", "B"], required=True)
    age_min_days = serializers.IntegerField(min_value=0, required=True)
    age_max_days = serializers.IntegerField(
        min_value=0, required=False, allow_null=True, default=None
    )
    low = serializers.DecimalField(
        max_digits=10,
        decimal_places=3,
        required=False,
        allow_null=True,
        default=None,
    )
    high = serializers.DecimalField(
        max_digits=10,
        decimal_places=3,
        required=False,
        allow_null=True,
        default=None,
    )
    critical_low = serializers.DecimalField(
        max_digits=10,
        decimal_places=3,
        required=False,
        allow_null=True,
        default=None,
    )
    critical_high = serializers.DecimalField(
        max_digits=10,
        decimal_places=3,
        required=False,
        allow_null=True,
        default=None,
    )
    unit = serializers.CharField(max_length=64, required=True)
    effective_from = serializers.DateField(required=True)
    effective_to = serializers.DateField(required=False, allow_null=True, default=None)

    def validate_unit(self, value: str) -> str:
        unit = value.strip()
        if not unit:
            raise serializers.ValidationError("Unit cannot be empty.")
        return unit

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        attrs = _reject_unknown_fields(self, attrs)
        return _validate_range_cross_fields(attrs)


class ReferenceRangeUpdateSerializer(serializers.Serializer):
    sex = serializers.ChoiceField(choices=["M", "F", "B"], required=False)
    age_min_days = serializers.IntegerField(min_value=0, required=False)
    age_max_days = serializers.IntegerField(
        min_value=0, required=False, allow_null=True
    )
    low = serializers.DecimalField(
        max_digits=10, decimal_places=3, required=False, allow_null=True
    )
    high = serializers.DecimalField(
        max_digits=10, decimal_places=3, required=False, allow_null=True
    )
    critical_low = serializers.DecimalField(
        max_digits=10, decimal_places=3, required=False, allow_null=True
    )
    critical_high = serializers.DecimalField(
        max_digits=10, decimal_places=3, required=False, allow_null=True
    )
    unit = serializers.CharField(max_length=64, required=False)
    effective_from = serializers.DateField(required=False)
    effective_to = serializers.DateField(required=False, allow_null=True)

    def validate_unit(self, value: str) -> str:
        unit = value.strip()
        if not unit:
            raise serializers.ValidationError("Unit cannot be empty.")
        return unit

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        attrs = _reject_unknown_fields(self, attrs)
        return _validate_range_cross_fields(attrs)
