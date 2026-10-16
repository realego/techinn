from django.conf import settings
from django.core.mail import send_mail
from django.core.management.base import BaseCommand
from django.utils import timezone
from decimal import Decimal

from apps.orders.models import OrderItem
from apps.services.models import CustomerService, DomainAsset, HostingAccount, HostingResource, Mailbox, ProviderConnection
from apps.services.periods import extend_service_period
from apps.services.providers.cyberpanel import (
    CyberPanelClient,
    CyberPanelError,
    generate_owner_password,
    run_local_mail_operation,
)
from apps.services.storage import set_shared_hosting_disk_quota


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
            if item.customer_services.exists():
                continue
            order = item.order
            domain_name = str((order.metadata or {}).get("preferred_domain", "")).strip().rstrip(".").lower()
            domain = DomainAsset.objects.filter(
                domain_name__iexact=domain_name,
                status=DomainAsset.Status.ACTIVE,
                customer_service__customer=order.customer,
            ).select_related("customer_service").first() if domain_name else None
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
                service = CustomerService.objects.create(
                    customer=order.customer,
                    product=item.product,
                    order_item=item,
                    status=CustomerService.Status.ACTIVE,
                    started_at=started_at,
                    provisioning_data={"cyberpanel": {"status": "active", "domain": domain.domain_name, "mail_only": True}},
                )
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
                    limit_value=Decimal("1000"),
                    used_value=Decimal(mailbox_count),
                    unit="mailboxes",
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
                try:
                    if was_inactive:
                        client.set_website_status(domain=domain.domain_name, state="Un-Suspend")
                except CyberPanelError as error:
                    failed += 1
                    self.stderr.write(self.style.WARNING(f"{domain.domain_name}: {error}"))
                    continue
                existing_service.status = CustomerService.Status.ACTIVE
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
            service = CustomerService.objects.create(
                customer=order.customer,
                product=item.product,
                order_item=item,
                status=CustomerService.Status.PROVISIONING,
                started_at=started_at,
                provisioning_data={"cyberpanel": {"status": "provisioning", "domain": domain.domain_name}},
            )
            extend_service_period(service, item, now=started_at)
            account = HostingAccount.objects.create(
                customer_service=service,
                primary_domain=domain,
                external_account_id=domain.domain_name,
                status=HostingAccount.Status.PENDING,
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
                if not result.get("already_exists"):
                    try:
                        sent = send_mail(
                            "Your TechInn hosting account is ready",
                            "Your hosting service is active.\n\n"
                            f"Domain: {domain.domain_name}\nCyberPanel: {settings.CYBERPANEL_API_URL}\n"
                            f"Username: {username}\nTemporary password: {password}\n\n"
                            "Please sign in and change the temporary password.",
                            settings.DEFAULT_FROM_EMAIL,
                            [order.customer.email],
                            fail_silently=False,
                        )
                    except Exception as error:
                        raise CyberPanelError("Hosting was created, but the access email could not be sent.") from error
                    if not sent:
                        raise CyberPanelError("Hosting was created, but the access email could not be sent.")
                account.username = username
                account.linux_username = result.get("linux_username", "")
                account.status = HostingAccount.Status.ACTIVE
                account.save(update_fields=("username", "linux_username", "status", "updated_at"))
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
                service.status = CustomerService.Status.ACTIVE
                service.provisioning_data = {
                    **(service.provisioning_data or {}),
                    "cyberpanel": {"status": "active", "domain": domain.domain_name, "imported": bool(result.get("already_exists"))},
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
        self.stdout.write(f"CyberPanel hosting provisioned: {completed}; waiting for an active domain or plan package mapping: {waiting}; failed: {failed}.")
