import uuid
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch
from urllib.parse import urlencode

from django.test import SimpleTestCase, override_settings
from rest_framework.test import APITestCase

from apps.accounts.models import Customer
from apps.catalog.models import Product
from apps.billing.models import Payment, PaymentProvider
from apps.billing.paynow import (
    MOBILE_INITIATE_URL,
    PaynowInitiation,
    PaynowNetworkError,
    PaynowProtocolError,
    PaynowRejected,
    _hash_values,
    check_payment_status,
    initiate_payment,
)
from apps.billing.views import _mark_payment_status
from apps.orders.models import Order
from apps.services.models import CustomerService, DomainAsset, HostingAccount, HostingResource


@override_settings(
    PAYNOW_ID="test-id",
    PAYNOW_KEY="test-key",
    PAYNOW_EMAIL="payments@example.com",
    PAYNOW_RETURN_URL="",
    PAYNOW_RESULT_URL="https://my.techinn.co.zw/api/v1/billing/payments/paynow/result/",
)
class PaynowCheckoutApiTests(APITestCase):
    def setUp(self):
        self.customer = Customer.objects.create_user(
            email="paynow-customer@example.com",
            password="StrongTestPass123!",
            first_name="Paynow",
            status=Customer.Status.ACTIVE,
        )
        self.client.force_authenticate(self.customer)
        self.checkout_key = str(uuid.uuid4())
        self.payload = {
            "checkout_key": self.checkout_key,
            "payment_method": "ecocash",
            "displayed_total": "5.50",
            "phone": "+263771234567",
            "payment_phone": "+263771234567",
            "items": [
                {
                    "product_id": "web-basic",
                    "quantity": 1,
                    "options": {
                        "backup-retention": "90days",
                    },
                }
            ],
            "details": {"business_name": "Example Business"},
        }

    @patch("apps.billing.views.initiate_payment")
    def test_checkout_uses_seeded_server_prices_and_starts_paynow(self, initiate):
        initiate.return_value = PaynowInitiation(
            status="ok",
            poll_url="https://www.paynow.co.zw/interface/checkpayment?guid=test",
            instructions="Approve the payment request on your phone.",
            redirect_url="",
            provider_reference="PAYNOW-REF",
        )

        response = self.client.post(
            "/api/v1/billing/checkout/",
            {**self.payload, "amount": "0.01"},
            format="json",
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["amount"], "5.50")
        self.assertEqual(response.data["status"], Payment.Status.PROCESSING)
        self.assertNotIn("instructions", response.data)
        self.assertNotIn("Approve the payment request", str(response.data))
        self.assertEqual(Order.objects.get().total, Decimal("5.50"))
        self.assertEqual(Order.objects.get().items.count(), 2)
        payment = Payment.objects.get()
        self.assertEqual(payment.provider_reference, "PAYNOW-REF")
        self.assertNotIn("poll_url", response.data)
        initiate.assert_called_once()

    @patch("apps.billing.views.initiate_payment")
    def test_checkout_normalizes_mobile_numbers_to_local_format(self, initiate):
        initiate.return_value = PaynowInitiation(
            status="ok",
            poll_url="https://www.paynow.co.zw/interface/checkpayment?guid=test",
            instructions="",
            redirect_url="",
            provider_reference="PAYNOW-REF",
        )
        phone_formats = (
            "+263 77 123 4567",
            "263771234567",
            "077-123-4567",
            "771234567",
            "00263 77 123 4567",
        )

        for index, phone in enumerate(phone_formats):
            with self.subTest(phone_format=phone):
                initiate.return_value = PaynowInitiation(
                    status="ok",
                    poll_url=f"https://www.paynow.co.zw/interface/checkpayment?guid=test-{index}",
                    instructions="",
                    redirect_url="",
                    provider_reference=f"PAYNOW-REF-{index}",
                )
                response = self.client.post(
                    "/api/v1/billing/checkout/",
                    {
                        **self.payload,
                        "checkout_key": str(uuid.uuid4()),
                        "payment_phone": phone,
                    },
                    format="json",
                )
                self.assertEqual(response.status_code, 201)
                self.assertEqual(initiate.call_args.args[2], "0771234567")

    @patch("apps.billing.views.initiate_payment")
    def test_checkout_rejects_non_zimbabwe_mobile_numbers(self, initiate):
        response = self.client.post(
            "/api/v1/billing/checkout/",
            {**self.payload, "payment_phone": "+1 202 555 0123"},
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("Zimbabwe mobile number", str(response.data["payment_phone"]))
        initiate.assert_not_called()

    @patch("apps.billing.views.initiate_payment")
    def test_uncertain_initiation_stays_processing_and_retry_is_idempotent(self, initiate):
        initiate.side_effect = PaynowNetworkError("network unavailable")

        first_response = self.client.post(
            "/api/v1/billing/checkout/",
            self.payload,
            format="json",
        )
        retry_response = self.client.post(
            "/api/v1/billing/checkout/",
            self.payload,
            format="json",
        )

        self.assertEqual(first_response.status_code, 202)
        self.assertEqual(retry_response.status_code, 200)
        self.assertEqual(first_response.data["status"], Payment.Status.PROCESSING)
        self.assertEqual(retry_response.data["status"], Payment.Status.PROCESSING)
        self.assertEqual(Payment.objects.count(), 1)
        self.assertEqual(Order.objects.count(), 1)
        initiate.assert_called_once()

    @patch("apps.billing.views.initiate_payment", side_effect=PaynowRejected("The mobile number is invalid."))
    def test_checkout_returns_and_records_paynow_rejection_reason(self, _initiate):
        response = self.client.post(
            "/api/v1/billing/checkout/",
            self.payload,
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("The mobile number is invalid.", response.data["detail"])
        attempt = Payment.objects.get().attempts.get(request_type="verify")
        self.assertEqual(attempt.response_data["reason"], "The mobile number is invalid.")

    @patch("apps.billing.views.is_configured", return_value=False)
    def test_checkout_without_gateway_configuration_does_not_create_order(self, _is_configured):
        response = self.client.post(
            "/api/v1/billing/checkout/",
            self.payload,
            format="json",
        )

        self.assertEqual(response.status_code, 503)
        self.assertEqual(Order.objects.count(), 0)

    @patch("apps.billing.views.initiate_payment")
    def test_changed_server_price_is_rejected_before_payment(self, initiate):
        response = self.client.post(
            "/api/v1/billing/checkout/",
            {**self.payload, "displayed_total": "8.49"},
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(Order.objects.count(), 0)
        initiate.assert_not_called()

    @patch("apps.billing.views.initiate_payment")
    def test_yearly_plan_uses_server_annual_prices(self, initiate):
        initiate.return_value = PaynowInitiation(
            status="ok",
            poll_url="https://www.paynow.co.zw/interface/checkpayment?guid=test",
            instructions="",
            redirect_url="",
            provider_reference="PAYNOW-ANNUAL",
        )
        payload = {
            **self.payload,
            "displayed_total": "59.40",
            "items": [{
                "product_id": "web-basic",
                "quantity": 1,
                "options": {
                    "billing": "yearly",
                    "backup-retention": "90days",
                },
            }],
        }

        response = self.client.post("/api/v1/billing/checkout/", payload, format="json")

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["amount"], "59.40")

    @patch("apps.billing.views.initiate_payment")
    def test_chatbot_checkout_uses_server_prices_for_selected_features(self, initiate):
        initiate.return_value = PaynowInitiation(
            status="ok",
            poll_url="https://www.paynow.co.zw/interface/checkpayment?guid=chatbot",
            instructions="",
            redirect_url="",
            provider_reference="PAYNOW-CHATBOT",
        )
        response = self.client.post(
            "/api/v1/billing/checkout/",
            {
                **self.payload,
                "displayed_total": "175.00",
                "items": [{
                    "product_id": "chatbot-basic",
                    "quantity": 1,
                    "options": {
                        "flows": "enabled",
                        "payments": "enabled",
                        "booking": "enabled",
                        "tickets": "enabled",
                    },
                }],
                "details": {},
            },
            format="json",
        )

        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["amount"], "175.00")
        items = Order.objects.get().items.select_related("addon", "product")
        self.assertEqual(items.count(), 5)
        self.assertEqual(items.get(product__slug="chatbot-basic").unit_price, Decimal("80.00"))
        self.assertEqual(items.get(addon__slug="chatbot-flows").unit_price, Decimal("25.00"))
        self.assertEqual(items.get(addon__slug="chatbot-payments").unit_price, Decimal("30.00"))
        self.assertEqual(items.get(addon__slug="chatbot-booking").unit_price, Decimal("0.00"))
        self.assertEqual(items.get(addon__slug="chatbot-tickets").unit_price, Decimal("40.00"))

    @patch("apps.billing.views.initiate_payment")
    @override_settings(CHECKOUT_TEST_EMAIL="realego01@gmail.com")
    def test_exact_test_customer_pays_one_cent_and_activates_paid_order(self, initiate):
        initiate.return_value = PaynowInitiation(
            status="ok",
            poll_url="https://www.paynow.co.zw/interface/checkpayment?guid=test-customer",
            instructions="",
            redirect_url="",
            provider_reference="PAYNOW-TEST-CUSTOMER",
        )
        test_customer = Customer.objects.create_user(
            email="realego01@gmail.com",
            password="a-secure-test-password",
            first_name="Test",
            status=Customer.Status.ACTIVE,
        )
        self.client.force_authenticate(test_customer)
        response = self.client.post(
            "/api/v1/billing/checkout/",
            {
                **self.payload,
                "displayed_total": "0.01",
                "items": [{
                    "product_id": "chatbot-basic",
                    "quantity": 1,
                    "options": {
                        "flows": "enabled",
                        "payments": "enabled",
                        "booking": "enabled",
                        "tickets": "enabled",
                    },
                }],
                "details": {},
            },
            format="json",
        )

        self.assertEqual(response.status_code, 201, response.data)
        payment = Payment.objects.get(customer=test_customer)
        order = Order.objects.get(customer=test_customer)
        self.assertEqual(payment.amount, Decimal("0.01"))
        self.assertTrue(payment.provider_data["test_checkout"])
        from apps.accounts.serializers import CustomerSerializer
        self.assertTrue(CustomerSerializer(test_customer).data["test_checkout_enabled"])
        self.assertEqual(order.status, Order.Status.AWAITING_PAYMENT)
        self.assertEqual(order.subtotal, Decimal("175.00"))
        self.assertEqual(order.discount_total, Decimal("174.99"))
        self.assertEqual(order.total, Decimal("0.01"))
        self.assertEqual(order.metadata["test_checkout"]["charged_total"], "0.01")

        _mark_payment_status(payment, "paid", "PAYNOW-TEST-CONFIRMED")

        order.refresh_from_db()
        payment.refresh_from_db()
        invoice = payment.invoice
        self.assertEqual(order.status, Order.Status.PAID)
        self.assertEqual(invoice.discount_total, Decimal("174.99"))
        invoices = self.client.get("/api/v1/billing/invoices/")
        invoice_data = next(item for item in invoices.data["results"] if item["invoice_number"] == invoice.invoice_number)
        self.assertTrue(invoice_data["is_test"])
        self.assertEqual(invoice_data["discount_total"], "174.99")

    @patch("apps.billing.views.initiate_payment")
    @override_settings(CHECKOUT_TEST_EMAIL="realego01@gmail.com")
    def test_test_price_is_not_available_to_other_customers(self, initiate):
        response = self.client.post(
            "/api/v1/billing/checkout/",
            {
                **self.payload,
                "displayed_total": "0.01",
                "items": [{
                    "product_id": "chatbot-basic",
                    "quantity": 1,
                    "options": {},
                }],
                "details": {},
            },
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(Order.objects.count(), 0)
        initiate.assert_not_called()

    @patch("apps.billing.views.initiate_payment")
    def test_storage_extension_is_targeted_and_uses_monthly_and_annual_prices(self, initiate):
        service = CustomerService.objects.create(
            customer=self.customer,
            product=Product.objects.get(slug="web-basic"),
            status=CustomerService.Status.ACTIVE,
        )
        domain = DomainAsset.objects.create(
            customer_service=service,
            domain_name="storage.example.co.zw",
            status=DomainAsset.Status.ACTIVE,
        )
        account = HostingAccount.objects.create(
            customer_service=service,
            primary_domain=domain,
            status=HostingAccount.Status.ACTIVE,
            username="storagecustomer",
        )
        HostingResource.objects.create(
            hosting_account=account,
            resource_type=HostingResource.ResourceType.DISK,
            limit_value=2,
            used_value=0,
            unit="GB",
        )
        initiate.side_effect = [
            PaynowInitiation(
                status="ok",
                poll_url="https://www.paynow.co.zw/interface/checkpayment?guid=monthly",
                instructions="",
                redirect_url="",
                provider_reference="PAYNOW-STORAGE-MONTHLY",
            ),
            PaynowInitiation(
                status="ok",
                poll_url="https://www.paynow.co.zw/interface/checkpayment?guid=annual",
                instructions="",
                redirect_url="",
                provider_reference="PAYNOW-STORAGE-ANNUAL",
            ),
        ]

        for interval, total in (("monthly", "2.00"), ("yearly", "21.60")):
            options = {"billing": "yearly"} if interval == "yearly" else {}
            with self.subTest(interval=interval):
                response = self.client.post(
                    "/api/v1/billing/checkout/",
                    {
                        **self.payload,
                        "checkout_key": str(uuid.uuid4()),
                        "displayed_total": total,
                        "items": [{
                            "product_id": "web-storage-addon",
                            "service_uuid": str(service.uuid),
                            "quantity": 1,
                            "options": options,
                        }],
                        "details": {},
                    },
                    format="json",
                )
                self.assertEqual(response.status_code, 201, response.data)
                self.assertEqual(response.data["amount"], total)
                line = Order.objects.latest("id").items.get(addon__slug="web-storage-5gb")
                self.assertEqual(line.unit_price, Decimal(total))
                self.assertEqual(line.metadata["customer_service_uuid"], str(service.uuid))

    @patch("apps.billing.views.initiate_payment")
    def test_domain_checkout_prices_selected_extension_on_server(self, initiate):
        initiate.return_value = PaynowInitiation(
            status="ok",
            poll_url="https://www.paynow.co.zw/interface/checkpayment?guid=test",
            instructions="",
            redirect_url="",
            provider_reference="PAYNOW-DOMAIN",
        )
        payload = {
            **self.payload,
            "displayed_total": "12.00",
            "items": [{
                "product_id": "domains",
                "quantity": 1,
                "options": {"extension": "co-zw"},
                "domain_name": "Example.co.zw",
            }],
            "details": {
                "registrant_name": "Example Owner",
                "physical_address": "1 Main Street",
                "physical_city": "Harare",
                "physical_country": "Zimbabwe",
                "postal_same_as_physical": "true",
                "nameserver_type": "techinn",
            },
        }

        response = self.client.post("/api/v1/billing/checkout/", payload, format="json")

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["amount"], "12.00")
        self.assertEqual(Order.objects.get().items.first().metadata["domain"], "example.co.zw")

    @patch("apps.billing.views.initiate_payment")
    def test_domain_checkout_requires_registrant_physical_and_postal_address(self, initiate):
        initiate.return_value = PaynowInitiation(
            status="ok",
            poll_url="https://www.paynow.co.zw/interface/checkpayment?guid=domain",
            instructions="",
            redirect_url="",
            provider_reference="PAYNOW-DOMAIN",
        )
        payload = {
            **self.payload,
            "displayed_total": "12.00",
            "items": [{
                "product_id": "domains",
                "quantity": 1,
                "options": {"extension": "co-zw"},
                "domain_name": "example.co.zw",
            }],
            "details": {
                "registrant_name": "Example Owner",
                "physical_address": "1 Main Street",
                "physical_city": "Harare",
                "physical_country": "Zimbabwe",
                "postal_same_as_physical": "true",
                "nameserver_type": "techinn",
            },
        }

        response = self.client.post("/api/v1/billing/checkout/", payload, format="json")

        self.assertEqual(response.status_code, 201, response.data)
        metadata = Order.objects.get().metadata
        self.assertEqual(metadata["physical_address"], "1 Main Street")
        self.assertEqual(metadata["contact_phone"], "+263771234567")

    def test_custom_nameserver_requires_ip_when_not_in_techinn_defaults(self):
        payload = {
            **self.payload,
            "displayed_total": "12.00",
            "items": [{
                "product_id": "domains",
                "quantity": 1,
                "options": {"extension": "co-zw"},
                "domain_name": "example.co.zw",
            }],
            "details": {
                "registrant_name": "Example Owner",
                "physical_address": "1 Main Street",
                "physical_city": "Harare",
                "physical_country": "Zimbabwe",
                "postal_same_as_physical": "true",
                "nameserver_type": "custom",
                "nameserver_1": "ns1.example.net",
                "nameserver_2": "ns2.example.net",
            },
        }

        response = self.client.post("/api/v1/billing/checkout/", payload, format="json")

        self.assertEqual(response.status_code, 400)
        self.assertIn("IP address", str(response.data["details"]))

    @patch("apps.billing.views.check_payment_status")
    def test_poll_confirms_payment_and_marks_order_paid(self, check_status):
        payment = self._create_payment_with_poll_url()
        check_status.return_value = {
            "status": "Paid",
            "reference": payment.reference,
            "amount": "8.50",
            "paynowreference": "PAYNOW-REF",
        }

        response = self.client.post(f"/api/v1/billing/payments/{payment.uuid}/poll/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["status"], Payment.Status.SUCCESSFUL)
        payment.refresh_from_db()
        self.assertEqual(payment.order.status, Order.Status.PAID)

    @patch("apps.billing.views.check_payment_status")
    def test_cancel_marks_pending_payment_and_order_cancelled(self, check_status):
        payment = self._create_payment_with_poll_url()
        check_status.return_value = {
            "status": "Pending",
            "reference": payment.reference,
            "amount": "8.50",
            "paynowreference": "PAYNOW-REF",
        }

        response = self.client.post(f"/api/v1/billing/payments/{payment.uuid}/cancel/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["status"], Payment.Status.CANCELLED)
        self.assertIn("cannot revoke", response.data["message"])
        payment.refresh_from_db()
        self.assertEqual(payment.order.status, Order.Status.CANCELLED)
        self.assertTrue(payment.events.filter(event_type="customer_cancelled").exists())

    @patch("apps.billing.views.check_payment_status")
    def test_cancel_does_not_cancel_payment_already_paid_at_paynow(self, check_status):
        payment = self._create_payment_with_poll_url()
        check_status.return_value = {
            "status": "Paid",
            "reference": payment.reference,
            "amount": "8.50",
            "paynowreference": "PAYNOW-REF",
        }

        response = self.client.post(f"/api/v1/billing/payments/{payment.uuid}/cancel/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["status"], Payment.Status.SUCCESSFUL)
        payment.refresh_from_db()
        self.assertEqual(payment.order.status, Order.Status.PAID)
        self.assertFalse(payment.events.filter(event_type="customer_cancelled").exists())

    @patch("apps.billing.views.check_payment_status", side_effect=PaynowNetworkError("timeout"))
    def test_cancel_keeps_payment_active_when_paynow_status_cannot_be_confirmed(self, _check_status):
        payment = self._create_payment_with_poll_url()

        response = self.client.post(f"/api/v1/billing/payments/{payment.uuid}/cancel/")

        self.assertEqual(response.status_code, 503)
        payment.refresh_from_db()
        self.assertEqual(payment.status, Payment.Status.PROCESSING)
        self.assertEqual(payment.order.status, Order.Status.AWAITING_PAYMENT)

    @patch("apps.billing.views.check_payment_status", side_effect=PaynowNetworkError("timeout"))
    def test_poll_timeout_keeps_payment_processing(self, _check_status):
        payment = self._create_payment_with_poll_url()

        response = self.client.post(f"/api/v1/billing/payments/{payment.uuid}/poll/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["status"], Payment.Status.PROCESSING)
        payment.refresh_from_db()
        self.assertEqual(payment.order.status, Order.Status.AWAITING_PAYMENT)

    def test_payment_status_is_scoped_to_authenticated_customer(self):
        payment = self._create_payment_with_poll_url()
        other_customer = Customer.objects.create_user(
            email="other-paynow-customer@example.com",
            password="StrongTestPass123!",
            first_name="Other",
            status=Customer.Status.ACTIVE,
        )
        self.client.force_authenticate(other_customer)

        response = self.client.post(f"/api/v1/billing/payments/{payment.uuid}/poll/")

        self.assertEqual(response.status_code, 404)

    @patch("apps.billing.views.verify_response_hash", return_value=True)
    def test_paynow_callback_marks_order_paid_only_for_matching_payment(self, _verify_hash):
        payment = self._create_payment_with_poll_url()

        response = self.client.post(
            "/api/v1/billing/payments/paynow/result/",
            {
                "status": "Paid",
                "reference": payment.reference,
                "amount": "8.50",
                "paynowreference": "PAYNOW-CALLBACK-REF",
                "hash": "verified-by-test",
            },
            format="multipart",
        )

        self.assertEqual(response.status_code, 200)
        payment.refresh_from_db()
        self.assertEqual(payment.status, Payment.Status.SUCCESSFUL)
        self.assertEqual(payment.order.status, Order.Status.PAID)

    @patch("apps.billing.views.verify_response_hash", return_value=True)
    def test_late_paynow_success_reconciles_after_customer_cancelled_locally(self, _verify_hash):
        payment = self._create_payment_with_poll_url()
        payment.status = Payment.Status.CANCELLED
        payment.save(update_fields=("status",))
        payment.order.status = Order.Status.CANCELLED
        payment.order.save(update_fields=("status",))

        response = self.client.post(
            "/api/v1/billing/payments/paynow/result/",
            {
                "status": "Paid",
                "reference": payment.reference,
                "amount": "8.50",
                "paynowreference": "PAYNOW-LATE-PAID",
                "hash": "verified-by-test",
            },
            format="multipart",
        )

        self.assertEqual(response.status_code, 200)
        payment.refresh_from_db()
        self.assertEqual(payment.status, Payment.Status.SUCCESSFUL)
        self.assertEqual(payment.order.status, Order.Status.PAID)

    def _create_payment_with_poll_url(self):
        provider = PaymentProvider.objects.create(
            name="Paynow",
            slug="paynow",
            provider_type="paynow",
            status=PaymentProvider.Status.ACTIVE,
        )
        order = Order.objects.create(
            customer=self.customer,
            order_number=f"TI-{uuid.uuid4().hex.upper()}",
            status=Order.Status.AWAITING_PAYMENT,
            total=Decimal("8.50"),
        )
        return Payment.objects.create(
            customer=self.customer,
            order=order,
            payment_provider=provider,
            reference=order.order_number,
            amount=order.total,
            currency="USD",
            status=Payment.Status.PROCESSING,
            provider_data={
                "poll_url": "https://www.paynow.co.zw/interface/checkpayment?guid=test",
            },
        )


@override_settings(PAYNOW_ID="test-id", PAYNOW_KEY="test-key", PAYNOW_EMAIL="fallback@example.com")
class PaynowAdapterTests(SimpleTestCase):
    @patch("apps.billing.paynow.requests.post")
    def test_mobile_initiation_uses_payer_email_and_verified_paynow_response(self, post):
        response_fields = {
            "status": "Ok",
            "pollurl": "https://www.paynow.co.zw/interface/checkpayment?guid=test",
            "paynowreference": "PAYNOW-REF",
            "instructions": "Approve the request on your phone.",
        }
        response_fields["hash"] = _hash_values(response_fields)
        response = SimpleNamespace(
            text=urlencode(response_fields),
            raise_for_status=lambda: None,
        )
        post.return_value = response
        payment = SimpleNamespace(
            reference="TI-TEST-ORDER",
            amount=Decimal("8.50"),
            order=SimpleNamespace(order_number="TI-TEST-ORDER"),
            customer=SimpleNamespace(email="buyer@example.com"),
        )

        result = initiate_payment(
            payment,
            "ecocash",
            "+263771234567",
            "https://my.techinn.co.zw/checkout/?payment=test",
            "https://my.techinn.co.zw/api/v1/billing/payments/paynow/result/",
        )

        self.assertEqual(result.provider_reference, "PAYNOW-REF")
        self.assertEqual(result.instructions, "Approve the request on your phone.")
        self.assertEqual(post.call_args.args[0], MOBILE_INITIATE_URL)
        form_data = post.call_args.kwargs["data"]
        self.assertEqual(form_data["authemail"], "buyer@example.com")
        self.assertEqual(form_data["phone"], "%2B263771234567")
        self.assertEqual(form_data["method"], "ecocash")
        self.assertEqual(form_data["amount"], "8.50")
        self.assertEqual(form_data["hash"], _hash_values({
            key: value for key, value in form_data.items() if key != "hash"
        }))

    @override_settings(PAYNOW_KEY="test-key")
    def test_poll_rejects_non_paynow_urls_before_request(self):
        with self.assertRaises(PaynowProtocolError):
            check_payment_status("http://127.0.0.1/internal")
