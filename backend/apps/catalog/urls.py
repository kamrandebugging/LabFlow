"""URL routing for Diagnostic Catalog endpoints (Doc 03 §5.2, §6.3, KAN-118)."""

from django.urls import path

from apps.catalog.views import (
    PanelDetailView,
    PanelListCreateView,
    PanelPriceListCreateView,
    TestDetailView,
    TestListCreateView,
    TestPriceListCreateView,
)

urlpatterns = [
    # Tests
    path("tests", TestListCreateView.as_view(), name="test-list-create"),
    path("tests/", TestListCreateView.as_view(), name="test-list-create-slash"),
    path("tests/<uuid:pk>", TestDetailView.as_view(), name="test-detail"),
    path("tests/<uuid:pk>/", TestDetailView.as_view(), name="test-detail-slash"),
    path(
        "tests/<uuid:pk>/prices",
        TestPriceListCreateView.as_view(),
        name="test-prices",
    ),
    path(
        "tests/<uuid:pk>/prices/",
        TestPriceListCreateView.as_view(),
        name="test-prices-slash",
    ),
    # Panels
    path("panels", PanelListCreateView.as_view(), name="panel-list-create"),
    path("panels/", PanelListCreateView.as_view(), name="panel-list-create-slash"),
    path("panels/<uuid:pk>", PanelDetailView.as_view(), name="panel-detail"),
    path("panels/<uuid:pk>/", PanelDetailView.as_view(), name="panel-detail-slash"),
    path(
        "panels/<uuid:pk>/prices",
        PanelPriceListCreateView.as_view(),
        name="panel-prices",
    ),
    path(
        "panels/<uuid:pk>/prices/",
        PanelPriceListCreateView.as_view(),
        name="panel-prices-slash",
    ),
]
