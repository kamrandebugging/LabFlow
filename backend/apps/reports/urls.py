"""URL routing for Reports endpoints (Doc 03 §5.6, §6.7; KAN-155 / LAB-30)."""

from django.urls import path

from apps.reports.views import ReportRegenerateView

urlpatterns = [
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
]
