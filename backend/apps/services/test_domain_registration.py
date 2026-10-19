import uuid
import fcntl
import tempfile
from pathlib import Path
from decimal import Decimal
from io import StringIO
from unittest.mock import Mock, patch

import requests
from django.core.management import call_command

from django.test import SimpleTestCase, TestCase, override_settings

from apps.accounts.models import Customer
from apps.catalog.models import Product, ServiceType
from apps.orders.models import Order, OrderItem
from apps.services.domain_registration import DomainRegistrationError, process_paid_domain_item
from apps.services.serializers import DomainAssetSerializer
from apps.services.providers.cloudflare import CloudflareClient, cloudflare_credentials
from apps.services.models import CustomerService, DNSZone, DomainAsset


@override_settings(ZISPA_SUBMISSIONS_ENABLED=True)
class PaidDomainRegistrationTests(TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.lock_directory = temporary.name
        self.settings_override = override_settings(DOMAIN_REGISTRATION_LOCK_DIR=temporary.name)
        self.settings_override.enable()
        self.addCleanup(self.settings_override.disable)
        self.customer = Customer.objects.create_user(
            email="domain-owner@example.com",
            password="test-password",
            first_name="Domain",
            last_name="Owner",
            phone="+263771234567",
            status=Customer.Status.ACTIVE,
        )
        service_type = ServiceType.objects.get(slug="domains")
        product = Product.objects.get(slug="domains", service_type=service_type)
        self.order = Order.objects.create(
            customer=self.customer,
            order_number=f"TI-{uuid.uuid4().hex.upper()}",
            status=Order.Status.PAID,
            total=Decimal("12.00"),
            metadata={
                "registrant_name": "Domain Owner",
                "registrant_business_name": "Example Ltd",
                "contact_phone": "+263771234567",
                "physical_address": "1 Main Street",
                "physical_city": "Harare",
                "physical_country": "Zimbabwe",
                "postal_same_as_physical": "true",
                "nameserver_type": "custom",
                "nameserver_1": "ns1.example.net",
                "nameserver_ip_1": "8.8.8.8",
                "nameserver_2": "ns2.example.net",
                "nameserver_ip_2": "8.8.4.4",
            },
        )
        self.item = OrderItem.objects.create(
            order=self.order,
            product=product,
            description="Domain registration (example.co.zw)",
            quantity=1,
            unit_price=Decimal("12.00"),
            subtotal=Decimal("12.00"),
            metadata={"domain": "example.co.zw", "options": {"extension": "co-zw"}},
        )

    @override_settings(
        ZISPA_API_URL="https://zispa.example.test",
        ZISPA_API_KEY="test-zispa-key",
        ZISPA_AUTO_SEND=True,
        ZISPA_DEFAULT_NAMESERVERS=[],
    )
    @patch("apps.services.domain_registration._provider_token", return_value="test-cloudflare-token")
    @patch("apps.services.domain_registration.requests.post")
    def test_paid_domain_creates_cloudflare_zone_and_submits_registrant_to_zispa(
        self,
        post,
        _provider_token,
    ):
        draft_response = Mock()
        draft_response.json.return_value = {"id": 123}
        send_response = Mock()
        post.side_effect = [draft_response, send_response]
        cloudflare = Mock()
        cloudflare.onboard_zone.return_value = {
            "id": "zone-id",
            "name": "example.co.zw",
            "nameservers": ["ns1.cloudflare.test", "ns2.cloudflare.test"],
            "status": "pending",
        }
        service = process_paid_domain_item(self.item, cloudflare)

        domain = DomainAsset.objects.get(domain_name="example.co.zw")
        dns_zone = DNSZone.objects.get(domain=domain)
        progress = service.provisioning_data["domain_registration"]
        self.assertEqual(domain.status, DomainAsset.Status.PENDING)
        self.assertEqual(domain.nameservers, ["ns1.example.net", "ns2.example.net"])
        self.assertEqual(dns_zone.nameservers, ["ns1.cloudflare.test", "ns2.cloudflare.test"])
        self.assertEqual(dns_zone.external_zone_id, "zone-id")
        self.assertEqual(progress["status"], "zispa_submitted")
        self.assertEqual(progress["zispa_request_id"], "123")
        self.assertIn("zispa_sent_at", progress)
        payload = post.call_args_list[0].kwargs["json"]
        self.assertEqual(payload["physical_address"], "1 Main Street")
        self.assertEqual(payload["postal_address"], "1 Main Street")
        self.assertEqual(
            payload["nameservers"],
            [
                {"hostname": "ns1.example.net", "ip": "8.8.8.8"},
                {"hostname": "ns2.example.net", "ip": "8.8.4.4"},
            ],
        )
        self.assertEqual(payload["nameserver_ips"], ["8.8.8.8", "8.8.4.4"])
        self.assertEqual(post.call_count, 2)

        process_paid_domain_item(self.item, cloudflare)

        cloudflare.onboard_zone.assert_called_once()
        self.assertEqual(post.call_count, 2)

    @override_settings(
        ZISPA_API_URL="https://zispa.example.test",
        ZISPA_API_KEY="test-zispa-key",
        ZISPA_AUTO_SEND=False,
        ZISPA_DEFAULT_NAMESERVERS=[
            {"hostname": "ns1.techinn.test", "ip": "8.8.8.8"},
            {"hostname": "ns2.techinn.test", "ip": "8.8.4.4"},
        ],
    )
    @patch("apps.services.domain_registration._provider_token", return_value="test-cloudflare-token")
    @patch("apps.services.domain_registration.requests.post")
    def test_techinn_nameservers_use_environment_ip_mapping(self, post, _provider_token):
        self.order.metadata.update({
            "nameserver_type": "techinn",
            "nameserver_1": "",
            "nameserver_2": "",
            "nameserver_ip_1": "",
            "nameserver_ip_2": "",
        })
        self.order.save(update_fields=("metadata",))
        post.return_value = Mock()
        post.return_value.json.return_value = {"id": 124}
        cloudflare = Mock()
        cloudflare.onboard_zone.return_value = {
            "id": "zone-id",
            "name": "example.co.zw",
            "nameservers": ["ns1.techinn.test", "ns2.techinn.test"],
            "status": "pending",
        }

        process_paid_domain_item(self.item, cloudflare)

        self.assertEqual(
            post.call_args.kwargs["json"]["nameserver_ips"],
            ["8.8.8.8", "8.8.4.4"],
        )
        self.assertEqual(
            DomainAsset.objects.get().nameservers,
            ["ns1.techinn.test", "ns2.techinn.test"],
        )

    def fake_cloudflare(self):
        client = Mock()
        client.onboard_zone.return_value = {
            "id": "zone-id", "name": "example.co.zw",
            "nameservers": ["one.cloudflare.test", "two.cloudflare.test"], "status": "pending",
        }
        return client

    @override_settings(ZISPA_SUBMISSIONS_ENABLED=False, ZISPA_AUTO_SEND=True)
    @patch("apps.services.domain_registration.requests.post")
    @patch("apps.services.domain_registration._provider_token")
    def test_release_gate_blocks_all_provider_calls(self, token, post):
        cloudflare = self.fake_cloudflare()
        service = process_paid_domain_item(self.item, cloudflare)
        self.assertEqual(service.provisioning_data["domain_registration"]["status"], "awaiting_release")
        token.assert_not_called()
        post.assert_not_called()
        cloudflare.onboard_zone.assert_not_called()
        self.assertEqual(DomainAsset.objects.get().status, "pending")

    @patch("apps.services.domain_registration.requests.post")
    def test_unpaid_order_is_rejected(self, post):
        self.order.status = Order.Status.AWAITING_PAYMENT
        self.order.save(update_fields=["status"])
        with self.assertRaisesMessage(DomainRegistrationError, "Payment must be confirmed"):
            process_paid_domain_item(self.item, self.fake_cloudflare())
        post.assert_not_called()
        self.assertFalse(CustomerService.objects.exists())

    @override_settings(ZISPA_API_URL="https://zispa.example.test", ZISPA_API_KEY="test-key", ZISPA_AUTO_SEND=False)
    @patch("apps.services.domain_registration._provider_token", return_value="test-token")
    @patch("apps.services.domain_registration.requests.post")
    def test_saved_draft_can_be_sent_after_enable_without_creating_another(self, post, token):
        post.return_value = Mock()
        post.return_value.json.return_value = {"id": 321}
        cloudflare = self.fake_cloudflare()
        service = process_paid_domain_item(self.item, cloudflare)
        key = post.call_args.kwargs["json"]["idempotency_key"]
        self.assertEqual(key, f"techinn-my-domain-{service.uuid}")
        self.assertEqual(service.provisioning_data["domain_registration"]["status"], "zispa_draft_created")
        with override_settings(ZISPA_AUTO_SEND=True):
            process_paid_domain_item(self.item, cloudflare)
        self.assertEqual(post.call_count, 2)
        self.assertTrue(post.call_args.args[0].endswith("/requests/321/send"))
        cloudflare.onboard_zone.assert_called_once()
        domain = DomainAsset.objects.get()
        self.assertEqual(domain.status, "pending")
        self.assertEqual(DomainAssetSerializer(domain).data["registration"]["status"], "zispa_submitted")

    @override_settings(ZISPA_API_URL="https://zispa.example.test", ZISPA_API_KEY="test-key", ZISPA_AUTO_SEND=True)
    @patch("apps.services.domain_registration._provider_token", return_value="test-token")
    @patch("apps.services.domain_registration.requests.post")
    def test_send_timeout_requires_review_and_never_resends(self, post, token):
        draft = Mock()
        draft.json.return_value = {"id": 322}
        post.side_effect = [draft, requests.Timeout("response lost")]
        cloudflare = self.fake_cloudflare()
        with self.assertRaises(DomainRegistrationError):
            process_paid_domain_item(self.item, cloudflare)
        service = CustomerService.objects.get()
        progress = service.provisioning_data["domain_registration"]
        self.assertEqual(progress["status"], "needs_attention")
        self.assertIn("zispa_send_attempted_at", progress)
        self.assertEqual(progress["zispa_request_id"], "322")
        process_paid_domain_item(self.item, cloudflare)
        self.assertEqual(post.call_count, 2)

    @override_settings(ZISPA_API_URL="https://zispa.example.test", ZISPA_API_KEY="test-key", ZISPA_AUTO_SEND=False)
    @patch("apps.services.domain_registration._provider_token", return_value="test-token")
    @patch("apps.services.domain_registration.requests.post")
    def test_draft_timeout_reuses_persisted_key(self, post, token):
        draft = Mock()
        draft.json.return_value = {"id": 323}
        post.side_effect = [requests.Timeout("response lost"), draft]
        cloudflare = self.fake_cloudflare()
        with self.assertRaises(DomainRegistrationError):
            process_paid_domain_item(self.item, cloudflare)
        first_key = post.call_args.kwargs["json"]["idempotency_key"]
        service = CustomerService.objects.get()
        self.assertEqual(service.provisioning_data["domain_registration"]["status"], "retry_pending")
        process_paid_domain_item(self.item, cloudflare)
        self.assertEqual(post.call_count, 1)  # Backoff is respected.
        service.provisioning_data["domain_registration"]["next_retry_at"] = None
        service.save()
        process_paid_domain_item(self.item, cloudflare)
        self.assertEqual(post.call_count, 2)
        self.assertEqual(post.call_args.kwargs["json"]["idempotency_key"], first_key)

    @patch("apps.services.domain_registration.requests.post")
    def test_concurrent_worker_does_not_enter_provisioning(self, post):
        path = Path(self.lock_directory) / f"order-item-{self.item.pk}.lock"
        with path.open("w") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            with self.assertRaisesMessage(DomainRegistrationError, "already being processed"):
                process_paid_domain_item(self.item, self.fake_cloudflare())
        post.assert_not_called()

    @patch("apps.services.management.commands.process_domain_registrations.process_paid_domain_item")
    def test_completed_items_do_not_consume_batch_limit(self, process):
        CustomerService.objects.create(customer=self.customer, product=self.item.product, order_item=self.item,
                                       provisioning_data={"domain_registration": {"status": "zispa_submitted"}})
        second = OrderItem.objects.create(order=self.order, product=self.item.product, quantity=1,
                                          unit_price=12, subtotal=12, metadata={"domain": "second.co.zw"})
        process.return_value = Mock(provisioning_data={"domain_registration": {"status": "awaiting_release"}})
        call_command("process_domain_registrations", limit=1, stdout=StringIO())
        self.assertEqual(process.call_count, 1)
        self.assertEqual(process.call_args.args[0].pk, second.pk)


class CloudflareCredentialCompatibilityTests(SimpleTestCase):
    @patch("apps.services.providers.cloudflare.urlopen")
    def test_legacy_credentials_verify_with_read_only_headers(self, urlopen):
        urlopen.return_value.__enter__.return_value.read.return_value = b'{"success":true,"result":[]}'
        credentials = cloudflare_credentials({"email": "owner@example.test", "api_key": "test-key"})
        self.assertEqual(CloudflareClient().verify_token(credentials), {"status": "active"})
        request = urlopen.call_args.args[0]
        self.assertEqual(request.get_method(), "GET")
        self.assertEqual(request.get_header("X-auth-email"), "owner@example.test")
        self.assertEqual(request.get_header("X-auth-key"), "test-key")
        self.assertIsNone(request.get_header("Authorization"))

    @patch("apps.services.providers.cloudflare.urlopen")
    def test_api_token_authentication_is_preserved(self, urlopen):
        urlopen.return_value.__enter__.return_value.read.return_value = b'{"success":true,"result":{"status":"active"}}'
        credentials = cloudflare_credentials({"api_token": "test-token"})
        CloudflareClient().verify_token(credentials)
        request = urlopen.call_args.args[0]
        self.assertEqual(request.get_header("Authorization"), "Bearer test-token")
        self.assertIsNone(request.get_header("X-auth-key"))
