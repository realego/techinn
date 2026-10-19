"""Billing lifecycle notifications."""

from django.db import transaction
from django.db.models.signals import post_save
from django.dispatch import receiver

from apps.billing.models import Invoice
from apps.notifications.lifecycle import ensure_lifecycle_templates, queue_lifecycle_event


@receiver(post_save, sender=Invoice)
def queue_invoice_ready_email(sender, instance, created, **kwargs):
    """Queue one invoice-ready message when an unpaid invoice is first created."""
    if not created or instance.status != Invoice.Status.UNPAID:
        return

    def enqueue():
        # This also makes the hook safe for invoices created by the admin or a
        # future billing integration before the template worker has run.
        ensure_lifecycle_templates()
        queue_lifecycle_event(
            customer=instance.customer,
            slug="invoice-ready",
            key=f"invoice:{instance.pk}:ready",
            context={
                "invoice_number": instance.invoice_number,
                "due_date": instance.due_at.strftime("%d %B %Y") if instance.due_at else "Shown in your billing area",
                "amount_due": f"{instance.currency} {instance.total}",
            },
            category="billing_reminders",
        )

    transaction.on_commit(enqueue)
