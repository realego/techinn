from django.conf import settings
from django.db import models

from apps.services.models import CustomerService


class AutomationRule(models.Model):
    class OffsetUnit(models.TextChoices):
        MINUTES = "minutes", "Minutes"
        HOURS = "hours", "Hours"
        DAYS = "days", "Days"
        WEEKS = "weeks", "Weeks"
        MONTHS = "months", "Months"

    class Direction(models.TextChoices):
        BEFORE = "before", "Before"
        AFTER = "after", "After"
        AT = "at", "At"

    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        INACTIVE = "inactive", "Inactive"

    name = models.CharField(max_length=150)
    slug = models.SlugField(max_length=150, unique=True)
    event_type = models.CharField(max_length=100)
    offset_value = models.IntegerField(null=True, blank=True)
    offset_unit = models.CharField(max_length=10, choices=OffsetUnit.choices, null=True, blank=True)
    direction = models.CharField(max_length=6, choices=Direction.choices, null=True, blank=True)
    action_type = models.CharField(max_length=100)
    configuration = models.JSONField(null=True, blank=True)
    status = models.CharField(max_length=8, choices=Status.choices, default=Status.ACTIVE)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name


class AutomationExecution(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        PROCESSING = "processing", "Processing"
        COMPLETED = "completed", "Completed"
        FAILED = "failed", "Failed"
        SKIPPED = "skipped", "Skipped"

    automation_rule = models.ForeignKey(
        AutomationRule,
        on_delete=models.PROTECT,
        related_name="executions",
    )
    customer_service = models.ForeignKey(
        CustomerService,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="automation_executions",
    )
    customer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="automation_executions",
    )
    scheduled_for = models.DateTimeField()
    executed_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING, db_index=True)
    result = models.JSONField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("automation_rule", "customer_service", "scheduled_for"),
                name="uq_automation_execution",
            ),
        ]
        indexes = [models.Index(fields=("status", "scheduled_for"), name="idx_automation_pending")]
