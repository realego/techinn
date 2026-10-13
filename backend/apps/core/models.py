from django.conf import settings
from django.db import models

from apps.services.models import CustomerService


class SystemEvent(models.Model):
    event_type = models.CharField(max_length=150, db_index=True)
    customer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="system_events",
    )
    customer_service = models.ForeignKey(
        CustomerService,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="system_events",
    )
    entity_type = models.CharField(max_length=100, blank=True)
    entity_id = models.BigIntegerField(null=True, blank=True)
    payload = models.JSONField(null=True, blank=True)
    processed = models.BooleanField(default=False, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [models.Index(fields=("processed", "created_at"), name="idx_event_processing")]


class Setting(models.Model):
    class ValueType(models.TextChoices):
        STRING = "string", "String"
        INTEGER = "integer", "Integer"
        DECIMAL = "decimal", "Decimal"
        BOOLEAN = "boolean", "Boolean"
        JSON = "json", "JSON"

    setting_key = models.CharField(max_length=150, unique=True)
    value = models.TextField(blank=True)
    value_type = models.CharField(max_length=8, choices=ValueType.choices, default=ValueType.STRING)
    is_secret = models.BooleanField(default=False)
    description = models.CharField(max_length=255, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.setting_key
