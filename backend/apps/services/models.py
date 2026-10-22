import uuid

from django.conf import settings
from django.core.validators import MinValueValidator, RegexValidator
from django.db import models
from django.db.models import Q

from apps.catalog.models import Product
from apps.orders.models import OrderItem
from apps.services.fields import EncryptedTextField


class CustomerService(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        PROVISIONING = "provisioning", "Provisioning"
        ACTIVE = "active", "Active"
        SUSPENDED = "suspended", "Suspended"
        EXPIRED = "expired", "Expired"
        CANCELLED = "cancelled", "Cancelled"
        TERMINATED = "terminated", "Terminated"
        FAILED = "failed", "Failed"

    uuid = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    customer = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="services")
    product = models.ForeignKey(Product, on_delete=models.PROTECT, related_name="customer_services")
    order_item = models.ForeignKey(
        OrderItem,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="customer_services",
    )
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.PENDING, db_index=True)
    started_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    next_due_at = models.DateTimeField(null=True, blank=True)
    auto_renew = models.BooleanField(default=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)
    provisioning_data = models.JSONField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=("customer",), name="idx_customer_services_customer"),
            models.Index(fields=("status", "expires_at"), name="idx_customer_services_expiry"),
            models.Index(fields=("status", "next_due_at"), name="idx_customer_services_due"),
        ]


class ServiceMember(models.Model):
    class Role(models.TextChoices):
        ADMIN = "admin", "Administrator"
        TECHNICAL = "technical", "Technical"
        BILLING = "billing", "Billing"
        CUSTOM = "custom", "Custom"

    customer_service = models.ForeignKey(
        CustomerService,
        on_delete=models.CASCADE,
        related_name="members",
    )
    customer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="service_memberships",
    )
    role = models.CharField(max_length=10, choices=Role.choices, default=Role.CUSTOM)
    can_manage_domains = models.BooleanField(default=False)
    can_manage_dns = models.BooleanField(default=False)
    can_manage_hosting = models.BooleanField(default=False)
    can_manage_email = models.BooleanField(default=False)
    can_view_billing = models.BooleanField(default=False)
    invited_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="service_invitations_sent",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("customer_service", "customer"),
                name="uq_service_member",
            )
        ]


class ServiceInstance(models.Model):
    display_name = models.CharField(max_length=150, blank=True)
    dashboard_url = models.URLField(max_length=1000, blank=True, help_text="Customer dashboard/login URL. Use HTTPS; never include passwords or access tokens.")
    customer_service = models.ForeignKey(
        CustomerService,
        on_delete=models.CASCADE,
        related_name="instances",
    )
    instance_type = models.CharField(max_length=100)
    external_id = models.CharField(max_length=255, blank=True)
    status = models.CharField(max_length=50, default="active")
    data = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("customer_service", "instance_type"),
                name="uq_service_instance",
            ),
        ]


class DomainAsset(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        ACTIVE = "active", "Active"
        EXPIRED = "expired", "Expired"
        SUSPENDED = "suspended", "Suspended"
        TRANSFER_PENDING = "transfer_pending", "Transfer pending"
        FAILED = "failed", "Failed"

    customer_service = models.ForeignKey(
        CustomerService,
        on_delete=models.PROTECT,
        related_name="domains",
    )
    domain_name = models.CharField(
        max_length=253,
        unique=True,
        db_index=True,
        validators=[
            RegexValidator(
                r"^(?=.{1,253}$)(?:[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?\.)+[A-Za-z0-9-]{2,63}$",
                "Enter a fully qualified domain name.",
            )
        ],
    )
    registrar = models.CharField(max_length=100, blank=True)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING, db_index=True)
    registered_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    auto_renew = models.BooleanField(default=True)
    nameservers = models.JSONField(default=list, blank=True)
    suspension_data = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("domain_name",)

    def __str__(self):
        return self.domain_name


class DNSZone(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        ACTIVE = "active", "Active"
        ERROR = "error", "Error"

    domain = models.OneToOneField(DomainAsset, on_delete=models.CASCADE, related_name="dns_zone")
    provider_connection = models.ForeignKey(
        "ProviderConnection",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="dns_zones",
    )
    external_zone_id = models.CharField(max_length=255, blank=True)
    nameservers = models.JSONField(default=list, blank=True)
    status = models.CharField(max_length=8, choices=Status.choices, default=Status.PENDING)
    dnssec_enabled = models.BooleanField(default=False)
    last_synced_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


class DNSRecord(models.Model):
    class RecordType(models.TextChoices):
        A = "A", "A"
        AAAA = "AAAA", "AAAA"
        CNAME = "CNAME", "CNAME"
        MX = "MX", "MX"
        TXT = "TXT", "TXT"
        NS = "NS", "NS"
        SRV = "SRV", "SRV"
        CAA = "CAA", "CAA"

    zone = models.ForeignKey(DNSZone, on_delete=models.CASCADE, related_name="records")
    name = models.CharField(max_length=253)
    record_type = models.CharField(max_length=5, choices=RecordType.choices)
    content = models.TextField()
    ttl = models.PositiveIntegerField(default=3600, validators=[MinValueValidator(1)])
    priority = models.PositiveSmallIntegerField(null=True, blank=True)
    proxied = models.BooleanField(default=False)
    external_record_id = models.CharField(max_length=255, blank=True)
    synced_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("name", "record_type", "priority")
        indexes = [models.Index(fields=("zone", "name"), name="idx_dns_record_zone_name")]


class HostingAccount(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        ACTIVE = "active", "Active"
        SUSPENDED = "suspended", "Suspended"
        TERMINATED = "terminated", "Terminated"
        ERROR = "error", "Error"

    customer_service = models.OneToOneField(
        CustomerService,
        on_delete=models.PROTECT,
        related_name="hosting_account",
    )
    server_name = models.CharField(max_length=150, blank=True)
    external_account_id = models.CharField(max_length=255, blank=True)
    username = models.CharField(max_length=150, blank=True)
    linux_username = models.CharField(max_length=150, blank=True)
    primary_domain = models.ForeignKey(
        DomainAsset,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="hosting_accounts",
    )
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.PENDING, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


class HostingWebsite(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Provisioning"
        ACTIVE = "active", "Active"
        ERROR = "error", "Setup failed"

    class CertificateStatus(models.TextChoices):
        NOT_INSTALLED = "not_installed", "Not installed"
        PENDING = "pending", "Installing"
        ACTIVE = "active", "Installed"
        ERROR = "error", "Installation failed"

    hosting_account = models.ForeignKey(
        HostingAccount,
        on_delete=models.CASCADE,
        related_name="websites",
    )
    domain_name = models.CharField(max_length=253, unique=True)
    master_domain = models.CharField(max_length=253)
    document_root = models.CharField(max_length=512, blank=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    last_error = models.TextField(blank=True)
    certificate_status = models.CharField(
        max_length=14,
        choices=CertificateStatus.choices,
        default=CertificateStatus.NOT_INSTALLED,
    )
    certificate_error = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("domain_name",)


class HostingResource(models.Model):
    class ResourceType(models.TextChoices):
        DISK = "disk", "Disk storage"
        BANDWIDTH = "bandwidth", "Bandwidth"
        DOMAINS = "domains", "Websites"
        DATABASES = "databases", "Databases"
        EMAIL_ACCOUNTS = "email_accounts", "Email accounts"
        INODES = "inodes", "Inodes"
        CPU = "cpu", "CPU"
        RAM = "ram", "RAM"

    hosting_account = models.ForeignKey(
        HostingAccount,
        on_delete=models.CASCADE,
        related_name="resources",
    )
    resource_type = models.CharField(max_length=16, choices=ResourceType.choices)
    limit_value = models.DecimalField(max_digits=20, decimal_places=4, validators=[MinValueValidator(0)])
    used_value = models.DecimalField(
        max_digits=20,
        decimal_places=4,
        default=0,
        validators=[MinValueValidator(0)],
    )
    unit = models.CharField(max_length=20)
    measured_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("hosting_account", "resource_type"),
                name="uq_hosting_resource_type",
            ),
            models.CheckConstraint(condition=models.Q(limit_value__gte=0), name="ck_hosting_resource_limit"),
            models.CheckConstraint(condition=models.Q(used_value__gte=0), name="ck_hosting_resource_usage"),
        ]


class HostingStorageAddon(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        ACTIVE = "active", "Active"
        ERROR = "error", "Error"
        EXPIRING = "expiring", "Expiring"
        EXPIRED = "expired", "Expired"

    customer_service = models.ForeignKey(
        CustomerService,
        on_delete=models.PROTECT,
        related_name="storage_addons",
    )
    order_item = models.OneToOneField(
        OrderItem,
        on_delete=models.PROTECT,
        related_name="hosting_storage_addon",
    )
    storage_gb = models.DecimalField(max_digits=8, decimal_places=2, validators=[MinValueValidator(0.01)])
    status = models.CharField(max_length=8, choices=Status.choices, default=Status.PENDING, db_index=True)
    starts_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True, db_index=True)
    last_error = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


class Mailbox(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        ACTIVE = "active", "Active"
        SUSPENDED = "suspended", "Suspended"
        CLEARING = "clearing", "Clearing storage"
        DELETING = "deleting", "Deletion pending"
        DELETED = "deleted", "Deleted"
        ERROR = "error", "Error"

    hosting_account = models.ForeignKey(
        HostingAccount,
        on_delete=models.PROTECT,
        related_name="mailboxes",
    )
    domain = models.ForeignKey(DomainAsset, on_delete=models.PROTECT, related_name="mailboxes")
    email_domain = models.CharField(max_length=253, blank=True, default="")
    local_part = models.CharField(
        max_length=64,
        validators=[RegexValidator(r"^[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+$")],
    )
    quota_mb = models.PositiveIntegerField()
    used_mb = models.PositiveIntegerField(default=0)
    external_mailbox_id = models.CharField(max_length=255, blank=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING, db_index=True)
    last_error = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("domain", "email_domain", "local_part"),
                name="uq_mailbox_domain_local_part",
            ),
            models.CheckConstraint(condition=models.Q(quota_mb__gte=1), name="ck_mailbox_quota"),
            models.CheckConstraint(condition=models.Q(used_mb__gte=0), name="ck_mailbox_usage"),
        ]

    @property
    def effective_domain(self):
        return self.email_domain or self.domain.domain_name

    @property
    def email_address(self):
        return f"{self.local_part}@{self.effective_domain}"


class MailboxAccess(models.Model):
    class Role(models.TextChoices):
        OWNER = "owner", "Owner"
        ADMIN = "admin", "Administrator"
        USER = "user", "Mailbox user"

    mailbox = models.ForeignKey(Mailbox, on_delete=models.CASCADE, related_name="access_grants")
    customer = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="mailbox_access")
    role = models.CharField(max_length=5, choices=Role.choices, default=Role.USER)
    can_manage = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=("mailbox", "customer"), name="uq_mailbox_customer_access"),
        ]


class ProviderConnection(models.Model):
    class Provider(models.TextChoices):
        CLOUDFLARE = "cloudflare", "Cloudflare"
        CPANEL = "cpanel", "cPanel / WHM"
        CYBERPANEL = "cyberpanel", "CyberPanel"
        REGISTRAR = "registrar", "Domain registrar"
        MAIL = "mail", "Mail server"

    class Scope(models.TextChoices):
        GLOBAL = "global", "TechInn managed"
        CUSTOMER = "customer", "Customer connected"

    class Status(models.TextChoices):
        PENDING = "pending", "Pending verification"
        ACTIVE = "active", "Active"
        REVOKED = "revoked", "Revoked"
        ERROR = "error", "Error"

    customer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="provider_connections",
    )
    provider = models.CharField(max_length=12, choices=Provider.choices)
    scope = models.CharField(max_length=8, choices=Scope.choices)
    name = models.CharField(max_length=150)
    credentials = EncryptedTextField()
    external_account_id = models.CharField(max_length=255, blank=True)
    status = models.CharField(max_length=8, choices=Status.choices, default=Status.PENDING)
    last_verified_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=(
                    models.Q(scope="global", customer__isnull=True)
                    | models.Q(scope="customer", customer__isnull=False)
                ),
                name="ck_provider_connection_scope",
            ),
        ]
        ordering = ("-created_at",)


class ProvisioningAction(models.Model):
    class ActionType(models.TextChoices):
        DNS_UPSERT = "dns_upsert", "DNS record change"
        DNS_DELETE = "dns_delete", "DNS record removal"
        MAILBOX_CREATE = "mailbox_create", "Create mailbox"
        MAILBOX_UPDATE = "mailbox_update", "Update mailbox"
        MAILBOX_DELETE = "mailbox_delete", "Delete mailbox"
        MAILBOX_PASSWORD_RESET = "mailbox_pw_reset", "Reset mailbox password"
        MAILBOX_CLEAR_STORAGE = "mailbox_clear_storage", "Clear mailbox storage"
        HOSTING_WEBSITE_CREATE = "hosting_site_create", "Create hosting website"
        HOSTING_WEBSITE_CERTIFICATE = "hosting_site_cert", "Install website certificate"
        HOSTING_STORAGE_UPDATE = "hosting_storage_update", "Update hosting storage"
        HOSTING_SUSPEND = "hosting_suspend", "Suspend hosting"
        HOSTING_UNSUSPEND = "hosting_unsuspend", "Unsuspend hosting"
        HOSTING_SYNC = "hosting_sync", "Sync hosting usage"
        DOMAIN_SYNC = "domain_sync", "Sync domain"
        CLOUDFLARE_VERIFY = "cloudflare_verify", "Verify Cloudflare connection"

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        PROCESSING = "processing", "Processing"
        COMPLETED = "completed", "Completed"
        FAILED = "failed", "Failed"
        CANCELLED = "cancelled", "Cancelled"

    customer_service = models.ForeignKey(
        CustomerService,
        on_delete=models.PROTECT,
        related_name="provisioning_actions",
    )
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="provisioning_actions",
    )
    action_type = models.CharField(max_length=28, choices=ActionType.choices)
    payload = models.JSONField(default=dict)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING, db_index=True)
    attempts = models.PositiveIntegerField(default=0)
    last_error = models.TextField(blank=True)
    scheduled_at = models.DateTimeField(auto_now_add=True, db_index=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [models.Index(fields=("status", "scheduled_at"), name="idx_provisioning_pending")]


class ServiceAuditEvent(models.Model):
    customer_service = models.ForeignKey(
        CustomerService,
        on_delete=models.PROTECT,
        related_name="audit_events",
    )
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="service_audit_events",
    )
    event_type = models.CharField(max_length=100)
    entity_type = models.CharField(max_length=100)
    entity_id = models.CharField(max_length=100)
    payload = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ("-created_at",)


class SupportTicket(models.Model):
    class Status(models.TextChoices):
        OPEN = "open", "Open"
        PENDING_SUPPORT = "pending_support", "Pending support"
        PENDING_CUSTOMER = "pending_customer", "Pending customer"
        RESOLVED = "resolved", "Resolved"
        CLOSED = "closed", "Closed"

    class Priority(models.TextChoices):
        LOW = "low", "Low"
        NORMAL = "normal", "Normal"
        HIGH = "high", "High"
        URGENT = "urgent", "Urgent"

    customer = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="support_tickets")
    customer_service = models.ForeignKey(
        CustomerService, on_delete=models.SET_NULL, null=True, blank=True, related_name="support_tickets"
    )
    subject = models.CharField(max_length=180)
    category = models.CharField(max_length=24, default="other")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.OPEN, db_index=True)
    priority = models.CharField(max_length=10, choices=Priority.choices, default=Priority.NORMAL)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-updated_at",)
        indexes = [models.Index(fields=("customer", "status"), name="idx_ticket_customer_status")]

    @property
    def ticket_number(self):
        return f"TI-{self.pk:06d}"


class SupportTicketMessage(models.Model):
    ticket = models.ForeignKey(SupportTicket, on_delete=models.CASCADE, related_name="messages")
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    body = models.TextField()
    is_staff = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("created_at",)


class DomainConnection(models.Model):
    """A customer-scoped claim; only verified claims can reserve a DomainAsset."""
    class Mode(models.TextChoices):
        MANAGED = "managed", "Use TechInn DNS"
        EXTERNAL = "external", "Keep existing DNS"
        CLOUDFLARE = "cloudflare", "Use my Cloudflare account"

    customer = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="domain_connections")
    customer_service = models.OneToOneField(
        CustomerService,
        on_delete=models.PROTECT,
        related_name="domain_connection",
        null=True,
        blank=True,
    )
    domain_name = models.CharField(max_length=253)
    mode = models.CharField(max_length=12, choices=Mode.choices)
    services = models.CharField(max_length=8, choices=(("website", "Website"), ("email", "Email"), ("both", "Website and email")))
    provider_connection = models.ForeignKey("ProviderConnection", null=True, blank=True, on_delete=models.SET_NULL)
    external_zone_id = models.CharField(max_length=255, blank=True)
    verification_token = models.CharField(max_length=96)
    verified_at = models.DateTimeField(null=True, blank=True)
    domain = models.ForeignKey(DomainAsset, null=True, blank=True, on_delete=models.PROTECT)
    status = models.CharField(max_length=20, default="awaiting_ownership")
    nameservers = models.JSONField(default=list)
    previous_records = models.JSONField(default=list)
    required_records = models.JSONField(default=list)
    imported_records = models.JSONField(default=list)
    review_approved_at = models.DateTimeField(null=True, blank=True)
    dns_applied_at = models.DateTimeField(null=True, blank=True)
    checks = models.JSONField(default=dict)
    last_error = models.TextField(blank=True)
    last_checked_at = models.DateTimeField(null=True, blank=True)
    next_check_at = models.DateTimeField(null=True, blank=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=("customer", "domain_name"), name="uq_customer_domain_connection"),
            models.UniqueConstraint(
                fields=("domain_name",),
                condition=Q(verified_at__isnull=False),
                name="uq_verified_domain_connection",
            ),
        ]
        ordering = ("-created_at",)
