"""Customer-facing project services and explicitly configured dashboard access."""
from urllib.parse import urlsplit
from django.db import transaction
from django.utils import timezone
from apps.services.models import CustomerService
from apps.services.periods import extend_service_period

PROJECT_TYPES = ('chatbot-development', 'website-design', 'website-development', 'app-development')
PAID_SERVICE_TYPES = PROJECT_TYPES + ('domains', 'web-hosting', 'email-hosting')


def service_dashboard_links(service, allowed):
    expiry = service.expires_at or service.next_due_at
    if not allowed or service.status != 'active' or (expiry and expiry <= timezone.now()):
        return []
    result = []
    for instance in service.instances.all():
        # Export only explicit access fields, never the instance's private JSON data.
        url = instance.dashboard_url
        if instance.status != 'active' or not url:
            continue
        try:
            parsed = urlsplit(url)
            if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password:
                continue
        except ValueError:
            continue
        result.append({'name': instance.display_name or 'Open dashboard', 'url': url})
    return result


@transaction.atomic
def sync_paid_services(order):
    """Idempotently record paid projects as awaiting setup; don't claim they are live."""
    order = type(order).objects.select_for_update().get(pk=order.pk)
    if order.status not in ('paid', 'completed'):
        return 0
    created = 0
    for item in order.items.select_related('product__service_type'):
        if not item.product_id or item.product.service_type.slug not in PAID_SERVICE_TYPES:
            continue
        for _ in range(max(0, item.quantity - item.customer_services.count())):
            service = CustomerService.objects.create(customer=order.customer, product=item.product,
                order_item=item, status='pending', auto_renew=item.product.billing_type == 'recurring',
                provisioning_data={'setup': {'status': 'awaiting_setup'}, 'billing_interval': (item.metadata or {}).get('billing_interval', 'monthly')})
            extend_service_period(service, item)
            created += 1
    return created
