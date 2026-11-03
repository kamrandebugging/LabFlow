"""URL routing for Samples endpoints (Doc 03 §5.4, KAN-137 / LAB-21,
KAN-138 / LAB-22, KAN-143 / LAB-23)."""

from django.urls import path

from apps.samples.views import (
    SampleCancelView,
    SampleCollectionView,
    SampleEventsView,
    SampleLabelView,
    SampleReceiveView,
    SampleRecollectView,
    SampleRejectView,
    SampleTransferCreateView,
    TransferCancelView,
    TransferExceptionsView,
    TransferMarkLostView,
    TransferReceiveView,
)

_LIFECYCLE = [
    ("receive", SampleReceiveView),
    ("reject", SampleRejectView),
    ("recollect", SampleRecollectView),
    ("cancel", SampleCancelView),
    ("transfer", SampleTransferCreateView),
    ("events", SampleEventsView),
]

_TRANSFER_ACTIONS = [
    ("receive", TransferReceiveView),
    ("cancel", TransferCancelView),
    ("mark-lost", TransferMarkLostView),
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
    path(
        "transfers/exceptions",
        TransferExceptionsView.as_view(),
        name="transfer-exceptions",
    ),
    path(
        "transfers/exceptions/",
        TransferExceptionsView.as_view(),
        name="transfer-exceptions-slash",
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

for action, view in _TRANSFER_ACTIONS:
    urlpatterns += [
        path(
            f"transfers/<uuid:transfer_id>/{action}",
            view.as_view(),
            name=f"transfer-{action}",
        ),
        path(
            f"transfers/<uuid:transfer_id>/{action}/",
            view.as_view(),
            name=f"transfer-{action}-slash",
        ),
    ]
