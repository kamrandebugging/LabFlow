"""DRF Views for Diagnostic Catalog & Pricing (Doc 03 §5.2, §6.3, KAN-118, KAN-119).

Enforces:
- BS-5: Tenant-wide catalog read matrix (O, M, R, T, P).
- Owner-only write permissions (Role.OWNER).
- CT-V1 & T-12 money string validation (422 money_must_be_string).
- CT-V3 empty/inactive panel validation (422 empty_panel / inactive_component).
- CT-2 effective dating of price changes.
- KAN-119: reference range CRUD; Owner + Pathologist writes; CT-4/CT-V2
  overlap rejection (422 overlapping_range); Doc 08 error envelope.
"""

import uuid
from typing import Any, cast

from django.db.models import Q
from django.shortcuts import get_object_or_404
from rest_framework import permissions, status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import Role, StaffUser
from apps.catalog.models import Panel, ReferenceRange, Test, TestPrice
from apps.catalog.serializers import (
    PanelCreateSerializer,
    PanelSerializer,
    PanelUpdateSerializer,
    ReferenceRangeCreateSerializer,
    ReferenceRangeSerializer,
    ReferenceRangeUpdateSerializer,
    TestCreateSerializer,
    TestPriceCreateSerializer,
    TestPriceSerializer,
    TestSerializer,
    TestUpdateSerializer,
)
from apps.catalog.services import (
    CatalogService,
    OverlappingRangeError,
    RangeWindowError,
)

CATALOG_READ_ROLES = {
    Role.OWNER,
    Role.MANAGER,
    Role.RECEPTION,
    Role.TECHNICIAN,
    Role.PATHOLOGIST,
}

RANGE_WRITE_ROLES = {
    Role.OWNER,
    Role.PATHOLOGIST,
}

PRICE_READ_ROLES = {
    Role.OWNER,
    Role.MANAGER,
    Role.RECEPTION,
    Role.PATHOLOGIST,
}


def _get_client_ip(request: Request) -> str:
    x_forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
    if x_forwarded_for:
        return x_forwarded_for.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR", "")


def _format_error(code: str, message: str, details: Any = None) -> dict[str, Any]:
    err: dict[str, Any] = {"code": code, "message": message}
    if details is not None:
        err["details"] = details
    return {"error": err}


class TestListCreateView(APIView):
    """GET /api/v1/tests & POST /api/v1/tests."""

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request: Request) -> Response:
        user = cast(StaffUser, request.user)
        if user.role not in CATALOG_READ_ROLES:
            return Response(
                _format_error("forbidden", "You do not have permission to view tests."),
                status=status.HTTP_403_FORBIDDEN,
            )

        queryset = Test.objects.all().order_by("code")
        q = request.query_params.get("q")
        if q:
            queryset = queryset.filter(Q(code__icontains=q) | Q(name__icontains=q))

        active = request.query_params.get("active")
        if active is None:
            active = request.query_params.get("is_active")
        if active is not None:
            is_active = active.lower() in ("true", "1")
            queryset = queryset.filter(is_active=is_active)

        category = request.query_params.get("category")
        if category:
            queryset = queryset.filter(category__iexact=category)

        serializer = TestSerializer(queryset, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    def post(self, request: Request) -> Response:
        user = cast(StaffUser, request.user)
        if user.role != Role.OWNER:
            return Response(
                _format_error("forbidden", "Only the Owner may create catalog tests."),
                status=status.HTTP_403_FORBIDDEN,
            )

        serializer = TestCreateSerializer(data=request.data)
        if not serializer.is_valid():
            err_dict = serializer.errors
            if "code" in err_dict and any(
                "already exists" in str(e) for e in err_dict["code"]
            ):
                return Response(
                    _format_error("duplicate_code", "Duplicate test code.", err_dict),
                    status=status.HTTP_422_UNPROCESSABLE_ENTITY,
                )
            return Response(
                _format_error("validation_error", "Invalid payload.", err_dict),
                status=status.HTTP_422_UNPROCESSABLE_ENTITY,
            )

        data = serializer.validated_data
        ip = _get_client_ip(request)
        user_agent = request.META.get("HTTP_USER_AGENT", "")

        test_obj = CatalogService.create_test(
            code=data["code"],
            name=data["name"],
            category=data.get("category"),
            unit=data.get("unit"),
            is_active=data.get("is_active", True),
            actor=user,
            ip=ip,
            user_agent=user_agent,
        )
        return Response(
            TestSerializer(test_obj).data,
            status=status.HTTP_201_CREATED,
        )


class TestDetailView(APIView):
    """GET /api/v1/tests/{id} & PATCH /api/v1/tests/{id}."""

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request: Request, pk: uuid.UUID) -> Response:
        user = cast(StaffUser, request.user)
        if user.role not in CATALOG_READ_ROLES:
            return Response(
                _format_error("forbidden", "You do not have permission to view tests."),
                status=status.HTTP_403_FORBIDDEN,
            )

        test_obj = get_object_or_404(Test, pk=pk)
        return Response(TestSerializer(test_obj).data, status=status.HTTP_200_OK)

    def patch(self, request: Request, pk: uuid.UUID) -> Response:
        user = cast(StaffUser, request.user)
        if user.role != Role.OWNER:
            return Response(
                _format_error("forbidden", "Only the Owner may update catalog tests."),
                status=status.HTTP_403_FORBIDDEN,
            )

        test_obj = get_object_or_404(Test, pk=pk)
        serializer = TestUpdateSerializer(data=request.data, partial=True)
        if not serializer.is_valid():
            return Response(
                _format_error(
                    "validation_error", "Invalid payload.", serializer.errors
                ),
                status=status.HTTP_422_UNPROCESSABLE_ENTITY,
            )

        ip = _get_client_ip(request)
        user_agent = request.META.get("HTTP_USER_AGENT", "")

        updated = CatalogService.update_test(
            test_obj=test_obj,
            data=serializer.validated_data,
            actor=user,
            ip=ip,
            user_agent=user_agent,
        )
        return Response(TestSerializer(updated).data, status=status.HTTP_200_OK)


class PanelListCreateView(APIView):
    """GET /api/v1/panels & POST /api/v1/panels."""

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request: Request) -> Response:
        user = cast(StaffUser, request.user)
        if user.role not in CATALOG_READ_ROLES:
            return Response(
                _format_error(
                    "forbidden", "You do not have permission to view panels."
                ),
                status=status.HTTP_403_FORBIDDEN,
            )

        queryset = (
            Panel.objects.all().prefetch_related("panel_tests__test").order_by("code")
        )
        q = request.query_params.get("q")
        if q:
            queryset = queryset.filter(Q(code__icontains=q) | Q(name__icontains=q))

        active = request.query_params.get("active")
        if active is None:
            active = request.query_params.get("is_active")
        if active is not None:
            is_active = active.lower() in ("true", "1")
            queryset = queryset.filter(is_active=is_active)

        serializer = PanelSerializer(queryset, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    def post(self, request: Request) -> Response:
        user = cast(StaffUser, request.user)
        if user.role != Role.OWNER:
            return Response(
                _format_error("forbidden", "Only the Owner may create panels."),
                status=status.HTTP_403_FORBIDDEN,
            )

        serializer = PanelCreateSerializer(data=request.data)
        if not serializer.is_valid():
            err_dict = serializer.errors
            test_ids_err = str(err_dict.get("test_ids", ""))
            if "empty_panel" in test_ids_err:
                return Response(
                    _format_error(
                        "empty_panel", "Panel must contain at least one test."
                    ),
                    status=status.HTTP_422_UNPROCESSABLE_ENTITY,
                )
            if "inactive_component" in test_ids_err:
                return Response(
                    _format_error(
                        "inactive_component",
                        "Panel cannot contain inactive tests.",
                    ),
                    status=status.HTTP_422_UNPROCESSABLE_ENTITY,
                )
            return Response(
                _format_error("validation_error", "Invalid payload.", err_dict),
                status=status.HTTP_422_UNPROCESSABLE_ENTITY,
            )

        data = serializer.validated_data
        ip = _get_client_ip(request)
        user_agent = request.META.get("HTTP_USER_AGENT", "")

        panel = CatalogService.create_panel(
            code=data["code"],
            name=data["name"],
            test_ids=data["test_ids"],
            is_active=data.get("is_active", True),
            actor=user,
            ip=ip,
            user_agent=user_agent,
        )
        return Response(
            PanelSerializer(panel).data,
            status=status.HTTP_201_CREATED,
        )


class PanelDetailView(APIView):
    """GET /api/v1/panels/{id} & PATCH /api/v1/panels/{id}."""

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request: Request, pk: uuid.UUID) -> Response:
        user = cast(StaffUser, request.user)
        if user.role not in CATALOG_READ_ROLES:
            return Response(
                _format_error(
                    "forbidden", "You do not have permission to view panels."
                ),
                status=status.HTTP_403_FORBIDDEN,
            )

        panel = get_object_or_404(
            Panel.objects.prefetch_related("panel_tests__test"), pk=pk
        )
        return Response(PanelSerializer(panel).data, status=status.HTTP_200_OK)

    def patch(self, request: Request, pk: uuid.UUID) -> Response:
        user = cast(StaffUser, request.user)
        if user.role != Role.OWNER:
            return Response(
                _format_error("forbidden", "Only the Owner may update panels."),
                status=status.HTTP_403_FORBIDDEN,
            )

        panel = get_object_or_404(Panel, pk=pk)
        serializer = PanelUpdateSerializer(data=request.data, partial=True)
        if not serializer.is_valid():
            err_dict = serializer.errors
            test_ids_err = str(err_dict.get("test_ids", ""))
            if "empty_panel" in test_ids_err:
                return Response(
                    _format_error(
                        "empty_panel", "Panel must contain at least one test."
                    ),
                    status=status.HTTP_422_UNPROCESSABLE_ENTITY,
                )
            if "inactive_component" in test_ids_err:
                return Response(
                    _format_error(
                        "inactive_component",
                        "Panel cannot contain inactive tests.",
                    ),
                    status=status.HTTP_422_UNPROCESSABLE_ENTITY,
                )
            return Response(
                _format_error("validation_error", "Invalid payload.", err_dict),
                status=status.HTTP_422_UNPROCESSABLE_ENTITY,
            )

        ip = _get_client_ip(request)
        user_agent = request.META.get("HTTP_USER_AGENT", "")

        updated = CatalogService.update_panel(
            panel=panel,
            data=serializer.validated_data,
            actor=user,
            ip=ip,
            user_agent=user_agent,
        )
        return Response(PanelSerializer(updated).data, status=status.HTTP_200_OK)


class TestPriceListCreateView(APIView):
    """GET /api/v1/tests/{id}/prices & POST /api/v1/tests/{id}/prices."""

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request: Request, pk: uuid.UUID) -> Response:
        user = cast(StaffUser, request.user)
        if user.role not in PRICE_READ_ROLES:
            return Response(
                _format_error(
                    "forbidden", "You do not have permission to view prices."
                ),
                status=status.HTTP_403_FORBIDDEN,
            )

        get_object_or_404(Test, pk=pk)
        prices = TestPrice.objects.filter(test_id=pk).order_by("-effective_from")
        serializer = TestPriceSerializer(prices, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    def post(self, request: Request, pk: uuid.UUID) -> Response:
        user = cast(StaffUser, request.user)
        if user.role != Role.OWNER:
            return Response(
                _format_error("forbidden", "Only the Owner may set test prices."),
                status=status.HTTP_403_FORBIDDEN,
            )

        get_object_or_404(Test, pk=pk)
        serializer = TestPriceCreateSerializer(data=request.data)
        if not serializer.is_valid():
            err_dict = serializer.errors
            amount_err = str(err_dict.get("amount", ""))
            if (
                "Amount must be a string" in amount_err
                or "max_two_decimals" in amount_err
            ):
                return Response(
                    _format_error(
                        "money_must_be_string",
                        "Amount must be a string with at most 2 decimal places.",
                        err_dict,
                    ),
                    status=status.HTTP_422_UNPROCESSABLE_ENTITY,
                )
            return Response(
                _format_error("validation_error", "Invalid payload.", err_dict),
                status=status.HTTP_422_UNPROCESSABLE_ENTITY,
            )

        data = serializer.validated_data
        ip = _get_client_ip(request)
        user_agent = request.META.get("HTTP_USER_AGENT", "")

        price = CatalogService.set_price(
            test_id=pk,
            amount=data["amount"],
            effective_from=data.get("effective_from"),
            branch_id=data.get("branch_id"),
            actor=user,
            ip=ip,
            user_agent=user_agent,
        )
        return Response(
            TestPriceSerializer(price).data,
            status=status.HTTP_201_CREATED,
        )


class PanelPriceListCreateView(APIView):
    """GET /api/v1/panels/{id}/prices & POST /api/v1/panels/{id}/prices."""

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request: Request, pk: uuid.UUID) -> Response:
        user = cast(StaffUser, request.user)
        if user.role not in PRICE_READ_ROLES:
            return Response(
                _format_error(
                    "forbidden", "You do not have permission to view prices."
                ),
                status=status.HTTP_403_FORBIDDEN,
            )

        get_object_or_404(Panel, pk=pk)
        prices = TestPrice.objects.filter(panel_id=pk).order_by("-effective_from")
        serializer = TestPriceSerializer(prices, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    def post(self, request: Request, pk: uuid.UUID) -> Response:
        user = cast(StaffUser, request.user)
        if user.role != Role.OWNER:
            return Response(
                _format_error("forbidden", "Only the Owner may set panel prices."),
                status=status.HTTP_403_FORBIDDEN,
            )

        get_object_or_404(Panel, pk=pk)
        serializer = TestPriceCreateSerializer(data=request.data)
        if not serializer.is_valid():
            err_dict = serializer.errors
            amount_err = str(err_dict.get("amount", ""))
            if (
                "Amount must be a string" in amount_err
                or "max_two_decimals" in amount_err
            ):
                return Response(
                    _format_error(
                        "money_must_be_string",
                        "Amount must be a string with at most 2 decimal places.",
                        err_dict,
                    ),
                    status=status.HTTP_422_UNPROCESSABLE_ENTITY,
                )
            return Response(
                _format_error("validation_error", "Invalid payload.", err_dict),
                status=status.HTTP_422_UNPROCESSABLE_ENTITY,
            )

        data = serializer.validated_data
        ip = _get_client_ip(request)
        user_agent = request.META.get("HTTP_USER_AGENT", "")

        price = CatalogService.set_price(
            panel_id=pk,
            amount=data["amount"],
            effective_from=data.get("effective_from"),
            branch_id=data.get("branch_id"),
            actor=user,
            ip=ip,
            user_agent=user_agent,
        )
        return Response(
            TestPriceSerializer(price).data,
            status=status.HTTP_201_CREATED,
        )


class ReferenceRangeListCreateView(APIView):
    """GET /api/v1/tests/{id}/ranges & POST /api/v1/tests/{id}/ranges (KAN-119)."""

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request: Request, pk: uuid.UUID) -> Response:
        user = cast(StaffUser, request.user)
        if user.role not in CATALOG_READ_ROLES:
            return Response(
                _format_error(
                    "forbidden", "You do not have permission to view ranges."
                ),
                status=status.HTTP_403_FORBIDDEN,
            )

        get_object_or_404(Test, pk=pk)
        ranges = ReferenceRange.objects.filter(test_id=pk).order_by(
            "-effective_from", "sex", "age_min_days"
        )
        serializer = ReferenceRangeSerializer(ranges, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    def post(self, request: Request, pk: uuid.UUID) -> Response:
        user = cast(StaffUser, request.user)
        if user.role not in RANGE_WRITE_ROLES:
            return Response(
                _format_error(
                    "forbidden",
                    "Only the Owner or Pathologist may create reference ranges.",
                ),
                status=status.HTTP_403_FORBIDDEN,
            )

        get_object_or_404(Test, pk=pk)
        serializer = ReferenceRangeCreateSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(
                _format_error(
                    "validation_error", "Invalid payload.", serializer.errors
                ),
                status=status.HTTP_422_UNPROCESSABLE_ENTITY,
            )

        data = serializer.validated_data
        ip = _get_client_ip(request)
        user_agent = request.META.get("HTTP_USER_AGENT", "")

        try:
            range_obj = CatalogService.create_reference_range(
                test_id=pk,
                sex=data["sex"],
                age_min_days=data["age_min_days"],
                age_max_days=data["age_max_days"],
                low=data["low"],
                high=data["high"],
                critical_low=data["critical_low"],
                critical_high=data["critical_high"],
                unit=data["unit"],
                effective_from=data["effective_from"],
                effective_to=data["effective_to"],
                actor=user,
                ip=ip,
                user_agent=user_agent,
            )
        except OverlappingRangeError as exc:
            return Response(
                _format_error("overlapping_range", str(exc)),
                status=status.HTTP_422_UNPROCESSABLE_ENTITY,
            )
        except RangeWindowError as exc:
            return Response(
                _format_error("validation_error", str(exc)),
                status=status.HTTP_422_UNPROCESSABLE_ENTITY,
            )
        return Response(
            ReferenceRangeSerializer(range_obj).data,
            status=status.HTTP_201_CREATED,
        )


class ReferenceRangeDetailView(APIView):
    """PATCH /api/v1/tests/{id}/ranges/{range_id} (KAN-119).

    Supersedes the range (Doc 03 §5.2): the old row is closed and a new row
    opened, preserving history. A payload with only effective_to retires the
    row without a successor.
    """

    permission_classes = [permissions.IsAuthenticated]

    def patch(self, request: Request, pk: uuid.UUID, range_id: uuid.UUID) -> Response:
        user = cast(StaffUser, request.user)
        if user.role not in RANGE_WRITE_ROLES:
            return Response(
                _format_error(
                    "forbidden",
                    "Only the Owner or Pathologist may update reference ranges.",
                ),
                status=status.HTTP_403_FORBIDDEN,
            )

        get_object_or_404(Test, pk=pk)
        range_obj = get_object_or_404(ReferenceRange, pk=range_id, test_id=pk)

        serializer = ReferenceRangeUpdateSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(
                _format_error(
                    "validation_error", "Invalid payload.", serializer.errors
                ),
                status=status.HTTP_422_UNPROCESSABLE_ENTITY,
            )

        ip = _get_client_ip(request)
        user_agent = request.META.get("HTTP_USER_AGENT", "")

        try:
            updated = CatalogService.supersede_reference_range(
                range_obj=range_obj,
                data=serializer.validated_data,
                actor=user,
                ip=ip,
                user_agent=user_agent,
            )
        except OverlappingRangeError as exc:
            return Response(
                _format_error("overlapping_range", str(exc)),
                status=status.HTTP_422_UNPROCESSABLE_ENTITY,
            )
        except RangeWindowError as exc:
            return Response(
                _format_error("invalid_effective_window", str(exc)),
                status=status.HTTP_422_UNPROCESSABLE_ENTITY,
            )
        return Response(
            ReferenceRangeSerializer(updated).data,
            status=status.HTTP_200_OK,
        )
