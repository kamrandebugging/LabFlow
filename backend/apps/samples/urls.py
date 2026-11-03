"""URL routing for Samples endpoints (Doc 03 §5.4, KAN-137 / LAB-21,
KAN-138 / LAB-22)."""

from django.urls import path

from apps.samples.views import (
    SampleCancelView,
    SampleCollectionView,
    SampleLabelView,
    SampleReceiveView,
    SampleRecollectView,
    SampleRejectView,
)

_LIFECYCLE = [
    ("receive", SampleReceiveView),
    ("reject", SampleRejectView),
    ("recollect", SampleRecollectView),
    ("cancel", SampleCancelView),
]

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

for action, view in _LIFECYCLE:
    urlpatterns += [
        path(
            f"samples/<uuid:sample_id>/{action}",
            view.as_view(),
            name=f"sample-{action}",
        ),
        path(
            f"samples/<uuid:sample_id>/{action}/",
            view.as_view(),
            name=f"sample-{action}-slash",
        ),
    ]
