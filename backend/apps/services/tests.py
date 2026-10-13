from decimal import Decimal
from unittest.mock import Mock, patch

from django.db import connection
from rest_framework.test import APITestCase

from apps.accounts.models import Customer
from apps.catalog.models import Product, ServiceType
from apps.services.models import (
    CustomerService,
    DNSRecord,
    DNSZone,
    DomainAsset,
    HostingAccount,
    HostingResource,
    Mailbox,
    ProviderConnection,
    ProvisioningAction,
    ServiceAuditEvent,
    ServiceMember,
)
from apps.services.management.commands.process_provisioning import process_dns_action
from apps.services.providers.cloudflare import CloudflareClient
from apps.services.providers.cyberpanel import run_local_mail_operation


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

        reduced = self.client.patch(
            f"/api/v1/services/mailboxes/{mailbox.id}/",
            {"quota_mb": 256},
            format="json",
        )
        self.assertEqual(reduced.status_code, 200, reduced.data)
        self.assertEqual(reduced.data["quota_mb"], 256)
        self.assertFalse(ProvisioningAction.objects.exists())

        below_current_usage = self.client.patch(
            f"/api/v1/services/mailboxes/{mailbox.id}/",
            {"quota_mb": 99},
            format="json",
        )
        self.assertEqual(below_current_usage.status_code, 400)
        mailbox.refresh_from_db()
        self.assertEqual(mailbox.quota_mb, 256)

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
        domain = DomainAsset.objects.get(domain_name="external.example")
        self.assertEqual(domain.customer_service, self.service)
        self.assertEqual(domain.nameservers, ["ns1.cloudflare.com", "ns2.cloudflare.com"])
        self.assertEqual(domain.dns_zone.provider_connection, connection_obj)
        self.assertEqual(domain.dns_zone.external_zone_id, "external-zone")
        self.assertEqual(domain.dns_zone.status, DNSZone.Status.PENDING)
        self.assertIsNone(domain.dns_zone.last_synced_at)
        self.account.refresh_from_db()
        self.assertEqual(self.account.primary_domain, self.domain)
        self.assertEqual(ServiceAuditEvent.objects.get().event_type, "domain.cloudflare.connected")

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

    def test_retry_of_mailbox_already_created_sets_the_new_chosen_password(self):
        listed = '[{"email":"sales@example.co.zw"}]'
        with patch(
            "apps.services.providers.cyberpanel.subprocess.run",
            side_effect=[
                Mock(returncode=0, stdout=listed, stderr=""),
                Mock(returncode=0, stdout='{"ok":true,"message":"None"}', stderr=""),
                Mock(returncode=0, stdout=listed, stderr=""),
            ],
        ) as run:
            result = run_local_mail_operation(
                operation="create", domain="example.co.zw", local_part="sales",
                password="A-strong-new-password-123!",
            )
        self.assertTrue(result["already_exists"])
        self.assertEqual(run.call_count, 3)
