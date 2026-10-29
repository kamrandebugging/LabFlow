from django.contrib import admin
from django.http import JsonResponse
from django.urls import path

from apps.platform.views import PlatformTenantCreateView


def healthz_view(_request: object) -> JsonResponse:
    return JsonResponse({"status": "ok"})


urlpatterns = [
    path("admin/", admin.site.urls),
    path("healthz", healthz_view, name="public-healthz"),
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
]
