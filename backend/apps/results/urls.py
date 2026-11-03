"""URL routing for Results endpoints (Doc 03 §5.5, KAN-150 / LAB-25,
KAN-151 / LAB-26)."""

from django.urls import path

from apps.results.views import ResultApproveView, ResultEntryView, ResultWithdrawView

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
]
