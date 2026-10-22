from django.db import transaction
import json
import re

from rest_framework import serializers
from django.utils import timezone

from apps.services.models import (
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
    SupportTicket,
    SupportTicketMessage,
)
from apps.accounts.models import Customer
from apps.services.domain_availability import normalize_domain_name
from apps.services.permissions import accessible_services_for, require_service_permission
from apps.services.storage import mailbox_storage_budget


class DomainAssetSerializer(serializers.ModelSerializer):
    customer_service = serializers.UUIDField(source="customer_service.uuid", read_only=True)
    registration = serializers.SerializerMethodField()

    def get_registration(self, obj):
        progress = (obj.customer_service.provisioning_data or {}).get("domain_registration", {})
        if obj.status == DomainAsset.Status.ACTIVE:
            status = "registered"
        elif obj.status == DomainAsset.Status.TRANSFER_PENDING:
            status = "transfer_pending"
        else:
            status = progress.get("status", "pending")
        messages = {
            "pending": ("Preparing registration", "We are preparing your domain registration."),
            "transfer_pending": ("Transfer awaiting confirmation", "The transfer has not been verified yet. This domain will be marked active after the transfer is confirmed."),
            "awaiting_release": ("Queued for review", "Your registration is queued for TechInn review."),
            "cloudflare_ready": ("DNS prepared", "Nameservers are ready; registration is being prepared."),
            "zispa_draft_created": ("Ready for submission", "Your registration details are prepared for submission."),
            "zispa_submitted": ("Submitted", "Sent to the registry. Registration is awaiting confirmation."),
            "retry_pending": ("Registration delayed", "We will retry automatically. You do not need to order again."),
            "needs_attention": ("Under review", "TechInn is checking your registration. You do not need to order again."),
            "registrar_manual_required": ("Registrar review", "TechInn will complete registration with the appropriate registrar."),
            "registered": ("Registered", "Your domain registration is confirmed."),
        }
        label, message = messages.get(status, messages["pending"])
        return {"status": status, "label": label, "message": message}

    class Meta:
        model = DomainAsset
        fields = (
            "id",
            "customer_service",
            "domain_name",
            "registrar",
            "status",
            "registered_at",
            "expires_at",
            "auto_renew",
            "nameservers",
            "suspension_data",
            "registration",
        )


class DNSRecordSerializer(serializers.ModelSerializer):
    zone = serializers.PrimaryKeyRelatedField(queryset=DNSZone.objects.none(), write_only=True, required=False)

    class Meta:
        model = DNSRecord
        fields = ("id", "zone", "name", "record_type", "content", "ttl", "priority", "proxied", "synced_at", "created_at", "updated_at")
        read_only_fields = ("id", "created_at", "updated_at")

    def get_fields(self):
        fields = super().get_fields()
        request = self.context.get("request")
        if request and request.user.is_authenticated:
            fields["zone"].queryset = DNSZone.objects.filter(
                domain__customer_service__in=accessible_services_for(request.user)
            )
        return fields

    def validate(self, attrs):
        zone = attrs.get("zone", getattr(self.instance, "zone", None))
        if self.instance and "zone" in attrs and attrs["zone"] != self.instance.zone:
            raise serializers.ValidationError({"zone": "A DNS record cannot be moved to another zone."})
        record_name = attrs.get("name", getattr(self.instance, "name", ""))
        if zone and record_name not in {"@", zone.domain.domain_name} and not record_name.endswith(
            "." + zone.domain.domain_name
        ):
            raise serializers.ValidationError({"name": "DNS record names must be within this domain."})
        record_type = attrs.get("record_type", getattr(self.instance, "record_type", None))
        if record_type == DNSRecord.RecordType.CNAME and attrs.get("priority") is not None:
            raise serializers.ValidationError({"priority": "CNAME records cannot have an MX priority."})
        return attrs


class DNSZoneSerializer(serializers.ModelSerializer):
    domain = serializers.CharField(source="domain.domain_name", read_only=True)
    records = DNSRecordSerializer(many=True, read_only=True)

    class Meta:
        model = DNSZone
        fields = ("id", "domain", "status", "dnssec_enabled", "last_synced_at", "nameservers", "records")


class HostingResourceSerializer(serializers.ModelSerializer):
    remaining_value = serializers.SerializerMethodField()

    class Meta:
        model = HostingResource
        fields = ("resource_type", "limit_value", "used_value", "remaining_value", "unit", "measured_at")

    def get_remaining_value(self, resource):
        return max(resource.limit_value - resource.used_value, 0)


class HostingAccountSerializer(serializers.ModelSerializer):
    customer_service = serializers.UUIDField(source="customer_service.uuid", read_only=True)
    primary_domain = serializers.CharField(source="primary_domain.domain_name", read_only=True, allow_null=True)
    resources = HostingResourceSerializer(many=True, read_only=True)

    class Meta:
        model = HostingAccount
        fields = (
            "id",
            "customer_service",
            "server_name",
            "username",
            "primary_domain",
            "status",
            "resources",
        )


class HostingWebsiteSerializer(serializers.ModelSerializer):
    class Meta:
        model = HostingWebsite
        fields = (
            "id",
            "domain_name",
            "master_domain",
            "status",
            "last_error",
            "certificate_status",
            "certificate_error",
        )
        read_only_fields = fields


class HostingWebsiteCreateSerializer(serializers.Serializer):
    subdomain = serializers.CharField(max_length=63, trim_whitespace=True)

    def validate_subdomain(self, value):
        value = value.strip().lower()
        if not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", value):
            raise serializers.ValidationError(
                "Use one subdomain label containing letters, numbers or hyphens."
            )
        if value in {"www", "mail", "ftp", "webmail", "cpanel"}:
            raise serializers.ValidationError("That subdomain label is reserved.")
        return value


class MailboxSerializer(serializers.ModelSerializer):
    email_address = serializers.CharField(read_only=True)
    hosting_account = serializers.PrimaryKeyRelatedField(read_only=True)
    domain = serializers.CharField(source="effective_domain", read_only=True)
    error_message = serializers.CharField(source="last_error", read_only=True)

    class Meta:
        model = Mailbox
        fields = (
            "id",
            "email_address",
            "domain",
            "hosting_account",
            "local_part",
            "quota_mb",
            "used_mb",
            "status",
            "error_message",
            "created_at",
        )
        read_only_fields = ("id", "used_mb", "status", "error_message", "created_at")


class MailboxCreateSerializer(serializers.ModelSerializer):
    hosting_account_id = serializers.IntegerField(min_value=1, write_only=True)
    domain_id = serializers.IntegerField(min_value=1, write_only=True)
    email_domain = serializers.CharField(max_length=253, required=False, allow_blank=True, write_only=True)
    password = serializers.CharField(write_only=True, trim_whitespace=False, min_length=8, max_length=128)

    class Meta:
        model = Mailbox
        fields = ("hosting_account_id", "domain_id", "email_domain", "local_part", "quota_mb", "password")

    def validate(self, attrs):
        local_part = attrs["local_part"]
        if not re.fullmatch(r"[A-Za-z0-9!#$%&'*+/=?^_`{|}~-]+(?:\.[A-Za-z0-9!#$%&'*+/=?^_`{|}~-]+)*", local_part):
            raise serializers.ValidationError({"local_part": "Enter a valid mailbox name without consecutive dots."})
        request = self.context["request"]
        try:
            account = HostingAccount.objects.select_related("customer_service").get(
                pk=attrs["hosting_account_id"],
                customer_service__in=accessible_services_for(request.user),
            )
            domain = DomainAsset.objects.get(
                pk=attrs["domain_id"],
                customer_service__in=accessible_services_for(request.user),
                status=DomainAsset.Status.ACTIVE,
            )
        except (HostingAccount.DoesNotExist, DomainAsset.DoesNotExist) as error:
            raise serializers.ValidationError("Select an active domain and hosting account that you own.") from error

        email_domain = (attrs.get("email_domain") or domain.domain_name).strip().rstrip(".").lower()
        if email_domain != domain.domain_name.lower():
            website = HostingWebsite.objects.filter(
                domain_name=email_domain,
                master_domain=domain.domain_name,
                status=HostingWebsite.Status.ACTIVE,
                hosting_account__status=HostingAccount.Status.ACTIVE,
                hosting_account__customer_service__status="active",
                hosting_account__customer_service__customer=account.customer_service.customer,
            ).first()
            if website is None:
                raise serializers.ValidationError({
                    "email_domain": "Select the root domain or an active subdomain website under it."
                })
            attrs["email_domain"] = email_domain
        else:
            attrs["email_domain"] = ""

        if account.customer_service.status != "active":
            raise serializers.ValidationError({"hosting_account_id": "Hosting service is not active."})
        if account.customer_service.expires_at and account.customer_service.expires_at <= timezone.now():
            raise serializers.ValidationError({"hosting_account_id": "This service is outside its paid period."})
        if account.status != HostingAccount.Status.ACTIVE:
            raise serializers.ValidationError({"hosting_account_id": "Hosting account is not provisioned."})
        if account.customer_service.customer_id != domain.customer_service.customer_id:
            raise serializers.ValidationError({"domain_id": "Choose a domain owned by the same customer as this email service."})
        if not HostingAccount.objects.filter(
            primary_domain=domain,
            status=HostingAccount.Status.ACTIVE,
            customer_service__customer=account.customer_service.customer,
        ).exists():
            raise serializers.ValidationError({"domain_id": "Choose a domain with an active CyberPanel website."})
        require_service_permission(request.user, account.customer_service, "can_manage_email")
        require_service_permission(request.user, domain.customer_service, "can_manage_email")
        email_limit = account.resources.filter(
            resource_type=HostingResource.ResourceType.EMAIL_ACCOUNTS
        ).first()
        if email_limit and account.mailboxes.exclude(status=Mailbox.Status.DELETED).count() >= email_limit.limit_value:
            raise serializers.ValidationError({"hosting_account_id": "This hosting plan has no mailbox slots remaining."})
        if attrs["quota_mb"] < 1:
            raise serializers.ValidationError({"quota_mb": "Mailbox quota must be at least 1 MB."})

        mailbox_storage_caps = {
            "email-essential": 2 * 1024,
            "email-team": 5 * 1024,
            "email-business-mail": 15 * 1024,
        }
        product_slug = account.customer_service.product.slug
        mailbox_cap = mailbox_storage_caps.get(product_slug)
        if mailbox_cap and attrs["quota_mb"] > mailbox_cap:
            raise serializers.ValidationError({
                "quota_mb": f"This email plan supports up to {mailbox_cap} MB per mailbox."
            })

        budget = mailbox_storage_budget(account)
        if budget:
            if budget.get("invalid_unit"):
                raise serializers.ValidationError(
                    {"quota_mb": "Hosting disk allocation must use MB or GB units to validate mailbox quotas."}
                )
            if attrs["quota_mb"] > budget["available_mb"]:
                raise serializers.ValidationError({
                    "quota_mb": (
                        f"This mailbox needs {attrs['quota_mb']:,} MB, but only {budget['available_mb']:,} MB "
                        "of this hosting plan's unallocated storage remains after website files and existing mailbox allocations."
                    )
                })

        attrs["hosting_account"] = account
        attrs["domain"] = domain
        return attrs


class ProviderConnectionSerializer(serializers.ModelSerializer):
    credentials = serializers.JSONField(write_only=True)

    class Meta:
        model = ProviderConnection
        fields = ("id", "provider", "name", "credentials", "external_account_id", "status", "created_at")
        read_only_fields = ("id", "external_account_id", "status", "created_at")

    def validate_provider(self, value):
        if value not in {ProviderConnection.Provider.CLOUDFLARE}:
            raise serializers.ValidationError("Customer connections currently support Cloudflare only.")
        return value

    def validate_credentials(self, value):
        if not isinstance(value, dict):
            raise serializers.ValidationError("Credentials must be an object.")
        token = value.get("api_token")
        if not isinstance(token, str) or not token.strip():
            raise serializers.ValidationError({"api_token": "Enter a non-empty Cloudflare API token."})
        if set(value) != {"api_token"}:
            raise serializers.ValidationError("Only an API token is accepted for Cloudflare connections.")
        return value

    def create(self, validated_data):
        credentials = validated_data.pop("credentials")
        if not isinstance(credentials, dict) or not credentials:
            raise serializers.ValidationError({"credentials": "Provide the provider credential fields as an object."})
        validated_data["credentials"] = json.dumps(credentials)
        validated_data["customer"] = self.context["request"].user
        validated_data["scope"] = ProviderConnection.Scope.CUSTOMER
        return super().create(validated_data)


class CloudflareZoneLinkSerializer(serializers.Serializer):
    domain_id = serializers.IntegerField(min_value=1)
    connection_id = serializers.IntegerField(min_value=1)
    cloudflare_zone_id = serializers.RegexField(regex=r"^[A-Za-z0-9_-]{1,64}$")


class CloudflareZoneConnectSerializer(serializers.Serializer):
    service_uuid = serializers.UUIDField()
    connection_id = serializers.IntegerField(min_value=1)
    cloudflare_zone_id = serializers.RegexField(regex=r"^[A-Za-z0-9_-]{1,64}$")


class HostingPrimaryDomainSerializer(serializers.Serializer):
    domain_id = serializers.IntegerField(min_value=1)


class ServiceDomainSelectionSerializer(serializers.Serializer):
    domain_name = serializers.CharField(max_length=253, trim_whitespace=True)


class ProvisioningActionSerializer(serializers.ModelSerializer):
    service = serializers.UUIDField(source="customer_service.uuid", read_only=True)
    error_message = serializers.CharField(source="last_error", read_only=True)

    class Meta:
        model = ProvisioningAction
        fields = (
            "id",
            "service",
            "action_type",
            "status",
            "attempts",
            "scheduled_at",
            "completed_at",
            "error_message",
        )


class ServiceAuditEventSerializer(serializers.ModelSerializer):
    class Meta:
        model = ServiceAuditEvent
        fields = ("id", "event_type", "entity_type", "entity_id", "payload", "created_at")


class SupportTicketMessageSerializer(serializers.ModelSerializer):
    author_name = serializers.SerializerMethodField()

    class Meta:
        model = SupportTicketMessage
        fields = ("id", "body", "author_name", "is_staff", "created_at")

    def get_author_name(self, obj):
        if not obj.author:
            return "TechInn support"
        return getattr(obj.author, "get_full_name", lambda: "")() or getattr(obj.author, "email", "Support")


class SupportTicketSerializer(serializers.ModelSerializer):
    ticket_number = serializers.ReadOnlyField()
    service_uuid = serializers.UUIDField(source="customer_service.uuid", read_only=True, allow_null=True)
    service_label = serializers.SerializerMethodField()
    messages = SupportTicketMessageSerializer(many=True, read_only=True)
    message = serializers.CharField(write_only=True, required=False, allow_blank=False, max_length=10000)
    service = serializers.UUIDField(write_only=True, required=False, allow_null=True)

    class Meta:
        model = SupportTicket
        fields = (
            "id", "ticket_number", "subject", "category", "status", "priority", "service_uuid",
            "service_label", "service", "message", "messages", "created_at", "updated_at",
        )
        read_only_fields = ("id", "ticket_number", "status", "service_uuid", "service_label", "messages", "created_at", "updated_at")

    def get_service_label(self, obj):
        if not obj.customer_service:
            return None
        return str(obj.customer_service.product)

    def validate_service(self, value):
        if value in (None, ""):
            return None
        request = self.context.get("request")
        service = accessible_services_for(request.user).filter(uuid=value).first() if request else None
        if not service:
            raise serializers.ValidationError("Choose a service from this account.")
        return service

    @transaction.atomic
    def create(self, validated_data):
        message = validated_data.pop("message", "")
        service = validated_data.pop("service", None)
        ticket = SupportTicket.objects.create(customer=self.context["request"].user, customer_service=service, **validated_data)
        first_message = SupportTicketMessage.objects.create(ticket=ticket, author=ticket.customer, body=message) if message else None
        from apps.notifications.tickets import queue_ticket_notification
        queue_ticket_notification(ticket, first_message)
        return ticket


class ServiceMemberSerializer(serializers.ModelSerializer):
    email = serializers.EmailField(write_only=True)
    customer_email = serializers.EmailField(source="customer.email", read_only=True)

    class Meta:
        model = ServiceMember
        fields = (
            "id",
            "email",
            "customer_email",
            "role",
            "can_manage_domains",
            "can_manage_dns",
            "can_manage_hosting",
            "can_manage_email",
            "can_view_billing",
            "created_at",
        )
        read_only_fields = ("id", "customer_email", "created_at")

    def validate_email(self, value):
        try:
            customer = Customer.objects.get(email__iexact=value)
        except Customer.DoesNotExist as error:
            raise serializers.ValidationError("This email does not belong to a registered customer account.") from error
        service = self.context["service"]
        if customer.pk == service.customer_id:
            raise serializers.ValidationError("The service owner does not need a separate member invitation.")
        self.context["member_customer"] = customer
        return value

    def validate(self, attrs):
        if self.instance and "email" in attrs:
            raise serializers.ValidationError({"email": "Remove this member and invite a new account to change the email."})
        if not self.instance and ServiceMember.objects.filter(customer_service=self.context["service"], customer=self.context.get("member_customer")).exists():
            raise serializers.ValidationError({"email": "This customer already has access. Update their role instead."})
        role = attrs.get("role", self.instance.role if self.instance else "technical")
        fields = ("can_manage_domains", "can_manage_dns", "can_manage_hosting", "can_manage_email", "can_view_billing")
        if role != ServiceMember.Role.CUSTOM:
            for field in fields:
                attrs[field] = role == "admin" or (role == "technical" and field != "can_view_billing") or (role == "billing" and field == "can_view_billing")
        attrs["role"] = role
        return attrs

    def create(self, validated_data):
        validated_data.pop("email")
        return ServiceMember.objects.create(
            customer_service=self.context["service"],
            customer=self.context["member_customer"],
            invited_by=self.context["request"].user,
            **validated_data,
        )


class MailboxAccessSerializer(serializers.ModelSerializer):
    email = serializers.EmailField(write_only=True)
    customer_email = serializers.EmailField(source="customer.email", read_only=True)

    class Meta:
        model = MailboxAccess
        fields = ("id", "email", "customer_email", "role", "can_manage", "created_at")
        read_only_fields = ("id", "customer_email", "created_at")

    def validate_email(self, value):
        from apps.accounts.models import Customer

        try:
            customer = Customer.objects.get(email__iexact=value)
        except Customer.DoesNotExist as error:
            raise serializers.ValidationError("This email does not belong to a registered customer account.") from error

        service = self.context["mailbox"].hosting_account.customer_service
        if customer.pk != service.customer_id and not service.members.filter(customer=customer).exists():
            raise serializers.ValidationError("Invite this customer to the service before granting mailbox access.")
        if MailboxAccess.objects.filter(mailbox=self.context["mailbox"], customer=customer).exists():
            raise serializers.ValidationError("This customer already has access to the mailbox.")
        self.context["access_customer"] = customer
        return value

    def create(self, validated_data):
        validated_data.pop("email")
        return MailboxAccess.objects.create(
            mailbox=self.context["mailbox"],
            customer=self.context["access_customer"],
            **validated_data,
        )
