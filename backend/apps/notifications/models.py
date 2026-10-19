from django.conf import settings
from django.db import models
from django.utils import timezone


class EmailTemplate(models.Model):
    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        INACTIVE = "inactive", "Inactive"

    name = models.CharField(max_length=150)
    slug = models.SlugField(max_length=150, unique=True)
    subject = models.CharField(max_length=255)
    body_html = models.TextField()
    body_text = models.TextField(blank=True)
    status = models.CharField(max_length=8, choices=Status.choices, default=Status.ACTIVE)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name


class EmailTemplateVariable(models.Model):
    email_template = models.ForeignKey(
        EmailTemplate,
        on_delete=models.CASCADE,
        related_name="variables",
    )
    variable_name = models.CharField(max_length=100)
    description = models.CharField(max_length=255, blank=True)
    required = models.BooleanField(default=False)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("email_template", "variable_name"),
                name="uq_template_variable",
            ),
        ]


class EmailQueue(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        PROCESSING = "processing", "Processing"
        SENT = "sent", "Sent"
        FAILED = "failed", "Failed"
        CANCELLED = "cancelled", "Cancelled"

    customer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="queued_emails",
    )
    email_template = models.ForeignKey(EmailTemplate, on_delete=models.PROTECT, related_name="queued_emails")
    recipient_email = models.EmailField(max_length=255)
    subject = models.CharField(max_length=255)
    payload = models.JSONField(default=dict)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING, db_index=True)
    attempts = models.PositiveIntegerField(default=0)
    scheduled_at = models.DateTimeField(default=timezone.now, db_index=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    last_error = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)


class EmailLog(models.Model):
    class Status(models.TextChoices):
        SENT = "sent", "Sent"
        DELIVERED = "delivered", "Delivered"
        BOUNCED = "bounced", "Bounced"
        COMPLAINED = "complained", "Complained"
        FAILED = "failed", "Failed"

    email_queue = models.ForeignKey(EmailQueue, on_delete=models.CASCADE, related_name="logs")
    provider = models.CharField(max_length=100, blank=True)
    provider_message_id = models.CharField(max_length=255, blank=True)
    status = models.CharField(max_length=10, choices=Status.choices)
    response_data = models.JSONField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)


class ContactRequest(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        HANDLED = "handled", "Handled"

    name = models.CharField(max_length=120)
    email = models.EmailField(max_length=255)
    phone = models.CharField(max_length=40, blank=True)
    message = models.TextField(max_length=4000)
    source = models.CharField(max_length=80, default="shop")
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    handled_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("-created_at",)

    def __str__(self):
        return f"{self.name} · {self.email}"
