import ipaddress
import fcntl
import json
import os
import socket
from datetime import timedelta
from pathlib import Path
from urllib.parse import quote

import requests
from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.services.domain_availability import normalize_domain_name
from apps.services.models import CustomerService, DNSZone, DomainAsset, ProviderConnection
from apps.services.periods import extend_service_period
from apps.services.providers.cloudflare import CloudflareClient, CloudflareError, cloudflare_credentials


class DomainRegistrationError(RuntimeError):
    pass


def _save_progress(service, **changes):
    progress = dict((service.provisioning_data or {}).get("domain_registration", {}))
    progress.update(changes)
    service.provisioning_data = {**(service.provisioning_data or {}), "domain_registration": progress}
    service.save(update_fields=("provisioning_data", "updated_at"))
    return progress


def registration_ready(progress):
    status = progress.get("status")
    if status in {"zispa_submitted", "registrar_manual_required", "needs_attention", "registered"}:
        return False
    if status == "zispa_draft_created" and not settings.ZISPA_AUTO_SEND:
        return False
    if status == "awaiting_release" and not settings.ZISPA_SUBMISSIONS_ENABLED:
        return False
    retry = progress.get("next_retry_at")
    return not retry or retry <= timezone.now().isoformat()


def _provider_token():
    connection = ProviderConnection.objects.filter(
        provider=ProviderConnection.Provider.CLOUDFLARE,
        scope=ProviderConnection.Scope.GLOBAL,
        customer__isnull=True,
        status=ProviderConnection.Status.ACTIVE,
    ).first()
    if connection is None:
        raise DomainRegistrationError("No verified TechInn Cloudflare connection is configured.")
    try:
        credentials = json.loads(connection.credentials)
    except (TypeError, json.JSONDecodeError) as error:
        raise DomainRegistrationError("The TechInn Cloudflare connection has invalid credentials.") from error
    try:
        return cloudflare_credentials(credentials)
    except CloudflareError as error:
        raise DomainRegistrationError(str(error)) from error


def _default_nameserver_ips():
    configured = {}
    for item in settings.ZISPA_DEFAULT_NAMESERVERS:
        hostname = item["hostname"].strip().rstrip(".").lower()
        address = item["ip"].strip()
        try:
            parsed_address = ipaddress.ip_address(address)
        except ValueError as error:
            raise DomainRegistrationError(
                f"Configured IP address for nameserver {hostname} is invalid."
            ) from error
        if not parsed_address.is_global:
            raise DomainRegistrationError(
                f"Configured IP address for nameserver {hostname} must be public."
            )
        configured[hostname] = address
    return configured


def _nameserver_ip(hostname, provided_ip, defaults):
    if provided_ip:
        try:
            parsed_address = ipaddress.ip_address(provided_ip)
        except ValueError as error:
            raise DomainRegistrationError(f"The IP address for nameserver {hostname} is invalid.") from error
        if not parsed_address.is_global:
            raise DomainRegistrationError(f"The IP address for nameserver {hostname} must be public.")
        return str(parsed_address)
    if hostname in defaults:
        return defaults[hostname]
    try:
        addresses = socket.getaddrinfo(hostname, 53, type=socket.SOCK_STREAM)
    except socket.gaierror as error:
        raise DomainRegistrationError(
            f"Could not resolve an IP address for nameserver {hostname}."
        ) from error
    for result in addresses:
        address = result[4][0]
        if ipaddress.ip_address(address).is_global:
            return address
    raise DomainRegistrationError(f"Nameserver {hostname} did not resolve to a public IP address.")


def _delegation_nameservers(details, cloudflare_nameservers):
    defaults = _default_nameserver_ips()
    if details.get("nameserver_type", "techinn") == "custom":
        selected = [
            (
                details.get(f"nameserver_{index}", "").strip().rstrip(".").lower(),
                details.get(f"nameserver_ip_{index}", "").strip(),
            )
            for index in range(1, 5)
            if details.get(f"nameserver_{index}", "").strip()
        ]
    else:
        selected = [
            (hostname.strip().rstrip(".").lower(), "")
            for hostname in cloudflare_nameservers
            if isinstance(hostname, str) and hostname.strip()
        ]
    if len(selected) < 2:
        raise DomainRegistrationError("At least two nameservers are required for domain registration.")

    nameservers = []
    addresses = []
    for hostname, address in selected:
        if hostname in nameservers:
            raise DomainRegistrationError("Nameservers must be unique.")
        nameservers.append(hostname)
        addresses.append(_nameserver_ip(hostname, address, defaults))
    return nameservers, addresses


def _submit_zispa(service, domain, registrant, nameservers, nameserver_ips, order_item_id):
    if not settings.ZISPA_SUBMISSIONS_ENABLED:
        raise DomainRegistrationError("ZISPA submissions are paused.")
    if not settings.ZISPA_API_URL or not settings.ZISPA_API_KEY or not settings.ZISPA_DRAFT_API_KEY:
        raise DomainRegistrationError("ZISPA registration is not configured.")
    progress = dict((service.provisioning_data or {}).get("domain_registration", {}))
    request_id = progress.get("zispa_request_id", "")
    result = None
    draft_headers = {"X-Kunda-Zispa-Key": settings.ZISPA_DRAFT_API_KEY}
    send_headers = {"X-Kunda-Zispa-Key": settings.ZISPA_API_KEY}
    if progress.get("zispa_sent_at"):
        return None
    if progress.get("zispa_send_attempted_at"):
        _save_progress(service, status="needs_attention", message="A previous send needs confirmation before it can be retried.")
        raise DomainRegistrationError("A previous ZISPA send needs manual confirmation.")
    if not request_id:
        idempotency_key = progress.get("idempotency_key") or f"techinn-my-domain-{service.uuid}"
        # Persist before network I/O: a timed-out draft uses exactly the same key on retry.
        progress = _save_progress(service, idempotency_key=idempotency_key)
        payload = {
            "domain": domain,
            "action": "N",
            "owner_name": registrant["registrant_name"],
            "organisation": registrant.get("registrant_business_name", ""),
            "physical_address": registrant["physical_address"],
            "postal_address": registrant.get("postal_address") or registrant["physical_address"],
            "town_city": registrant["physical_city"],
            "country": registrant["physical_country"],
            "phone": registrant["contact_phone"],
            "fax": "",
            "email": registrant["customer_email"],
            # Kunda validates each delegation server together with its IP.  The
            # older integration sent these as two parallel arrays, which the
            # draft endpoint accepts syntactically but rejects as
            # ``missing_nameservers``.
            "nameservers": [
                {"hostname": hostname, "ip": address}
                for hostname, address in zip(nameservers, nameserver_ips)
            ],
            "nameserver_ips": nameserver_ips,
            "idempotency_key": idempotency_key,
        }
        try:
            response = requests.post(
                f"{settings.ZISPA_API_URL}/requests",
                json=payload,
                headers=draft_headers,
                timeout=30,
            )
            response.raise_for_status()
            result = response.json()
        except (requests.RequestException, ValueError) as error:
            raise DomainRegistrationError("ZISPA could not create the registration request.") from error
        if not isinstance(result, dict) or not result.get("id"):
            raise DomainRegistrationError("ZISPA did not return a registration request ID.")
        request_id = str(result["id"])
        progress["zispa_request_id"] = request_id
        progress["zispa_draft_created_at"] = timezone.now().isoformat()
        service.provisioning_data = {
            **(service.provisioning_data or {}),
            "domain_registration": progress,
        }
        service.save(update_fields=("provisioning_data", "updated_at"))

    if settings.ZISPA_AUTO_SEND and not progress.get("zispa_sent_at"):
        # A lost response is ambiguous. Never automatically send the same request again.
        progress = _save_progress(service, zispa_send_attempted_at=timezone.now().isoformat())
        try:
            response = requests.post(
                f"{settings.ZISPA_API_URL}/requests/{quote(request_id, safe='')}/send",
                headers=send_headers,
                timeout=30,
            )
            response.raise_for_status()
        except requests.RequestException as error:
            _save_progress(service, status="needs_attention", message="The registry submission needs confirmation. TechInn will check it before retrying.")
            raise DomainRegistrationError("ZISPA could not submit the registration request.") from error
        progress["zispa_sent_at"] = timezone.now().isoformat()
        service.provisioning_data = {
            **(service.provisioning_data or {}),
            "domain_registration": progress,
        }
        service.save(update_fields=("provisioning_data", "updated_at"))
    return result


def process_paid_domain_item(order_item, cloudflare_client=None):
    # Same-host process lock covers the full provider interaction, not just DB writes.
    # It is released by the OS after a worker crash; the send marker handles ambiguity.
    directory = Path(settings.DOMAIN_REGISTRATION_LOCK_DIR)
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    fd = os.open(directory / f"order-item-{order_item.pk}.lock", os.O_CREAT | os.O_RDWR, 0o600)
    with os.fdopen(fd, "w") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise DomainRegistrationError("This registration is already being processed.") from error
        order_item.order.refresh_from_db(fields=["status"])
        if order_item.order.status not in {"paid", "processing", "completed"}:
            raise DomainRegistrationError("Payment must be confirmed before domain provisioning.")
        if not order_item.product or order_item.product.slug != "domains":
            raise DomainRegistrationError("This order item is not a domain registration.")
        service, _ = CustomerService.objects.get_or_create(
            order_item=order_item,
            defaults={"customer": order_item.order.customer, "product": order_item.product,
                      "status": CustomerService.Status.PROVISIONING,
                      "provisioning_data": {"domain_registration": {"status": "pending"}}},
        )
        progress = (service.provisioning_data or {}).get("domain_registration", {})
        if not registration_ready(progress):
            return service
        _save_progress(service, last_attempt_at=timezone.now().isoformat())
        try:
            return _process_paid_domain_item(order_item, cloudflare_client)
        except (DomainRegistrationError, ValueError) as error:
            service.refresh_from_db()
            progress = (service.provisioning_data or {}).get("domain_registration", {})
            attempts = int(progress.get("attempts", 0)) + 1
            review = bool(progress.get("zispa_send_attempted_at")) or attempts >= 5
            _save_progress(service, status="needs_attention" if review else "retry_pending",
                           attempts=attempts, message="TechInn is checking your registration." if review else "Registration is delayed; we will retry automatically.",
                           next_retry_at=(timezone.now() + timedelta(minutes=min(60, 5 * 2 ** min(attempts - 1, 4)))).isoformat())
            raise error


def _process_paid_domain_item(order_item, cloudflare_client=None):
    item_metadata = order_item.metadata or {}
    domain = normalize_domain_name(item_metadata.get("domain", ""))
    registrant = dict(order_item.order.metadata or {})
    registrant["customer_email"] = order_item.order.customer.email
    registrant["contact_phone"] = registrant.get("contact_phone", "").strip()
    if domain.endswith(".co.zw"):
        missing = [
            key
            for key in ("registrant_name", "physical_address", "physical_city", "physical_country")
            if not registrant.get(key, "").strip()
        ]
        if not registrant["contact_phone"]:
            missing.append("contact_phone")
        if missing:
            raise DomainRegistrationError("Registrant contact and physical address details are incomplete.")

    existing_domain = DomainAsset.objects.filter(
        domain_name__iexact=domain,
        customer_service__customer=order_item.order.customer,
        status=DomainAsset.Status.ACTIVE,
    ).select_related("customer_service").first()
    if existing_domain:
        service = existing_domain.customer_service
        extend_service_period(service, order_item)
        existing_domain.expires_at = service.expires_at
        existing_domain.save(update_fields=("expires_at", "updated_at"))
        return service

    with transaction.atomic():
        service = CustomerService.objects.select_for_update().filter(order_item=order_item).first()
        if service is None:
            started_at = timezone.now()
            service = CustomerService.objects.create(
                customer=order_item.order.customer,
                product=order_item.product,
                order_item=order_item,
                status=CustomerService.Status.PROVISIONING,
                started_at=started_at,
                provisioning_data={"domain_registration": {"status": "pending"}},
            )
            extend_service_period(service, order_item, now=started_at)
        domain_asset, created = DomainAsset.objects.get_or_create(
            domain_name=domain,
            defaults={
                "customer_service": service,
                "registrar": "ZISPA" if domain.endswith(".co.zw") else "Manual registrar",
                "status": DomainAsset.Status.PENDING,
                "expires_at": service.expires_at,
            },
        )
        if service.expires_at and domain_asset.expires_at != service.expires_at:
            domain_asset.expires_at = service.expires_at
            domain_asset.save(update_fields=("expires_at", "updated_at"))
        if not created and domain_asset.customer_service_id != service.id:
            # A second paid order for the same pending domain must reuse the
            # original registration service. Never create another registry
            # record or another set of nameservers.
            canonical_service = CustomerService.objects.select_for_update().get(
                pk=domain_asset.customer_service_id,
            )
            canonical_progress = dict((canonical_service.provisioning_data or {}).get("domain_registration", {}))
            current_progress = dict((service.provisioning_data or {}).get("domain_registration", {}))
            if current_progress.get("status") == "merged" and current_progress.get("merged_into_service_uuid") == str(canonical_service.uuid):
                return canonical_service
            if canonical_progress.get("status") in {
                "zispa_submitted",
                "registrar_manual_required",
                "registered",
            }:
                return canonical_service
            if service.pk != canonical_service.pk:
                extend_service_period(canonical_service, order_item)
                domain_asset.expires_at = canonical_service.expires_at
                domain_asset.save(update_fields=("expires_at", "updated_at"))
                service.status = CustomerService.Status.CANCELLED
                service.provisioning_data = {
                    **(service.provisioning_data or {}),
                    "domain_registration": {
                        "status": "merged",
                        "merged_into_service_uuid": str(canonical_service.uuid),
                        "message": "This repeat purchase was merged into the existing domain registration.",
                    },
                }
                service.save(update_fields=("status", "provisioning_data", "updated_at"))
                service = canonical_service
                progress = canonical_progress
                if progress.get("status") in {"needs_attention", "rejected"} and (
                    progress.get("zispa_sent_at") or progress.get("zispa_send_attempted_at")
                ):
                    # An explicitly rejected submission may be restarted once.
                    # Keep the Cloudflare nameservers, but create a fresh draft
                    # and idempotency key for the corrected registrant data.
                    progress = {
                        key: value for key, value in progress.items()
                        if key not in {
                            "zispa_request_id", "zispa_draft_created_at",
                            "zispa_send_attempted_at", "zispa_sent_at",
                            "idempotency_key", "next_retry_at",
                        }
                    }
                    progress.update({"status": "pending", "message": "Corrected registration details are ready for a fresh submission."})
                    service.provisioning_data = {**(service.provisioning_data or {}), "domain_registration": progress}
                    service.save(update_fields=("provisioning_data", "updated_at"))
            # The original pending service remains the sole registration owner.
        dns_zone, _ = DNSZone.objects.get_or_create(domain=domain_asset)

    progress = dict((service.provisioning_data or {}).get("domain_registration", {}))
    if progress.get("status") in {
        "zispa_submitted",
        "registrar_manual_required",
        "registered",
    }:
        return service

    if domain.endswith(".co.zw") and not settings.ZISPA_SUBMISSIONS_ENABLED:
        _save_progress(service, status="awaiting_release", message="Your registration is queued for TechInn review.")
        return service

    if domain.endswith(".co.zw") and progress.get("zispa_request_id"):
        # The draft already owns the submitted nameservers and contact details.
        # Resume it without requiring another Cloudflare call or creating a new draft.
        _submit_zispa(service, domain, registrant, domain_asset.nameservers,
                      progress.get("nameserver_ips", []), order_item.pk)
        progress = (service.provisioning_data or {}).get("domain_registration", {})
        _save_progress(service, status="zispa_submitted" if progress.get("zispa_sent_at") else "zispa_draft_created",
                       next_retry_at=None)
        return service

    try:
        token = _provider_token()
        zone = (cloudflare_client or CloudflareClient()).onboard_zone(token, domain)
    except CloudflareError as error:
        raise DomainRegistrationError(str(error)) from error

    cloudflare_nameservers = zone["nameservers"]
    if len(cloudflare_nameservers) < 2:
        raise DomainRegistrationError("Cloudflare has not assigned two authoritative nameservers yet.")
    delegation_nameservers, nameserver_ips = _delegation_nameservers(
        registrant,
        cloudflare_nameservers,
    )
    dns_zone.external_zone_id = zone["id"]
    dns_zone.nameservers = cloudflare_nameservers
    dns_zone.status = (
        DNSZone.Status.ACTIVE
        if zone["status"] == "active"
        else DNSZone.Status.PENDING
    )
    dns_zone.save(update_fields=("external_zone_id", "nameservers", "status", "updated_at"))
    domain_asset.nameservers = delegation_nameservers
    domain_asset.save(update_fields=("nameservers", "updated_at"))

    progress.update({
        "status": "cloudflare_ready",
        "cloudflare_zone_id": zone["id"],
        "cloudflare_status": zone["status"],
        "cloudflare_nameservers": cloudflare_nameservers,
        "delegation_nameservers": delegation_nameservers,
        "nameserver_ips": nameserver_ips,
    })
    service.provisioning_data = {
        **(service.provisioning_data or {}),
        "domain_registration": progress,
    }
    service.save(update_fields=("provisioning_data", "updated_at"))

    if not domain.endswith(".co.zw"):
        progress["status"] = "registrar_manual_required"
        progress["message"] = "Cloudflare zone is ready; this extension is not handled by the ZISPA bridge."
    else:
        _submit_zispa(
            service,
            domain,
            registrant,
            delegation_nameservers,
            nameserver_ips,
            order_item.pk,
        )
        progress = {
            **dict((service.provisioning_data or {}).get("domain_registration", {})),
            **progress,
        }
        progress["status"] = (
            "zispa_submitted"
            if progress.get("zispa_sent_at")
            else "zispa_draft_created"
        )

    service.provisioning_data = {
        **(service.provisioning_data or {}),
        "domain_registration": progress,
    }
    service.save(update_fields=("provisioning_data", "updated_at"))
    return service
