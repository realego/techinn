from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.billing.models import Payment
from apps.notifications.lifecycle import (
    ensure_lifecycle_templates,
    queue_domain_processing_update,
    queue_lifecycle_event,
)
from apps.orders.models import Order
from apps.services.models import CustomerService, DomainAsset


class Command(BaseCommand):
    help = "Queue idempotent cart, payment, processing, renewal and suspension notifications."

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=500)

    def handle(self, *args, **options):
        ensure_lifecycle_templates()
        now = timezone.now()
        queued = 0
        # A checkout that remains unpaid for 24 hours receives one reminder.
        for order in Order.objects.filter(status=Order.Status.AWAITING_PAYMENT, created_at__lte=now - timedelta(hours=24)).select_related("customer")[:options["limit"]]:
            if queue_lifecycle_event(customer=order.customer, slug="cart-payment-reminder", key=f"cart:{order.pk}:24h", context={"order_number": order.order_number}, category="billing_reminders"):
                queued += 1

        # Payment and provisioning rows are queued by their state, with a stable key.
        # Payment confirmation is sent immediately by the payment callback.
        # Keeping it out of this hourly queue prevents duplicate receipts.
        for payment in Payment.objects.filter(status=Payment.Status.SUCCESSFUL, provider_data__wallet_top_up=True).select_related("customer")[:options["limit"]]:
            if queue_lifecycle_event(customer=payment.customer, slug="balance-deposit-confirmation", key=f"deposit:payment:{payment.pk}", context={"payment_uuid": str(payment.uuid)}):
                queued += 1

        for service in CustomerService.objects.filter(status__in=(CustomerService.Status.PENDING, CustomerService.Status.PROVISIONING)).select_related("customer")[:options["limit"]]:
            if queue_lifecycle_event(customer=service.customer, slug="service-processing", key=f"service:processing:{service.pk}", context={"service_uuid": str(service.uuid)}):
                queued += 1

        for domain in DomainAsset.objects.filter(status__in=(DomainAsset.Status.PENDING, DomainAsset.Status.TRANSFER_PENDING)).select_related("customer_service__customer")[:options["limit"]]:
            if queue_domain_processing_update(domain=domain, now=now):
                queued += 1

        for service in CustomerService.objects.filter(status=CustomerService.Status.ACTIVE, expires_at__isnull=False).select_related("customer", "product__service_type")[:options["limit"]]:
            months = ((service.provisioning_data or {}).get("billing_interval") == "yearly") and 12 or 1
            days = (service.expires_at - now).total_seconds() / 86400
            offsets = (30, 15, 5) if months >= 12 else (10, 5)
            for offset in offsets:
                if 0 <= days <= offset and days > offset - 1:
                    if queue_lifecycle_event(customer=service.customer, slug="service-expiry-reminder", key=f"service:{service.pk}:expires:{offset}", context={"service_uuid": str(service.uuid), "days": offset}, category="billing_reminders"):
                        queued += 1
            if days <= 0 and queue_lifecycle_event(customer=service.customer, slug="service-overdue-suspension", key=f"service:{service.pk}:overdue", context={"service_uuid": str(service.uuid), "action": "suspend"}, category="billing_reminders"):
                queued += 1

        for domain in DomainAsset.objects.filter(status=DomainAsset.Status.ACTIVE, expires_at__isnull=False).select_related("customer_service__customer")[:options["limit"]]:
            days = (domain.expires_at - now).total_seconds() / 86400
            for offset in (30, 15, 5):
                if 0 <= days <= offset and days > offset - 1 and queue_lifecycle_event(customer=domain.customer_service.customer, slug="domain-expiry-reminder", key=f"domain:{domain.pk}:expires:{offset}", context={"domain": domain.domain_name, "days": offset}, category="billing_reminders"):
                    queued += 1
            if days <= 0 and queue_lifecycle_event(customer=domain.customer_service.customer, slug="service-overdue-suspension", key=f"domain:{domain.pk}:overdue", context={"domain": domain.domain_name, "action": "suspend"}, category="billing_reminders"):
                queued += 1
        self.stdout.write(f"Lifecycle events queued: {queued}")
