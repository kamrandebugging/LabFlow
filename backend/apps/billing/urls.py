"""URL routing for Billing endpoints (Doc 03 §5.3, §6.4, KAN-124 / LAB-18,
KAN-130 / LAB-19, KAN-132 / LAB-20)."""

from django.urls import path

from apps.billing.views import (
    InvoiceCancelView,
    InvoiceCollectionView,
    InvoiceDetailView,
    InvoiceHistoryView,
    PaymentCreateView,
)

urlpatterns = [
    path("invoices", InvoiceCollectionView.as_view(), name="invoice-collection"),
    path(
        "invoices/",
        InvoiceCollectionView.as_view(),
        name="invoice-collection-slash",
    ),
    path(
        "invoices/<uuid:invoice_id>/cancel",
        InvoiceCancelView.as_view(),
        name="invoice-cancel",
    ),
    path(
        "invoices/<uuid:invoice_id>/cancel/",
        InvoiceCancelView.as_view(),
        name="invoice-cancel-slash",
    ),
    path(
        "invoices/<str:invoice_id>",
        InvoiceDetailView.as_view(),
        name="invoice-detail",
    ),
    path(
        "invoices/<str:invoice_id>/",
        InvoiceDetailView.as_view(),
        name="invoice-detail-slash",
    ),
    path(
        "invoices/<uuid:invoice_id>/payments",
        PaymentCreateView.as_view(),
        name="payment-create",
    ),
    path(
        "invoices/<uuid:invoice_id>/payments/",
        PaymentCreateView.as_view(),
        name="payment-create-slash",
    ),
    path(
        "invoices/<str:invoice_id>/history",
        InvoiceHistoryView.as_view(),
        name="invoice-history",
    ),
    path(
        "invoices/<str:invoice_id>/history/",
        InvoiceHistoryView.as_view(),
        name="invoice-history-slash",
    ),
]
