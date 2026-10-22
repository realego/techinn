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
        domain = DomainAsset.objects.filter(
            domain_name=context.get("domain"),
            status__in=("pending", "transfer_pending"),
        ).select_related("customer_service").first()
        if not domain:
            return "Domain no longer processing."
        registration = dict((domain.customer_service.provisioning_data or {}).get("domain_registration", {}))
        current_state = f"{domain.status}:{registration.get('status') or 'pending'}"
        # Legacy rows did not persist a state.  Do not deliver them: they are
        # exactly the repeated "still processing" messages this policy stops.
        if context.get("state") != current_state:
            return "Domain processing state changed before delivery."
        if timezone.now() - domain.created_at < timedelta(hours=1):
            return "Domain processing notification is within the first-hour quiet period."
    elif slug == "cart-payment-reminder":
        if not Order.objects.filter(order_number=context.get("order_number"), status="awaiting_payment").exists():
            return "Order no longer awaiting payment."
    elif slug == "invoice-ready":
        if not Invoice.objects.filter(invoice_number=context.get("invoice_number"), status="unpaid").exists():
            return "Invoice no longer unpaid."
    if slug in {"service-processing", "domain-processing", "cart-payment-reminder"} and row.created_at < timezone.now()-timedelta(days=2):
        return "Transient notification expired while queued."
    return ""
