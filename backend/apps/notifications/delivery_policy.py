"""Recheck transient messages at delivery time so stale updates cannot mislead."""
from datetime import timedelta
from django.utils import timezone
from apps.orders.models import Order
from apps.services.models import CustomerService, DomainAsset
from apps.billing.models import Invoice


def obsolete_reason(row):
    slug = row.email_template.slug
    context = row.payload.get("context", {})
    if slug == "service-processing":
        if not CustomerService.objects.filter(uuid=context.get("service_uuid"), status__in=("pending", "provisioning")).exists():
            return "Service no longer processing."
    elif slug == "domain-processing":
        if not DomainAsset.objects.filter(domain_name=context.get("domain"), status__in=("pending", "transfer_pending")).exists():
            return "Domain no longer processing."
    elif slug == "cart-payment-reminder":
        if not Order.objects.filter(order_number=context.get("order_number"), status="awaiting_payment").exists():
            return "Order no longer awaiting payment."
    elif slug == "invoice-ready":
        if not Invoice.objects.filter(invoice_number=context.get("invoice_number"), status="unpaid").exists():
            return "Invoice no longer unpaid."
    if slug in {"service-processing", "domain-processing", "cart-payment-reminder"} and row.created_at < timezone.now()-timedelta(days=2):
        return "Transient notification expired while queued."
    return ""
