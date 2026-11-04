"""LAB-45 (KAN-264): n8n callback URL routes (Doc 06 §10, A-19 namespace).

These are the only endpoints an external service calls. They live on the
tenant subdomain. POST /api/v1/webhooks/n8n/critical-escalation is NOT
built in v1 (Doc 06 §10) and returns 404 like any unbuilt path.
"""

from django.urls import path

from apps.automation.views_callbacks import (
    NotificationCallbackView,
    ReportDeliveryCallbackView,
    SettlementDeliveryCallbackView,
)

urlpatterns = [
    path(
        "notification",
        NotificationCallbackView.as_view(),
        name="webhook-notification-callback",
    ),
    path(
        "notification/",
        NotificationCallbackView.as_view(),
        name="webhook-notification-callback-slash",
    ),
    path(
        "report-delivery",
        ReportDeliveryCallbackView.as_view(),
        name="webhook-report-delivery-callback",
    ),
    path(
        "report-delivery/",
        ReportDeliveryCallbackView.as_view(),
        name="webhook-report-delivery-callback-slash",
    ),
    path(
        "settlement-delivery",
        SettlementDeliveryCallbackView.as_view(),
        name="webhook-settlement-delivery-callback",
    ),
    path(
        "settlement-delivery/",
        SettlementDeliveryCallbackView.as_view(),
        name="webhook-settlement-delivery-callback-slash",
    ),
]
