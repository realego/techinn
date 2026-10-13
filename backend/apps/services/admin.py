from django.contrib import admin

from apps.services.models import (
    CustomerService,
    DNSRecord,
    DNSZone,
    DomainAsset,
    HostingAccount,
    HostingResource,
    Mailbox,
    MailboxAccess,
    ProviderConnection,
    ProvisioningAction,
    ServiceAuditEvent,
    ServiceMember,
    ServiceInstance,
)


class ServiceInstanceInline(admin.TabularInline):
    model = ServiceInstance
    extra = 0


class DNSRecordInline(admin.TabularInline):
    model = DNSRecord
    extra = 0


@admin.register(CustomerService)
class CustomerServiceAdmin(admin.ModelAdmin):
    list_display = ("uuid", "customer", "product", "status", "expires_at", "next_due_at")
    list_filter = ("status", "auto_renew")
    search_fields = ("uuid", "customer__email", "product__name")
    inlines = (ServiceInstanceInline,)


admin.site.register(ServiceInstance)


@admin.register(ServiceMember)
class ServiceMemberAdmin(admin.ModelAdmin):
    list_display = ("customer_service", "customer", "role", "can_manage_dns", "can_manage_email")
    list_filter = ("role", "can_manage_domains", "can_manage_dns", "can_manage_hosting", "can_manage_email")
    search_fields = ("customer__email", "customer_service__customer__email")


@admin.register(DomainAsset)
class DomainAssetAdmin(admin.ModelAdmin):
    list_display = ("domain_name", "customer_owner", "status", "registrar", "expires_at", "auto_renew")
    list_filter = ("status", "auto_renew")
    search_fields = ("domain_name", "customer_service__customer__email")
    readonly_fields = ("created_at", "updated_at")

    @admin.display(description="Customer", ordering="customer_service__customer__email")
    def customer_owner(self, obj):
        return obj.customer_service.customer.email


@admin.register(DNSZone)
class DNSZoneAdmin(admin.ModelAdmin):
    list_display = ("domain", "status", "dnssec_enabled", "provider_connection")
    list_filter = ("status", "dnssec_enabled")
    search_fields = ("domain__domain_name",)
    inlines = (DNSRecordInline,)


@admin.register(HostingAccount)
class HostingAccountAdmin(admin.ModelAdmin):
    list_display = ("customer_service", "username", "server_name", "status")
    list_filter = ("status", "server_name")
    search_fields = ("username", "external_account_id", "customer_service__customer__email")


@admin.register(HostingResource)
class HostingResourceAdmin(admin.ModelAdmin):
    list_display = ("hosting_account", "resource_type", "limit_value", "used_value", "unit", "measured_at")
    list_filter = ("resource_type", "unit")


@admin.register(Mailbox)
class MailboxAdmin(admin.ModelAdmin):
    list_display = ("local_part", "domain", "hosting_account", "quota_mb", "used_mb", "status")
    list_filter = ("status",)
    search_fields = ("local_part", "domain__domain_name", "external_mailbox_id")
    readonly_fields = ("used_mb", "external_mailbox_id", "created_at", "updated_at")


@admin.register(MailboxAccess)
class MailboxAccessAdmin(admin.ModelAdmin):
    list_display = ("mailbox", "customer", "role", "can_manage")
    list_filter = ("role", "can_manage")
    search_fields = ("customer__email", "mailbox__local_part", "mailbox__domain__domain_name")


@admin.register(ProviderConnection)
class ProviderConnectionAdmin(admin.ModelAdmin):
    list_display = ("name", "provider", "scope", "customer", "status", "last_verified_at")
    list_filter = ("provider", "scope", "status")
    search_fields = ("name", "customer__email", "external_account_id")
    exclude = ("credentials",)
    readonly_fields = ("last_verified_at", "created_at", "updated_at")


@admin.register(ProvisioningAction)
class ProvisioningActionAdmin(admin.ModelAdmin):
    list_display = ("action_type", "customer_service", "status", "attempts", "scheduled_at")
    list_filter = ("action_type", "status")
    search_fields = ("customer_service__customer__email", "customer_service__uuid")
    readonly_fields = (
        "customer_service",
        "requested_by",
        "action_type",
        "payload",
        "attempts",
        "last_error",
        "scheduled_at",
        "started_at",
        "completed_at",
    )


@admin.register(ServiceAuditEvent)
class ServiceAuditEventAdmin(admin.ModelAdmin):
    list_display = ("event_type", "entity_type", "entity_id", "actor", "created_at")
    list_filter = ("event_type", "entity_type")
    search_fields = ("entity_id", "actor__email", "customer_service__customer__email")
    readonly_fields = (
        "customer_service",
        "actor",
        "event_type",
        "entity_type",
        "entity_id",
        "payload",
        "created_at",
    )
