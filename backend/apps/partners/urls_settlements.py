"""URL routing for Settlement workflow endpoints (Doc 05 §7, §10; KAN-261 / LAB-42)."""

from django.urls import path

from apps.partners.views_settlements import (
    SettlementApproveView,
    SettlementCancelView,
    SettlementDetailView,
    SettlementListView,
    SettlementMarkPaidView,
    SettlementSendView,
)

urlpatterns = [
    path(
        "settlements",
        SettlementListView.as_view(),
        name="settlement-list",
    ),
    path(
        "settlements/",
        SettlementListView.as_view(),
        name="settlement-list-slash",
    ),
    path(
        "settlements/<uuid:id>",
        SettlementDetailView.as_view(),
        name="settlement-detail",
    ),
    path(
        "settlements/<uuid:id>/",
        SettlementDetailView.as_view(),
        name="settlement-detail-slash",
    ),
    path(
        "settlements/<uuid:id>/approve",
        SettlementApproveView.as_view(),
        name="settlement-approve",
    ),
    path(
        "settlements/<uuid:id>/approve/",
        SettlementApproveView.as_view(),
        name="settlement-approve-slash",
    ),
    path(
        "settlements/<uuid:id>/cancel",
        SettlementCancelView.as_view(),
        name="settlement-cancel",
    ),
    path(
        "settlements/<uuid:id>/cancel/",
        SettlementCancelView.as_view(),
        name="settlement-cancel-slash",
    ),
    path(
        "settlements/<uuid:id>/mark-paid",
        SettlementMarkPaidView.as_view(),
        name="settlement-mark-paid",
    ),
    path(
        "settlements/<uuid:id>/mark-paid/",
        SettlementMarkPaidView.as_view(),
        name="settlement-mark-paid-slash",
    ),
    path(
        "settlements/<uuid:id>/send",
        SettlementSendView.as_view(),
        name="settlement-send",
    ),
    path(
        "settlements/<uuid:id>/send/",
        SettlementSendView.as_view(),
        name="settlement-send-slash",
    ),
]
