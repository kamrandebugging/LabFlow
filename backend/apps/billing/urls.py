"""URL routing for Billing endpoints (Doc 03 §5.3, §6.4, KAN-124 / LAB-18)."""

from django.urls import path

from apps.billing.views import InvoiceCreateView

urlpatterns = [
    path("invoices", InvoiceCreateView.as_view(), name="invoice-create"),
    path("invoices/", InvoiceCreateView.as_view(), name="invoice-create-slash"),
]
