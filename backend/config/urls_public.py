from django.contrib import admin
from django.http import JsonResponse
from django.urls import path

from apps.platform.tls import tls_check_view
from apps.platform.views import (
    PlatformPlanListCreateView,
    PlatformPlanRetireView,
    PlatformTenantCreateView,
    PlatformTenantSubscriptionView,
)
from apps.platform.views_admin import (
    PlatformAuditListView,
    PlatformTenantCompleteOffboardView,
    PlatformTenantDetailView,
    PlatformTenantOffboardView,
    PlatformTenantReactivateView,
    PlatformTenantResendActivationView,
    PlatformTenantRetryProvisioningView,
    PlatformTenantSuspendView,
)


def healthz_view(_request: object) -> JsonResponse:
    return JsonResponse({"status": "ok"})


def _platform_paths() -> list:
    """LAB-37 (KAN-162): platform admin routes, apex host only (Doc 04 §15.1).

    Each route is registered with and without trailing slash, matching the
    existing platform route style.
    """
    routes = [
        (
            "api/v1/platform/tenants/<uuid:tenant_id>",
            PlatformTenantDetailView,
            "platform-tenant-detail",
        ),
        (
            "api/v1/platform/tenants/<uuid:tenant_id>/suspend",
            PlatformTenantSuspendView,
            "platform-tenant-suspend",
        ),
        (
            "api/v1/platform/tenants/<uuid:tenant_id>/reactivate",
            PlatformTenantReactivateView,
            "platform-tenant-reactivate",
        ),
        (
            "api/v1/platform/tenants/<uuid:tenant_id>/offboard",
            PlatformTenantOffboardView,
            "platform-tenant-offboard",
        ),
        (
            "api/v1/platform/tenants/<uuid:tenant_id>/complete-offboarding",
            PlatformTenantCompleteOffboardView,
            "platform-tenant-complete-offboarding",
        ),
        (
            "api/v1/platform/tenants/<uuid:tenant_id>/retry-provisioning",
            PlatformTenantRetryProvisioningView,
            "platform-tenant-retry-provisioning",
        ),
        (
            "api/v1/platform/tenants/<uuid:tenant_id>/resend-activation",
            PlatformTenantResendActivationView,
            "platform-tenant-resend-activation",
        ),
        ("api/v1/platform/audit", PlatformAuditListView, "platform-audit-list"),
    ]
    paths = []
    for route, view_cls, name in routes:
        paths.append(path(route, view_cls.as_view(), name=name))
        paths.append(path(route + "/", view_cls.as_view(), name=name + "-slash"))
    return paths


urlpatterns = [
    path("admin/", admin.site.urls),
    path("healthz", healthz_view, name="public-healthz"),
    path("internal/tls-check", tls_check_view, name="internal-tls-check"),
    path("internal/tls-check/", tls_check_view, name="internal-tls-check-slash"),
    path(
        "api/v1/platform/tenants",
        PlatformTenantCreateView.as_view(),
        name="platform-tenants-create",
    ),
    path(
        "api/v1/platform/tenants/",
        PlatformTenantCreateView.as_view(),
        name="platform-tenants-create-slash",
    ),
    path(
        "platform/tenants",
        PlatformTenantCreateView.as_view(),
        name="platform-tenants-create-short",
    ),
    path(
        "platform/tenants/",
        PlatformTenantCreateView.as_view(),
        name="platform-tenants-create-short-slash",
    ),
    # Plans CRUD (Doc 04 §11.1, §15.1 — LAB-36)
    path(
        "api/v1/platform/plans",
        PlatformPlanListCreateView.as_view(),
        name="platform-plans-list-create",
    ),
    path(
        "api/v1/platform/plans/",
        PlatformPlanListCreateView.as_view(),
        name="platform-plans-list-create-slash",
    ),
    path(
        "api/v1/platform/plans/<uuid:plan_id>/retire",
        PlatformPlanRetireView.as_view(),
        name="platform-plan-retire",
    ),
    path(
        "api/v1/platform/plans/<uuid:plan_id>/retire/",
        PlatformPlanRetireView.as_view(),
        name="platform-plan-retire-slash",
    ),
    # Subscription change (Doc 04 §15.1 — LAB-36)
    path(
        "api/v1/platform/tenants/<uuid:tenant_id>/subscription",
        PlatformTenantSubscriptionView.as_view(),
        name="platform-tenant-subscription",
    ),
    path(
        "api/v1/platform/tenants/<uuid:tenant_id>/subscription/",
        PlatformTenantSubscriptionView.as_view(),
        name="platform-tenant-subscription-slash",
    ),
    # Platform admin routes (Doc 04 §15.1 — LAB-37)
    *_platform_paths(),
]
