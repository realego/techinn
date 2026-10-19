from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from apps.services.models import (
    CustomerService,
    DomainAsset,
    HostingAccount,
    Mailbox,
    ProviderConnection,
    ServiceAuditEvent,
)
from apps.services.providers.cyberpanel import (
    CyberPanelClient,
    CyberPanelError,
    generate_owner_password,
    run_local_mail_operation,
)
from apps.services.website_suspension import WebsiteSuspensionError, suspend_websites


class Command(BaseCommand):
    help = "Deactivate paid services when their database-stored billing periods expire."

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=100)

    def handle(self, *args, **options):
        limit = options["limit"]
        if limit < 1 or limit > 500:
            self.stderr.write(self.style.ERROR("--limit must be between 1 and 500."))
            return

        now = timezone.now()
        services = CustomerService.objects.filter(
            status=CustomerService.Status.ACTIVE,
            expires_at__isnull=False,
            expires_at__lte=now,
        ).select_related(
            "customer", "product__service_type", "hosting_account__primary_domain"
        ).order_by("expires_at")[:limit]
        connection = ProviderConnection.objects.filter(
            provider=ProviderConnection.Provider.CYBERPANEL,
            scope=ProviderConnection.Scope.GLOBAL,
            customer__isnull=True,
            status=ProviderConnection.Status.ACTIVE,
        ).first()
        client = CyberPanelClient(connection) if connection else None
        completed = failed = 0

        for candidate in services:
            with transaction.atomic():
                try:
                    service = CustomerService.objects.select_for_update().select_related(
                        "customer", "product__service_type", "hosting_account__primary_domain"
                    ).get(pk=candidate.pk, status=CustomerService.Status.ACTIVE, expires_at__lte=now)
                except CustomerService.DoesNotExist:
                    continue

            service_type = service.product.service_type.slug
            try:
                if service_type == "web-hosting":
                    account = getattr(service, "hosting_account", None)
                    domain = getattr(getattr(account, "primary_domain", None), "domain_name", "")
                    if not client or not domain:
                        raise CyberPanelError("CyberPanel or the primary domain is unavailable for suspension.")
                    client.set_website_status(domain=domain, state="Suspend")
                    if account.status != HostingAccount.Status.SUSPENDED:
                        account.status = HostingAccount.Status.SUSPENDED
                        account.save(update_fields=("status", "updated_at"))
                    suspend_websites(service)
                elif service_type == "email-hosting":
                    account = getattr(service, "hosting_account", None)
                    if account:
                        mailboxes = account.mailboxes.filter(status=Mailbox.Status.ACTIVE).order_by("id")
                        for mailbox in mailboxes.iterator(chunk_size=50):
                            run_local_mail_operation(
                                operation="change_password",
                                domain=mailbox.effective_domain,
                                local_part=mailbox.local_part,
                                password=generate_owner_password(),
                            )
                            mailbox.status = Mailbox.Status.SUSPENDED
                            mailbox.save(update_fields=("status", "updated_at"))
                        account.status = HostingAccount.Status.SUSPENDED
                        account.save(update_fields=("status", "updated_at"))
                elif service_type in {"domains", "domain-registration"}:
                    expired_domains = DomainAsset.objects.filter(
                        customer_service=service,
                        expires_at__isnull=False,
                        expires_at__lte=now,
                        status=DomainAsset.Status.ACTIVE,
                    )
                    for domain_asset in expired_domains:
                        zone = getattr(domain_asset, "dns_zone", None)
                        original = list(domain_asset.nameservers or (zone.nameservers if zone else []))
                        if original:
                            domain_asset.suspension_data = {"original_nameservers": original, "suspended_at": now.isoformat()}
                            domain_asset.nameservers = ["ns1.suspended.techinn.co.zw", "ns2.suspended.techinn.co.zw"]
                            domain_asset.status = DomainAsset.Status.EXPIRED
                            domain_asset.save(update_fields=("status", "nameservers", "suspension_data", "updated_at"))
                            if zone:
                                zone.nameservers = domain_asset.nameservers
                                zone.status = zone.Status.ERROR
                                zone.save(update_fields=("nameservers", "status", "updated_at"))
                        else:
                            domain_asset.status = DomainAsset.Status.EXPIRED
                            domain_asset.save(update_fields=("status", "updated_at"))

                service.status = CustomerService.Status.EXPIRED
                data = dict(service.provisioning_data or {})
                data["service_period"] = {"status": "expired", "expired_at": now.isoformat()}
                service.provisioning_data = data
                service.save(update_fields=("status", "provisioning_data", "updated_at"))
                ServiceAuditEvent.objects.create(
                    customer_service=service,
                    event_type="service.expired",
                    entity_type="customer_service",
                    entity_id=str(service.uuid),
                    payload={"service_type": service_type, "expires_at": service.expires_at.isoformat()},
                )
                completed += 1
            except (CyberPanelError, WebsiteSuspensionError) as error:
                failed += 1
                self.stderr.write(self.style.WARNING(f"Service {service.uuid}: {error}"))

        self.stdout.write(f"Expired services deactivated: {completed}; awaiting provider recovery: {failed}.")
