import calendar

from django.utils import timezone

from apps.catalog.models import ProductPrice


def _add_months(value, months):
    month_index = value.month - 1 + months
    year = value.year + month_index // 12
    month = month_index % 12 + 1
    day = min(value.day, calendar.monthrange(year, month)[1])
    return value.replace(year=year, month=month, day=day)


def period_months_for_order_item(order_item):
    metadata = order_item.metadata or {}
    if "period_months" in metadata:
        try:
            return max(int(metadata["period_months"]), 0)
        except (TypeError, ValueError):
            return 0
    interval = metadata.get("billing_interval")
    if not interval or not order_item.product_id:
        return 0
    price = ProductPrice.objects.filter(
        product=order_item.product,
        currency=order_item.order.currency,
        billing_interval=interval,
        status=ProductPrice.Status.ACTIVE,
    ).first()
    return price.period_months if price else 0


def extend_service_period(service, order_item, *, now=None):
    """Apply one paid order item's DB-configured period exactly once."""
    now = now or timezone.now()
    data = dict(service.provisioning_data or {})
    applied_items = list(data.get("period_order_item_ids", []))
    if order_item.pk in applied_items:
        return service

    months = period_months_for_order_item(order_item)
    if months:
        start = max(now, service.expires_at) if service.expires_at else now
        service.started_at = service.started_at or start
        service.expires_at = _add_months(start, months)
        service.next_due_at = service.expires_at
    applied_items.append(order_item.pk)
    data["period_order_item_ids"] = applied_items
    service.provisioning_data = data
    service.save(update_fields=("started_at", "expires_at", "next_due_at", "provisioning_data", "updated_at"))
    return service
