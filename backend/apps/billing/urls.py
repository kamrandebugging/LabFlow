"""URL routing for Billing endpoints (Doc 03 §5.3, §6.4, KAN-124 / LAB-18,
KAN-130 / LAB-19)."""

from django.urls import path

from apps.billing.views import InvoiceCreateView, PaymentCreateView

urlpatterns = [
    path("invoices", InvoiceCreateView.as_view(), name="invoice-create"),
    path("invoices/", InvoiceCreateView.as_view(), name="invoice-create-slash"),
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
]
