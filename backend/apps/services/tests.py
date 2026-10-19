import base64
import json
from decimal import Decimal
from unittest.mock import Mock, patch

from django.db import connection
from django.test import override_settings
from rest_framework.test import APITestCase

from apps.accounts.models import Customer
from apps.catalog.models import Addon, Product, ServiceType
from apps.orders.models import Order, OrderItem
from apps.services.models import (
    CustomerService,
    DNSRecord,
    DNSZone,
    DomainAsset,
    HostingAccount,
    HostingResource,
    HostingStorageAddon,
    HostingWebsite,
    Mailbox,
    ProviderConnection,
    ProvisioningAction,
    ServiceAuditEvent,
    ServiceMember,
)
from apps.services.serializers import DomainAssetSerializer
from apps.services.management.commands.process_provisioning import (
    process_dns_action,
    process_mailbox_action,
    process_hosting_storage_action,
    process_hosting_certificate_action,
    process_hosting_website_action,
    queue_hosting_storage_actions,
)
from apps.services.management.commands.sync_cyberpanel_services import sync_mailboxes
from apps.services.providers.cloudflare import CloudflareClient
from apps.services.providers.cyberpanel import (
    CyberPanelError,
    run_local_mail_operation,
    run_local_mail_quota_operation,
    set_linux_user_disk_quota,
)
from apps.services.storage import mailbox_storage_budget, set_shared_hosting_disk_quota


class CustomerControlPanelApiTests(APITestCase):
    def setUp(self):
        self.customer = Customer.objects.create_user(
            email="hosting-customer@example.com",
            password="A-strong-test-password-123",
            first_name="Hosting",
            status=Customer.Status.ACTIVE,
        )
        self.other_customer = Customer.objects.create_user(
            email="other-customer@example.com",
            password="A-strong-test-password-123",
            first_name="Other",
            status=Customer.Status.ACTIVE,
        )
        service_type, _ = ServiceType.objects.get_or_create(
            name="Web Hosting",
            slug="web-hosting",
        )
        product = Product.objects.create(
            service_type=service_type,
            name="Business",
            slug="business-hosting",
            billing_type=Product.BillingType.RECURRING,
        )
        self.service = CustomerService.objects.create(
            customer=self.customer,
            product=product,
            status=CustomerService.Status.ACTIVE,
        )
        self.other_service = CustomerService.objects.create(
            customer=self.other_customer,
            product=product,
            status=CustomerService.Status.ACTIVE,
        )
        self.domain = DomainAsset.objects.create(
            customer_service=self.service,
            domain_name="example.co.zw",
            status=DomainAsset.Status.ACTIVE,
        )
        self.other_domain = DomainAsset.objects.create(
            customer_service=self.other_service,
            domain_name="other.co.zw",
            status=DomainAsset.Status.ACTIVE,
        )
        self.zone = DNSZone.objects.create(domain=self.domain, status=DNSZone.Status.ACTIVE)
        self.other_zone = DNSZone.objects.create(domain=self.other_domain, status=DNSZone.Status.ACTIVE)
        self.account = HostingAccount.objects.create(
            customer_service=self.service,
            primary_domain=self.domain,
            status=HostingAccount.Status.ACTIVE,
            username="hostingcustomer",
        )
        HostingResource.objects.create(
            hosting_account=self.account,
            resource_type=HostingResource.ResourceType.DISK,
            limit_value=Decimal("10"),
            used_value=Decimal("2"),
            unit="GB",
        )
        HostingResource.objects.create(
            hosting_account=self.account,
            resource_type=HostingResource.ResourceType.EMAIL_ACCOUNTS,
            limit_value=Decimal("3"),
            unit="mailboxes",
        )
        self.client.force_authenticate(self.customer)

    @patch("apps.services.panel_access.Path.read_bytes", return_value=b"test-sso-secret")
    def test_pending_domain_allows_paid_preparation_but_suspension_blocks_access(self, key):
        self.domain.status = 'pending'
        self.domain.save()
        self.service.status = 'provisioning'
        self.service.save()
        path = f'/api/v1/services/hosting-accounts/{self.account.pk}/file-manager/'
        with override_settings(CYBERPANEL_API_URL='https://panel.example.com'):
            self.assertEqual(self.client.post(path).status_code, 200)
            self.service.status = 'suspended'
            self.service.save()
            self.assertEqual(self.client.post(path).status_code, 400)

    @patch("apps.services.panel_access.Path.read_bytes", return_value=b"test-sso-secret")
    def test_file_manager_checks_owner_active_plan_and_expiry(self, key):
        from datetime import timedelta
        from django.utils import timezone
        from django.test import override_settings
        path = f"/api/v1/services/hosting-accounts/{self.account.pk}/file-manager/"
        with override_settings(CYBERPANEL_API_URL="https://panel.example.com"):
            response = self.client.post(path)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["url"], "https://panel.example.com/api/techinn/session/")
        self.assertEqual(response["Cache-Control"], "no-store")
        self.client.force_authenticate(self.other_customer)
        self.assertEqual(self.client.post(path).status_code, 404)
        self.client.force_authenticate(self.customer)
        self.service.status = "suspended"
        self.service.save()
        self.assertEqual(self.client.post(path).status_code, 400)
        self.service.status = "active"
        self.service.expires_at = timezone.now() - timedelta(seconds=1)
        self.service.save()
        self.assertEqual(self.client.post(path).status_code, 400)
        self.client.force_authenticate(None)
        self.assertEqual(self.client.post(path).status_code, 401)

    @patch("apps.services.panel_access.Path.read_bytes", return_value=b"test-sso-secret")
    def test_hosting_panel_login_uses_cyberpanel_account_access_for_active_customer(self, key):
        path = f"/api/v1/services/hosting-accounts/{self.account.pk}/panel-login/"
        with override_settings(CYBERPANEL_API_URL="https://panel.example.com"):
            response = self.client.post(path)

        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["url"], "https://panel.example.com/api/techinn/session/")
        ticket_data = response.data["ticket"].split(".")[0]
        ticket_payload = json.loads(
            base64.urlsafe_b64decode(ticket_data + "=" * (-len(ticket_data) % 4))
        )
        self.assertEqual(ticket_payload["access_mode"], "panel")
        self.assertEqual(ticket_payload["username"], self.account.username)
        self.assertNotIn("child_domain", ticket_payload)

        self.customer.status = self.customer.Status.PENDING
        self.customer.save(update_fields=("status",))
        self.assertEqual(self.client.post(path).status_code, 400)

        self.customer.status = self.customer.Status.ACTIVE
        self.customer.save(update_fields=("status",))
        self.client.force_authenticate(self.other_customer)
        self.assertEqual(self.client.post(path).status_code, 404)

    def test_unverified_domain_transfer_is_not_reported_as_registered(self):
        self.domain.status = DomainAsset.Status.TRANSFER_PENDING
        self.domain.save(update_fields=("status",))

        registration = DomainAssetSerializer(self.domain).data["registration"]

        self.assertEqual(registration["status"], "transfer_pending")
        self.assertEqual(registration["label"], "Transfer awaiting confirmation")
        self.assertIn("not been verified yet", registration["message"])

    @patch("apps.services.panel_access.Path.read_bytes", return_value=b"test-sso-secret")
    def test_file_manager_ticket_targets_an_active_subdomain_website(self, key):
        website = HostingWebsite.objects.create(
            hosting_account=self.account,
            domain_name="blog.example.co.zw",
            master_domain=self.domain.domain_name,
            document_root="/home/example.co.zw/public_html/blog",
            status=HostingWebsite.Status.ACTIVE,
        )
        with override_settings(CYBERPANEL_API_URL="https://panel.example.com"):
            response = self.client.post(
                f"/api/v1/services/hosting-accounts/{self.account.pk}/file-manager/",
                {"website_domain": website.domain_name},
                format="json",
            )
        self.assertEqual(response.status_code, 200)
        ticket_data = response.data["ticket"].split(".")[0]
        ticket_payload = json.loads(
            base64.urlsafe_b64decode(ticket_data + "=" * (-len(ticket_data) % 4))
        )
        self.assertEqual(ticket_payload["domain"], self.domain.domain_name)
        self.assertEqual(ticket_payload["child_domain"], website.domain_name)
        self.assertEqual(response["Cache-Control"], "no-store")

        response = self.client.post(
            f"/api/v1/services/hosting-accounts/{self.account.pk}/file-manager/",
            {"website_domain": "other.example.co.zw"},
            format="json",
        )
        self.assertEqual(response.status_code, 400)

    def test_customer_can_queue_subdomain_website_once(self):
        path = f"/api/v1/services/hosting-accounts/{self.account.pk}/websites/"
        response = self.client.post(path, {"subdomain": "blog"}, format="json")

        self.assertEqual(response.status_code, 202, response.data)
        website = HostingWebsite.objects.get(domain_name="blog.example.co.zw")
        self.assertEqual(website.master_domain, self.domain.domain_name)
        self.assertEqual(website.status, HostingWebsite.Status.PENDING)
        action = ProvisioningAction.objects.get(
            action_type=ProvisioningAction.ActionType.HOSTING_WEBSITE_CREATE
        )
        self.assertEqual(action.payload, {"hosting_website_id": website.id})

        duplicate = self.client.post(path, {"subdomain": "BLOG"}, format="json")
        self.assertEqual(duplicate.status_code, 202)
        self.assertEqual(ProvisioningAction.objects.count(), 1)

    def test_subdomain_creation_rejects_invalid_labels_and_non_owners(self):
        path = f"/api/v1/services/hosting-accounts/{self.account.pk}/websites/"
        response = self.client.post(path, {"subdomain": "blog.example"}, format="json")
        self.assertEqual(response.status_code, 400)
        response = self.client.post(path, {"subdomain": "mail"}, format="json")
        self.assertEqual(response.status_code, 400)

        self.client.force_authenticate(self.other_customer)
        self.assertEqual(
            self.client.post(path, {"subdomain": "blog"}, format="json").status_code,
            404,
        )

    def test_mailbox_delete_uses_scoped_account_and_maildir_deletion(self):
        with patch(
            "apps.services.providers.cyberpanel.subprocess.run",
            return_value=Mock(returncode=0, stdout='{"ok": true, "message": "None"}\n', stderr=""),
        ) as run:
            result = run_local_mail_operation(
                operation="delete",
                domain="delete.example.co.zw",
                local_part="user",
            )

        self.assertIsNone(result)
        script = run.call_args.args[0][2]
        self.assertIn("EUsers.objects.filter(email=d['email']).delete()", script)
        self.assertIn("django.setup()", script)
        self.assertIn("resolved_domain_root.parent != root", script)
        self.assertIn("resolved_account_path.parent != resolved_domain_root", script)
        self.assertIn("shutil.rmtree(resolved_account_path)", script)
        self.assertEqual(run.call_args.kwargs["cwd"], "/usr/local/CyberCP")
        payload = json.loads(run.call_args.kwargs["input"])
        self.assertEqual(payload["domain"], "delete.example.co.zw")
        self.assertEqual(payload["local_part"], "user")

    def test_subdomain_worker_activates_website_after_panel_confirmation(self):
        self.client.post(
            f"/api/v1/services/hosting-accounts/{self.account.pk}/websites/",
            {"subdomain": "blog"},
            format="json",
        )
        website = HostingWebsite.objects.get(domain_name="blog.example.co.zw")
        action = ProvisioningAction.objects.get(
            action_type=ProvisioningAction.ActionType.HOSTING_WEBSITE_CREATE
        )
        client = Mock()
        client.create_child_website.return_value = {
            "success": True,
            "domain": website.domain_name,
            "document_root": "/home/example.co.zw/public_html/blog",
        }

        process_hosting_website_action(action, client)
        website.refresh_from_db()
        self.assertEqual(website.status, HostingWebsite.Status.ACTIVE)
        self.assertEqual(website.document_root, client.create_child_website.return_value["document_root"])
        client.create_child_website.assert_called_once_with(
            master_domain=self.domain.domain_name,
            child_domain=website.domain_name,
            username=self.account.username,
            plan_expires=None,
        )

    def test_customer_can_queue_and_complete_subdomain_certificate(self):
        website = HostingWebsite.objects.create(
            hosting_account=self.account,
            domain_name="blog.example.co.zw",
            master_domain=self.domain.domain_name,
            document_root="/home/example.co.zw/public_html/blog",
            status=HostingWebsite.Status.ACTIVE,
        )
        path = (
            f"/api/v1/services/hosting-accounts/{self.account.pk}/"
            f"websites/{website.pk}/certificate/"
        )

        response = self.client.post(path, {}, format="json")
        self.assertEqual(response.status_code, 202, response.data)
        self.assertEqual(response.data["certificate_status"], HostingWebsite.CertificateStatus.PENDING)
        action = ProvisioningAction.objects.get(
            action_type=ProvisioningAction.ActionType.HOSTING_WEBSITE_CERTIFICATE
        )

        provider = Mock()
        process_hosting_certificate_action(action, provider)
        website.refresh_from_db()
        self.assertEqual(website.certificate_status, HostingWebsite.CertificateStatus.ACTIVE)
        self.assertEqual(website.certificate_error, "")
        provider.install_child_certificate.assert_called_once_with(
            master_domain=self.domain.domain_name,
            child_domain=website.domain_name,
            username=self.account.username,
            plan_expires=None,
        )

    def test_certificate_request_cannot_target_another_customer_website(self):
        website = HostingWebsite.objects.create(
            hosting_account=self.account,
            domain_name="blog.example.co.zw",
            master_domain=self.domain.domain_name,
            document_root="/home/example.co.zw/public_html/blog",
            status=HostingWebsite.Status.ACTIVE,
        )
        self.client.force_authenticate(self.other_customer)
        path = (
            f"/api/v1/services/hosting-accounts/{self.account.pk}/"
            f"websites/{website.pk}/certificate/"
        )
        self.assertEqual(self.client.post(path, {}, format="json").status_code, 404)

    def test_dashboard_returns_customer_domains_hosting_and_allocations_only(self):
        response = self.client.get("/api/v1/services/dashboard/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data["services"]), 1)
        service = response.data["services"][0]
        self.assertEqual(service["hosting"]["username"], "hostingcustomer")
        self.assertEqual(service["hosting"]["resources"][0]["type"], "disk")
        self.assertEqual(service["domains"][0]["name"], "example.co.zw")
        self.assertEqual(self.client.get("/api/v1/services/domains/").data["count"], 1)

    @patch(
        "apps.services.views.check_domain_availability",
        return_value={"available": True, "status": "available", "method": "whois"},
    )
    def test_domain_search_returns_estimate_and_registry_warning(self, check):
        self.client.force_authenticate(user=None)
        response = self.client.get("/api/v1/services/domains/search/?domain=Example.com")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["domain_name"], "example.com")
        self.assertTrue(response.data["available"])
        self.assertIn("first come", response.data["availability_note"])
        check.assert_called_once_with("example.com")

    def test_domain_search_rejects_unsupported_extensions(self):
        response = self.client.get("/api/v1/services/domains/search/?domain=example.invalid")

        self.assertEqual(response.status_code, 400)
        self.assertIn("domain", response.data)

    @patch("apps.services.views.check_domain_availability")
    def test_domain_already_in_techinn_is_reported_as_taken(self, check):
        response = self.client.get(
            f"/api/v1/services/domains/search/?domain={self.domain.domain_name}"
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.data["available"])
        self.assertEqual(response.data["status"], "taken")
        self.assertEqual(response.data["method"], "techinn")
        check.assert_not_called()

    def test_customer_can_manage_dns_records_and_changes_are_audited_and_queued(self):
        response = self.client.post(
            "/api/v1/services/dns-records/",
            {
                "zone": self.zone.id,
                "name": "www.example.co.zw",
                "record_type": "A",
                "content": "192.0.2.10",
                "ttl": 300,
            },
            format="json",
        )

        self.assertEqual(response.status_code, 201, response.data)
        record = DNSRecord.objects.get()
        action = ProvisioningAction.objects.get()
        self.assertEqual(action.action_type, ProvisioningAction.ActionType.DNS_UPSERT)
        self.assertEqual(action.payload["domain"], "example.co.zw")
        self.assertEqual(ServiceAuditEvent.objects.get().actor, self.customer)

        update = self.client.patch(
            f"/api/v1/services/dns-records/{record.id}/",
            {"content": "192.0.2.11"},
            format="json",
        )
        self.assertEqual(update.status_code, 200)
        self.assertEqual(ProvisioningAction.objects.count(), 2)

    def test_customer_cannot_access_another_customers_dns_zone_or_record(self):
        response = self.client.post(
            "/api/v1/services/dns-records/",
            {
                "zone": self.other_zone.id,
                "name": "www.other.co.zw",
                "record_type": "A",
                "content": "192.0.2.12",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(DNSRecord.objects.count(), 0)

        other_record = DNSRecord.objects.create(
            zone=self.other_zone,
            name="www.other.co.zw",
            record_type=DNSRecord.RecordType.A,
            content="192.0.2.12",
        )
        self.assertEqual(
            self.client.get(f"/api/v1/services/dns-records/{other_record.id}/").status_code,
            404,
        )

    def test_dns_record_names_must_belong_to_the_customer_domain(self):
        response = self.client.post(
            "/api/v1/services/dns-records/",
            {
                "zone": self.zone.id,
                "name": "unrelated.example.net",
                "record_type": "A",
                "content": "192.0.2.13",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertFalse(DNSRecord.objects.exists())

    def test_mailbox_creation_is_owner_scoped_quota_checked_and_queued(self):
        response = self.client.post(
            "/api/v1/services/mailboxes/",
            {
                "hosting_account_id": self.account.id,
                "domain_id": self.domain.id,
                "local_part": "sales",
                "quota_mb": 1024,
                "password": "Strong-password-123!",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 202)
        mailbox = Mailbox.objects.get()
        self.assertEqual(mailbox.email_address, "sales@example.co.zw")
        self.assertEqual(mailbox.status, Mailbox.Status.PENDING)
        self.assertEqual(
            ProvisioningAction.objects.get().action_type,
            ProvisioningAction.ActionType.MAILBOX_CREATE,
        )
        self.assertNotIn("password", response.data)
        action = ProvisioningAction.objects.get()
        self.assertNotIn("Strong-password-123!", str(action.payload))

    def test_mailbox_creation_rejects_foreign_domain_and_plan_limit_overage(self):
        foreign_domain = self.client.post(
            "/api/v1/services/mailboxes/",
            {
                "hosting_account_id": self.account.id,
                "domain_id": self.other_domain.id,
                "local_part": "sales",
                "quota_mb": 1024,
                "password": "Strong-password-123!",
            },
            format="json",
        )
        self.assertEqual(foreign_domain.status_code, 400)

        for address in ("first", "second", "third"):
            Mailbox.objects.create(
                hosting_account=self.account,
                domain=self.domain,
                local_part=address,
                quota_mb=100,
            )
        over_limit = self.client.post(
            "/api/v1/services/mailboxes/",
            {
                "hosting_account_id": self.account.id,
                "domain_id": self.domain.id,
                "local_part": "fourth",
                "quota_mb": 100,
                "password": "Strong-password-123!",
            },
            format="json",
        )
        self.assertEqual(over_limit.status_code, 400)

    def test_mailbox_creation_targets_active_subdomain_but_retains_root_service(self):
        HostingWebsite.objects.create(
            hosting_account=self.account,
            domain_name="shop.example.co.zw",
            master_domain=self.domain.domain_name,
            status=HostingWebsite.Status.ACTIVE,
        )
        response = self.client.post(
            "/api/v1/services/mailboxes/",
            {
                "hosting_account_id": self.account.id,
                "domain_id": self.domain.id,
                "email_domain": "shop.example.co.zw",
                "local_part": "orders",
                "quota_mb": 1024,
                "password": "Strong-password-123!",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 202, response.data)
        mailbox = Mailbox.objects.get()
        self.assertEqual(mailbox.domain_id, self.domain.id)
        self.assertEqual(mailbox.effective_domain, "shop.example.co.zw")
        self.assertEqual(mailbox.email_address, "orders@shop.example.co.zw")

    def test_mailbox_storage_allocation_can_be_increased_or_reduced_above_usage(self):
        mailbox = Mailbox.objects.create(
            hosting_account=self.account,
            domain=self.domain,
            local_part="team",
            quota_mb=512,
            used_mb=100,
            status=Mailbox.Status.ACTIVE,
        )

        increased = self.client.patch(
            f"/api/v1/services/mailboxes/{mailbox.id}/",
            {"quota_mb": 1024},
            format="json",
        )
        self.assertEqual(increased.status_code, 200, increased.data)
        self.assertEqual(increased.data["quota_mb"], 1024)
        blocked = self.client.delete(f"/api/v1/services/mailboxes/{mailbox.id}/")
        self.assertEqual(blocked.status_code, 400)
        blocked = self.client.patch(f"/api/v1/services/mailboxes/{mailbox.id}/", {"quota_mb": 256}, format="json")
        self.assertEqual(blocked.status_code, 400)
        dashboard = self.client.get("/api/v1/services/dashboard/")
        row = next(row for service in dashboard.data["services"] if service["hosting"] for row in service["hosting"]["mailboxes"] if row["id"] == mailbox.id)
        self.assertEqual(row["pending_action"], "mailbox_update")
        ProvisioningAction.objects.filter(payload__mailbox_id=mailbox.id).update(status=ProvisioningAction.Status.COMPLETED)

        reduced = self.client.patch(
            f"/api/v1/services/mailboxes/{mailbox.id}/",
            {"quota_mb": 256},
            format="json",
        )
        self.assertEqual(reduced.status_code, 200, reduced.data)
        self.assertEqual(reduced.data["quota_mb"], 256)
        quota_actions = ProvisioningAction.objects.filter(
            action_type=ProvisioningAction.ActionType.MAILBOX_UPDATE,
        ).order_by("id")
        self.assertEqual(quota_actions.count(), 2)
        self.assertEqual(
            [action.payload["quota_mb"] for action in quota_actions],
            [1024, 256],
        )

        below_current_usage = self.client.patch(
            f"/api/v1/services/mailboxes/{mailbox.id}/",
            {"quota_mb": 99},
            format="json",
        )
        self.assertEqual(below_current_usage.status_code, 400)
        self.assertEqual(quota_actions.count(), 2)
        mailbox.refresh_from_db()
        self.assertEqual(mailbox.quota_mb, 256)

    def test_mailbox_quota_can_be_reduced_when_hosting_disk_is_over_limit(self):
        mailbox = Mailbox.objects.create(
            hosting_account=self.account,
            domain=self.domain,
            local_part="overlimit",
            quota_mb=1024,
            used_mb=128,
            status=Mailbox.Status.ACTIVE,
        )
        disk = self.account.resources.get(resource_type=HostingResource.ResourceType.DISK)
        disk.used_value = Decimal("12")
        disk.save(update_fields=("used_value",))

        reduced = self.client.patch(
            f"/api/v1/services/mailboxes/{mailbox.id}/",
            {"quota_mb": 512},
            format="json",
        )
        self.assertEqual(reduced.status_code, 200, reduced.data)
        self.assertEqual(reduced.data["quota_mb"], 512)

        increased = self.client.patch(
            f"/api/v1/services/mailboxes/{mailbox.id}/",
            {"quota_mb": 1536},
            format="json",
        )
        self.assertEqual(increased.status_code, 400)

    def test_clear_mailbox_storage_requires_confirmation_and_queues_for_owner(self):
        mailbox = Mailbox.objects.create(
            hosting_account=self.account,
            domain=self.domain,
            local_part="clearable",
            quota_mb=512,
            used_mb=75,
            status=Mailbox.Status.ACTIVE,
        )
        path = f"/api/v1/services/mailboxes/{mailbox.id}/clear-storage/"

        unconfirmed = self.client.post(path, {}, format="json")
        self.assertEqual(unconfirmed.status_code, 400)
        mailbox.refresh_from_db()
        self.assertEqual(mailbox.status, Mailbox.Status.ACTIVE)
        self.assertFalse(ProvisioningAction.objects.filter(
            action_type=ProvisioningAction.ActionType.MAILBOX_CLEAR_STORAGE,
        ).exists())

        confirmed = self.client.post(path, {"confirm": True}, format="json")
        self.assertEqual(confirmed.status_code, 202, confirmed.data)
        mailbox.refresh_from_db()
        self.assertEqual(mailbox.status, Mailbox.Status.CLEARING)
        action = ProvisioningAction.objects.get(
            action_type=ProvisioningAction.ActionType.MAILBOX_CLEAR_STORAGE,
        )
        self.assertEqual(action.payload["mailbox_id"], mailbox.id)
        self.assertEqual(self.client.post(path, {"confirm": True}, format="json").status_code, 400)
        self.assertEqual(
            self.client.delete(f"/api/v1/services/mailboxes/{mailbox.id}/").status_code,
            400,
        )

        self.client.force_authenticate(self.other_customer)
        forbidden = self.client.post(path, {"confirm": True}, format="json")
        self.assertEqual(forbidden.status_code, 404)

    def test_mailbox_clear_worker_updates_usage_only_after_verified_success(self):
        mailbox = Mailbox.objects.create(
            hosting_account=self.account,
            domain=self.domain,
            local_part="worker-clear",
            quota_mb=512,
            used_mb=75,
            status=Mailbox.Status.CLEARING,
        )
        action = ProvisioningAction.objects.create(
            customer_service=self.service,
            action_type=ProvisioningAction.ActionType.MAILBOX_CLEAR_STORAGE,
            payload={"mailbox_id": mailbox.id},
        )
        with patch(
            "apps.services.management.commands.process_provisioning.run_local_mail_operation",
            return_value={"ok": True, "used_mb": 0},
        ) as clear_mailbox:
            process_mailbox_action(action)
        clear_mailbox.assert_called_once_with(
            operation="clear_storage",
            domain=mailbox.effective_domain,
            local_part=mailbox.local_part,
        )
        mailbox.refresh_from_db()
        self.assertEqual(mailbox.used_mb, 0)
        self.assertEqual(mailbox.status, Mailbox.Status.ACTIVE)

    def test_mailbox_clear_worker_restores_status_when_cleanup_fails(self):
        mailbox = Mailbox.objects.create(
            hosting_account=self.account,
            domain=self.domain,
            local_part="failed-clear",
            quota_mb=512,
            used_mb=75,
            status=Mailbox.Status.CLEARING,
        )
        action = ProvisioningAction.objects.create(
            customer_service=self.service,
            action_type=ProvisioningAction.ActionType.MAILBOX_CLEAR_STORAGE,
            payload={"mailbox_id": mailbox.id},
        )
        with patch(
            "apps.services.management.commands.process_provisioning.run_local_mail_operation",
            side_effect=CyberPanelError("Cleanup could not be verified."),
        ), self.assertRaises(CyberPanelError):
            process_mailbox_action(action)
        mailbox.refresh_from_db()
        self.assertEqual(mailbox.used_mb, 75)
        self.assertEqual(mailbox.status, Mailbox.Status.ACTIVE)
        self.assertEqual(mailbox.last_error, "Cleanup could not be verified.")

    def test_mailbox_delete_worker_restores_active_status_when_provider_delete_fails(self):
        mailbox = Mailbox.objects.create(
            hosting_account=self.account,
            domain=self.domain,
            local_part="failed-delete",
            quota_mb=512,
            used_mb=0,
            status=Mailbox.Status.DELETING,
        )
        action = ProvisioningAction.objects.create(
            customer_service=self.service,
            action_type=ProvisioningAction.ActionType.MAILBOX_DELETE,
            payload={"mailbox_id": mailbox.id},
        )
        with patch(
            "apps.services.management.commands.process_provisioning.run_local_mail_operation",
            side_effect=CyberPanelError("Mailbox could not be deleted."),
        ), self.assertRaises(CyberPanelError):
            process_mailbox_action(action)

        mailbox.refresh_from_db()
        self.assertEqual(mailbox.status, Mailbox.Status.ACTIVE)
        self.assertEqual(mailbox.last_error, "Mailbox could not be deleted.")

    def test_mailbox_quota_worker_restores_allocation_after_provider_failure(self):
        mailbox = Mailbox.objects.create(
            hosting_account=self.account,
            domain=self.domain,
            local_part="failed-quota",
            quota_mb=768,
            used_mb=0,
            status=Mailbox.Status.ACTIVE,
        )
        action = ProvisioningAction.objects.create(
            customer_service=self.service,
            action_type=ProvisioningAction.ActionType.MAILBOX_UPDATE,
            payload={
                "mailbox_id": mailbox.id,
                "previous_quota_mb": 512,
                "quota_mb": 768,
            },
        )
        with patch(
            "apps.services.management.commands.process_provisioning.run_local_mail_quota_operation",
            side_effect=(CyberPanelError("Quota could not be updated."), None),
        ), patch("apps.services.management.commands.process_provisioning.set_shared_hosting_disk_quota"), self.assertRaises(CyberPanelError):
            process_mailbox_action(action)

        mailbox.refresh_from_db()
        self.assertEqual(mailbox.quota_mb, 512)
        self.assertEqual(mailbox.last_error, "Quota could not be updated.")

    def test_mailbox_import_reconciles_existing_server_mailbox_and_clears_stale_error(self):
        mailbox = Mailbox.objects.create(
            hosting_account=self.account,
            domain=self.domain,
            local_part="reconciled",
            quota_mb=512,
            used_mb=0,
            status=Mailbox.Status.ERROR,
            last_error="This mailbox already exists.",
        )
        with (
            patch(
                "apps.services.management.commands.sync_cyberpanel_services.run_local_mail_quota_operation",
            ),
            patch(
                "apps.services.management.commands.sync_cyberpanel_services.set_shared_hosting_disk_quota",
            ),
        ):
            sync_mailboxes(
                self.account,
                self.domain,
                [{"email": mailbox.email_address, "used_mb": 1}],
                email_limit=3,
            )

        mailbox.refresh_from_db()
        self.assertEqual(mailbox.status, Mailbox.Status.ACTIVE)
        self.assertEqual(mailbox.used_mb, 1)
        self.assertEqual(mailbox.last_error, "")

    def test_shared_storage_budget_reserves_mail_quota_from_website_quota(self):
        Mailbox.objects.create(
            hosting_account=self.account,
            domain=self.domain,
            local_part="storage",
            quota_mb=3 * 1024,
            used_mb=512,
            status=Mailbox.Status.ACTIVE,
        )
        budget = mailbox_storage_budget(self.account)
        self.assertEqual(budget["limit_mb"], 10 * 1024)
        self.assertEqual(budget["web_used_mb"], 2 * 1024)
        self.assertEqual(budget["allocated_mb"], 3 * 1024)
        self.assertEqual(budget["available_mb"], 5 * 1024)

        self.account.linux_username = "siteowner"
        with patch("apps.services.storage.set_linux_user_disk_quota") as apply_quota:
            set_shared_hosting_disk_quota(self.account)
        apply_quota.assert_called_once_with("siteowner", 7 * 1024)

    def test_linux_user_quota_accepts_enabled_quotaon_status(self):
        with (
            patch("apps.services.providers.cyberpanel.pwd.getpwnam"),
            patch(
                "apps.services.providers.cyberpanel.shutil.which",
                side_effect=("/usr/sbin/quotaon", "/usr/sbin/setquota"),
            ),
            patch("apps.services.providers.cyberpanel.os.geteuid", return_value=0),
            patch(
                "apps.services.providers.cyberpanel.subprocess.run",
                side_effect=(
                    Mock(returncode=1, stdout="user quota on / (/dev/sda1) is on\n", stderr=""),
                    Mock(returncode=0, stdout="", stderr=""),
                ),
            ) as run,
        ):
            set_linux_user_disk_quota("siteowner", 512)

        self.assertEqual(
            run.call_args_list[1].args[0],
            ["/usr/sbin/setquota", "-u", "siteowner", "512M", "512M", "0", "0", "/"],
        )

    def test_mailbox_quota_writer_uses_cyberpanel_environment(self):
        with (
            patch(
                "apps.services.providers.cyberpanel.shutil.which",
                return_value="/usr/bin/doveadm",
            ),
            patch(
                "apps.services.providers.cyberpanel.subprocess.run",
                side_effect=(
                    Mock(returncode=0, stdout='{"ok": true}\n', stderr=""),
                    Mock(returncode=0, stdout="", stderr=""),
                ),
            ) as run,
        ):
            run_local_mail_quota_operation(
                operation="set",
                domain="quota-test.example.co.zw",
                local_part="probe",
                quota_mb=100,
            )

        self.assertEqual(run.call_args_list[0].kwargs["cwd"], "/usr/local/CyberCP")
        self.assertIn("VARCHAR(320)", run.call_args_list[0].args[0][2])
        self.assertEqual(
            run.call_args_list[1].args[0],
            ["/usr/bin/doveadm", "quota", "recalc", "-u", "probe@quota-test.example.co.zw"],
        )

    def test_mailbox_clear_expunge_is_scoped_and_verifies_zero_usage(self):
        quota_output = "Quota name\tType\tValue\tLimit\t%\nUser quota\tSTORAGE\t0\t2097152\t0\n"
        with (
            patch("apps.services.providers.cyberpanel.shutil.which", return_value="/usr/bin/doveadm"),
            patch(
                "apps.services.providers.cyberpanel.subprocess.run",
                side_effect=(
                    Mock(returncode=0, stdout="INBOX\nINBOX.Deleted Items\nINBOX.Archive\n", stderr=""),
                    Mock(returncode=0, stdout="", stderr=""),
                    Mock(returncode=0, stdout="", stderr=""),
                    Mock(returncode=0, stdout="", stderr=""),
                    Mock(returncode=0, stdout="", stderr=""),
                    Mock(returncode=0, stdout=quota_output, stderr=""),
                    Mock(returncode=0, stdout='{"updated": 1}\n', stderr=""),
                ),
            ) as run,
        ):
            result = run_local_mail_operation(
                operation="clear_storage",
                domain="clear.example.co.zw",
                local_part="user",
            )

        self.assertEqual(result, {"ok": True, "used_mb": 0})
        self.assertEqual(
            [call.args[0] for call in run.call_args_list[:-1]],
            [
                ["/usr/bin/doveadm", "mailbox", "list", "-u", "user@clear.example.co.zw"],
                ["/usr/bin/doveadm", "expunge", "-u", "user@clear.example.co.zw", "mailbox", "INBOX", "ALL"],
                ["/usr/bin/doveadm", "expunge", "-u", "user@clear.example.co.zw", "mailbox", "INBOX.Deleted Items", "ALL"],
                ["/usr/bin/doveadm", "expunge", "-u", "user@clear.example.co.zw", "mailbox", "INBOX.Archive", "ALL"],
                ["/usr/bin/doveadm", "quota", "recalc", "-u", "user@clear.example.co.zw"],
                ["/usr/bin/doveadm", "-f", "tab", "quota", "get", "-u", "user@clear.example.co.zw"],
            ],
        )
        self.assertEqual(
            run.call_args_list[-1].args[0][:2],
            ["/usr/local/CyberCP/bin/python", "-c"],
        )
        self.assertEqual(run.call_args_list[-1].kwargs["cwd"], "/usr/local/CyberCP")
        self.assertIn(
            "EUsers.objects.filter(email=d['email']).update(DiskUsage='0')",
            run.call_args_list[-1].args[0][2],
        )
        self.assertIn("django.setup()", run.call_args_list[-1].args[0][2])

    def test_paid_storage_extension_updates_shared_disk_limit(self):
        self.account.linux_username = "siteowner"
        self.account.save(update_fields=("linux_username",))
        order = Order.objects.create(
            customer=self.customer,
            order_number="TEST-STORAGE-ORDER",
            status=Order.Status.PAID,
            total=Decimal("2.00"),
        )
        order_item = OrderItem.objects.create(
            order=order,
            addon=Addon.objects.get(slug="web-storage-5gb"),
            description="Extra 5 GB SSD storage",
            quantity=1,
            unit_price=Decimal("2.00"),
            subtotal=Decimal("2.00"),
            metadata={
                "period_months": 1,
                "customer_service_uuid": str(self.service.uuid),
            },
        )
        addon = HostingStorageAddon.objects.create(
            customer_service=self.service,
            order_item=order_item,
            storage_gb=5,
        )
        action = ProvisioningAction(
            customer_service=self.service,
            action_type=ProvisioningAction.ActionType.HOSTING_STORAGE_UPDATE,
            payload={"hosting_storage_addon_id": addon.id},
        )

        with patch("apps.services.management.commands.process_provisioning.set_shared_hosting_disk_quota") as apply_quota:
            process_hosting_storage_action(action)

        disk = self.account.resources.get(resource_type=HostingResource.ResourceType.DISK)
        disk.refresh_from_db()
        addon.refresh_from_db()
        self.assertEqual(disk.limit_value, Decimal("15"))
        self.assertEqual(addon.status, HostingStorageAddon.Status.ACTIVE)
        self.assertGreater(addon.expires_at, addon.starts_at)
        apply_quota.assert_called_once_with(self.account, total_limit_gb=Decimal("15.000000"))

    def test_storage_extension_waits_for_confirmed_payment(self):
        order = Order.objects.create(
            customer=self.customer,
            order_number="TEST-STORAGE-PENDING",
            status=Order.Status.PROCESSING,
            total=Decimal("2.00"),
        )
        OrderItem.objects.create(
            order=order,
            addon=Addon.objects.get(slug="web-storage-5gb"),
            description="Extra 5 GB SSD storage",
            quantity=1,
            unit_price=Decimal("2.00"),
            subtotal=Decimal("2.00"),
            metadata={
                "period_months": 1,
                "type": "hosting_storage_extension",
                "customer_service_uuid": str(self.service.uuid),
            },
        )
        self.assertEqual(queue_hosting_storage_actions(25), 0)
        self.assertFalse(HostingStorageAddon.objects.exists())
        self.assertFalse(
            ProvisioningAction.objects.filter(
                action_type=ProvisioningAction.ActionType.HOSTING_STORAGE_UPDATE,
            ).exists()
        )

    def test_cloudflare_credentials_are_encrypted_and_never_returned(self):
        token = "CF-test-token-that-should-not-be-plain-text"
        create = self.client.post(
            "/api/v1/services/provider-connections/",
            {
                "provider": ProviderConnection.Provider.CLOUDFLARE,
                "name": "My Cloudflare",
                "credentials": {"api_token": token},
            },
            format="json",
        )
        self.assertEqual(create.status_code, 201)
        self.assertNotIn("credentials", create.data)

        stored = ProviderConnection.objects.get()
        self.assertEqual(stored.credentials, f'{{"api_token": "{token}"}}')
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT credentials FROM services_providerconnection WHERE id = %s",
                [stored.id],
            )
            ciphertext = cursor.fetchone()[0]
        self.assertNotIn(token, ciphertext)

        listing = self.client.get("/api/v1/services/provider-connections/")
        self.assertEqual(listing.status_code, 200)
        self.assertNotIn("credentials", listing.data["results"][0])

    def test_customer_cannot_read_or_revoke_another_customers_provider_connection(self):
        connection_obj = ProviderConnection.objects.create(
            customer=self.other_customer,
            provider=ProviderConnection.Provider.CLOUDFLARE,
            scope=ProviderConnection.Scope.CUSTOMER,
            name="Other Cloudflare",
            credentials='{"api_token":"other-token"}',
        )
        response = self.client.delete(
            f"/api/v1/services/provider-connections/{connection_obj.id}/"
        )
        self.assertEqual(response.status_code, 404)
        connection_obj.refresh_from_db()
        self.assertEqual(connection_obj.status, ProviderConnection.Status.PENDING)

    def test_owner_can_invite_service_members_with_role_defaults(self):
        response = self.client.post(
            f"/api/v1/services/{self.service.uuid}/members/",
            {"email": self.other_customer.email, "role": ServiceMember.Role.ADMIN},
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        member = ServiceMember.objects.get()
        self.assertTrue(member.can_manage_dns)
        self.assertTrue(member.can_manage_email)
        self.assertTrue(member.can_view_billing)
        self.assertEqual(response.data["customer_email"], self.other_customer.email)

    def test_service_member_dns_access_obeys_explicit_permissions(self):
        membership = ServiceMember.objects.create(
            customer_service=self.service,
            customer=self.other_customer,
            role=ServiceMember.Role.CUSTOM,
            can_manage_dns=True,
        )
        self.client.force_authenticate(self.other_customer)
        response = self.client.post(
            "/api/v1/services/dns-records/",
            {
                "zone": self.zone.id,
                "name": "www.example.co.zw",
                "record_type": "A",
                "content": "192.0.2.30",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201, response.data)
        membership.can_manage_dns = False
        membership.save(update_fields=("can_manage_dns",))
        denied = self.client.post(
            "/api/v1/services/dns-records/",
            {
                "zone": self.zone.id,
                "name": "mail.example.co.zw",
                "record_type": "A",
                "content": "192.0.2.31",
            },
            format="json",
        )
        self.assertEqual(denied.status_code, 403)

    def test_mailbox_access_grants_require_an_existing_service_member(self):
        mailbox = Mailbox.objects.create(
            hosting_account=self.account,
            domain=self.domain,
            local_part="admin",
            quota_mb=512,
            status=Mailbox.Status.ACTIVE,
        )
        ServiceMember.objects.create(
            customer_service=self.service,
            customer=self.other_customer,
            role=ServiceMember.Role.TECHNICAL,
            can_manage_email=True,
        )
        response = self.client.post(
            f"/api/v1/services/mailboxes/{mailbox.id}/access/",
            {
                "email": self.other_customer.email,
                "role": "admin",
                "can_manage": True,
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        self.assertTrue(mailbox.access_grants.get().can_manage)

    def test_cloudflare_verification_and_zone_link_are_customer_scoped(self):
        create = self.client.post(
            "/api/v1/services/provider-connections/",
            {
                "provider": ProviderConnection.Provider.CLOUDFLARE,
                "name": "My account",
                "credentials": {"api_token": "test-cloudflare-token"},
            },
            format="json",
        )
        connection_id = create.data["id"]
        with patch.object(CloudflareClient, "verify_token", return_value={"status": "active"}):
            verified = self.client.post(
                f"/api/v1/services/provider-connections/{connection_id}/verify/",
                {},
                format="json",
            )
        self.assertEqual(verified.status_code, 200)
        self.assertEqual(verified.data["status"], ProviderConnection.Status.ACTIVE)

        with patch.object(
            CloudflareClient,
            "get_zone",
            return_value={"id": "zone-123", "name": self.domain.domain_name},
        ):
            linked = self.client.post(
                "/api/v1/services/cloudflare/zones/link/",
                {
                    "domain_id": self.domain.id,
                    "connection_id": connection_id,
                    "cloudflare_zone_id": "zone-123",
                },
                format="json",
            )
        self.assertEqual(linked.status_code, 200)
        self.zone.refresh_from_db()
        self.assertEqual(self.zone.provider_connection_id, connection_id)
        self.assertEqual(self.zone.external_zone_id, "zone-123")
        self.assertEqual(self.zone.status, DNSZone.Status.PENDING)
        self.assertIsNone(self.zone.last_synced_at)

    def test_customer_can_connect_external_cloudflare_domain_to_hosting_service(self):
        from datetime import timedelta
        from django.utils import timezone
        self.service.expires_at = timezone.now() + timedelta(days=30)
        self.service.save()
        self.account.primary_domain = None
        self.account.save()
        connection_obj = ProviderConnection.objects.create(
            customer=self.customer,
            provider=ProviderConnection.Provider.CLOUDFLARE,
            scope=ProviderConnection.Scope.CUSTOMER,
            name="Cloudflare",
            credentials='{"api_token":"test-cloudflare-token"}',
            status=ProviderConnection.Status.ACTIVE,
        )
        with patch.object(
            CloudflareClient,
            "list_zones",
            return_value=[{
                "id": "external-zone",
                "name": "external.example",
                "name_servers": ["ns1.cloudflare.com", "ns2.cloudflare.com"],
            }],
        ):
            response = self.client.post(
                "/api/v1/services/cloudflare/zones/connect/",
                {
                    "service_uuid": str(self.service.uuid),
                    "connection_id": connection_obj.id,
                    "cloudflare_zone_id": "external-zone",
                },
                format="json",
            )

        self.assertEqual(response.status_code, 201, response.data)
        from apps.services.models import DomainConnection
        connection = DomainConnection.objects.get(domain_name="external.example")
        self.assertEqual(connection.customer_service, self.service)
        self.assertEqual(connection.provider_connection, connection_obj)
        self.assertEqual(connection.status, "awaiting_ownership")
        self.assertFalse(DomainAsset.objects.filter(domain_name="external.example").exists())
        self.account.refresh_from_db()
        self.assertIsNone(self.account.primary_domain)

    def test_external_domain_connection_rejects_zones_not_in_verified_cloudflare_account(self):
        connection_obj = ProviderConnection.objects.create(
            customer=self.customer,
            provider=ProviderConnection.Provider.CLOUDFLARE,
            scope=ProviderConnection.Scope.CUSTOMER,
            name="Cloudflare",
            credentials='{"api_token":"test-cloudflare-token"}',
            status=ProviderConnection.Status.ACTIVE,
        )
        with patch.object(CloudflareClient, "list_zones", return_value=[]):
            response = self.client.post(
                "/api/v1/services/cloudflare/zones/connect/",
                {
                    "service_uuid": str(self.service.uuid),
                    "connection_id": connection_obj.id,
                    "cloudflare_zone_id": "not-owned-zone",
                },
                format="json",
            )
        self.assertEqual(response.status_code, 400)
        self.assertFalse(DomainAsset.objects.filter(domain_name="external.example").exists())

    def test_customer_can_change_active_hosting_primary_domain_to_linked_domain(self):
        domain = DomainAsset.objects.create(
            customer_service=self.service,
            domain_name="second.example",
            status=DomainAsset.Status.ACTIVE,
        )
        response = self.client.patch(
            f"/api/v1/services/hosting-accounts/{self.account.id}/primary-domain/",
            {"domain_id": domain.id},
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.account.refresh_from_db()
        self.assertEqual(self.account.primary_domain, domain)
        self.assertEqual(ServiceAuditEvent.objects.get().event_type, "hosting.primary_domain.updated")

    def test_cloudflare_dns_worker_creates_and_tracks_records(self):
        connection_obj = ProviderConnection.objects.create(
            customer=self.customer,
            provider=ProviderConnection.Provider.CLOUDFLARE,
            scope=ProviderConnection.Scope.CUSTOMER,
            name="Cloudflare",
            credentials='{"api_token":"test-cloudflare-token"}',
            status=ProviderConnection.Status.ACTIVE,
        )
        self.zone.provider_connection = connection_obj
        self.zone.external_zone_id = "zone-123"
        self.zone.save()
        record = DNSRecord.objects.create(
            zone=self.zone,
            name="www.example.co.zw",
            record_type=DNSRecord.RecordType.A,
            content="192.0.2.40",
            ttl=300,
        )
        action = ProvisioningAction.objects.create(
            customer_service=self.service,
            action_type=ProvisioningAction.ActionType.DNS_UPSERT,
            payload={"zone_id": self.zone.id, "record_id": record.id},
        )
        client = CloudflareClient()
        with patch.object(client, "create_dns_record", return_value={"id": "record-123"}) as create:
            process_dns_action(action, client)
        record.refresh_from_db()
        self.assertEqual(record.external_record_id, "record-123")
        self.assertIsNotNone(record.synced_at)
        create.assert_called_once()

    def test_cloudflare_dns_listing_reads_every_page(self):
        client = CloudflareClient()
        first_page = [{"id": str(index)} for index in range(100)]
        second_page = [{"id": "record-101"}]
        with patch.object(client, "_request", side_effect=[first_page, second_page]) as request:
            records = client.list_dns_records("test-token", "zone-123")
        self.assertEqual(len(records), 101)
        self.assertEqual(request.call_count, 2)
        self.assertEqual(request.call_args_list[1].kwargs["query"]["page"], 2)

    def test_mailbox_create_uses_structured_helper_and_keeps_password_out_of_argv(self):
        for already_exists in (False, True):
            with self.subTest(already_exists=already_exists), patch(
                "apps.services.providers.cyberpanel.subprocess.run",
                return_value=Mock(returncode=0, stdout='1,None\n' + json.dumps({"ok": True, "already_exists": already_exists}), stderr=""),
            ) as run:
                result = run_local_mail_operation(
                    operation="create", domain="example.co.zw", local_part="sales", password="chosen-password",
                )
                self.assertEqual(result["already_exists"], already_exists)
                self.assertEqual(run.call_count, 1)
                self.assertNotIn("chosen-password", str(run.call_args.args))
                self.assertEqual(json.loads(run.call_args.kwargs["input"])["password"], "chosen-password")
                script = run.call_args.args[0][2]
                self.assertNotIn("listEmailsJson", script)
                self.assertIn("bcrypt.checkpw", script)

    def test_delete_returns_json_and_dashboard_tracks_completion(self):
        mailbox = Mailbox.objects.create(hosting_account=self.account, domain=self.domain,
            local_part="delete-response", quota_mb=100, status=Mailbox.Status.ACTIVE)
        response = self.client.delete(f"/api/v1/services/mailboxes/{mailbox.id}/")
        self.assertEqual(response.status_code, 202)
        self.assertEqual(response.json()["status"], "deleting")
        dashboard = self.client.get("/api/v1/services/dashboard/")
        rows = [row for service in dashboard.data["services"] if service["hosting"] for row in service["hosting"]["mailboxes"]]
        self.assertEqual(next(row for row in rows if row["id"] == mailbox.id)["pending_action"], "mailbox_delete")
        mailbox.status = Mailbox.Status.DELETED
        mailbox.save()
        dashboard = self.client.get("/api/v1/services/dashboard/")
        rows = [row for service in dashboard.data["services"] if service["hosting"] for row in service["hosting"]["mailboxes"]]
        self.assertNotIn(mailbox.id, [row["id"] for row in rows])

    def test_deleted_mailbox_stays_deleted_when_quota_cleanup_fails(self):
        mailbox = Mailbox.objects.create(hosting_account=self.account, domain=self.domain,
            local_part="deleted-cleanup", quota_mb=100, status=Mailbox.Status.DELETING)
        action = ProvisioningAction.objects.create(customer_service=self.service,
            action_type=ProvisioningAction.ActionType.MAILBOX_DELETE, payload={"mailbox_id": mailbox.id})
        with patch("apps.services.management.commands.process_provisioning.run_local_mail_operation"), patch(
            "apps.services.management.commands.process_provisioning.run_local_mail_quota_operation",
            side_effect=CyberPanelError("Quota cleanup failed"),
        ), self.assertRaises(CyberPanelError):
            process_mailbox_action(action)
        mailbox.refresh_from_db()
        self.assertEqual(mailbox.status, Mailbox.Status.DELETED)

    def test_unexpected_mailbox_exception_is_reported_instead_of_leaving_pending(self):
        mailbox = Mailbox.objects.create(hosting_account=self.account, domain=self.domain,
            local_part="unexpected-error", quota_mb=100, status=Mailbox.Status.CLEARING)
        action = ProvisioningAction.objects.create(customer_service=self.service,
            action_type=ProvisioningAction.ActionType.MAILBOX_CLEAR_STORAGE, payload={"mailbox_id": mailbox.id})
        with patch("apps.services.management.commands.process_provisioning.run_local_mail_operation",
            side_effect=ValueError("private provider data")), self.assertRaises(CyberPanelError):
            process_mailbox_action(action)
        mailbox.refresh_from_db()
        self.assertEqual(mailbox.status, Mailbox.Status.ACTIVE)
        self.assertIn("unexpectedly", mailbox.last_error)
        self.assertNotIn("private provider data", mailbox.last_error)
