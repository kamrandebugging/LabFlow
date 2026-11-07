import contextlib

from django.contrib import admin
from django.core.cache import cache
from django.db import connection
from django.http import JsonResponse
from django.urls import path

from apps.platform.auth_views import (
    PlatformLoginView,
    PlatformLogoutView,
    PlatformPasswordResetConfirmView,
    PlatformPasswordResetRequestView,
    PlatformRefreshView,
    PlatformTotpEnrollConfirmView,
    PlatformTotpEnrollView,
    PlatformTotpVerifyView,
)
from apps.platform.tls import tls_check_view
from apps.platform.views import (
    PlatformPlanListCreateView,
    PlatformPlanRetireView,
    PlatformTenantCreateView,
    PlatformTenantSubscriptionView,
)
from apps.platform.views_access import PlatformAccessControlView
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
from apps.platform.views_demo_requests import (
    PlatformDemoRequestConvertView,
    PlatformDemoRequestDetailView,
    PlatformDemoRequestListView,
    PublicDemoRequestCaptureView,
)
from apps.platform.views_health import PlatformHealthRetryView, PlatformHealthView
from apps.platform.views_metrics import PlatformOverviewMetricsView
from apps.platform.views_platform_settings import PlatformSettingsView
from apps.platform.views_subscriptions import (
    PlatformSubscriptionChangePlanView,
    PlatformSubscriptionDetailView,
    PlatformSubscriptionListView,
    PlatformSubscriptionMarkPaidView,
)
from apps.platform.views_users import (
    PlatformUserDisableView,
    PlatformUserInviteView,
    PlatformUsersListView,
)


def healthz_view(_request: object) -> JsonResponse:
    return JsonResponse({"status": "ok"})


def readyz_view(_request: object) -> JsonResponse:
    """Readiness probe: both PostgreSQL and Redis must answer.

    Liveness (``/healthz``) only proves the process is up; this proves the
    dependencies the auth and dashboard surfaces need are reachable.
    """
    checks = {"database": "unavailable", "cache": "unavailable"}
    with contextlib.suppress(Exception):
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
        checks["database"] = "ok"
    with contextlib.suppress(Exception):
        cache.set("platform:readyz", "1", timeout=5)
        if cache.get("platform:readyz") is not None:
            checks["cache"] = "ok"

    ready = all(value == "ok" for value in checks.values())
    return JsonResponse(
        {"status": "ok" if ready else "unavailable", "checks": checks},
        status=200 if ready else 503,
    )


def _platform_auth_paths() -> list:
    """Platform operator auth routes — apex host only (Doc 08 §4, Doc 04 §12.1).

    Separate from ``apps.accounts.urls`` (the tenant staff surface): platform
    operators are global, carry no tenant claim and use their own cookie path.
    """
    routes = [
        (
            "api/v1/platform/auth/login",
            PlatformLoginView,
            "platform-auth-login",
        ),
        (
            "api/v1/platform/auth/totp/verify",
            PlatformTotpVerifyView,
            "platform-auth-totp-verify",
        ),
        (
            "api/v1/platform/auth/totp/enroll",
            PlatformTotpEnrollView,
            "platform-auth-totp-enroll",
        ),
        (
            "api/v1/platform/auth/totp/enroll/confirm",
            PlatformTotpEnrollConfirmView,
            "platform-auth-totp-enroll-confirm",
        ),
        (
            "api/v1/platform/auth/refresh",
            PlatformRefreshView,
            "platform-auth-refresh",
        ),
        (
            "api/v1/platform/auth/logout",
            PlatformLogoutView,
            "platform-auth-logout",
        ),
        (
            "api/v1/platform/auth/password-reset/request",
            PlatformPasswordResetRequestView,
            "platform-auth-password-reset-request",
        ),
        (
            "api/v1/platform/auth/password-reset/confirm",
            PlatformPasswordResetConfirmView,
            "platform-auth-password-reset-confirm",
        ),
    ]
    paths = []
    for route, view_cls, name in routes:
        paths.append(path(route, view_cls.as_view(), name=name))
        paths.append(path(route + "/", view_cls.as_view(), name=name + "-slash"))
    return paths


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
    path("readyz", readyz_view, name="public-readyz"),
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
    # Platform overview metrics (master dashboard Phase 1)
    path(
        "api/v1/platform/metrics",
        PlatformOverviewMetricsView.as_view(),
        name="platform-metrics-root",
    ),
    path(
        "api/v1/platform/metrics/",
        PlatformOverviewMetricsView.as_view(),
        name="platform-metrics-root-slash",
    ),
    path(
        "api/v1/platform/metrics/overview",
        PlatformOverviewMetricsView.as_view(),
        name="platform-metrics-overview",
    ),
    path(
        "api/v1/platform/metrics/overview/",
        PlatformOverviewMetricsView.as_view(),
        name="platform-metrics-overview-slash",
    ),
    # Public demo request capture
    path(
        "api/v1/demo-requests",
        PublicDemoRequestCaptureView.as_view(),
        name="demo-requests-capture",
    ),
    path(
        "api/v1/demo-requests/",
        PublicDemoRequestCaptureView.as_view(),
        name="demo-requests-capture-slash",
    ),
    # Platform Subscriptions (Phase 2)
    path(
        "api/v1/platform/subscriptions",
        PlatformSubscriptionListView.as_view(),
        name="platform-subscriptions-list",
    ),
    path(
        "api/v1/platform/subscriptions/",
        PlatformSubscriptionListView.as_view(),
        name="platform-subscriptions-list-slash",
    ),
    path(
        "api/v1/platform/subscriptions/<uuid:subscription_id>",
        PlatformSubscriptionDetailView.as_view(),
        name="platform-subscriptions-detail",
    ),
    path(
        "api/v1/platform/subscriptions/<uuid:subscription_id>/",
        PlatformSubscriptionDetailView.as_view(),
        name="platform-subscriptions-detail-slash",
    ),
    path(
        "api/v1/platform/subscriptions/<uuid:subscription_id>/mark-paid",
        PlatformSubscriptionMarkPaidView.as_view(),
        name="platform-subscriptions-mark-paid",
    ),
    path(
        "api/v1/platform/subscriptions/<uuid:subscription_id>/mark-paid/",
        PlatformSubscriptionMarkPaidView.as_view(),
        name="platform-subscriptions-mark-paid-slash",
    ),
    path(
        "api/v1/platform/subscriptions/<uuid:subscription_id>/change-plan",
        PlatformSubscriptionChangePlanView.as_view(),
        name="platform-subscriptions-change-plan",
    ),
    path(
        "api/v1/platform/subscriptions/<uuid:subscription_id>/change-plan/",
        PlatformSubscriptionChangePlanView.as_view(),
        name="platform-subscriptions-change-plan-slash",
    ),
    # Platform Access Control (Phase 2)
    path(
        "api/v1/platform/access/<uuid:tenant_id>",
        PlatformAccessControlView.as_view(),
        name="platform-access-detail",
    ),
    path(
        "api/v1/platform/access/<uuid:tenant_id>/",
        PlatformAccessControlView.as_view(),
        name="platform-access-detail-slash",
    ),
    # Platform Users (Phase 2)
    path(
        "api/v1/platform/users",
        PlatformUsersListView.as_view(),
        name="platform-users-list",
    ),
    path(
        "api/v1/platform/users/",
        PlatformUsersListView.as_view(),
        name="platform-users-list-slash",
    ),
    path(
        "api/v1/platform/users/invite",
        PlatformUserInviteView.as_view(),
        name="platform-users-invite",
    ),
    path(
        "api/v1/platform/users/invite/",
        PlatformUserInviteView.as_view(),
        name="platform-users-invite-slash",
    ),
    path(
        "api/v1/platform/users/<uuid:user_id>/disable",
        PlatformUserDisableView.as_view(),
        name="platform-users-disable",
    ),
    path(
        "api/v1/platform/users/<uuid:user_id>/disable/",
        PlatformUserDisableView.as_view(),
        name="platform-users-disable-slash",
    ),
    # Platform Demo Requests (Phase 2)
    path(
        "api/v1/platform/demo-requests",
        PlatformDemoRequestListView.as_view(),
        name="platform-demo-requests-list",
    ),
    path(
        "api/v1/platform/demo-requests/",
        PlatformDemoRequestListView.as_view(),
        name="platform-demo-requests-list-slash",
    ),
    path(
        "api/v1/platform/demo-requests/<uuid:request_id>",
        PlatformDemoRequestDetailView.as_view(),
        name="platform-demo-requests-detail",
    ),
    path(
        "api/v1/platform/demo-requests/<uuid:request_id>/",
        PlatformDemoRequestDetailView.as_view(),
        name="platform-demo-requests-detail-slash",
    ),
    path(
        "api/v1/platform/demo-requests/<uuid:request_id>/convert",
        PlatformDemoRequestConvertView.as_view(),
        name="platform-demo-requests-convert",
    ),
    path(
        "api/v1/platform/demo-requests/<uuid:request_id>/convert/",
        PlatformDemoRequestConvertView.as_view(),
        name="platform-demo-requests-convert-slash",
    ),
    # Platform Health & Telemetry (Phase 2)
    path(
        "api/v1/platform/health", PlatformHealthView.as_view(), name="platform-health"
    ),
    path(
        "api/v1/platform/health/",
        PlatformHealthView.as_view(),
        name="platform-health-slash",
    ),
    path(
        "api/v1/platform/health/failures/<str:failure_id>/retry",
        PlatformHealthRetryView.as_view(),
        name="platform-health-retry",
    ),
    path(
        "api/v1/platform/health/failures/<str:failure_id>/retry/",
        PlatformHealthRetryView.as_view(),
        name="platform-health-retry-slash",
    ),
    # Platform Settings (Phase 2)
    path(
        "api/v1/platform/settings",
        PlatformSettingsView.as_view(),
        name="platform-settings",
    ),
    path(
        "api/v1/platform/settings/",
        PlatformSettingsView.as_view(),
        name="platform-settings-slash",
    ),
    # Platform operator auth (master dashboard Phase 1, Doc 08 §4)
    *_platform_auth_paths(),
]
