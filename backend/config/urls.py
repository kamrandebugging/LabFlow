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
