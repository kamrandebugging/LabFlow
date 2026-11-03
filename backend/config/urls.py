"""
URL configuration for LabFlow project.
OpenAPI docs endpoints wired via drf-spectacular.
"""

from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularRedocView,
    SpectacularSwaggerView,
)

from apps.platform.tls import tls_check_view

urlpatterns = [
    path("admin/", admin.site.urls),
    path("internal/tls-check", tls_check_view, name="internal-tls-check"),
    path("internal/tls-check/", tls_check_view, name="internal-tls-check-slash"),
    # Authentication & Sessions (Doc 07 §5, Doc 08 §4)
    path("api/v1/auth/", include("apps.accounts.urls")),
    # Patients (Doc 03 §5.1, §6.2, Doc 04 §8.5)
    path("api/v1/patients", include("apps.patients.urls")),
    path("api/v1/patients/", include("apps.patients.urls")),
    # Diagnostic Catalog: Tests, Panels, Prices (Doc 03 §5.2, §6.3, KAN-118)
    path("api/v1/", include("apps.catalog.urls")),
    path("api/v1/catalog/", include("apps.catalog.urls")),
    # Billing: Invoices (Doc 03 §5.3, §6.4, KAN-124 / LAB-18)
    path("api/v1/", include("apps.billing.urls")),
    path("api/v1/billing/", include("apps.billing.urls")),
    # Samples: accessioning + labels (Doc 03 §5.4, KAN-137 / LAB-21)
    path("api/v1/", include("apps.samples.urls")),
    # Results: batch result entry (Doc 03 §5.5, KAN-150 / LAB-25)
    path("api/v1/", include("apps.results.urls")),
    # Reports: async PDF pipeline (Doc 03 §5.6, KAN-155 / LAB-30)
    path("api/v1/", include("apps.reports.urls")),
    # Staff Administration & TOTP Recovery (Doc 04 §15.2, Doc 08 §4.4, LAB-52)
    path(
        "api/v1/staff/<uuid:user_id>/reset-totp",
        __import__(
            "apps.accounts.views_auth", fromlist=["StaffTotpResetView"]
        ).StaffTotpResetView.as_view(),
        name="staff-totp-reset",
    ),
    path(
        "api/v1/staff/<uuid:user_id>/reset-totp/",
        __import__(
            "apps.accounts.views_auth", fromlist=["StaffTotpResetView"]
        ).StaffTotpResetView.as_view(),
        name="staff-totp-reset-slash",
    ),
    # OpenAPI Schema & API Documentation
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path(
        "api/docs/",
        SpectacularSwaggerView.as_view(url_name="schema"),
        name="swagger-ui",
    ),
    path(
        "api/redoc/",
        SpectacularRedocView.as_view(url_name="schema"),
        name="redoc",
    ),
]
