"""URL routing for Samples endpoints (Doc 03 §5.4, KAN-137 / LAB-21)."""

from django.urls import path

from apps.samples.views import SampleCollectionView, SampleLabelView

urlpatterns = [
    path("samples", SampleCollectionView.as_view(), name="sample-collection"),
    path(
        "samples/",
        SampleCollectionView.as_view(),
        name="sample-collection-slash",
    ),
    path(
        "samples/<uuid:sample_id>/label",
        SampleLabelView.as_view(),
        name="sample-label",
    ),
    path(
        "samples/<uuid:sample_id>/label/",
        SampleLabelView.as_view(),
        name="sample-label-slash",
    ),
]
