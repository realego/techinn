"""Idempotent lifecycle notification queueing.

The worker is deliberately separate from this module: lifecycle runs record one
queue row per event, while delivery can be enabled once templates are written.
"""
from django.db import IntegrityError, transaction
from apps.accounts.models import Customer
from datetime import timedelta

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


DOMAIN_PROCESSING_GRACE = timedelta(hours=1)


def queue_domain_processing_update(*, domain, now=None):
    """Queue a domain-processing email only after a real state transition.

    Domain activation is polled more often than customers need email.  The
    initial state is recorded without sending anything, and transitions seen
    during the first hour are also recorded silently.  This prevents a worker
    restart or a long-running registry check from turning one pending domain
    into a recurring inbox notification.
    """
    now = now or timezone.now()
    service = domain.customer_service
    data = dict(service.provisioning_data or {})
    registration = dict(data.get("domain_registration", {}))
    state = f"{domain.status}:{registration.get('status') or 'pending'}"
    notification_state = dict(data.get("notification_state", {}))
    previous_state = notification_state.get("domain_processing")
    state_changed = previous_state is not None and previous_state != state

    if previous_state != state:
        notification_state["domain_processing"] = state
        notification_state["domain_processing_observed_at"] = now.isoformat()
        data["notification_state"] = notification_state
        service.provisioning_data = data
        service.save(update_fields=("provisioning_data", "updated_at"))

    # The first hour is intentionally quiet.  A later state change can send
    # one update, but an unchanged pending state never catches up with a
    # delayed "still processing" email.
    if not state_changed or now - domain.created_at < DOMAIN_PROCESSING_GRACE:
        return None

    return queue_lifecycle_event(
        customer=service.customer,
        slug="domain-processing",
        key=f"domain:processing:{domain.pk}:{state}",
        context={"domain": domain.domain_name, "status": domain.status, "state": state},
    )


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
