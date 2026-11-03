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

from apps.accounts.views_staff import StaffBranchesView
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
    # Branches: CRUD + close/reopen (Doc 04 §8.2, §8.3, §11.3, KAN-158 / LAB-33)
    path("api/v1/branches", include("apps.branches.urls")),
    path("api/v1/branches/", include("apps.branches.urls")),
    # Reports: async PDF pipeline (Doc 03 §5.6, KAN-155 / LAB-30)
    path("api/v1/", include("apps.reports.urls")),
    # Tenant Settings: registry + accessors (Doc 04 §10, KAN-160 / LAB-35)
    path("api/v1/", include("apps.platform.urls_settings")),
    # Tenant data exports (Doc 04 §4.3; KAN-163 / LAB-38)
    path("api/v1/exports", include("apps.accounts.urls_exports")),
    path("api/v1/exports/", include("apps.accounts.urls_exports")),
    # Staff branch assignments (Doc 04 §8.4, §15, KAN-159 / LAB-34)
    path(
        "api/v1/staff/<uuid:staff_id>/branches",
        StaffBranchesView.as_view(),
        name="staff-branches",
    ),
    path(
        "api/v1/staff/<uuid:staff_id>/branches/",
        StaffBranchesView.as_view(),
        name="staff-branches-slash",
    ),
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
