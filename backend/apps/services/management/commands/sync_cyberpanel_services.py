import json
import os
import subprocess
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from apps.catalog.models import Product
from apps.services.models import CustomerService, DomainAsset, HostingAccount, HostingResource, Mailbox


PANEL_READ_SCRIPT = r"""
import os,sys,json
sys.path.insert(0,'/usr/local/CyberCP')
os.environ.setdefault('DJANGO_SETTINGS_MODULE','CyberCP.settings')
import django; django.setup()
from loginSystem.models import Administrator
from websiteFunctions.models import Websites
from mailServer.models import EUsers
from plogical.virtualHostUtilities import virtualHostUtilities
for admin in Administrator.objects.exclude(userName='admin').filter(state='ACTIVE'):
    for site in Websites.objects.filter(admin=admin,state=1):
        try:
            disk_used_mb = virtualHostUtilities.FindStats(site)[0]
        except Exception:
            disk_used_mb = 0
        package = site.package
        mailboxes = [{'email': email.email, 'used_mb': email.DiskUsage} for email in
            EUsers.objects.filter(emailOwner__domain=site.domain)]
        print(json.dumps({'email':admin.email,'username':admin.userName,'domain':site.domain,
            'package_name':package.packageName,'disk_limit_mb':package.diskSpace,
            'disk_used_mb':disk_used_mb,'allowed_domains':package.allowedDomains,
            'email_limit':package.emailAccounts,
            'mailboxes':mailboxes}))
"""


def sync_storage_resource(account, record):
    try:
        limit_mb = max(1, int(record["disk_limit_mb"]))
        used_mb = max(0, int(float(record.get("disk_used_mb", 0))))
    except (KeyError, TypeError, ValueError):
        return
    HostingResource.objects.update_or_create(
        hosting_account=account,
        resource_type=HostingResource.ResourceType.DISK,
        defaults={
            "limit_value": Decimal(limit_mb) / Decimal(1024),
            "used_value": Decimal(used_mb) / Decimal(1024),
            "unit": "GB",
            "measured_at": timezone.now(),
        },
    )


def sync_mailboxes(account, domain, records, email_limit):
    for mailbox_record in records:
        try:
            address = mailbox_record["email"].strip().lower()
            local_part, mailbox_domain = address.rsplit("@", 1)
            if mailbox_domain != domain.domain_name.lower():
                continue
            used_mb = max(0, int(float(mailbox_record.get("used_mb", 0))))
        except (AttributeError, KeyError, TypeError, ValueError):
            continue
        Mailbox.objects.update_or_create(
            domain=domain,
            local_part=local_part,
            defaults={
                "hosting_account": account,
                "quota_mb": max(2048, used_mb),
                "used_mb": used_mb,
                "external_mailbox_id": address,
                "status": Mailbox.Status.ACTIVE,
            },
        )
    try:
        limit = max(1, int(email_limit or 1000))
    except (TypeError, ValueError):
        limit = 1000
    used = Mailbox.objects.filter(hosting_account=account).exclude(
        status__in=(Mailbox.Status.DELETED, Mailbox.Status.DELETING)
    ).count()
    HostingResource.objects.update_or_create(
        hosting_account=account,
        resource_type=HostingResource.ResourceType.EMAIL_ACCOUNTS,
        defaults={"limit_value": Decimal(limit), "used_value": Decimal(used), "unit": "mailboxes"},
    )


class Command(BaseCommand):
    help = "Import active CyberPanel websites that match an existing TechInn customer email."

    def handle(self, *args, **options):
        env = os.environ.copy()
        env.pop("DJANGO_SETTINGS_MODULE", None)
        try:
            result = subprocess.run(
                ["/usr/local/CyberCP/bin/python", "-c", PANEL_READ_SCRIPT],
                check=True, capture_output=True, text=True, timeout=60, env=env,
            )
        except (OSError, subprocess.SubprocessError) as error:
            raise CommandError("Could not read active websites from CyberPanel.") from error

        product = Product.objects.filter(slug="web-basic").first()
        if product is None:
            raise CommandError("The web-basic hosting product has not been seeded.")
        User = get_user_model()
        imported = skipped = 0
        for line in result.stdout.splitlines():
            try:
                record = json.loads(line)
                email = record["email"].strip().lower()
                domain_name = record["domain"].strip().rstrip(".").lower()
                username = record["username"].strip()
            except (json.JSONDecodeError, KeyError, AttributeError):
                continue
            user = User.objects.filter(email__iexact=email).first()
            if not user or not domain_name or not username:
                skipped += 1
                continue
            existing_domain = DomainAsset.objects.filter(domain_name__iexact=domain_name).first()
            if existing_domain and existing_domain.customer_service.customer_id != user.id:
                skipped += 1
                continue
            existing_account = HostingAccount.objects.filter(external_account_id=domain_name).first()
            if existing_account:
                if existing_account.customer_service.customer_id == user.id:
                    existing_account.username = username
                    existing_account.status = HostingAccount.Status.ACTIVE
                    existing_account.save(update_fields=("username", "status", "updated_at"))
                    sync_storage_resource(existing_account, record)
                    if existing_domain:
                        sync_mailboxes(existing_account, existing_domain, record.get("mailboxes", []), record.get("email_limit"))
                    skipped += 1
                    continue
                skipped += 1
                continue
            with transaction.atomic():
                service = CustomerService.objects.create(
                    customer=user,
                    product=product,
                    status=CustomerService.Status.ACTIVE,
                    provisioning_data={"cyberpanel": {"status": "active", "imported": True}},
                )
                domain = existing_domain or DomainAsset.objects.create(
                    customer_service=service,
                    domain_name=domain_name,
                    registrar="CyberPanel (existing service)",
                    status=DomainAsset.Status.ACTIVE,
                )
                account = HostingAccount.objects.create(
                    customer_service=service,
                    server_name="CyberPanel",
                    external_account_id=domain_name,
                    username=username,
                    primary_domain=domain,
                    status=HostingAccount.Status.ACTIVE,
                )
                sync_storage_resource(account, record)
                sync_mailboxes(account, domain, record.get("mailboxes", []), record.get("email_limit"))
            imported += 1
        self.stdout.write(f"Imported {imported} active hosting service(s); skipped {skipped} unmatched or duplicate site(s).")
