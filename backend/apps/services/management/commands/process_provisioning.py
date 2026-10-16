import json
import secrets
import string
from calendar import monthrange
from datetime import timedelta

from django.conf import settings
from django.core.mail import send_mail
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from apps.orders.models import OrderItem
from apps.services.models import (
    CustomerService,
    DNSRecord,
    DNSZone,
    Mailbox,
    HostingAccount,
    HostingWebsite,
    HostingStorageAddon,
    HostingResource,
    ProviderConnection,
    ProvisioningAction,
)
from apps.services.fields import decrypt_secret
from apps.services.providers.cloudflare import CloudflareClient, CloudflareError, cloudflare_credentials
from apps.services.providers.cyberpanel import (
    CyberPanelClient,
    CyberPanelError,
    run_local_mail_operation,
    run_local_mail_quota_operation,
)
from apps.services.storage import set_shared_hosting_disk_quota


DNS_ACTIONS = (
    ProvisioningAction.ActionType.DNS_UPSERT,
    ProvisioningAction.ActionType.DNS_DELETE,
)
MAILBOX_ACTIONS = (
    ProvisioningAction.ActionType.MAILBOX_CREATE,
    ProvisioningAction.ActionType.MAILBOX_UPDATE,
    ProvisioningAction.ActionType.MAILBOX_DELETE,
    ProvisioningAction.ActionType.MAILBOX_PASSWORD_RESET,
    ProvisioningAction.ActionType.MAILBOX_CLEAR_STORAGE,
)
HOSTING_WEBSITE_ACTIONS = (ProvisioningAction.ActionType.HOSTING_WEBSITE_CREATE,)
HOSTING_CERTIFICATE_ACTIONS = (ProvisioningAction.ActionType.HOSTING_WEBSITE_CERTIFICATE,)
HOSTING_STORAGE_ADDON_CAPACITY_GB = {"web-storage-5gb": 5}


def _add_calendar_months(value, months):
    month_index = value.month - 1 + months
    year = value.year + month_index // 12
    month = month_index % 12 + 1
    day = min(value.day, monthrange(year, month)[1])
    return value.replace(year=year, month=month, day=day)


def queue_hosting_storage_actions(limit):
    now = timezone.now()
    order_items = OrderItem.objects.filter(
        order__status__in=("paid", "completed"),
        addon__slug__in=HOSTING_STORAGE_ADDON_CAPACITY_GB,
        metadata__type="hosting_storage_extension",
    ).select_related("order__customer", "addon").order_by("created_at")[:limit]
    for item in order_items:
        service_uuid = (item.metadata or {}).get("customer_service_uuid")
        if not isinstance(service_uuid, str):
            continue
        service = CustomerService.objects.filter(
            uuid=service_uuid,
            customer=item.order.customer,
            product__service_type__slug="web-hosting",
            status=CustomerService.Status.ACTIVE,
            hosting_account__status=HostingAccount.Status.ACTIVE,
        ).select_related("hosting_account").first()
        if not service:
            continue
        addon, _ = HostingStorageAddon.objects.get_or_create(
            order_item=item,
            defaults={
                "customer_service": service,
                "storage_gb": HOSTING_STORAGE_ADDON_CAPACITY_GB[item.addon.slug],
                "status": HostingStorageAddon.Status.PENDING,
            },
        )
        if addon.customer_service_id != service.id or addon.status not in {
            HostingStorageAddon.Status.PENDING,
            HostingStorageAddon.Status.EXPIRING,
        }:
            continue

    due_addons = HostingStorageAddon.objects.filter(
        status=HostingStorageAddon.Status.ACTIVE,
        expires_at__lte=now,
    ).select_related("customer_service")
    for candidate in due_addons:
        with transaction.atomic():
            addon = HostingStorageAddon.objects.select_for_update().get(pk=candidate.pk)
            if addon.status == HostingStorageAddon.Status.ACTIVE and addon.expires_at and addon.expires_at <= now:
                addon.status = HostingStorageAddon.Status.EXPIRING
                addon.save(update_fields=("status", "updated_at"))

    retry_after = now - timedelta(minutes=5)
    addons = HostingStorageAddon.objects.filter(
        status__in=(HostingStorageAddon.Status.PENDING, HostingStorageAddon.Status.EXPIRING)
    ).select_related("customer_service", "order_item__order").order_by("id")[:limit]
    queued = 0
    for candidate in addons:
        if (
            candidate.status == HostingStorageAddon.Status.PENDING
            and (
                candidate.customer_service.status != CustomerService.Status.ACTIVE
                or candidate.customer_service.hosting_account.status != HostingAccount.Status.ACTIVE
                or candidate.order_item.order.status not in ("paid", "completed")
            )
        ):
            continue
        action_exists = ProvisioningAction.objects.filter(
            customer_service=candidate.customer_service,
            action_type=ProvisioningAction.ActionType.HOSTING_STORAGE_UPDATE,
            payload__hosting_storage_addon_id=candidate.id,
            status__in=(ProvisioningAction.Status.PENDING, ProvisioningAction.Status.PROCESSING),
        ).exists()
        if action_exists:
            continue
        recent_failure = ProvisioningAction.objects.filter(
            customer_service=candidate.customer_service,
            action_type=ProvisioningAction.ActionType.HOSTING_STORAGE_UPDATE,
            payload__hosting_storage_addon_id=candidate.id,
            status=ProvisioningAction.Status.FAILED,
            created_at__gte=retry_after,
        ).exists()
        if recent_failure:
            continue
        ProvisioningAction.objects.create(
            customer_service=candidate.customer_service,
            action_type=ProvisioningAction.ActionType.HOSTING_STORAGE_UPDATE,
            payload={"hosting_storage_addon_id": candidate.id},
        )
        queued += 1
    return queued


def process_hosting_storage_action(action):
    try:
        addon = HostingStorageAddon.objects.select_related(
            "customer_service__hosting_account",
            "order_item__order",
        ).get(
            id=action.payload.get("hosting_storage_addon_id"),
            customer_service=action.customer_service,
        )
    except HostingStorageAddon.DoesNotExist as error:
        raise CyberPanelError("The hosting storage extension was not found.") from error

    if addon.status == HostingStorageAddon.Status.ACTIVE:
        return
    service = addon.customer_service
    account = service.hosting_account
    resource = account.resources.filter(resource_type=HostingResource.ResourceType.DISK).first()
    if not resource:
        raise CyberPanelError("This hosting service has no storage allocation to extend.")
    if not account.linux_username:
        raise CyberPanelError("The hosting account's filesystem owner has not been verified.")

    unit = resource.unit.lower()
    if unit in {"gb", "gib"}:
        current_limit_gb = resource.limit_value
        divisor = 1
    elif unit in {"mb", "mib"}:
        current_limit_gb = resource.limit_value / 1024
        divisor = 1024
    else:
        raise CyberPanelError("The hosting storage limit uses an unsupported unit.")

    now = timezone.now()
    if addon.status == HostingStorageAddon.Status.EXPIRING:
        new_limit_gb = max(current_limit_gb - addon.storage_gb, 0)
        set_shared_hosting_disk_quota(account, total_limit_gb=new_limit_gb)
        resource.limit_value = new_limit_gb * divisor
        resource.save(update_fields=("limit_value",))
        addon.status = HostingStorageAddon.Status.EXPIRED
        addon.last_error = ""
        addon.save(update_fields=("status", "last_error", "updated_at"))
        return

    if (
        addon.status != HostingStorageAddon.Status.PENDING
        or addon.order_item.order.status not in ("paid", "completed")
        or service.status != CustomerService.Status.ACTIVE
        or account.status != HostingAccount.Status.ACTIVE
    ):
        raise CyberPanelError("Storage can only be added to an active, paid hosting service.")
    months = (addon.order_item.metadata or {}).get("period_months")
    if months not in (1, 12):
        raise CyberPanelError("The storage extension has an invalid billing period.")
    new_limit_gb = current_limit_gb + addon.storage_gb
    set_shared_hosting_disk_quota(account, total_limit_gb=new_limit_gb)
    resource.limit_value = new_limit_gb * divisor
    resource.save(update_fields=("limit_value",))
    addon.status = HostingStorageAddon.Status.ACTIVE
    addon.starts_at = now
    addon.expires_at = _add_calendar_months(now, months)
    addon.last_error = ""
    addon.save(update_fields=("status", "starts_at", "expires_at", "last_error", "updated_at"))


def sync_mailbox_count(mailbox):
    resource = HostingResource.objects.filter(
        hosting_account=mailbox.hosting_account,
        resource_type=HostingResource.ResourceType.EMAIL_ACCOUNTS,
    ).first()
    if resource:
        resource.used_value = Mailbox.objects.filter(
            hosting_account=mailbox.hosting_account
        ).exclude(status__in=(Mailbox.Status.DELETED, Mailbox.Status.DELETING)).count()
        resource.measured_at = timezone.now()
        resource.save(update_fields=("used_value", "measured_at"))


def process_mailbox_action(action):
    mailbox_id = action.payload.get("mailbox_id")
    if not mailbox_id:
        raise CyberPanelError("The mailbox for this action was not found.")
    try:
        mailbox = Mailbox.objects.select_related(
            "domain", "hosting_account__customer_service__customer"
        ).get(
            id=mailbox_id,
            hosting_account__customer_service=action.customer_service,
        )
    except Mailbox.DoesNotExist:
        action.status = ProvisioningAction.Status.CANCELLED
        action.completed_at = timezone.now()
        action.save(update_fields=("status", "completed_at"))
        return
    email = mailbox.email_address.lower()
    try:
        if action.action_type == ProvisioningAction.ActionType.MAILBOX_CREATE:
            service = mailbox.hosting_account.customer_service
            if service.status != "active" or (service.expires_at and service.expires_at <= timezone.now()):
                mailbox.status = Mailbox.Status.DELETED
                mailbox.save(update_fields=("status", "updated_at"))
                sync_mailbox_count(mailbox)
                action.status = ProvisioningAction.Status.CANCELLED
                action.completed_at = timezone.now()
                action.save(update_fields=("status", "completed_at"))
                return
            if mailbox.status == Mailbox.Status.DELETED:
                action.status = ProvisioningAction.Status.CANCELLED
                action.completed_at = timezone.now()
                action.save(update_fields=("status", "completed_at"))
                return
            if mailbox.effective_domain != mailbox.domain.domain_name and not HostingWebsite.objects.filter(
                domain_name=mailbox.effective_domain,
                master_domain=mailbox.domain.domain_name,
                status=HostingWebsite.Status.ACTIVE,
                hosting_account__status=HostingAccount.Status.ACTIVE,
                hosting_account__customer_service__status="active",
                hosting_account__customer_service__customer=service.customer,
            ).exists():
                raise CyberPanelError("The selected subdomain website is no longer active.")
            password = decrypt_secret(action.payload.get("password_encrypted"))
            if len(password) < 8:
                raise CyberPanelError("The mailbox password was not available; request mailbox creation again.")
            run_local_mail_operation(
                operation="create", domain=mailbox.effective_domain,
                local_part=mailbox.local_part, password=password,
            )
            run_local_mail_quota_operation(
                operation="set",
                domain=mailbox.effective_domain,
                local_part=mailbox.local_part,
                quota_mb=mailbox.quota_mb,
            )
            set_shared_hosting_disk_quota(mailbox.hosting_account)
            send_mail(
                "Your TechInn email mailbox is ready",
                f"Your mailbox is ready.\n\nEmail address: {email}\n"
                f"Webmail: {settings.TECHINN_WEBMAIL_URL}\n"
                "Sign in with the password you chose when creating this mailbox.",
                settings.DEFAULT_FROM_EMAIL,
                [mailbox.hosting_account.customer_service.customer.email],
                fail_silently=True,
            )
            mailbox.status = Mailbox.Status.ACTIVE
            mailbox.last_error = ""
            mailbox.external_mailbox_id = email
            mailbox.save(update_fields=("status", "last_error", "external_mailbox_id", "updated_at"))
            action.payload = {key: value for key, value in action.payload.items() if key != "password_encrypted"}
            action.save(update_fields=("payload",))
            sync_mailbox_count(mailbox)
        elif action.action_type == ProvisioningAction.ActionType.MAILBOX_UPDATE:
            if mailbox.status != Mailbox.Status.ACTIVE:
                raise CyberPanelError("Only an active mailbox allocation can be changed.")
            run_local_mail_quota_operation(
                operation="set",
                domain=mailbox.effective_domain,
                local_part=mailbox.local_part,
                quota_mb=action.payload["quota_mb"],
            )
            set_shared_hosting_disk_quota(mailbox.hosting_account)
            mailbox.last_error = ""
            mailbox.save(update_fields=("last_error", "updated_at"))
        elif action.action_type == ProvisioningAction.ActionType.MAILBOX_PASSWORD_RESET:
            service = mailbox.hosting_account.customer_service
            if mailbox.status != Mailbox.Status.ACTIVE or service.status != "active" or (
                service.expires_at and service.expires_at <= timezone.now()
            ):
                raise CyberPanelError("Only an active mailbox password can be reset.")
            alphabet = string.ascii_letters + string.digits + "!@#$%_-"
            password = "".join(secrets.choice(alphabet) for _ in range(24))
            run_local_mail_operation(
                operation="change_password", domain=mailbox.effective_domain,
                local_part=mailbox.local_part, password=password,
            )
            try:
                send_mail(
                    "Your TechInn email password was reset",
                    f"A new temporary password was created for {email}.\n\n"
                    f"Webmail: {settings.TECHINN_WEBMAIL_URL}\n"
                    f"Temporary password: {password}\n\nPlease change it after signing in.",
                    settings.DEFAULT_FROM_EMAIL,
                    [mailbox.hosting_account.customer_service.customer.email],
                    fail_silently=False,
                )
            except Exception as error:
                raise CyberPanelError("Password changed, but the access email could not be delivered.") from error
        elif action.action_type == ProvisioningAction.ActionType.MAILBOX_CLEAR_STORAGE:
            service = mailbox.hosting_account.customer_service
            if mailbox.status != Mailbox.Status.CLEARING or service.status != "active" or (
                service.expires_at and service.expires_at <= timezone.now()
            ):
                raise CyberPanelError("Only an active mailbox can have its stored messages cleared.")
            result = run_local_mail_operation(
                operation="clear_storage",
                domain=mailbox.effective_domain,
                local_part=mailbox.local_part,
            )
            if not result.get("ok") or result.get("used_mb") != 0:
                raise CyberPanelError("Mailbox storage cleanup could not be verified.")
            mailbox.used_mb = 0
            mailbox.status = Mailbox.Status.ACTIVE
            mailbox.last_error = ""
            mailbox.save(update_fields=("used_mb", "status", "last_error", "updated_at"))
        else:
            run_local_mail_operation(
                operation="delete", domain=mailbox.effective_domain,
                local_part=mailbox.local_part,
            )
            # The account is gone. Subsequent quota cleanup failures must not
            # make a deleted mailbox appear active again in the dashboard.
            mailbox.status = Mailbox.Status.DELETED
            mailbox.last_error = ""
            mailbox.save(update_fields=("status", "last_error", "updated_at"))
            sync_mailbox_count(mailbox)
            run_local_mail_quota_operation(
                operation="delete", domain=mailbox.effective_domain,
                local_part=mailbox.local_part,
            )
            set_shared_hosting_disk_quota(mailbox.hosting_account)
    except Exception as error:
        if not isinstance(error, CyberPanelError):
            error = CyberPanelError("Mailbox processing stopped unexpectedly. Please retry the operation.")
        mailbox.last_error = str(error)
        if action.action_type == ProvisioningAction.ActionType.MAILBOX_CREATE:
            mailbox.status = Mailbox.Status.ERROR
            mailbox.save(update_fields=("status", "last_error", "updated_at"))
        elif action.action_type == ProvisioningAction.ActionType.MAILBOX_CLEAR_STORAGE:
            if mailbox.status == Mailbox.Status.CLEARING:
                mailbox.status = Mailbox.Status.ACTIVE
            mailbox.save(update_fields=("status", "last_error", "updated_at"))
        elif action.action_type == ProvisioningAction.ActionType.MAILBOX_DELETE:
            if mailbox.status != Mailbox.Status.DELETED:
                mailbox.status = Mailbox.Status.ACTIVE
            mailbox.save(update_fields=("status", "last_error", "updated_at"))
        elif action.action_type == ProvisioningAction.ActionType.MAILBOX_UPDATE:
            previous_quota_mb = action.payload.get("previous_quota_mb")
            requested_quota_mb = action.payload.get("quota_mb")
            if (
                previous_quota_mb is not None
                and requested_quota_mb is not None
                and mailbox.quota_mb == requested_quota_mb
            ):
                try:
                    run_local_mail_quota_operation(
                        operation="set",
                        domain=mailbox.effective_domain,
                        local_part=mailbox.local_part,
                        quota_mb=previous_quota_mb,
                    )
                except CyberPanelError as restore_error:
                    mailbox.last_error = (
                        f"{error} Previous mailbox storage could not be restored: {restore_error}"
                    )
                    mailbox.save(update_fields=("last_error", "updated_at"))
                else:
                    mailbox.quota_mb = previous_quota_mb
                    mailbox.save(update_fields=("quota_mb", "last_error", "updated_at"))
                    try:
                        set_shared_hosting_disk_quota(mailbox.hosting_account)
                    except CyberPanelError as restore_error:
                        mailbox.last_error = f"{error} Website storage restoration needs attention: {restore_error}"
                        mailbox.save(update_fields=("last_error", "updated_at"))
            else:
                mailbox.save(update_fields=("last_error", "updated_at"))
        else:
            mailbox.save(update_fields=("last_error", "updated_at"))
        raise error


def cloudflare_token(connection):
    try:
        credentials = json.loads(connection.credentials)
        token = cloudflare_credentials(credentials)
    except (json.JSONDecodeError, KeyError, TypeError, CloudflareError) as error:
        raise CloudflareError("The Cloudflare connection has invalid stored credentials.") from error
    return token


def process_hosting_website_action(action, client):
    try:
        website = HostingWebsite.objects.select_related(
            "hosting_account__primary_domain",
            "hosting_account__customer_service",
        ).get(
            id=action.payload.get("hosting_website_id"),
            hosting_account__customer_service=action.customer_service,
        )
    except HostingWebsite.DoesNotExist as error:
        raise CyberPanelError("The subdomain website request was not found.") from error

    account = website.hosting_account
    service = account.customer_service
    expiry = service.expires_at or service.next_due_at
    if (
        website.status != HostingWebsite.Status.PENDING
        or service.status != "active"
        or account.status != "active"
        or (expiry and expiry <= timezone.now())
        or not account.primary_domain
        or not account.username
    ):
        raise CyberPanelError("Subdomain setup requires an active hosting account.")

    result = client.create_child_website(
        master_domain=website.master_domain,
        child_domain=website.domain_name,
        username=account.username,
        plan_expires=expiry.timestamp() if expiry else None,
    )
    expected_root = f"/home/{website.master_domain}/public_html/"
    document_root = result["document_root"]
    if not document_root.startswith(expected_root):
        raise CyberPanelError("CyberPanel returned an invalid subdomain path.")

    website.document_root = document_root
    website.status = HostingWebsite.Status.ACTIVE
    website.last_error = ""
    website.save(update_fields=("document_root", "status", "last_error", "updated_at"))


def process_hosting_certificate_action(action, client):
    try:
        website = HostingWebsite.objects.select_related(
            "hosting_account__customer_service",
        ).get(
            id=action.payload.get("hosting_website_id"),
            hosting_account__customer_service=action.customer_service,
        )
    except HostingWebsite.DoesNotExist as error:
        raise CyberPanelError("The selected website was not found.") from error

    account = website.hosting_account
    service = account.customer_service
    expiry = service.expires_at or service.next_due_at
    if (
        website.status != HostingWebsite.Status.ACTIVE
        or service.status != "active"
        or account.status != "active"
        or (expiry and expiry <= timezone.now())
        or not account.username
    ):
        raise CyberPanelError("Certificate installation requires an active hosting website.")

    client.install_child_certificate(
        master_domain=website.master_domain,
        child_domain=website.domain_name,
        username=account.username,
        plan_expires=expiry.timestamp() if expiry else None,
    )
    website.certificate_status = HostingWebsite.CertificateStatus.ACTIVE
    website.certificate_error = ""
    website.save(update_fields=("certificate_status", "certificate_error", "updated_at"))


def process_dns_action(action, client):
    try:
        zone = DNSZone.objects.select_related(
            "provider_connection"
        ).get(
            id=action.payload["zone_id"],
            domain__customer_service=action.customer_service,
        )
    except (DNSZone.DoesNotExist, KeyError) as error:
        raise CloudflareError("The DNS zone for this action no longer exists.") from error

    connection = zone.provider_connection
    if (
        not connection
        or connection.provider != ProviderConnection.Provider.CLOUDFLARE
        or connection.status != ProviderConnection.Status.ACTIVE
    ):
        raise CloudflareError("No active Cloudflare connection is linked to the DNS zone.")
    token = cloudflare_token(connection)

    if action.action_type == ProvisioningAction.ActionType.DNS_DELETE:
        external_id = action.payload.get("external_record_id")
        if external_id:
            client.delete_dns_record(token, zone.external_zone_id, external_id)
        return

    try:
        record = DNSRecord.objects.get(
            id=action.payload["record_id"],
            zone=zone,
        )
    except (DNSRecord.DoesNotExist, KeyError):
        action.status = ProvisioningAction.Status.CANCELLED
        action.completed_at = timezone.now()
        action.save(update_fields=("status", "completed_at"))
        return

    record_data = {
        "type": record.record_type,
        "name": record.name,
        "content": record.content,
        "ttl": record.ttl,
    }
    if record.priority is not None:
        record_data["priority"] = record.priority
    if record.record_type in {
        DNSRecord.RecordType.A,
        DNSRecord.RecordType.AAAA,
        DNSRecord.RecordType.CNAME,
    }:
        record_data["proxied"] = record.proxied

    if record.external_record_id:
        result = client.update_dns_record(
            token,
            zone.external_zone_id,
            record.external_record_id,
            record_data,
        )
    else:
        result = client.create_dns_record(token, zone.external_zone_id, record_data)
    synced_at = timezone.now()
    updated = DNSRecord.objects.filter(id=record.id).update(
        external_record_id=result["id"],
        synced_at=synced_at,
        updated_at=synced_at,
    )
    if not updated:
        client.delete_dns_record(token, zone.external_zone_id, result["id"])
        action.status = ProvisioningAction.Status.CANCELLED
        action.completed_at = synced_at
        action.save(update_fields=("status", "completed_at"))


class Command(BaseCommand):
    help = "Process queued Cloudflare DNS changes. Other provider actions require their own adapter."

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=50)

    def handle(self, *args, **options):
        limit = options["limit"]
        if limit < 1 or limit > 500:
            self.stderr.write(self.style.ERROR("--limit must be between 1 and 500."))
            return

        queued_storage_actions = queue_hosting_storage_actions(limit)
        action_ids = list(
            ProvisioningAction.objects.filter(
                status=ProvisioningAction.Status.PENDING,
                action_type__in=(
                    DNS_ACTIONS
                    + MAILBOX_ACTIONS
                    + HOSTING_WEBSITE_ACTIONS
                    + HOSTING_CERTIFICATE_ACTIONS
                    + (ProvisioningAction.ActionType.HOSTING_STORAGE_UPDATE,)
                ),
            )
            .order_by("id")
            .values_list("id", flat=True)[:limit]
        )
        client = CloudflareClient()
        cyberpanel_connection = ProviderConnection.objects.filter(
            provider=ProviderConnection.Provider.CYBERPANEL,
            scope=ProviderConnection.Scope.GLOBAL,
            customer__isnull=True,
            status=ProviderConnection.Status.ACTIVE,
        ).first()
        cyberpanel_client = CyberPanelClient(cyberpanel_connection) if cyberpanel_connection else None
        completed = 0
        failed = 0
        for action_id in action_ids:
            with transaction.atomic():
                try:
                    action = ProvisioningAction.objects.select_for_update().get(
                        id=action_id,
                        status=ProvisioningAction.Status.PENDING,
                    )
                except ProvisioningAction.DoesNotExist:
                    continue
                action.status = ProvisioningAction.Status.PROCESSING
                action.attempts += 1
                action.started_at = timezone.now()
                action.save(update_fields=("status", "attempts", "started_at"))

            action = ProvisioningAction.objects.select_related("customer_service").get(id=action_id)
            try:
                if action.action_type in DNS_ACTIONS:
                    process_dns_action(action, client)
                elif action.action_type == ProvisioningAction.ActionType.MAILBOX_CREATE:
                    if not cyberpanel_client:
                        raise CyberPanelError("No active CyberPanel connection is configured.")
                    process_mailbox_action(action)
                elif action.action_type in {
                    ProvisioningAction.ActionType.MAILBOX_UPDATE,
                    ProvisioningAction.ActionType.MAILBOX_DELETE,
                    ProvisioningAction.ActionType.MAILBOX_PASSWORD_RESET,
                    ProvisioningAction.ActionType.MAILBOX_CLEAR_STORAGE,
                }:
                    if not cyberpanel_client:
                        raise CyberPanelError("No active CyberPanel connection is configured.")
                    process_mailbox_action(action)
                elif action.action_type in HOSTING_WEBSITE_ACTIONS + HOSTING_CERTIFICATE_ACTIONS:
                    if not cyberpanel_client:
                        raise CyberPanelError("No active CyberPanel connection is configured.")
                    if action.action_type == ProvisioningAction.ActionType.HOSTING_WEBSITE_CREATE:
                        process_hosting_website_action(action, cyberpanel_client)
                    else:
                        process_hosting_certificate_action(action, cyberpanel_client)
                elif action.action_type == ProvisioningAction.ActionType.HOSTING_STORAGE_UPDATE:
                    process_hosting_storage_action(action)
            except (CloudflareError, CyberPanelError) as error:
                if action.action_type == ProvisioningAction.ActionType.HOSTING_WEBSITE_CREATE:
                    HostingWebsite.objects.filter(
                        id=action.payload.get("hosting_website_id"),
                        hosting_account__customer_service=action.customer_service,
                    ).update(status=HostingWebsite.Status.ERROR, last_error=str(error))
                elif action.action_type == ProvisioningAction.ActionType.HOSTING_WEBSITE_CERTIFICATE:
                    HostingWebsite.objects.filter(
                        id=action.payload.get("hosting_website_id"),
                        hosting_account__customer_service=action.customer_service,
                    ).update(
                        certificate_status=HostingWebsite.CertificateStatus.ERROR,
                        certificate_error=str(error),
                    )
                elif action.action_type == ProvisioningAction.ActionType.HOSTING_STORAGE_UPDATE:
                    HostingStorageAddon.objects.filter(
                        id=action.payload.get("hosting_storage_addon_id"),
                        customer_service=action.customer_service,
                        status__in=(
                            HostingStorageAddon.Status.PENDING,
                            HostingStorageAddon.Status.EXPIRING,
                        ),
                    ).update(last_error=str(error))
                elif action.action_type == ProvisioningAction.ActionType.MAILBOX_CLEAR_STORAGE:
                    Mailbox.objects.filter(
                        id=action.payload.get("mailbox_id"),
                        hosting_account__customer_service=action.customer_service,
                        status=Mailbox.Status.CLEARING,
                    ).update(status=Mailbox.Status.ACTIVE, last_error=str(error))
                action.status = ProvisioningAction.Status.FAILED
                action.last_error = str(error)
                action.completed_at = timezone.now()
                action.payload = {key: value for key, value in action.payload.items() if key != "password_encrypted"}
                action.save(update_fields=("status", "last_error", "completed_at", "payload"))
                failed += 1
            else:
                if action.status != ProvisioningAction.Status.CANCELLED:
                    action.status = ProvisioningAction.Status.COMPLETED
                    action.completed_at = timezone.now()
                    action.payload = {key: value for key, value in action.payload.items() if key != "password_encrypted"}
                    action.save(update_fields=("status", "completed_at", "payload"))
                elif "password_encrypted" in action.payload:
                    action.payload = {key: value for key, value in action.payload.items() if key != "password_encrypted"}
                    action.save(update_fields=("payload",))
                completed += 1

        waiting = ProvisioningAction.objects.filter(
            status=ProvisioningAction.Status.PENDING
        ).exclude(
            action_type__in=(
                DNS_ACTIONS
                + MAILBOX_ACTIONS
                + HOSTING_WEBSITE_ACTIONS
                + HOSTING_CERTIFICATE_ACTIONS
                + (ProvisioningAction.ActionType.HOSTING_STORAGE_UPDATE,)
            )
        ).count()
        self.stdout.write(
            self.style.SUCCESS(
                f"Provisioning actions completed: {completed}; failed: {failed}; "
                f"storage extensions queued: {queued_storage_actions}; "
                f"other provider actions awaiting adapters: {waiting}."
            )
        )
