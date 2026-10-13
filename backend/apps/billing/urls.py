from django.urls import path

from apps.billing.views import (
    CustomerCheckoutView,
    CustomerInvoiceListView,
    CustomerPaymentCancelView,
    CustomerPaymentPollView,
    CustomerWalletView,
    CustomerWalletTopUpView,
    PaynowResultView,
)


urlpatterns = [
    path("invoices/", CustomerInvoiceListView.as_view(), name="customer-invoices"),
    path("balance/", CustomerWalletView.as_view(), name="customer-balance"),
    path("balance/top-up/", CustomerWalletTopUpView.as_view(), name="customer-balance-top-up"),
    path("checkout/", CustomerCheckoutView.as_view(), name="customer-checkout"),
    path("payments/<uuid:uuid>/poll/", CustomerPaymentPollView.as_view(), name="customer-payment-poll"),
    path("payments/<uuid:uuid>/cancel/", CustomerPaymentCancelView.as_view(), name="customer-payment-cancel"),
    path("payments/paynow/result/", PaynowResultView.as_view(), name="paynow-result"),
]
