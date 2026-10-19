from smtplib import SMTPException


from apps.services.customer_services import service_dashboard_links
from django.conf import settings
from django.core.cache import cache
from django.core.management import call_command
import json

from django.db import transaction
from django.db.models import Prefetch
from django.utils import timezone
from rest_framework import generics, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.services.models import (
    CustomerService,
    DNSRecord,
    DNSZone,
    DomainAsset,
    HostingAccount,
    HostingWebsite,
    HostingResource,
    Mailbox,
    MailboxAccess,
    ProviderConnection,
    ProvisioningAction,
    ServiceAuditEvent,
    ServiceMember,
)
from apps.services.permissions import accessible_services_for, require_service_permission
from apps.services.storage import mailbox_storage_budget
from apps.services.fields import encrypt_secret
from apps.services.providers.cloudflare import CloudflareClient, CloudflareError, cloudflare_credentials
from apps.services.serializers import (
    CloudflareZoneConnectSerializer,
    DNSRecordSerializer,
    DNSZoneSerializer,
    CloudflareZoneLinkSerializer,
    DomainAssetSerializer,
    HostingAccountSerializer,
    HostingPrimaryDomainSerializer,
    ServiceDomainSelectionSerializer,
    HostingWebsiteCreateSerializer,
    HostingWebsiteSerializer,
    MailboxCreateSerializer,
    MailboxSerializer,
    MailboxAccessSerializer,
    ProviderConnectionSerializer,
    ProvisioningActionSerializer,
    ServiceAuditEventSerializer,
    ServiceMemberSerializer,
)
from apps.services.domain_availability import check_domain_availability, normalize_domain_name
from apps.orders.models import Order


def _queue_action(service, actor, action_type, payload):
    return ProvisioningAction.objects.create(
        customer_service=service,
        requested_by=actor,
        action_type=action_type,
        payload=payload,
    )


def _audit(service, actor, event_type, entity_type, entity_id, payload):
    ServiceAuditEvent.objects.create(
        customer_service=service,
        actor=actor,
        event_type=event_type,
        entity_type=entity_type,
        entity_id=str(entity_id),
        payload=payload,
    )


def _sync_mailbox_resource(account):
    resource = account.resources.filter(
        resource_type=HostingResource.ResourceType.EMAIL_ACCOUNTS
    ).first()
    if resource:
        resource.used_value = account.mailboxes.exclude(
            status__in=(Mailbox.Status.DELETED, Mailbox.Status.DELETING)
        ).count()
        resource.measured_at = timezone.now()
        resource.save(update_fields=("used_value", "measured_at"))


def _cloudflare_token(connection):
    try:
        credentials = json.loads(connection.credentials)
        token = cloudflare_credentials(credentials)
    except (json.JSONDecodeError, KeyError, TypeError, CloudflareError) as error:
        raise ValidationError({"credentials": "Cloudflare connection has invalid stored credentials."}) from error
    return token


def _domain_availability(domain_name):
    if DomainAsset.objects.filter(domain_name__iexact=domain_name).exists():
        return {"available": False, "status": "taken", "method": "techinn"}
    return check_domain_availability(domain_name)


class CustomerServiceQueryMixin:
    permission_classes = [IsAuthenticated]

    def get_service_queryset(self):
        return accessible_services_for(self.request.user)


class DashboardView(CustomerServiceQueryMixin, generics.GenericAPIView):
    def get(self, request):
        # Reconcile paid orders on dashboard load as a safety net for a payment
        # callback that completed before the service-record sync ran. The sync
        # is idempotent and keeps paid services visible as pending immediately.
        from apps.services.customer_services import sync_paid_services
        for paid_order in Order.objects.filter(customer=request.user, status__in=("paid", "completed")).only("id"):
            sync_paid_services(paid_order)
        services = (
            self.get_service_queryset()
            .select_related("product", "product__service_type", "order_item__order", "hosting_account__primary_domain")
            .prefetch_related(
                "domains__dns_zone__records",
                "hosting_account__primary_domain__dns_zone__records",
                "hosting_account__resources",
                "hosting_account__websites",
                "hosting_account__mailboxes__domain",
                "instances",
                Prefetch(
                    "members",
                    queryset=ServiceMember.objects.filter(customer=request.user),
                    to_attr="current_user_memberships",
                ),
            )
        )
        pending_mailbox_actions = {
            action.payload.get("mailbox_id"): action.action_type
            for action in ProvisioningAction.objects.filter(
                customer_service__in=services,
                status__in=(ProvisioningAction.Status.PENDING, ProvisioningAction.Status.PROCESSING),
                action_type__startswith="mailbox_",
            ).only("payload", "action_type").order_by("id")
        }
        results = []
        for service in services:
            is_owner = service.customer_id == request.user.id
            membership = service.current_user_memberships[0] if service.current_user_memberships else None
            permissions = {
                "can_manage_domains": bool(is_owner or (membership and membership.can_manage_domains)),
                "can_manage_dns": bool(is_owner or (membership and membership.can_manage_dns)),
                "can_manage_hosting": bool(is_owner or (membership and membership.can_manage_hosting)),
                "can_manage_email": bool(is_owner or (membership and membership.can_manage_email)),
                "can_view_billing": bool(is_owner or (membership and membership.can_view_billing)),
            }
            if service.product.service_type.slug == "email-hosting":
                permissions.update({
                    "can_manage_domains": False,
                    "can_manage_dns": False,
                    "can_manage_hosting": False,
                    "can_manage_email": bool(is_owner or (membership and membership.can_manage_email)),
                })
            try:
                account = service.hosting_account
                security = dict((service.provisioning_data or {}).get("security", {}))
                hosting = {
                    "id": account.id,
                    "status": account.status,
                    "server_name": "Hosting server",
                    "username": account.username,
                    "primary_domain": account.primary_domain.domain_name if account.primary_domain else None,
                    "domain_status": account.primary_domain.status if account.primary_domain else None,
                    "preview_url": (service.provisioning_data or {}).get("preview_url"),
                    "certificate_status": security.get("certificate_status") or ("error" if security.get("certificate_error") else "not_installed"),
                    "certificate_error": security.get("certificate_error", ""),
                    "websites": HostingWebsiteSerializer(account.websites.all(), many=True).data,
                    "resources": [
                        {
                            "type": resource.resource_type,
                            "limit": resource.limit_value,
                            "used": resource.used_value,
                            "unit": resource.unit,
                        }
                        for resource in account.resources.all()
                    ],
                    "mailboxes": [
                        {
                            "id": mailbox.id,
                            "email_address": mailbox.email_address,
                            "webmail_url": f"https://{mailbox.effective_domain}/webmail/",
                            "quota_mb": mailbox.quota_mb,
                            "used_mb": mailbox.used_mb,
                            "status": mailbox.status,
                            "error_message": mailbox.last_error,
                            "pending_action": pending_mailbox_actions.get(mailbox.id),
                        }
                        for mailbox in account.mailboxes.exclude(status=Mailbox.Status.DELETED)
                    ],
                }
            except HostingAccount.DoesNotExist:
                hosting = None

            service_domains = list(service.domains.all())
            primary_domain = getattr(getattr(service, "hosting_account", None), "primary_domain", None)
            if primary_domain and primary_domain.status == DomainAsset.Status.ACTIVE:
                if all(domain.id != primary_domain.id for domain in service_domains):
                    service_domains.append(primary_domain)
            if service.product.service_type.slug == "email-hosting" and permissions["can_manage_email"]:
                email_domains = DomainAsset.objects.filter(
                    customer_service__in=self.get_service_queryset(),
                    status=DomainAsset.Status.ACTIVE,
                    id__in=HostingAccount.objects.filter(
                        status=HostingAccount.Status.ACTIVE,
                        primary_domain__isnull=False,
                    ).values("primary_domain_id"),
                ).select_related("customer_service").order_by("domain_name")
                for candidate in email_domains:
                    try:
                        require_service_permission(request.user, candidate.customer_service, "can_manage_email")
                    except PermissionDenied:
                        continue
                    if all(domain.id != candidate.id for domain in service_domains):
                        service_domains.append(candidate)
            domains = []
            for domain in service_domains:
                try:
                    zone = domain.dns_zone
                    records = [
                        {
                            "id": record.id,
                            "name": record.name,
                            "record_type": record.record_type,
                            "content": record.content,
                            "ttl": record.ttl,
                            "priority": record.priority,
                            "proxied": record.proxied,
                            "synced_at": record.synced_at,
                        }
                        for record in zone.records.all()
                    ]
                    dns = {
                        "id": zone.id,
                        "status": zone.status,
                        "dnssec_enabled": zone.dnssec_enabled,
                        "last_synced_at": zone.last_synced_at,
                        "records": records,
                    }
                except DNSZone.DoesNotExist:
                    dns = None
                domains.append(
                    {
                        "id": domain.id,
                        "name": domain.domain_name,
                        "permissions": permissions,
                        "status": domain.status,
                        "expires_at": domain.expires_at,
                        "auto_renew": domain.auto_renew,
                        "nameservers": domain.nameservers,
                        "registration": DomainAssetSerializer().get_registration(domain),
                        "dns": dns,
                    }
                )

            if hosting:
                if not permissions["can_manage_email"]:
                    hosting["mailboxes"] = []
                if not permissions["can_manage_hosting"]:
                    hosting["username"] = ""
                    hosting["websites"] = []
            if not permissions["can_manage_dns"]:
                for domain in domains:
                    domain["dns"] = None

            domain_options = []
            if service.product.service_type.slug in {"web-hosting", "email-hosting"}:
                option_domains = DomainAsset.objects.filter(
                    customer_service__customer=service.customer,
                    status__in=(DomainAsset.Status.ACTIVE, DomainAsset.Status.PENDING, DomainAsset.Status.TRANSFER_PENDING),
                ).order_by("domain_name")
                selected_domain_id = (service.provisioning_data or {}).get("selected_domain_id")
                for option in option_domains:
                    domain_options.append({
                        "id": option.id,
                        "name": option.domain_name,
                        "status": option.status,
                        "selected": str(option.id) == str(selected_domain_id),
                    })

            billing_interval = (service.provisioning_data or {}).get("billing_interval")
            if not billing_interval and service.order_item_id:
                billing_interval = (service.order_item.metadata or {}).get("billing_interval")
            # The portal uses the shorter renewal labels, while preserving the
            # annual/monthly distinction from the original purchase.
            billing_interval = {
                "annually": "yearly",
                "annual": "yearly",
            }.get(billing_interval, billing_interval)
            results.append(
                {
                    "uuid": service.uuid,
                    "product": service.product.name,
                    "product_slug": service.product.slug,
                    "service_type": service.product.service_type.slug,
                    "service_type_name": service.product.service_type.name,
                    "dashboards": service_dashboard_links(service, is_owner or permissions["can_manage_hosting"]),
                    "billing": {"unit_price": str(service.order_item.unit_price), "currency": service.order_item.order.currency, "next_due_at": service.next_due_at, "interval": billing_interval} if permissions["can_view_billing"] and service.order_item_id else None,
                    "renewal": {"href": f"/dashboard/billing/?renew={service.uuid}#billing-payment", "service_uuid": str(service.uuid)} if permissions["can_view_billing"] and service.expires_at else None,
                    "is_owner": is_owner,
                    "permissions": permissions,
                    "status": service.status,
                    "started_at": service.started_at,
                    "expires_at": service.expires_at,
                    "next_due_at": service.next_due_at,
                    "auto_renew": service.auto_renew,
                    "hosting": hosting,
                    "domains": domains,
                    "domain_options": domain_options,
                }
            )
        connections = ProviderConnection.objects.filter(
            customer=request.user,
            scope=ProviderConnection.Scope.CUSTOMER,
        ).values("id", "provider", "name", "status", "last_verified_at")
        return Response({"services": results, "provider_connections": list(connections)})


class DomainListView(CustomerServiceQueryMixin, generics.ListAPIView):
    serializer_class = DomainAssetSerializer

    def get_queryset(self):
        return DomainAsset.objects.filter(
            customer_service__in=self.get_service_queryset()
        ).select_related("customer_service")


class DomainAvailabilityView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        try:
            domain_name = normalize_domain_name(request.query_params.get("domain", ""))
            result = _domain_availability(domain_name)
        except ValueError as error:
            raise ValidationError({"domain": str(error)}) from error
        return Response(
            {
                "domain_name": domain_name,
                **result,
                "availability_note": (
                    (
                        "Checked directly with ZISPA. Availability can change before registration; "
                        "domains are first come, first served and are not held."
                    )
                    if result["method"] == "zispa"
                    else (
                        "Availability is estimated from DNS/WHOIS/HTTP checks. Domains are first come, "
                        "first served and registration is manually verified. If the name is taken before "
                        "registration is completed, TechInn will let you know."
                    )
                ),
            }
        )


class ServiceDomainSelectionView(CustomerServiceQueryMixin, APIView):
    """Attach an owned/connected domain to a paid hosting or email service.

    This is intentionally separate from CyberPanel provisioning: selecting a domain
    records the customer's intent, while the worker provisions only after the
    selected domain is active.
    """

    @transaction.atomic
    def post(self, request, service_uuid):
        serializer = ServiceDomainSelectionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            service = self.get_service_queryset().select_for_update().select_related("product__service_type").get(uuid=service_uuid)
        except CustomerService.DoesNotExist as error:
            raise NotFound("Service was not found.") from error
        service_type = service.product.service_type.slug
        if service_type not in {"web-hosting", "email-hosting"}:
            raise ValidationError({"detail": "Only hosting and email services can be assigned a domain."})
        require_service_permission(request.user, service, "can_manage_hosting" if service_type == "web-hosting" else "can_manage_email")
        if service.status not in ("pending", "provisioning", "failed"):
            raise ValidationError({"detail": "This service has already been set up. Contact support to move it to another domain."})
        expiry = service.expires_at or service.next_due_at
        if expiry and expiry <= timezone.now():
            raise ValidationError({"detail": "Renew this service before setting up a domain."})
        try:
            domain = DomainAsset.objects.get(
                domain_name__iexact=serializer.validated_data["domain_name"].strip().rstrip("."),
                customer_service__customer=service.customer,
                status__in=(DomainAsset.Status.ACTIVE, DomainAsset.Status.PENDING, DomainAsset.Status.TRANSFER_PENDING),
            )
        except DomainAsset.DoesNotExist as error:
            raise ValidationError({"domain_name": "Enter a purchased or connected domain linked to this account."}) from error
        data = dict(service.provisioning_data or {})
        account = getattr(service, "hosting_account", None)
        if account and account.primary_domain_id and account.primary_domain_id != domain.id:
            raise ValidationError({"detail": "Setup has started for another domain. Contact support to change it."})
        data["selected_domain_id"] = domain.id
        data["selected_domain"] = domain.domain_name
        service.provisioning_data = data
        service.save(update_fields=("provisioning_data", "updated_at"))
        account = getattr(service, "hosting_account", None)
        if account and account.status == HostingAccount.Status.ACTIVE:
            account.primary_domain = domain
            account.save(update_fields=("primary_domain", "updated_at"))
        _audit(service, request.user, "service.domain.selected", "domain", domain.id, {"domain": domain.domain_name})
        return Response({"service_uuid": str(service.uuid), "domain_id": domain.id, "domain": domain.domain_name, "status": domain.status})


class DNSZoneViewSet(CustomerServiceQueryMixin, viewsets.ReadOnlyModelViewSet):
    serializer_class = DNSZoneSerializer

    def get_queryset(self):
        return DNSZone.objects.filter(
            domain__customer_service__in=self.get_service_queryset()
        ).prefetch_related("records", "domain")

    @action(detail=True, methods=["post"])
    def sync(self, request, pk=None):
        zone = self.get_object()
        service = zone.domain.customer_service
        require_service_permission(request.user, service, "can_manage_dns")
        connection = zone.provider_connection
        if (
            not connection
            or connection.provider != ProviderConnection.Provider.CLOUDFLARE
            or connection.status != ProviderConnection.Status.ACTIVE
        ):
            raise ValidationError({"detail": "Connect and verify an active Cloudflare account for this zone."})
        try:
            client = CloudflareClient()
            token = _cloudflare_token(connection)
            live_zone = client.get_zone(token, zone.external_zone_id)
            records = client.list_dns_records(token, zone.external_zone_id)
        except CloudflareError as error:
            raise ValidationError({"detail": str(error)}) from error
        live_nameservers = live_zone.get("name_servers", [])
        if not isinstance(live_nameservers, list) or any(not isinstance(item, str) for item in live_nameservers):
            raise ValidationError({"detail": "The DNS provider returned an invalid nameserver list."})
        allowed_types = {choice for choice, _ in DNSRecord.RecordType.choices}
        imported = 0
        external_ids = set()
        for item in records:
            if item.get("type") not in allowed_types or not item.get("id"):
                continue
            external_ids.add(item["id"])
            DNSRecord.objects.update_or_create(
                zone=zone,
                external_record_id=item["id"],
                defaults={
                    "name": item["name"],
                    "record_type": item["type"],
                    "content": item["content"],
                    "ttl": max(int(item.get("ttl", 3600)), 1),
                    "priority": item.get("priority"),
                    "proxied": bool(item.get("proxied", False)),
                    "synced_at": timezone.now(),
                },
            )
            imported += 1
        stale = DNSRecord.objects.filter(zone=zone, external_record_id__gt="").exclude(
            external_record_id__in=external_ids
        )
        removed = stale.count()
        stale.delete()
        zone.last_synced_at = timezone.now()
        zone.status = DNSZone.Status.ACTIVE
        zone.nameservers = live_nameservers
        zone.save(update_fields=("last_synced_at", "status", "nameservers", "updated_at"))
        # Keep the customer-facing domain nameserver table in step with the
        # live nameservers returned by Cloudflare, as the established portal does.
        domain = zone.domain
        domain.nameservers = live_nameservers
        domain.save(update_fields=("nameservers", "updated_at"))
        _audit(
            service,
            request.user,
            "dns.zone.synced",
            "dns_zone",
            zone.id,
            {"domain": zone.domain.domain_name, "records_imported": imported, "stale_records_removed": removed},
        )
        return Response({
            "domain": zone.domain.domain_name,
            "nameservers": live_nameservers,
            "records_imported": imported,
            "stale_records_removed": removed,
        })


class DomainActivationCheckView(CustomerServiceQueryMixin, APIView):
    """Check this customer's pending domains when the Domains view is visited.

    The cache key makes the operation safe to call from a browser visit while
    preventing refreshes or multiple open tabs from repeatedly querying the
    registrar. The scheduled worker remains responsible for routine checks.
    """

    cooldown_seconds = 20 * 60

    def post(self, request):
        key = f"domain-activation-check:{request.user.pk}"
        if not cache.add(key, timezone.now().isoformat(), timeout=self.cooldown_seconds):
            return Response({"checked": False, "rate_limited": True, "retry_after": self.cooldown_seconds})
        try:
            call_command("check_domain_activations", customer_id=request.user.pk, limit=50)
        except Exception:
            cache.delete(key)
            raise
        return Response({"checked": True, "rate_limited": False})


class DNSRecordViewSet(CustomerServiceQueryMixin, viewsets.ModelViewSet):
    serializer_class = DNSRecordSerializer
    http_method_names = ["get", "post", "patch", "delete", "head", "options"]

    def get_queryset(self):
        return DNSRecord.objects.filter(
            zone__domain__customer_service__in=self.get_service_queryset()
        ).select_related("zone__domain__customer_service")

    def _record_context(self, instance=None):
        zone_id = self.request.data.get("zone")
        if instance:
            zone = instance.zone
        elif zone_id:
            try:
                zone = DNSZone.objects.select_related("domain__customer_service").get(
                    id=zone_id,
                    domain__customer_service__in=self.get_service_queryset(),
                )
            except DNSZone.DoesNotExist as error:
                raise ValidationError({"zone": "DNS zone not found for this customer."}) from error
        else:
            raise ValidationError({"zone": "A customer-owned DNS zone is required."})
        return zone, zone.domain.customer_service

    def perform_create(self, serializer):
        zone, service = self._record_context()
        require_service_permission(self.request.user, service, "can_manage_dns")
        with transaction.atomic():
            record = serializer.save()
            payload = {
                "record_id": record.id,
                "zone_id": zone.id,
                "domain": zone.domain.domain_name,
                "name": record.name,
                "record_type": record.record_type,
                "content": record.content,
                "ttl": record.ttl,
                "priority": record.priority,
                "proxied": record.proxied,
            }
            _queue_action(service, self.request.user, ProvisioningAction.ActionType.DNS_UPSERT, payload)
            _audit(service, self.request.user, "dns.record.created", "dns_record", record.id, payload)

    def perform_update(self, serializer):
        zone, service = self._record_context(self.get_object())
        require_service_permission(self.request.user, service, "can_manage_dns")
        with transaction.atomic():
            record = serializer.save()
            payload = {
                "record_id": record.id,
                "zone_id": zone.id,
                "domain": zone.domain.domain_name,
                "name": record.name,
                "record_type": record.record_type,
                "content": record.content,
                "ttl": record.ttl,
                "priority": record.priority,
                "proxied": record.proxied,
            }
            _queue_action(service, self.request.user, ProvisioningAction.ActionType.DNS_UPSERT, payload)
            _audit(service, self.request.user, "dns.record.updated", "dns_record", record.id, payload)

    def perform_destroy(self, instance):
        zone, service = self._record_context(instance)
        require_service_permission(self.request.user, service, "can_manage_dns")
        payload = {
            "record_id": instance.id,
            "zone_id": zone.id,
            "domain": zone.domain.domain_name,
            "name": instance.name,
            "record_type": instance.record_type,
            "external_record_id": instance.external_record_id,
        }
        with transaction.atomic():
            ProvisioningAction.objects.filter(
                customer_service=service,
                action_type=ProvisioningAction.ActionType.DNS_UPSERT,
                status=ProvisioningAction.Status.PENDING,
                payload__record_id=instance.id,
            ).update(status=ProvisioningAction.Status.CANCELLED)
            _queue_action(service, self.request.user, ProvisioningAction.ActionType.DNS_DELETE, payload)
            _audit(service, self.request.user, "dns.record.deleted", "dns_record", instance.id, payload)
            instance.delete()


class HostingAccountListView(CustomerServiceQueryMixin, generics.ListAPIView):
    serializer_class = HostingAccountSerializer

    def get_queryset(self):
        return HostingAccount.objects.filter(
            customer_service__in=self.get_service_queryset()
        ).select_related("customer_service", "primary_domain").prefetch_related("resources")


class HostingPrimaryDomainView(CustomerServiceQueryMixin, APIView):
    def patch(self, request, account_id):
        serializer = HostingPrimaryDomainSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            account = HostingAccount.objects.select_related("customer_service").get(
                pk=account_id,
                customer_service__in=self.get_service_queryset(),
            )
        except HostingAccount.DoesNotExist as error:
            raise NotFound("Hosting account was not found.") from error
        service = account.customer_service
        require_service_permission(request.user, service, "can_manage_hosting")
        if service.status != CustomerService.Status.ACTIVE or account.status != HostingAccount.Status.ACTIVE:
            raise ValidationError({"detail": "Only an active hosting account can change its primary domain."})
        try:
            domain = DomainAsset.objects.get(
                pk=serializer.validated_data["domain_id"],
                customer_service=service,
                status=DomainAsset.Status.ACTIVE,
            )
        except DomainAsset.DoesNotExist as error:
            raise ValidationError({"domain_id": "Choose an active domain linked to this hosting service."}) from error
        account.primary_domain = domain
        account.save(update_fields=("primary_domain", "updated_at"))
        _audit(
            service,
            request.user,
            "hosting.primary_domain.updated",
            "hosting_account",
            account.id,
            {"domain": domain.domain_name},
        )
        return Response(HostingAccountSerializer(account).data)


class HostingWebsiteCreateView(CustomerServiceQueryMixin, APIView):
    @transaction.atomic
    def post(self, request, account_id):
        serializer = HostingWebsiteCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            account = HostingAccount.objects.select_for_update().select_related(
                "customer_service__product__service_type",
                "customer_service__customer",
                "primary_domain",
            ).get(
                pk=account_id,
                customer_service__in=self.get_service_queryset(),
            )
        except HostingAccount.DoesNotExist as error:
            raise NotFound("Hosting account was not found.") from error

        service = account.customer_service
        require_service_permission(request.user, service, "can_manage_hosting")
        expiry = service.expires_at or service.next_due_at
        if (
            service.status not in (CustomerService.Status.ACTIVE, CustomerService.Status.PROVISIONING)
            or account.status != HostingAccount.Status.ACTIVE
            or service.product.service_type.slug != "web-hosting"
            or (expiry and expiry <= timezone.now())
            or not account.primary_domain
            or account.primary_domain.status not in (DomainAsset.Status.ACTIVE, DomainAsset.Status.PENDING)
            or not account.username
        ):
            raise ValidationError({"detail": "Subdomains require an active hosting plan and domain."})
        require_service_permission(request.user, service, "can_manage_hosting")

        subdomain = serializer.validated_data["subdomain"]
        domain_name = f"{subdomain}.{account.primary_domain.domain_name}".lower()
        if len(domain_name) > 50:
            raise ValidationError({"subdomain": "The full subdomain must be 50 characters or fewer."})

        with transaction.atomic():
            existing = HostingWebsite.objects.select_for_update().filter(
                domain_name__iexact=domain_name
            ).first()
            if existing and existing.hosting_account_id != account.id:
                raise ValidationError({"subdomain": "This subdomain is already in use."})
            if DomainAsset.objects.filter(domain_name__iexact=domain_name).exists():
                raise ValidationError({"subdomain": "This subdomain already exists in your domain records."})

            if existing and existing.status == HostingWebsite.Status.ACTIVE:
                return Response(HostingWebsiteSerializer(existing).data)
            if existing and existing.status == HostingWebsite.Status.PENDING:
                return Response(HostingWebsiteSerializer(existing).data, status=status.HTTP_202_ACCEPTED)

            if existing:
                existing.status = HostingWebsite.Status.PENDING
                existing.document_root = ""
                existing.last_error = ""
                existing.save(update_fields=("status", "document_root", "last_error", "updated_at"))
                website = existing
            else:
                website = HostingWebsite.objects.create(
                    hosting_account=account,
                    domain_name=domain_name,
                    master_domain=account.primary_domain.domain_name,
                    status=HostingWebsite.Status.PENDING,
                )
            _queue_action(
                service,
                request.user,
                ProvisioningAction.ActionType.HOSTING_WEBSITE_CREATE,
                {"hosting_website_id": website.id},
            )
            _audit(
                service,
                request.user,
                "hosting.website.create_requested",
                "hosting_website",
                website.id,
                {"domain": domain_name},
            )
        return Response(HostingWebsiteSerializer(website).data, status=status.HTTP_202_ACCEPTED)


class HostingWebsiteCertificateView(CustomerServiceQueryMixin, APIView):
    @transaction.atomic
    def post(self, request, account_id, website_id):
        try:
            account = HostingAccount.objects.select_for_update().select_related(
                "customer_service__customer",
                "primary_domain",
            ).get(
                pk=account_id,
                customer_service__in=self.get_service_queryset(),
            )
        except HostingAccount.DoesNotExist as error:
            raise NotFound("Hosting account was not found.") from error

        service = account.customer_service
        require_service_permission(request.user, service, "can_manage_hosting")
        expiry = service.expires_at or service.next_due_at
        if (
            service.status != CustomerService.Status.ACTIVE
            or account.status != HostingAccount.Status.ACTIVE
            or (expiry and expiry <= timezone.now())
            or not account.primary_domain
        ):
            raise ValidationError({"detail": "Certificate installation requires an active hosting account."})
        require_service_permission(request.user, service, "can_manage_hosting")

        try:
            website = HostingWebsite.objects.select_for_update().get(
                pk=website_id,
                hosting_account=account,
                status=HostingWebsite.Status.ACTIVE,
            )
        except HostingWebsite.DoesNotExist as error:
            raise NotFound("The selected active website was not found.") from error

        if ProvisioningAction.objects.filter(
            customer_service=service,
            action_type=ProvisioningAction.ActionType.HOSTING_WEBSITE_CERTIFICATE,
            status__in=(ProvisioningAction.Status.PENDING, ProvisioningAction.Status.PROCESSING),
            payload__hosting_website_id=website.id,
        ).exists():
            website.certificate_status = HostingWebsite.CertificateStatus.PENDING
            website.certificate_error = ""
            website.save(update_fields=("certificate_status", "certificate_error", "updated_at"))
            return Response(HostingWebsiteSerializer(website).data, status=status.HTTP_202_ACCEPTED)

        website.certificate_status = HostingWebsite.CertificateStatus.PENDING
        website.certificate_error = ""
        website.save(update_fields=("certificate_status", "certificate_error", "updated_at"))
        _queue_action(
            service,
            request.user,
            ProvisioningAction.ActionType.HOSTING_WEBSITE_CERTIFICATE,
            {"hosting_website_id": website.id},
        )
        _audit(
            service,
            request.user,
            "hosting.website.certificate_requested",
            "hosting_website",
            website.id,
            {"domain": website.domain_name},
        )
        return Response(HostingWebsiteSerializer(website).data, status=status.HTTP_202_ACCEPTED)


class HostingPrimaryCertificateView(CustomerServiceQueryMixin, APIView):
    """Queue installation of the primary hosting domain certificate.

    Primary certificates are deliberately user initiated. Domain activation
    prepares DNS, while this action is the explicit point at which the owner
    asks TechInn's VPS issuer to install the certificate.
    """

    @transaction.atomic
    def post(self, request, account_id):
        try:
            account = HostingAccount.objects.select_for_update().select_related(
                "customer_service__customer", "primary_domain"
            ).get(pk=account_id, customer_service__in=self.get_service_queryset())
        except HostingAccount.DoesNotExist as error:
            raise NotFound("Hosting account was not found.") from error

        service = account.customer_service
        require_service_permission(request.user, service, "can_manage_hosting")
        expiry = service.expires_at or service.next_due_at
        if (
            service.status != CustomerService.Status.ACTIVE
            or account.status != HostingAccount.Status.ACTIVE
            or (expiry and expiry <= timezone.now())
            or not account.primary_domain
            or account.primary_domain.status != DomainAsset.Status.ACTIVE
        ):
            raise ValidationError({"detail": "Certificate installation requires an active hosting account and domain."})

        pending = ProvisioningAction.objects.filter(
            customer_service=service,
            action_type=ProvisioningAction.ActionType.HOSTING_WEBSITE_CERTIFICATE,
            status__in=(ProvisioningAction.Status.PENDING, ProvisioningAction.Status.PROCESSING),
            payload__hosting_account_id=account.id,
        ).exists()
        data = dict(service.provisioning_data or {})
        security = dict(data.get("security", {}))
        security.update({
            "certificate_status": "pending",
            "certificate_error": "",
            "certificate_requested_at": timezone.now().isoformat(),
        })
        data["security"] = security
        service.provisioning_data = data
        service.save(update_fields=("provisioning_data", "updated_at"))
        if not pending:
            _queue_action(
                service,
                request.user,
                ProvisioningAction.ActionType.HOSTING_WEBSITE_CERTIFICATE,
                {"hosting_account_id": account.id, "domain": account.primary_domain.domain_name},
            )
            _audit(
                service,
                request.user,
                "hosting.primary_certificate_requested",
                "hosting_account",
                account.id,
                {"domain": account.primary_domain.domain_name},
            )
        return Response(
            {
                "status": "pending",
                "domain": account.primary_domain.domain_name,
                "certificate_status": "pending",
            },
            status=status.HTTP_202_ACCEPTED,
        )


class MailboxViewSet(CustomerServiceQueryMixin, viewsets.ModelViewSet):
    http_method_names = ["get", "post", "patch", "delete", "head", "options"]

    def require_idle(self, mailbox):
        if ProvisioningAction.objects.filter(
            customer_service=mailbox.hosting_account.customer_service,
            payload__mailbox_id=mailbox.id,
            status__in=(ProvisioningAction.Status.PENDING, ProvisioningAction.Status.PROCESSING),
            action_type__startswith="mailbox_",
        ).exists():
            raise ValidationError({"detail": "This mailbox already has an operation in progress. Please wait for it to finish."})

    def get_serializer_class(self):
        if self.action == "create":
            return MailboxCreateSerializer
        return MailboxSerializer

    def get_queryset(self):
        return Mailbox.objects.filter(
            hosting_account__customer_service__in=self.get_service_queryset()
        ).exclude(status=Mailbox.Status.DELETED).select_related(
            "domain", "hosting_account__customer_service"
        )

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        with transaction.atomic():
            # Serialize mailbox allocations per hosting account. Serializer validation
            # runs before the transaction, so a second concurrent request could
            # otherwise observe the same free storage and oversubscribe the plan.
            account = HostingAccount.objects.select_for_update().get(
                pk=serializer.validated_data["hosting_account"].pk
            )
            email_limit = account.resources.filter(
                resource_type=HostingResource.ResourceType.EMAIL_ACCOUNTS
            ).first()
            if email_limit and account.mailboxes.exclude(
                status__in=(Mailbox.Status.DELETED, Mailbox.Status.DELETING)
            ).count() >= email_limit.limit_value:
                raise ValidationError({"hosting_account_id": "This hosting plan has no mailbox slots remaining."})
            budget = mailbox_storage_budget(account)
            requested_mb = serializer.validated_data["quota_mb"]
            if budget:
                if budget.get("invalid_unit"):
                    raise ValidationError({"quota_mb": "Hosting disk allocation must use MB or GB units to validate mailbox quotas."})
                if requested_mb > budget["available_mb"]:
                    raise ValidationError({
                        "quota_mb": (
                            f"This mailbox needs {requested_mb:,} MB, but only {budget['available_mb']:,} MB "
                            "of this hosting plan's unallocated storage remains after website files and existing mailbox allocations."
                        )
                    })
            password = serializer.validated_data.pop("password")
            mailbox = serializer.save(hosting_account=account)
            service = mailbox.hosting_account.customer_service
            require_service_permission(request.user, service, "can_manage_email")
            _sync_mailbox_resource(mailbox.hosting_account)
            payload = {
                "mailbox_id": mailbox.id,
                "email_address": mailbox.email_address,
                "quota_mb": mailbox.quota_mb,
                "domain_id": mailbox.domain_id,
                "email_domain": mailbox.effective_domain,
                "password_encrypted": encrypt_secret(password),
            }
            _queue_action(service, request.user, ProvisioningAction.ActionType.MAILBOX_CREATE, payload)
            _audit(
                service,
                request.user,
                "mailbox.create.requested",
                "mailbox",
                mailbox.id,
                {key: value for key, value in payload.items() if key != "password_encrypted"},
            )
        return Response(MailboxSerializer(mailbox).data, status=status.HTTP_202_ACCEPTED)

    @action(detail=True, methods=["post"], url_path="retry")
    def retry(self, request, pk=None):
        mailbox = self.get_object()
        service = mailbox.hosting_account.customer_service
        require_service_permission(request.user, service, "can_manage_email")
        password = request.data.get("password")
        if not isinstance(password, str) or len(password) < 8 or len(password) > 128:
            raise ValidationError({"password": "Choose a password between 8 and 128 characters."})
        if mailbox.status != Mailbox.Status.ERROR:
            raise ValidationError({"detail": "Only a failed mailbox setup can be retried."})
        if service.status != CustomerService.Status.ACTIVE or (
            service.expires_at and service.expires_at <= timezone.now()
        ):
            raise ValidationError({"detail": "This email service is not in an active paid period."})
        with transaction.atomic():
            account = HostingAccount.objects.select_for_update().get(pk=account.pk)
            mailbox = Mailbox.objects.select_for_update().get(pk=mailbox.pk)
            self.require_idle(mailbox)
            mailbox.status = Mailbox.Status.PENDING
            mailbox.last_error = ""
            mailbox.save(update_fields=("status", "last_error", "updated_at"))
            payload = {
                "mailbox_id": mailbox.id,
                "email_address": mailbox.email_address,
                "quota_mb": mailbox.quota_mb,
                "domain_id": mailbox.domain_id,
                "email_domain": mailbox.effective_domain,
                "password_encrypted": encrypt_secret(password),
            }
            _queue_action(service, request.user, ProvisioningAction.ActionType.MAILBOX_CREATE, payload)
            _audit(
                service,
                request.user,
                "mailbox.create.retried",
                "mailbox",
                mailbox.id,
                {key: value for key, value in payload.items() if key != "password_encrypted"},
            )
        return Response({"detail": "Mailbox setup queued for retry."}, status=status.HTTP_202_ACCEPTED)

    def partial_update(self, request, *args, **kwargs):
        mailbox = self.get_object()
        account = mailbox.hosting_account
        service = account.customer_service
        require_service_permission(request.user, service, "can_manage_email")
        if set(request.data) != {"quota_mb"}:
            raise ValidationError({"detail": "Only mailbox quota can be changed through this endpoint."})
        if mailbox.status != Mailbox.Status.ACTIVE:
            raise ValidationError({"detail": "Only an active mailbox allocation can be changed."})
        serializer = MailboxSerializer(mailbox, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        requested_mb = serializer.validated_data["quota_mb"]
        if requested_mb < mailbox.used_mb:
            raise ValidationError({"quota_mb": f"This mailbox already uses {mailbox.used_mb:,} MB. Choose at least that much storage."})

        mailbox_storage_caps = {
            "email-essential": 2 * 1024,
            "email-team": 5 * 1024,
            "email-business-mail": 15 * 1024,
        }
        mailbox_cap = mailbox_storage_caps.get(service.product.slug)
        if mailbox_cap and requested_mb > mailbox_cap:
            raise ValidationError({"quota_mb": f"This email plan supports up to {mailbox_cap:,} MB per mailbox."})

        budget = mailbox_storage_budget(account, excluding_mailbox=mailbox)
        if budget:
            if budget.get("invalid_unit"):
                raise ValidationError({"quota_mb": "Hosting disk allocation must use MB or GB units to validate mailbox quotas."})
            if requested_mb > mailbox.quota_mb and requested_mb > budget["available_mb"]:
                raise ValidationError({"quota_mb": f"Only {budget['available_mb']:,} MB is available for this mailbox."})

        with transaction.atomic():
            account = HostingAccount.objects.select_for_update().get(pk=account.pk)
            mailbox = Mailbox.objects.select_for_update().get(pk=mailbox.pk)
            self.require_idle(mailbox)
            if mailbox.status != Mailbox.Status.ACTIVE:
                raise ValidationError({"detail": "Only an active mailbox allocation can be changed."})
            if requested_mb < mailbox.used_mb:
                raise ValidationError({"quota_mb": f"This mailbox already uses {mailbox.used_mb:,} MB. Choose at least that much storage."})
            current_budget = mailbox_storage_budget(account, excluding_mailbox=mailbox)
            if current_budget:
                if current_budget.get("invalid_unit"):
                    raise ValidationError({"quota_mb": "Hosting disk allocation must use MB or GB units to validate mailbox quotas."})
                if requested_mb > mailbox.quota_mb and requested_mb > current_budget["available_mb"]:
                    raise ValidationError({"quota_mb": f"Only {current_budget['available_mb']:,} MB is available for this mailbox."})
            previous_quota_mb = mailbox.quota_mb
            mailbox.quota_mb = requested_mb
            mailbox.last_error = ""
            mailbox.save(update_fields=("quota_mb", "last_error", "updated_at"))
            payload = {
                "mailbox_id": mailbox.id,
                "email_address": mailbox.email_address,
                "quota_mb": mailbox.quota_mb,
                "previous_quota_mb": previous_quota_mb,
            }
            _queue_action(
                service,
                request.user,
                ProvisioningAction.ActionType.MAILBOX_UPDATE,
                payload,
            )
            _audit(service, request.user, "mailbox.allocation.updated", "mailbox", mailbox.id, payload)
        return Response(MailboxSerializer(mailbox).data)

    @action(detail=True, methods=["post"], url_path="clear-storage")
    def clear_storage(self, request, pk=None):
        mailbox = self.get_object()
        service = mailbox.hosting_account.customer_service
        require_service_permission(request.user, service, "can_manage_email")
        if request.data.get("confirm") is not True:
            raise ValidationError({"confirm": "Confirm that all messages in this mailbox should be permanently deleted."})
        if mailbox.status != Mailbox.Status.ACTIVE:
            raise ValidationError({"detail": "Only an active mailbox can have its stored messages cleared."})
        if service.status != CustomerService.Status.ACTIVE or (
            service.expires_at and service.expires_at <= timezone.now()
        ):
            raise ValidationError({"detail": "This email service is not in an active paid period."})

        with transaction.atomic():
            mailbox = Mailbox.objects.select_for_update().get(pk=mailbox.pk)
            self.require_idle(mailbox)
            if mailbox.status != Mailbox.Status.ACTIVE:
                raise ValidationError({"detail": "Only an active mailbox can have its stored messages cleared."})
            mailbox.status = Mailbox.Status.CLEARING
            mailbox.last_error = ""
            mailbox.save(update_fields=("status", "last_error", "updated_at"))
            payload = {"mailbox_id": mailbox.id, "email_address": mailbox.email_address}
            _queue_action(
                service,
                request.user,
                ProvisioningAction.ActionType.MAILBOX_CLEAR_STORAGE,
                payload,
            )
            _audit(service, request.user, "mailbox.storage.clear_requested", "mailbox", mailbox.id, payload)
        return Response({"detail": "Mailbox storage clear queued."}, status=status.HTTP_202_ACCEPTED)

    def destroy(self, request, *args, **kwargs):
        mailbox = self.get_object()
        require_service_permission(request.user, mailbox.hosting_account.customer_service, "can_manage_email")
        service = mailbox.hosting_account.customer_service
        with transaction.atomic():
            mailbox = Mailbox.objects.select_for_update().get(pk=mailbox.pk)
            self.require_idle(mailbox)
            if mailbox.status in (Mailbox.Status.CLEARING, Mailbox.Status.DELETING, Mailbox.Status.DELETED):
                raise ValidationError({"detail": "This mailbox already has an operation in progress."})
            mailbox.status = Mailbox.Status.DELETING
            mailbox.last_error = ""
            mailbox.save(update_fields=("status", "last_error", "updated_at"))
            _sync_mailbox_resource(mailbox.hosting_account)
            payload = {"mailbox_id": mailbox.id, "email_address": mailbox.email_address}
            _queue_action(service, request.user, ProvisioningAction.ActionType.MAILBOX_DELETE, payload)
            _audit(service, request.user, "mailbox.delete.requested", "mailbox", mailbox.id, payload)
        return Response({"detail": "Mailbox deletion queued.", "status": "deleting"}, status=status.HTTP_202_ACCEPTED)

    @action(detail=True, methods=["post"], url_path="request-password-reset")
    def request_password_reset(self, request, pk=None):
        mailbox = self.get_object()
        service = mailbox.hosting_account.customer_service
        require_service_permission(request.user, service, "can_manage_email")
        if mailbox.status != Mailbox.Status.ACTIVE or service.status != CustomerService.Status.ACTIVE or (
            service.expires_at and service.expires_at <= timezone.now()
        ):
            raise ValidationError({"detail": "Only an active mailbox password can be reset."})
        if not settings.EMAIL_HOST or not settings.DEFAULT_FROM_EMAIL:
            raise ValidationError({"detail": "Password verification email is not configured yet. Contact TechInn support."})
        from apps.accounts.otp import issue_otp, OTPCooldown
        try:
            issue_otp(request.user, purpose="mailbox", target=str(mailbox.pk))
        except OTPCooldown as error:
            return Response({"detail": str(error)}, status=status.HTTP_429_TOO_MANY_REQUESTS)
        except (SMTPException, OSError) as error:
            raise ValidationError({"detail": "The verification email could not be sent. Wait two minutes before trying again."}) from error
        return Response({"detail": "A verification code was sent to your account email."}, status=status.HTTP_202_ACCEPTED)

    @action(detail=True, methods=["post"], url_path="reset-password")
    @transaction.atomic
    def reset_password(self, request, pk=None):
        mailbox = self.get_object()
        mailbox = Mailbox.objects.select_for_update().get(pk=mailbox.pk)
        self.require_idle(mailbox)
        service = mailbox.hosting_account.customer_service
        require_service_permission(request.user, service, "can_manage_email")
        if mailbox.status != Mailbox.Status.ACTIVE or service.status != CustomerService.Status.ACTIVE or (
            service.expires_at and service.expires_at <= timezone.now()
        ):
            raise ValidationError({"detail": "Only an active mailbox password can be reset."})
        otp = request.data.get("otp")
        password = request.data.get("password")
        if not isinstance(otp, str) or not otp.isdigit() or len(otp) != 6:
            raise ValidationError({"otp": "Enter the 6-digit verification code sent to your account email."})
        if not isinstance(password, str) or len(password) < 8 or len(password) > 128:
            raise ValidationError({"password": "Choose a mailbox password between 8 and 128 characters."})
        from apps.accounts.otp import consume_otp
        if not consume_otp(request.user, otp, purpose="mailbox", target=str(mailbox.pk)):
            return Response({"otp": "That verification code is invalid, expired, or has reached its attempt limit."}, status=400)
        action = _queue_action(
            service,
            request.user,
            ProvisioningAction.ActionType.MAILBOX_PASSWORD_RESET,
            {
                "mailbox_id": mailbox.id,
                "email_address": mailbox.email_address,
                "password_encrypted": encrypt_secret(password),
            },
        )
        _audit(service, request.user, "mailbox.password_reset.requested", "mailbox", mailbox.id,
               {"email_address": mailbox.email_address, "action_id": action.id})
        return Response({"detail": "Your chosen mailbox password is queued for application. A confirmation email will follow."},
                        status=status.HTTP_202_ACCEPTED)


class ProviderConnectionViewSet(CustomerServiceQueryMixin, viewsets.ModelViewSet):
    serializer_class = ProviderConnectionSerializer
    http_method_names = ["get", "post", "delete", "head", "options"]

    def get_queryset(self):
        return ProviderConnection.objects.filter(
            customer=self.request.user,
            scope=ProviderConnection.Scope.CUSTOMER,
        ).defer("credentials")

    def perform_destroy(self, instance):
        instance.status = ProviderConnection.Status.REVOKED
        instance.save(update_fields=("status", "updated_at"))

    @action(detail=True, methods=["post"])
    def verify(self, request, pk=None):
        connection = self.get_object()
        try:
            credentials = json.loads(connection.credentials)
            token = cloudflare_credentials(credentials)
            CloudflareClient().verify_token(token)
        except (json.JSONDecodeError, KeyError, TypeError) as error:
            connection.status = ProviderConnection.Status.ERROR
            connection.save(update_fields=("status", "updated_at"))
            raise ValidationError({"credentials": "Cloudflare connection requires a valid API token."}) from error
        except CloudflareError as error:
            connection.status = ProviderConnection.Status.ERROR
            connection.save(update_fields=("status", "updated_at"))
            raise ValidationError({"credentials": str(error)}) from error
        connection.status = ProviderConnection.Status.ACTIVE
        connection.last_verified_at = timezone.now()
        connection.save(update_fields=("status", "last_verified_at", "updated_at"))
        return Response({"id": connection.id, "provider": connection.provider, "status": connection.status})

    @action(detail=True, methods=["get"])
    def zones(self, request, pk=None):
        connection = self.get_object()
        if connection.status != ProviderConnection.Status.ACTIVE:
            raise ValidationError({"detail": "Verify this Cloudflare connection before listing its zones."})
        try:
            zones = CloudflareClient().list_zones(_cloudflare_token(connection))
        except CloudflareError as error:
            raise ValidationError({"detail": str(error)}) from error
        return Response(
            [
                {"id": zone["id"], "name": zone["name"], "status": zone.get("status")}
                for zone in zones
                if zone.get("id") and zone.get("name")
            ]
        )


class CloudflareZoneLinkView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = CloudflareZoneLinkSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        payload = serializer.validated_data
        try:
            domain = DomainAsset.objects.select_related("customer_service").get(
                id=payload["domain_id"],
                customer_service__in=accessible_services_for(request.user),
                status=DomainAsset.Status.ACTIVE,
            )
        except DomainAsset.DoesNotExist as error:
            raise ValidationError(
                {"detail": "Choose an owned domain and a verified Cloudflare connection."}
            ) from error
        connections = ProviderConnection.objects.filter(
            id=payload["connection_id"],
            provider=ProviderConnection.Provider.CLOUDFLARE,
            status=ProviderConnection.Status.ACTIVE,
        )
        connection = connections.filter(
            scope=ProviderConnection.Scope.CUSTOMER,
            customer=request.user,
        ).first() or connections.filter(
            scope=ProviderConnection.Scope.GLOBAL,
            customer__isnull=True,
        ).first()
        if not connection:
            raise ValidationError({"connection_id": "Choose a Cloudflare connection available to this customer."})

        service = domain.customer_service
        require_service_permission(request.user, service, "can_manage_dns")
        cloudflare_zone_id = payload["cloudflare_zone_id"]
        try:
            cloudflare_zone = CloudflareClient().get_zone(
                _cloudflare_token(connection),
                cloudflare_zone_id,
            )
        except CloudflareError as error:
            raise ValidationError({"cloudflare_zone_id": str(error)}) from error
        if cloudflare_zone.get("name", "").lower() != domain.domain_name.lower():
            raise ValidationError(
                {"cloudflare_zone_id": "The Cloudflare zone name must exactly match the selected customer domain."}
            )

        zone, _ = DNSZone.objects.update_or_create(
            domain=domain,
            defaults={
                "provider_connection": connection,
                "external_zone_id": cloudflare_zone_id,
                "status": DNSZone.Status.PENDING,
                "last_synced_at": None,
            },
        )
        _audit(
            service,
            request.user,
            "dns.cloudflare.zone_linked",
            "dns_zone",
            zone.id,
            {"domain": domain.domain_name, "provider": ProviderConnection.Provider.CLOUDFLARE},
        )
        return Response(DNSZoneSerializer(zone).data)


class CloudflareZoneConnectView(CustomerServiceQueryMixin, APIView):
    def post(self, request):
        serializer = CloudflareZoneConnectSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        payload = serializer.validated_data
        try:
            service = self.get_service_queryset().select_related("product").get(
                uuid=payload["service_uuid"],
                status=CustomerService.Status.ACTIVE,
            )
        except CustomerService.DoesNotExist as error:
            raise ValidationError({"service_uuid": "Choose an active TechInn service."}) from error
        require_service_permission(request.user, service, "can_manage_domains")
        require_service_permission(request.user, service, "can_manage_dns")
        connection = ProviderConnection.objects.filter(
            id=payload["connection_id"],
            provider=ProviderConnection.Provider.CLOUDFLARE,
            status=ProviderConnection.Status.ACTIVE,
            scope=ProviderConnection.Scope.CUSTOMER,
            customer=request.user,
        ).first()
        if connection is None:
            raise ValidationError({"connection_id": "Choose your verified Cloudflare connection."})
        token = _cloudflare_token(connection)
        try:
            provider_zones = CloudflareClient().list_zones(token)
        except CloudflareError as error:
            raise ValidationError({"detail": str(error)}) from error
        zone = next(
            (
                item for item in provider_zones
                if item.get("id") == payload["cloudflare_zone_id"]
                and isinstance(item.get("name"), str)
            ),
            None,
        )
        if zone is None:
            raise ValidationError({"cloudflare_zone_id": "That domain is not available in your verified Cloudflare account."})
        domain_name = zone["name"].lower().rstrip(".")
        if not domain_name or len(domain_name) > 253:
            raise ValidationError({"cloudflare_zone_id": "Cloudflare returned an invalid domain name."})
        if DomainAsset.objects.filter(domain_name__iexact=domain_name).exists():
            raise ValidationError({"detail": "This domain is already connected to a TechInn service."})
        # Legacy entry point joins the verified onboarding workflow too.
        from apps.services.connection_views import DomainConnectionSerializer
        from apps.services.domain_connections import eligible_service
        from apps.services.models import DomainConnection
        import secrets
        if service.customer_id != request.user.id:
            raise ValidationError({"detail": "Only the plan owner can connect a new domain."})
        eligible_service(service, domain_name, "both")
        with transaction.atomic():
            service = CustomerService.objects.select_for_update().get(pk=service.pk)
            if DomainConnection.objects.filter(customer_service=service).exists():
                raise ValidationError({"detail": "This plan already has a connection. Continue in Connections."})
            connection_request = DomainConnection.objects.create(
                customer=request.user, customer_service=service, domain_name=domain_name,
                mode="cloudflare", services="both", provider_connection=connection,
                external_zone_id=payload["cloudflare_zone_id"],
                verification_token="techinn-" + secrets.token_urlsafe(32), next_check_at=None,
            )
        return Response(DomainConnectionSerializer(connection_request).data, status=status.HTTP_201_CREATED)


class CloudflareZoneListView(CustomerServiceQueryMixin, APIView):
    def get(self, request):
        connections = list(
            ProviderConnection.objects.filter(
                customer=request.user,
                provider=ProviderConnection.Provider.CLOUDFLARE,
                status=ProviderConnection.Status.ACTIVE,
            )
        )
        connections.extend(
            ProviderConnection.objects.filter(
                customer__isnull=True,
                scope=ProviderConnection.Scope.GLOBAL,
                provider=ProviderConnection.Provider.CLOUDFLARE,
                status=ProviderConnection.Status.ACTIVE,
            )
        )
        owned_domains = {
            domain.domain_name.lower(): domain
            for domain in DomainAsset.objects.filter(
                customer_service__in=self.get_service_queryset(),
                status=DomainAsset.Status.ACTIVE,
            ).select_related("customer_service")
        }
        matched_zones = []
        for connection in connections:
            try:
                provider_zones = CloudflareClient().list_zones(_cloudflare_token(connection))
            except CloudflareError as error:
                raise ValidationError(
                    {"detail": f"Could not list zones for connection {connection.name}: {error}"}
                ) from error
            for provider_zone in provider_zones:
                domain = owned_domains.get(provider_zone.get("name", "").lower())
                if domain:
                    try:
                        require_service_permission(request.user, domain.customer_service, "can_manage_dns")
                    except PermissionDenied:
                        continue
                    matched_zones.append(
                        {
                            "connection_id": connection.id,
                            "domain_id": domain.id,
                            "domain": domain.domain_name,
                            "cloudflare_zone_id": provider_zone.get("id"),
                            "status": provider_zone.get("status"),
                        }
                    )
        return Response({"zones": matched_zones})


class ProvisioningActionListView(CustomerServiceQueryMixin, generics.ListAPIView):
    serializer_class = ProvisioningActionSerializer

    def get_queryset(self):
        return ProvisioningAction.objects.filter(
            customer_service__in=self.get_service_queryset()
        ).select_related("customer_service").order_by("-created_at")


class ServiceAuditEventListView(CustomerServiceQueryMixin, generics.ListAPIView):
    serializer_class = ServiceAuditEventSerializer

    def get_queryset(self):
        return ServiceAuditEvent.objects.filter(
            customer_service__in=self.get_service_queryset()
        ).select_related("customer_service").order_by("-created_at")


class ServiceMemberListCreateView(CustomerServiceQueryMixin, generics.ListCreateAPIView):
    serializer_class = ServiceMemberSerializer

    def get_service(self):
        try:
            return CustomerService.objects.get(
                uuid=self.kwargs["service_uuid"],
                customer=self.request.user,
            )
        except CustomerService.DoesNotExist as error:
            raise PermissionDenied("Only the service owner can manage service members.") from error

    def get_queryset(self):
        return ServiceMember.objects.filter(customer_service=self.get_service()).select_related("customer")

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context["service"] = self.get_service()
        return context

    def perform_create(self, serializer):
        member = serializer.save()
        _audit(
            member.customer_service,
            self.request.user,
            "service.member.invited",
            "service_member",
            member.id,
            {"customer_email": member.customer.email, "role": member.role},
        )


class ServiceMemberDetailView(CustomerServiceQueryMixin, generics.RetrieveUpdateDestroyAPIView):
    serializer_class = ServiceMemberSerializer
    http_method_names = ["get", "patch", "delete", "head", "options"]

    def perform_update(self, serializer):
        member = serializer.save()
        _audit(member.customer_service, self.request.user, "service.member.updated", "service_member", member.id, {"role": member.role})

    def get_queryset(self):
        try:
            service = CustomerService.objects.get(
                uuid=self.kwargs["service_uuid"],
                customer=self.request.user,
            )
        except CustomerService.DoesNotExist as error:
            raise PermissionDenied("Only the service owner can manage service members.") from error
        return ServiceMember.objects.filter(customer_service=service).select_related("customer")

    def perform_destroy(self, instance):
        _audit(
            instance.customer_service,
            self.request.user,
            "service.member.removed",
            "service_member",
            instance.id,
            {"customer_email": instance.customer.email, "role": instance.role},
        )
        instance.delete()


class MailboxAccessListCreateView(CustomerServiceQueryMixin, generics.ListCreateAPIView):
    serializer_class = MailboxAccessSerializer

    def get_mailbox(self):
        try:
            mailbox = Mailbox.objects.select_related(
                "hosting_account__customer_service"
            ).get(
                pk=self.kwargs["mailbox_id"],
                hosting_account__customer_service__in=self.get_service_queryset(),
            )
        except Mailbox.DoesNotExist as error:
            raise PermissionDenied("Mailbox not found for this customer.") from error
        require_service_permission(
            self.request.user,
            mailbox.hosting_account.customer_service,
            "can_manage_email",
        )
        return mailbox

    def get_queryset(self):
        return MailboxAccess.objects.filter(mailbox=self.get_mailbox()).select_related("customer")

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context["mailbox"] = self.get_mailbox()
        return context

    def perform_create(self, serializer):
        grant = serializer.save()
        service = grant.mailbox.hosting_account.customer_service
        _audit(
            service,
            self.request.user,
            "mailbox.access.granted",
            "mailbox_access",
            grant.id,
            {
                "mailbox_id": grant.mailbox_id,
                "customer_email": grant.customer.email,
                "role": grant.role,
                "can_manage": grant.can_manage,
            },
        )


class MailboxAccessDetailView(CustomerServiceQueryMixin, generics.DestroyAPIView):
    def get_queryset(self):
        try:
            mailbox = Mailbox.objects.select_related(
                "hosting_account__customer_service"
            ).get(
                pk=self.kwargs["mailbox_id"],
                hosting_account__customer_service__in=self.get_service_queryset(),
            )
        except Mailbox.DoesNotExist as error:
            raise PermissionDenied("Mailbox not found for this customer.") from error
        require_service_permission(
            self.request.user,
            mailbox.hosting_account.customer_service,
            "can_manage_email",
        )
        return MailboxAccess.objects.filter(mailbox=mailbox).select_related("customer")

    def perform_destroy(self, instance):
        _audit(
            instance.mailbox.hosting_account.customer_service,
            self.request.user,
            "mailbox.access.revoked",
            "mailbox_access",
            instance.id,
            {"mailbox_id": instance.mailbox_id, "customer_email": instance.customer.email},
        )
        instance.delete()
