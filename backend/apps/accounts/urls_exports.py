"""URL routes for tenant data exports (Doc 04 §4.3; KAN-163 / LAB-38)."""

from django.urls import path

from apps.accounts.views_exports import (
    ExportDetailView,
    ExportDownloadView,
    ExportRequestView,
)

urlpatterns = [
    path("", ExportRequestView.as_view(), name="export-request"),
    path("/", ExportRequestView.as_view(), name="export-request-slash"),
    path(
        "<uuid:export_id>",
        ExportDetailView.as_view(),
        name="export-detail",
    ),
    path(
        "<uuid:export_id>/",
        ExportDetailView.as_view(),
        name="export-detail-slash",
    ),
    path(
        "<uuid:export_id>/download",
        ExportDownloadView.as_view(),
        name="export-download",
    ),
    path(
        "<uuid:export_id>/download/",
        ExportDownloadView.as_view(),
        name="export-download-slash",
    ),
]
