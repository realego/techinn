"""Idempotent lifecycle notification queueing.

The worker is deliberately separate from this module: lifecycle runs record one
queue row per event, while delivery can be enabled once templates are written.
"""
from django.db import IntegrityError, transaction
from apps.accounts.models import Customer
from django.utils import timezone

from apps.notifications.models import EmailQueue, EmailTemplate
from apps.notifications.preferences import notification_enabled


TEMPLATE_SLUGS = (
    "invoice-ready",
    "account-created",
    "password-reset",
    "purchased-services-guide",
    "domain-active",
    "cart-payment-reminder",
    "payment-confirmation",
    "domain-processing",
    "service-processing",
    "balance-deposit-confirmation",
    "domain-expiry-reminder",
    "service-expiry-reminder",
    "service-overdue-suspension",
)


def ensure_lifecycle_templates():
    """Create the active transactional template catalogue without overwriting edits."""
    names = {
        "invoice-ready": "Your TechInn invoice is ready",
        "account-created": "Your TechInn account is ready",
        "password-reset": "Your TechInn password reset code",
        "purchased-services-guide": "Getting started with your TechInn services",
        "domain-active": "Your TechInn domain is active",
        "cart-payment-reminder": "Cart payment reminder",
        "payment-confirmation": "Payment confirmation",
        "domain-processing": "Domain processing update",
        "service-processing": "Service processing update",
        "balance-deposit-confirmation": "Balance deposit confirmation",
        "domain-expiry-reminder": "Domain expiry reminder",
        "service-expiry-reminder": "Service expiry reminder",
        "service-overdue-suspension": "Service suspended for overdue renewal",
    }
    subjects = {
        "invoice-ready": "Your TechInn invoice is ready",
        "account-created": "Your TechInn account is ready",
        "password-reset": "Your TechInn password reset code",
        "purchased-services-guide": "Getting started with your TechInn services",
        "domain-active": "Your TechInn domain is active",
        "cart-payment-reminder": "Your TechInn payment is waiting",
        "payment-confirmation": "Your TechInn payment is confirmed",
        "domain-processing": "Your TechInn domain is processing",
        "service-processing": "Your TechInn service is being prepared",
        "balance-deposit-confirmation": "Your TechInn deposit is confirmed",
        "domain-expiry-reminder": "Renew your TechInn domain",
        "service-expiry-reminder": "Renew your TechInn service",
        "service-overdue-suspension": "Action required: service renewal overdue",
    }
    for slug in TEMPLATE_SLUGS:
        template, _ = EmailTemplate.objects.get_or_create(
            slug=slug,
            defaults={"name": names[slug], "subject": subjects[slug], "body_html": "", "body_text": "", "status": EmailTemplate.Status.ACTIVE},
        )
        changed = []
        if not template.subject:
            template.subject = subjects[slug]
            changed.append("subject")
        if template.status == EmailTemplate.Status.INACTIVE and not template.body_html and not template.body_text:
            template.status = EmailTemplate.Status.ACTIVE
            changed.append("status")
        if changed:
            template.save(update_fields=(*changed, "updated_at"))


@transaction.atomic
def queue_lifecycle_event(*, customer, slug, key, context=None, category="service_updates", scheduled_at=None):
    """Queue one event. Empty/inactive templates remain records, never sent."""
    if not notification_enabled(customer, category):
        return None
    template = EmailTemplate.objects.filter(slug=slug).first()
    if template is None or template.status != EmailTemplate.Status.ACTIVE:
        return None
    Customer.objects.select_for_update().get(pk=customer.pk)
    payload = {"lifecycle_key": key, "context": context or {}}
    if EmailQueue.objects.filter(payload__lifecycle_key=key).exists():
        return None
    try:
        return EmailQueue.objects.create(
            customer=customer,
            email_template=template,
            recipient_email=customer.email,
            subject=template.subject,
            payload=payload,
            scheduled_at=scheduled_at or timezone.now(),
        )
    except IntegrityError:
        return None
