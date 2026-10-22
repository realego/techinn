"""Confirm submitted domains and finish their DNS/hosting handoff."""

import json
from pathlib import Path

import requests
from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from apps.services.domain_availability import check_domain_availability
from apps.services.domain_registration import _provider_token
from apps.services.models import CustomerService, DNSRecord, DNSZone, DomainAsset, ProviderConnection
from apps.services.providers.cloudflare import CloudflareClient, CloudflareError
from apps.services.providers.cyberpanel import CyberPanelClient, CyberPanelError


def _server_ip():
    configured = getattr(settings, "TECHINN_HOSTING_IPV4", "")
    if configured:
        return configured.strip()
    return Path("/etc/cyberpanel/machineIP").read_text().strip().splitlines()[0]


def _upsert_records(domain, zone, records):
    """Add only TechInn's required records; never overwrite customer records."""
    token = _provider_token()
    client = CloudflareClient()
    existing = client.list_dns_records(token, zone.external_zone_id)
    existing_keys = {(row.get("type"), row.get("name", "").rstrip(".").lower()) for row in existing}
    for record in records:
        key = (record["type"], record["name"].rstrip(".").lower())
        if key in existing_keys:
            continue
        created = client.create_dns_record(token, zone.external_zone_id, record)
        DNSRecord.objects.update_or_create(
            zone=zone,
            external_record_id=created["id"],
            defaults={
                "name": record["name"],
                "record_type": record["type"],
                "content": record["content"],
                "ttl": record.get("ttl", 300),
                "priority": record.get("priority"),
                "proxied": False,
            },
        )
        existing_keys.add(key)


def _activate(domain_asset, service):
    now = timezone.now()
    domain_asset.status = DomainAsset.Status.ACTIVE
    domain_asset.registered_at = domain_asset.registered_at or now
    domain_asset.save(update_fields=("status", "registered_at", "updated_at"))
    if service.status in (CustomerService.Status.PENDING, CustomerService.Status.PROVISIONING):
        service.status = CustomerService.Status.ACTIVE
    data = dict(service.provisioning_data or {})
    progress = dict(data.get("domain_registration", {}))
    progress.update({
        "status": "registered",
        "activated_at": now.isoformat(),
        "message": "The domain is registered and DNS setup is being completed.",
    })
    data["domain_registration"] = progress
    service.provisioning_data = data
    service.save(update_fields=("status", "provisioning_data", "updated_at"))


def _secure_services(domain_asset):
    """Request CyberPanel certificates after the domain has real DNS."""
    connection = ProviderConnection.objects.filter(
        provider=ProviderConnection.Provider.CYBERPANEL,
        scope=ProviderConnection.Scope.GLOBAL,
        customer__isnull=True,
        status=ProviderConnection.Status.ACTIVE,
    ).first()
    if not connection:
        return
    client = CyberPanelClient(connection)
    services = CustomerService.objects.filter(
        customer=domain_asset.customer_service.customer,
        provisioning_data__selected_domain_id=domain_asset.id,
        status__in=(CustomerService.Status.ACTIVE, CustomerService.Status.PROVISIONING),
    ).select_related("product")
    for service in services:
        data = dict(service.provisioning_data or {})
        security = dict(data.get("security", {}))
        try:
            kind = service.product.service_type.slug
            # Domain activation only prepares DNS. The owner must request the
            # primary certificate from the dashboard, so activation checks do
            # not unexpectedly issue certificates.
            if kind == "web-hosting" and security.get("certificate_requested_at") and not security.get("website_certificate_at"):
                client.issue_ssl(domain=domain_asset.domain_name)
                security["website_certificate_at"] = timezone.now().isoformat()
                security["certificate_status"] = "active"
            # Mail TLS is installed and verified by the privileged webmail
            # worker. Issuing HTTPS here does not secure IMAP/SMTP, and this
            # activation worker cannot write their server configuration.
            data["security"] = security
            service.provisioning_data = data
            service.save(update_fields=("provisioning_data", "updated_at"))
        except CyberPanelError as error:
            security["certificate_error"] = str(error)
            data["security"] = security
            service.provisioning_data = data
            service.save(update_fields=("provisioning_data", "updated_at"))


class Command(BaseCommand):
    help = "Check submitted domain registrations and activate them when the registry confirms they are taken."

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=50)
        parser.add_argument("--customer-id", type=int)

    def handle(self, *args, **options):
        candidates = CustomerService.objects.filter(
            product__slug="domains",
            status__in=(CustomerService.Status.PENDING, CustomerService.Status.PROVISIONING, CustomerService.Status.ACTIVE),
        ).select_related("product").prefetch_related("domains")[: options["limit"]]
        if options.get("customer_id"):
            candidates = CustomerService.objects.filter(
                product__slug="domains",
                customer_id=options["customer_id"],
                status__in=(CustomerService.Status.PENDING, CustomerService.Status.PROVISIONING, CustomerService.Status.ACTIVE),
            ).select_related("product").prefetch_related("domains")[: options["limit"]]
        checked = activated = waiting = failed = 0
        for service in candidates:
            domain_asset = service.domains.filter(status=DomainAsset.Status.PENDING).first()
            progress = dict((service.provisioning_data or {}).get("domain_registration", {}))
            active_domain = service.domains.filter(status=DomainAsset.Status.ACTIVE).first()
            if not domain_asset and active_domain and progress.get("status") == "registered":
                # Keep DNS and certificates healthy on later 20-minute passes.
                try:
                    zone = DNSZone.objects.filter(domain=active_domain).first()
                    if zone and zone.external_zone_id:
                        ip = _server_ip()
                        _upsert_records(active_domain, zone, [
                            {"type": "A", "name": f"mail.{active_domain.domain_name}", "content": ip, "ttl": 300, "proxied": False},
                            {"type": "MX", "name": active_domain.domain_name, "content": f"mail.{active_domain.domain_name}", "priority": 10, "ttl": 300, "proxied": False},
                        ])
                    _secure_services(active_domain)
                except (CloudflareError, CyberPanelError, OSError, IndexError) as error:
                    self.stderr.write(self.style.WARNING(f"{active_domain.domain_name}: DNS/certificate retry delayed: {error}"))
                continue
            request_id = progress.get("zispa_request_id")
            registration_status = progress.get("status")
            if not domain_asset or registration_status not in ("zispa_submitted", "submitted", "registrar_manual_required"):
                continue
            checked += 1
            try:
                provider_status = ""
                if request_id:
                    response = requests.get(
                        f"{settings.ZISPA_API_URL.rstrip('/')}/requests/{request_id}",
                        headers={"X-Kunda-Zispa-Key": settings.ZISPA_API_KEY},
                        timeout=20,
                    )
                    response.raise_for_status()
                    provider = response.json()
                    provider_status = str(provider.get("status", "")).lower() if isinstance(provider, dict) else ""
                availability = check_domain_availability(domain_asset.domain_name)
                # A paid request plus a registry lookup saying "taken" is the
                # same confirmation used by the public domain search flow.
                confirmed = availability.get("available") is False and availability.get("method") in ("zispa", "dns", "whois", "http")
                if provider_status in ("failed", "rejected", "cancelled"):
                    progress.update({"status": "needs_attention", "message": "The registry rejected this registration; TechInn support will review it."})
                    data = dict(service.provisioning_data or {}); data["domain_registration"] = progress
                    service.provisioning_data = data; service.save(update_fields=("provisioning_data", "updated_at"))
                    failed += 1
                    continue
                if not confirmed:
                    waiting += 1
                    continue
                with transaction.atomic():
                    locked = CustomerService.objects.select_for_update().get(pk=service.pk)
                    locked_domain = locked.domains.select_for_update().get(pk=domain_asset.pk)
                    _activate(locked_domain, locked)
                    zone = DNSZone.objects.filter(domain=locked_domain).first()
                    if zone and zone.external_zone_id:
                        ip = _server_ip()
                        _upsert_records(locked_domain, zone, [
                            {"type": "A", "name": f"mail.{locked_domain.domain_name}", "content": ip, "ttl": 300, "proxied": False},
                            {"type": "MX", "name": locked_domain.domain_name, "content": f"mail.{locked_domain.domain_name}", "priority": 10, "ttl": 300, "proxied": False},
                            {"type": "TXT", "name": locked_domain.domain_name, "content": f"v=spf1 ip4:{ip} ~all", "ttl": 300, "proxied": False},
                            {"type": "CNAME", "name": f"autoconfig.{locked_domain.domain_name}", "content": f"mail.techinn.co.zw", "ttl": 300, "proxied": False},
                            {"type": "CNAME", "name": f"autodiscover.{locked_domain.domain_name}", "content": f"mail.techinn.co.zw", "ttl": 300, "proxied": False},
                        ])
                _secure_services(domain_asset)
                activated += 1
            except (requests.RequestException, ValueError, KeyError, OSError, CloudflareError) as error:
                failed += 1
                self.stderr.write(self.style.WARNING(f"{domain_asset.domain_name}: activation check failed: {error}"))
        self.stdout.write(f"Domain activations checked: {checked}; activated: {activated}; waiting: {waiting}; failed: {failed}.")
