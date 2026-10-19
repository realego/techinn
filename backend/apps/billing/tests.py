from decimal import Decimal
import uuid
from unittest.mock import patch

from django.test import override_settings
from rest_framework.test import APITestCase

from apps.accounts.models import Customer
from apps.billing.models import (
    Invoice,
    InvoiceItem,
    Payment,
    PaymentProvider,
    WalletAccount,
    WalletTransaction,
)
from apps.billing.paynow import PaynowInitiation
from apps.billing.views import _mark_payment_status
from apps.catalog.models import Product
from apps.orders.models import Order, OrderItem


class CustomerInvoiceApiTests(APITestCase):
    def setUp(self):
        self.customer = Customer.objects.create_user(
            email="billing-customer@example.com",
            password="Str0ng-password-not-used-elsewhere",
            first_name="Billing",
            status=Customer.Status.ACTIVE,
        )
        self.other_customer = Customer.objects.create_user(
            email="other-billing-customer@example.com",
            password="Str0ng-password-not-used-elsewhere",
            first_name="Other",
            status=Customer.Status.ACTIVE,
        )
        self.invoice = Invoice.objects.create(
            customer=self.customer,
            invoice_number="TI-1001",
            status=Invoice.Status.UNPAID,
            total="25.00",
        )
        Invoice.objects.create(
            customer=self.other_customer,
            invoice_number="TI-1002",
            status=Invoice.Status.UNPAID,
            total="99.00",
        )
        self.client.force_authenticate(self.customer)

    def test_invoice_list_only_includes_authenticated_customer_invoices(self):
        response = self.client.get("/api/v1/billing/invoices/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(response.data["results"][0]["invoice_number"], self.invoice.invoice_number)
        self.assertEqual(response.data["results"][0]["total"], "25.00")

    def test_invoice_list_requires_authentication(self):
        self.client.force_authenticate(user=None)

        response = self.client.get("/api/v1/billing/invoices/")

        self.assertEqual(response.status_code, 401)

    def test_paid_balance_top_up_creates_invoice_and_credits_wallet_once(self):
        product = Product.objects.get(slug="account-balance")
        order = Order.objects.create(
            customer=self.customer,
            order_number="TI-BALANCE-TEST-1",
            status=Order.Status.AWAITING_PAYMENT,
            subtotal="10.00",
            total="10.00",
        )
        item = OrderItem.objects.create(
            order=order,
            product=product,
            description="Account balance top-up",
            quantity=1,
            unit_price="10.00",
            subtotal="10.00",
        )
        provider = PaymentProvider.objects.create(
            name="Paynow test fixture",
            slug="paynow-test-fixture",
            provider_type="paynow",
            status=PaymentProvider.Status.INACTIVE,
        )
        payment = Payment.objects.create(
            customer=self.customer,
            order=order,
            payment_provider=provider,
            reference="PAYNOW-TEST-1",
            amount="10.00",
            currency="USD",
            provider_data={"method": "ecocash"},
        )

        _mark_payment_status(payment, "paid", "PAYNOW-TEST-REF-1")
        _mark_payment_status(payment, "paid", "PAYNOW-TEST-REF-1")

        order.refresh_from_db()
        payment.refresh_from_db()
        wallet = WalletAccount.objects.get(customer=self.customer)
        invoice = Invoice.objects.get(invoice_number=f"INV-{order.order_number}")
        self.assertEqual(order.status, Order.Status.PAID)
        self.assertEqual(payment.status, Payment.Status.SUCCESSFUL)
        self.assertEqual(payment.invoice_id, invoice.id)
        self.assertEqual(invoice.status, Invoice.Status.PAID)
        self.assertEqual(invoice.items.count(), 1)
        self.assertEqual(InvoiceItem.objects.get(invoice=invoice).description, item.description)
        self.assertEqual(wallet.balance, Decimal("10.00"))
        self.assertEqual(WalletTransaction.objects.filter(wallet=wallet).count(), 1)
        invoice_response = self.client.get("/api/v1/billing/invoices/")
        topup_invoice = next(row for row in invoice_response.data["results"] if row["invoice_number"] == invoice.invoice_number)
        self.assertEqual(topup_invoice["payment_method"], "ecocash")

    def test_wallet_balance_is_scoped_to_authenticated_customer(self):
        self.client.force_authenticate(self.customer)

        response = self.client.get("/api/v1/billing/balance/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(Decimal(response.data["balance"]), Decimal("0.00"))
        self.assertEqual(response.data["currency"], "USD")
        self.assertEqual(response.data["transactions"], [])


@override_settings(
    PAYNOW_ID="test-id",
    PAYNOW_KEY="test-key",
    PAYNOW_EMAIL="payments@example.com",
    PAYNOW_RETURN_URL="",
    PAYNOW_RESULT_URL="https://my.techinn.co.zw/api/v1/billing/payments/paynow/result/",
)
class CustomerWalletTopUpApiTests(APITestCase):
    def setUp(self):
        self.customer = Customer.objects.create_user(
            email="wallet-customer@example.com",
            password="Str0ng-password-not-used-elsewhere",
            first_name="Wallet",
            status=Customer.Status.ACTIVE,
        )
        self.client.force_authenticate(self.customer)
        self.payload = {
            "checkout_key": str(uuid.uuid4()),
            "amount": "42.75",
            "payment_method": "ecocash",
            "payment_phone": "+263 77 123 4567",
        }

    @patch("apps.billing.views.initiate_payment")
    def test_deposit_credits_balance_only_after_paynow_confirmation(self, initiate):
        initiate.return_value = PaynowInitiation(
            status="ok",
            poll_url="https://www.paynow.co.zw/interface/checkpayment?guid=wallet-test",
            instructions="Approve the payment request on your phone.",
            redirect_url="",
            provider_reference="PAYNOW-WALLET-REF",
        )

        response = self.client.post("/api/v1/billing/balance/top-up/", self.payload, format="json")

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["status"], Payment.Status.PROCESSING)
        payment = Payment.objects.get()
        self.assertEqual(payment.amount, Decimal("42.75"))
        self.assertTrue(payment.provider_data["wallet_top_up"])
        self.assertFalse(WalletAccount.objects.filter(customer=self.customer).exists())

        _mark_payment_status(payment, "paid", "PAYNOW-WALLET-REF")
        _mark_payment_status(payment, "paid", "PAYNOW-WALLET-REF")

        wallet = WalletAccount.objects.get(customer=self.customer)
        self.assertEqual(wallet.balance, Decimal("42.75"))
        self.assertEqual(WalletTransaction.objects.filter(wallet=wallet).count(), 1)
        retry = self.client.post("/api/v1/billing/balance/top-up/", self.payload, format="json")
        self.assertEqual(retry.status_code, 200)
        self.assertEqual(retry.data["status"], Payment.Status.SUCCESSFUL)
        initiate.assert_called_once()
        self.assertIn("/dashboard/billing/?payment=", initiate.call_args.args[3])

    @patch("apps.billing.views.initiate_payment")
    def test_deposit_rejects_invalid_amount_and_phone_before_creating_order(self, initiate):
        invalid_amount = self.client.post(
            "/api/v1/billing/balance/top-up/",
            {**self.payload, "amount": "0.00"},
            format="json",
        )
        invalid_phone = self.client.post(
            "/api/v1/billing/balance/top-up/",
            {**self.payload, "checkout_key": str(uuid.uuid4()), "payment_phone": "+1 202 555 0123"},
            format="json",
        )

        self.assertEqual(invalid_amount.status_code, 400)
        self.assertEqual(invalid_phone.status_code, 400)
        self.assertEqual(Order.objects.count(), 0)
        initiate.assert_not_called()

    @patch("apps.billing.views.initiate_payment")
    def test_one_cent_deposit_is_preserved_through_confirmation(self, initiate):
        initiate.return_value = PaynowInitiation(
            status="ok",
            poll_url="https://www.paynow.co.zw/interface/checkpayment?guid=cent-test",
            instructions="Approve the payment request on your phone.",
            redirect_url="",
            provider_reference="PAYNOW-CENT-REF",
        )
        response = self.client.post(
            "/api/v1/billing/balance/top-up/",
            {**self.payload, "amount": "0.01"},
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        payment = Payment.objects.get()
        self.assertEqual(payment.amount, Decimal("0.01"))
        self.assertFalse(WalletAccount.objects.filter(customer=self.customer).exists())
        _mark_payment_status(payment, "paid", "PAYNOW-CENT-REF")
        self.assertEqual(WalletAccount.objects.get(customer=self.customer).balance, Decimal("0.01"))
