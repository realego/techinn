from django.db import models


class ServiceType(models.Model):
    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        INACTIVE = "inactive", "Inactive"

    name = models.CharField(max_length=100, unique=True)
    slug = models.SlugField(max_length=100, unique=True)
    description = models.TextField(blank=True)
    status = models.CharField(max_length=8, choices=Status.choices, default=Status.ACTIVE)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name


class Product(models.Model):
    class BillingType(models.TextChoices):
        ONE_TIME = "one_time", "One time"
        RECURRING = "recurring", "Recurring"
        USAGE = "usage", "Usage"

    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        ACTIVE = "active", "Active"
        INACTIVE = "inactive", "Inactive"
        ARCHIVED = "archived", "Archived"

    service_type = models.ForeignKey(
        ServiceType,
        on_delete=models.PROTECT,
        related_name="products",
    )
    name = models.CharField(max_length=150)
    slug = models.SlugField(max_length=150, unique=True)
    description = models.TextField(blank=True)
    billing_type = models.CharField(max_length=10, choices=BillingType.choices)
    status = models.CharField(max_length=8, choices=Status.choices, default=Status.DRAFT)
    sort_order = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("sort_order", "name")
        constraints = [
            models.UniqueConstraint(
                fields=("service_type", "name"),
                name="uq_product_service_name",
            )
        ]
        indexes = [
            models.Index(fields=("service_type", "status"), name="idx_product_service"),
        ]

    def __str__(self):
        return self.name


class ProductPrice(models.Model):
    class BillingInterval(models.TextChoices):
        ONE_TIME = "one_time", "One time"
        MONTHLY = "monthly", "Monthly"
        QUARTERLY = "quarterly", "Quarterly"
        SEMI_ANNUALLY = "semi_annually", "Semi-annually"
        ANNUALLY = "annually", "Annually"
        BIENNIALLY = "biennially", "Biennially"
        CUSTOM = "custom", "Custom"

    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        INACTIVE = "inactive", "Inactive"

    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="prices")
    currency = models.CharField(max_length=3, default="USD")
    billing_interval = models.CharField(max_length=20, choices=BillingInterval.choices)
    period_months = models.PositiveSmallIntegerField(default=0)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    setup_fee = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    trial_days = models.PositiveIntegerField(default=0)
    is_default = models.BooleanField(default=False)
    status = models.CharField(max_length=8, choices=Status.choices, default=Status.ACTIVE)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("product", "currency", "billing_interval"),
                name="uq_product_price",
            ),
            models.CheckConstraint(condition=models.Q(amount__gte=0), name="ck_product_price_amount"),
            models.CheckConstraint(condition=models.Q(setup_fee__gte=0), name="ck_product_setup_fee"),
        ]

    def __str__(self):
        return f"{self.product} {self.currency} {self.billing_interval}"


class Feature(models.Model):
    class DataType(models.TextChoices):
        TEXT = "text", "Text"
        NUMBER = "number", "Number"
        BOOLEAN = "boolean", "Boolean"
        STORAGE = "storage", "Storage"
        JSON = "json", "JSON"

    name = models.CharField(max_length=150, unique=True)
    slug = models.SlugField(max_length=150, unique=True)
    data_type = models.CharField(max_length=8, choices=DataType.choices, default=DataType.TEXT)
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name


class ProductFeature(models.Model):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="feature_values")
    feature = models.ForeignKey(Feature, on_delete=models.CASCADE, related_name="product_values")
    value_text = models.TextField(null=True, blank=True)
    value_number = models.DecimalField(max_digits=20, decimal_places=4, null=True, blank=True)
    value_boolean = models.BooleanField(null=True, blank=True)
    value_json = models.JSONField(null=True, blank=True)
    display_value = models.CharField(max_length=255, blank=True)
    sort_order = models.IntegerField(default=0)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=("product", "feature"), name="uq_product_feature"),
        ]
        ordering = ("sort_order", "feature__name")


class Addon(models.Model):
    class BillingType(models.TextChoices):
        ONE_TIME = "one_time", "One time"
        RECURRING = "recurring", "Recurring"

    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        INACTIVE = "inactive", "Inactive"

    name = models.CharField(max_length=150)
    slug = models.SlugField(max_length=150, unique=True)
    description = models.TextField(blank=True)
    billing_type = models.CharField(max_length=10, choices=BillingType.choices)
    status = models.CharField(max_length=8, choices=Status.choices, default=Status.ACTIVE)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name


class AddonPrice(models.Model):
    class BillingInterval(models.TextChoices):
        ONE_TIME = "one_time", "One time"
        MONTHLY = "monthly", "Monthly"
        QUARTERLY = "quarterly", "Quarterly"
        ANNUALLY = "annually", "Annually"

    addon = models.ForeignKey(Addon, on_delete=models.CASCADE, related_name="prices")
    currency = models.CharField(max_length=3, default="USD")
    billing_interval = models.CharField(max_length=12, choices=BillingInterval.choices)
    amount = models.DecimalField(max_digits=12, decimal_places=2)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("addon", "currency", "billing_interval"),
                name="uq_addon_price",
            ),
            models.CheckConstraint(condition=models.Q(amount__gte=0), name="ck_addon_price_amount"),
        ]


class ProductAddon(models.Model):
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    addon = models.ForeignKey(Addon, on_delete=models.CASCADE)
    required = models.BooleanField(default=False)
    sort_order = models.IntegerField(default=0)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=("product", "addon"), name="uq_product_addon"),
        ]
        ordering = ("sort_order",)
