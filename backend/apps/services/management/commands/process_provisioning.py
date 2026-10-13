import json
import secrets
import string

from django.conf import settings
from django.core.mail import send_mail
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from apps.services.models import (
    DNSRecord,
    DNSZone,
    Mailbox,
    HostingResource,
    ProviderConnection,
    ProvisioningAction,
)
from apps.services.fields import decrypt_secret
from apps.services.providers.cloudflare import CloudflareClient, CloudflareError, cloudflare_credentials
from apps.services.providers.cyberpanel import CyberPanelClient, CyberPanelError, run_local_mail_operation


DNS_ACTIONS = (
    ProvisioningAction.ActionType.DNS_UPSERT,
    ProvisioningAction.ActionType.DNS_DELETE,
)
MAILBOX_ACTIONS = (
    ProvisioningAction.ActionType.MAILBOX_CREATE,
    ProvisioningAction.ActionType.MAILBOX_DELETE,
    ProvisioningAction.ActionType.MAILBOX_PASSWORD_RESET,
)


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
            password = decrypt_secret(action.payload.get("password_encrypted"))
            if len(password) < 8:
                raise CyberPanelError("The mailbox password was not available; request mailbox creation again.")
            run_local_mail_operation(
                operation="create", domain=mailbox.domain.domain_name,
                local_part=mailbox.local_part, password=password,
            )
            send_mail(
                "Your TechInn email mailbox is ready",
                f"Your mailbox is ready.\n\nEmail address: {email}\n"
                f"Webmail: https://{mailbox.domain.domain_name}/webmail\n"
                "Sign in with the password you chose when creating this mailbox.",
                settings.DEFAULT_FROM_EMAIL,
                [mailbox.hosting_account.customer_service.customer.email],
                fail_silently=True,
            )
            mailbox.status = Mailbox.Status.ACTIVE
            mailbox.external_mailbox_id = email
            mailbox.save(update_fields=("status", "external_mailbox_id", "updated_at"))
            action.payload = {key: value for key, value in action.payload.items() if key != "password_encrypted"}
            action.save(update_fields=("payload",))
            sync_mailbox_count(mailbox)
        elif action.action_type == ProvisioningAction.ActionType.MAILBOX_PASSWORD_RESET:
            service = mailbox.hosting_account.customer_service
            if mailbox.status != Mailbox.Status.ACTIVE or service.status != "active" or (
                service.expires_at and service.expires_at <= timezone.now()
            ):
                raise CyberPanelError("Only an active mailbox password can be reset.")
            alphabet = string.ascii_letters + string.digits + "!@#$%_-"
            password = "".join(secrets.choice(alphabet) for _ in range(24))
            run_local_mail_operation(
                operation="change_password", domain=mailbox.domain.domain_name,
                local_part=mailbox.local_part, password=password,
            )
            try:
                send_mail(
                    "Your TechInn email password was reset",
                    f"A new temporary password was created for {email}.\n\n"
                    f"Webmail: https://{mailbox.domain.domain_name}/webmail\n"
                    f"Temporary password: {password}\n\nPlease change it after signing in.",
                    settings.DEFAULT_FROM_EMAIL,
                    [mailbox.hosting_account.customer_service.customer.email],
                    fail_silently=False,
                )
            except Exception as error:
                raise CyberPanelError("Password changed, but the access email could not be delivered.") from error
        else:
            run_local_mail_operation(
                operation="delete", domain=mailbox.domain.domain_name,
                local_part=mailbox.local_part,
            )
            mailbox.status = Mailbox.Status.DELETED
            mailbox.save(update_fields=("status", "updated_at"))
            sync_mailbox_count(mailbox)
    except CyberPanelError:
        mailbox.status = Mailbox.Status.ERROR
        mailbox.save(update_fields=("status", "updated_at"))
        raise


def cloudflare_token(connection):
    try:
        credentials = json.loads(connection.credentials)
        token = cloudflare_credentials(credentials)
    except (json.JSONDecodeError, KeyError, TypeError, CloudflareError) as error:
        raise CloudflareError("The Cloudflare connection has invalid stored credentials.") from error
    return token


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

        action_ids = list(
            ProvisioningAction.objects.filter(
                status=ProvisioningAction.Status.PENDING,
                action_type__in=DNS_ACTIONS + MAILBOX_ACTIONS,
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
                    ProvisioningAction.ActionType.MAILBOX_DELETE,
                    ProvisioningAction.ActionType.MAILBOX_PASSWORD_RESET,
                }:
                    if not cyberpanel_client:
                        raise CyberPanelError("No active CyberPanel connection is configured.")
                    process_mailbox_action(action)
            except (CloudflareError, CyberPanelError) as error:
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
        ).exclude(action_type__in=DNS_ACTIONS + MAILBOX_ACTIONS).count()
        self.stdout.write(
            self.style.SUCCESS(
                f"Cloudflare DNS actions completed: {completed}; failed: {failed}; "
                f"other provider actions awaiting adapters: {waiting}."
            )
        )
