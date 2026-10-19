from django.conf import settings
from apps.notifications.emailing import send_mail
from django.core.management.base import BaseCommand
from django.utils import timezone
from decimal import Decimal

from apps.orders.models import OrderItem
from apps.services.models import CustomerService, DomainAsset, HostingAccount, HostingResource, Mailbox, ProviderConnection
from apps.services.periods import extend_service_period
from apps.services.customer_services import sync_paid_services
from apps.services.providers.cyberpanel import (
    CyberPanelClient,
    CyberPanelError,
    generate_owner_password,
    run_local_mail_operation,
)
from apps.services.storage import set_shared_hosting_disk_quota
from apps.services.site_defaults import install_coming_soon_page
from apps.services.website_suspension import restore_websites


EMAIL_PLAN_LIMITS = {
    "email-essential": Decimal("21"),
    "email-team": Decimal("50"),
    "email-business-mail": Decimal("1000"),
}
EMAIL_PLAN_STORAGE_GB = {
    "email-essential": Decimal("2"),
    "email-team": Decimal("5"),
    "email-business-mail": Decimal("15"),
}


def reactivate_email_mailboxes(service):
    suspended = list(service.hosting_account.mailboxes.filter(status=Mailbox.Status.SUSPENDED))
    if not suspended:
        return
    credentials = []
    for mailbox in suspended:
        password = generate_owner_password()
        run_local_mail_operation(
            operation="change_password",
            domain=mailbox.effective_domain,
            local_part=mailbox.local_part,
            password=password,
        )
        credentials.append((mailbox.email_address, mailbox.effective_domain, password))
    message = ["Your paid email service has been reactivated.", ""]
    for email_address, domain_name, password in credentials:
        message.extend((f"Email: {email_address}", f"Webmail: https://{domain_name}/webmail", f"Temporary password: {password}", ""))
    message.append("Please change each temporary password after signing in.")
    try:
        sent = send_mail(
            "Your TechInn email service is active again",
            "\n".join(message),
            settings.DEFAULT_FROM_EMAIL,
            [service.customer.email],
            fail_silently=False,
        )
    except Exception as error:
        raise CyberPanelError("Email service was renewed, but the new mailbox passwords could not be delivered.") from error
    if not sent:
        raise CyberPanelError("Email service was renewed, but the new mailbox passwords could not be delivered.")
    service.hosting_account.mailboxes.filter(status=Mailbox.Status.SUSPENDED).update(status=Mailbox.Status.ACTIVE)


class Command(BaseCommand):
    help = "Provision paid web-hosting orders for a customer's already-active domain."

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=25)

    def handle(self, *args, **options):
        connection = ProviderConnection.objects.filter(
            provider=ProviderConnection.Provider.CYBERPANEL,
            scope=ProviderConnection.Scope.GLOBAL,
            customer__isnull=True,
            status=ProviderConnection.Status.ACTIVE,
        ).first()
        if connection is None:
            self.stdout.write("CyberPanel hosting orders waiting: no active provider connection.")
            return
        items = OrderItem.objects.filter(
            order__status__in=("paid", "processing", "completed"),
            product__service_type__slug__in=("web-hosting", "email-hosting"),
        ).select_related("order__customer", "product").prefetch_related("customer_services").order_by("created_at")
        completed = waiting = failed = 0
        client = CyberPanelClient(connection)
        for item in items.iterator(chunk_size=50):
            if completed + waiting + failed >= options["limit"]:
                break
            order = item.order
            # Keep provisioning idempotent even if a payment callback was
            # delayed or interrupted after marking the order paid.
            sync_paid_services(order)
            item = OrderItem.objects.select_related("order__customer", "product").prefetch_related("customer_services").get(pk=item.pk)
            pending_service = item.customer_services.filter(status__in=(CustomerService.Status.PENDING, CustomerService.Status.PROVISIONING, CustomerService.Status.FAILED)).first()
            if not pending_service:
                continue
            # Never infer a domain from checkout text. The customer must select
            # the exact active domain for each hosting/email service in the
            # dashboard, which also supports different domains per service.
            selected_domain_id = (pending_service.provisioning_data or {}).get("selected_domain_id") if pending_service else None
            domain = DomainAsset.objects.filter(
                id=selected_domain_id,
                status__in=(DomainAsset.Status.ACTIVE, DomainAsset.Status.PENDING, DomainAsset.Status.TRANSFER_PENDING),
                customer_service__customer=order.customer,
            ).select_related("customer_service").first() if selected_domain_id else None
            if not domain:
                waiting += 1
                continue

            if item.product.service_type.slug == "email-hosting":
                panel_account = HostingAccount.objects.filter(
                    primary_domain=domain,
                    customer_service__customer=order.customer,
                    status=HostingAccount.Status.ACTIVE,
                ).first()
                if not panel_account:
                    waiting += 1
                    continue
                existing_service = CustomerService.objects.filter(
                    customer=order.customer,
                    product=item.product,
                    hosting_account__primary_domain=domain,
                ).select_related("hosting_account").order_by("-created_at").first()
                if existing_service:
                    was_inactive = (
                        existing_service.status != CustomerService.Status.ACTIVE
                        or existing_service.hosting_account.status != HostingAccount.Status.ACTIVE
                    )
                    extend_service_period(existing_service, item)
                    if was_inactive:
                        reactivate_email_mailboxes(existing_service)
                    existing_service.status = CustomerService.Status.ACTIVE
                    existing_service.hosting_account.status = HostingAccount.Status.ACTIVE
                    existing_service.hosting_account.save(update_fields=("status", "updated_at"))
                    existing_service.save(update_fields=("status", "updated_at"))
                    completed += 1
                    continue
                started_at = timezone.now()
                service = pending_service or CustomerService.objects.create(
                    customer=order.customer, product=item.product, order_item=item,
                    status=CustomerService.Status.ACTIVE, started_at=started_at,
                    provisioning_data={"cyberpanel": {"status": "active", "domain": domain.domain_name, "mail_only": True}},
                )
                service.status = CustomerService.Status.ACTIVE
                service.started_at = service.started_at or started_at
                service.provisioning_data = {**(service.provisioning_data or {}), "cyberpanel": {"status": "active", "domain": domain.domain_name, "mail_only": True}}
                service.save(update_fields=("status", "started_at", "provisioning_data", "updated_at"))
                extend_service_period(service, item, now=started_at)
                account = HostingAccount.objects.create(
                    customer_service=service,
                    server_name="CyberPanel",
                    external_account_id=domain.domain_name,
                    username=panel_account.username,
                    primary_domain=domain,
                    status=HostingAccount.Status.ACTIVE,
                )
                mailbox_count = Mailbox.objects.filter(domain=domain).update(hosting_account=account)
                HostingResource.objects.create(
                    hosting_account=account,
                    resource_type=HostingResource.ResourceType.EMAIL_ACCOUNTS,
                    limit_value=EMAIL_PLAN_LIMITS.get(item.product.slug, Decimal("21")),
                    used_value=Decimal(mailbox_count),
                    unit="mailboxes",
                    measured_at=timezone.now(),
                )
                HostingResource.objects.create(
                    hosting_account=account,
                    resource_type=HostingResource.ResourceType.DISK,
                    limit_value=EMAIL_PLAN_STORAGE_GB.get(item.product.slug, Decimal("2")),
                    used_value=Decimal("0"),
                    unit="GB",
                    measured_at=timezone.now(),
                )
                completed += 1
                continue

            package_setting = {
                "web-basic": ("CYBERPANEL_PACKAGE_WEB_BASIC", 2),
                "web-growth": ("CYBERPANEL_PACKAGE_WEB_GROWTH", 10),
                "web-business": ("CYBERPANEL_PACKAGE_WEB_BUSINESS", 25),
            }.get(item.product.slug)
            existing_service = CustomerService.objects.filter(
                pk=pending_service.pk,
                hosting_account__status=HostingAccount.Status.ACTIVE,
                hosting_account__username__gt="",
            ).select_related("hosting_account").first()
            if existing_service:
                domain_ready = domain.status == DomainAsset.Status.ACTIVE
                was_inactive = existing_service.hosting_account.status == HostingAccount.Status.SUSPENDED
                extend_service_period(existing_service, item)
                try:
                    if was_inactive:
                        client.set_website_status(domain=domain.domain_name, state="Un-Suspend")
                        restore_websites(existing_service)
                except CyberPanelError as error:
                    failed += 1
                    self.stderr.write(self.style.WARNING(f"{domain.domain_name}: {error}"))
                    continue
                existing_service.status = CustomerService.Status.ACTIVE if domain_ready else CustomerService.Status.PROVISIONING
                existing_service.hosting_account.status = HostingAccount.Status.ACTIVE
                existing_service.hosting_account.save(update_fields=("status", "updated_at"))
                existing_service.save(update_fields=("status", "updated_at"))
                completed += 1
                continue
            package = getattr(settings, package_setting[0], "") if package_setting else ""
            if not package:
                waiting += 1
                continue

            started_at = timezone.now()
            service = pending_service or CustomerService.objects.create(
                customer=order.customer, product=item.product, order_item=item,
                status=CustomerService.Status.PROVISIONING, started_at=started_at,
                provisioning_data={"cyberpanel": {"status": "provisioning", "domain": domain.domain_name}},
            )
            service.status = CustomerService.Status.PROVISIONING
            service.started_at = service.started_at or started_at
            service.provisioning_data = {**(service.provisioning_data or {}), "cyberpanel": {"status": "provisioning", "domain": domain.domain_name}}
            service.save(update_fields=("status", "started_at", "provisioning_data", "updated_at"))
            extend_service_period(service, item, now=started_at)
            account, _ = HostingAccount.objects.get_or_create(
                customer_service=service,
                defaults={"primary_domain": domain, "external_account_id": domain.domain_name,
                          "status": HostingAccount.Status.PENDING},
            )
            password = generate_owner_password()
            try:
                result = client.create_website(
                    domain=domain.domain_name,
                    email=order.customer.email,
                    owner_password=password,
                    package=package,
                )
                username = result.get("websiteOwner", "")
                # Access is issued through dashboard SSO. Notification retries
                # must never turn a successfully created site into a failure.
                account.username = username
                account.linux_username = result.get("linux_username", "")
                account.status = HostingAccount.Status.ACTIVE
                account.save(update_fields=("username", "linux_username", "status", "updated_at"))
                install_coming_soon_page(domain.domain_name, account.linux_username)
                HostingResource.objects.update_or_create(
                    hosting_account=account,
                    resource_type=HostingResource.ResourceType.DISK,
                    defaults={
                        "limit_value": Decimal(package_setting[1]),
                        "used_value": Decimal("0"),
                        "unit": "GB",
                        "measured_at": timezone.now(),
                    },
                )
                set_shared_hosting_disk_quota(account)
                HostingResource.objects.update_or_create(
                    hosting_account=account,
                    resource_type=HostingResource.ResourceType.EMAIL_ACCOUNTS,
                    defaults={
                        "limit_value": Decimal("1000"),
                        "used_value": Decimal("0"),
                        "unit": "mailboxes",
                        "measured_at": timezone.now(),
                    },
                )
                service.status = CustomerService.Status.ACTIVE if domain.status == DomainAsset.Status.ACTIVE else CustomerService.Status.PROVISIONING
                service.provisioning_data = {
                    **(service.provisioning_data or {}),
                    "cyberpanel": {"status": "active" if domain.status == DomainAsset.Status.ACTIVE else "provisioning", "domain": domain.domain_name, "imported": bool(result.get("already_exists"))},
                }
                service.save(update_fields=("status", "provisioning_data", "updated_at"))
                completed += 1
            except CyberPanelError as error:
                service.status = CustomerService.Status.FAILED
                service.provisioning_data = {
                    **(service.provisioning_data or {}),
                    "cyberpanel": {"status": "failed", "domain": domain.domain_name, "message": str(error)},
                }
                service.save(update_fields=("status", "provisioning_data", "updated_at"))
                account.status = HostingAccount.Status.ERROR
                account.save(update_fields=("status", "updated_at"))
                failed += 1
        from apps.services.website_preview import ensure_preview
        from apps.services.hosting_dns import prepare_website_dns
        for service in CustomerService.objects.filter(
            product__service_type__slug='web-hosting',
            order_item__isnull=False,
            provisioning_data__has_key='selected_domain_id',
            status__in=('active', 'provisioning'), hosting_account__status='active',
            hosting_account__primary_domain__isnull=False,
        ).select_related('hosting_account__primary_domain'):
            try:
                prepare_website_dns(service.hosting_account)
                ensure_preview(service)
            except Exception as error:
                data = dict(service.provisioning_data or {})
                data['preview_error'] = str(error)[:300]
                service.provisioning_data = data
                service.save(update_fields=('provisioning_data', 'updated_at'))
                self.stderr.write(f'Preview setup delayed for service {service.pk}: {error}')
        self.stdout.write(f"CyberPanel hosting provisioned: {completed}; waiting for a domain or plan package mapping: {waiting}; failed: {failed}.")
