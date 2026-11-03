"""URL routing for Results endpoints (Doc 03 §5.5, KAN-150 / LAB-25)."""

from django.urls import path

from apps.results.views import ResultEntryView

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
]
