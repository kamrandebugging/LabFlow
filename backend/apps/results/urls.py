"""URL routing for Results endpoints (Doc 03 §5.5, KAN-150 / LAB-25,
KAN-151 / LAB-26, KAN-152 / LAB-27, KAN-153 / LAB-28)."""

from django.urls import path

from apps.results.views import (
    CriticalNotificationView,
    ResultAmendView,
    ResultApproveView,
    ResultEntryView,
    ResultWithdrawView,
)

urlpatterns = [
    path(
        "samples/<uuid:sample_id>/results",
        ResultEntryView.as_view(),
        name="result-entry",
    ),
    path(
        "samples/<uuid:sample_id>/results/",
        ResultEntryView.as_view(),
        name="result-entry-slash",
    ),
    path(
        "results/<uuid:result_id>/approve",
        ResultApproveView.as_view(),
        name="result-approve",
    ),
    path(
        "results/<uuid:result_id>/approve/",
        ResultApproveView.as_view(),
        name="result-approve-slash",
    ),
    path(
        "results/<uuid:result_id>/withdraw",
        ResultWithdrawView.as_view(),
        name="result-withdraw",
    ),
    path(
        "results/<uuid:result_id>/withdraw/",
        ResultWithdrawView.as_view(),
        name="result-withdraw-slash",
    ),
    path(
        "results/<uuid:result_id>/amend",
        ResultAmendView.as_view(),
        name="result-amend",
    ),
    path(
        "results/<uuid:result_id>/amend/",
        ResultAmendView.as_view(),
        name="result-amend-slash",
    ),
    path(
        "results/<uuid:result_id>/critical-notifications",
        CriticalNotificationView.as_view(),
        name="critical-notification",
    ),
    path(
        "results/<uuid:result_id>/critical-notifications/",
        CriticalNotificationView.as_view(),
        name="critical-notification-slash",
    ),
]
