"""URL routing for Reports endpoints
(Doc 03 §5.6, §6.7, §6.8; KAN-155 / LAB-30, KAN-156 / LAB-31)."""

from django.urls import path

from apps.reports.views import (
    ReportAccessTokenIssueView,
    ReportAccessTokenRevokeView,
    ReportAccessView,
    ReportDeliverView,
    ReportFileDownloadView,
    ReportRegenerateView,
)
from apps.reports.views_query import (
    ExceptionsListView,
    ReportDetailView,
    ReportListView,
)

urlpatterns = [
    # Staff reports list
    path("reports", ReportListView.as_view(), name="report-list"),
    path("reports/", ReportListView.as_view(), name="report-list-slash"),
    # Exceptions triage list
    path("exceptions", ExceptionsListView.as_view(), name="exceptions-list"),
    path("exceptions/", ExceptionsListView.as_view(), name="exceptions-list-slash"),
    # Staff report detail
    path(
        "reports/<uuid:report_id>",
        ReportDetailView.as_view(),
        name="report-detail",
    ),
    path(
        "reports/<uuid:report_id>/",
        ReportDetailView.as_view(),
        name="report-detail-slash",
    ),
    path(
        "reports/<uuid:report_id>/regenerate",
        ReportRegenerateView.as_view(),
        name="report-regenerate",
    ),
    path(
        "reports/<uuid:report_id>/regenerate/",
        ReportRegenerateView.as_view(),
        name="report-regenerate-slash",
    ),
    # LAB-32: delivery dispatch (KAN-157).
    path(
        "reports/<uuid:report_id>/deliver",
        ReportDeliverView.as_view(),
        name="report-deliver",
    ),
    path(
        "reports/<uuid:report_id>/deliver/",
        ReportDeliverView.as_view(),
        name="report-deliver-slash",
    ),
    # LAB-31: public report portal (KAN-156).
    path(
        "reports/<uuid:report_id>/access-token",
        ReportAccessTokenIssueView.as_view(),
        name="report-access-token-issue",
    ),
    path(
        "reports/<uuid:report_id>/access-token/",
        ReportAccessTokenIssueView.as_view(),
        name="report-access-token-issue-slash",
    ),
    path(
        "reports/<uuid:report_id>/revoke-token",
        ReportAccessTokenRevokeView.as_view(),
        name="report-access-token-revoke",
    ),
    path(
        "reports/<uuid:report_id>/revoke-token/",
        ReportAccessTokenRevokeView.as_view(),
        name="report-access-token-revoke-slash",
    ),
    # PUBLIC: no auth — the token is the only credential (RP-V3).
    path(
        "report-access/<str:token>",
        ReportAccessView.as_view(),
        name="report-access",
    ),
    path(
        "report-access/<str:token>/",
        ReportAccessView.as_view(),
        name="report-access-slash",
    ),
    # PUBLIC: short-lived signed download target for the 302
    # (dev/test path; R2/MinIO pre-signed URLs in prod).
    path(
        "report-files/<path:signed>",
        ReportFileDownloadView.as_view(),
        name="report-file-download",
    ),
    path(
        "report-files/<path:signed>/",
        ReportFileDownloadView.as_view(),
        name="report-file-download-slash",
    ),
]
