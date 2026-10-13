import re
import uuid
from decimal import Decimal

from django.db import transaction
from rest_framework.exceptions import ValidationError

from apps.catalog.models import Addon, AddonPrice, Product, ProductPrice
from apps.orders.models import Order, OrderItem


OPTION_CHOICES = {
    "website-basic-website": {
        "extra-page": {str(count): ("website-extra-page", count) for count in range(1, 11)},
        "online-store": {"enabled": ("website-online-store", 1)},
        "booking": {"enabled": ("website-booking", 1)},
        "blog": {"enabled": ("website-blog", 1)},
    },
    "web-basic": {
        "storage": {"5gb": ("web-storage-5gb", 1), "10gb": ("web-storage-10gb", 1)},
        "backup-retention": {"30days": ("web-backup-30days", 1), "90days": ("web-backup-90days", 1)},
    },
    "web-growth": {
        "storage": {"5gb": ("web-storage-5gb", 1), "10gb": ("web-storage-10gb", 1)},
        "backup-retention": {"30days": ("web-backup-30days", 1), "90days": ("web-backup-90days", 1)},
    },
    "web-business": {
        "storage": {"5gb": ("web-storage-5gb", 1), "10gb": ("web-storage-10gb", 1)},
        "backup-retention": {"30days": ("web-backup-30days", 1), "90days": ("web-backup-90days", 1)},
    },
    "email-essential": {
        "storage": {"5gb": ("email-storage-5gb", 1), "10gb": ("email-storage-10gb", 1)},
        "archive": {"enabled": ("email-archive", 1)},
    },
    "email-team": {
        "storage": {"5gb": ("email-storage-5gb", 1), "10gb": ("email-storage-10gb", 1)},
        "archive": {"enabled": ("email-archive", 1)},
    },
    "email-business-mail": {
        "storage": {"5gb": ("email-storage-5gb", 1), "10gb": ("email-storage-10gb", 1)},
        "archive": {"enabled": ("email-archive", 1)},
    },
    "domains": {
        "extension": {
            "co-zw": ("domain-co-zw", 1),
            "com": ("domain-com", 1),
            "net": ("domain-net", 1),
            "online": ("domain-online", 1),
        },
        "monitoring": {"enabled": ("domain-monitoring", 1)},
        "dns-assistance": {"enabled": ("domain-dns-assistance", 1)},
    },
    "app-development": {
        "publishing": {"enabled": ("app-publishing", 1)},
        "maintenance": {"enabled": ("app-maintenance", 1)},
    },
}
RECURRING_PRODUCTS = {
    "web-basic",
    "web-growth",
    "web-business",
    "email-essential",
    "email-team",
    "email-business-mail",
    "domains",
}
DOMAIN_SUFFIXES = {
    "co-zw": ".co.zw",
    "com": ".com",
    "net": ".net",
    "online": ".online",
}
DOMAIN_PATTERN = re.compile(r"^(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}$")


def _domain_name(value, extension):
    domain = value.strip().lower()
    if len(domain) > 253 or not DOMAIN_PATTERN.fullmatch(domain):
        raise ValidationError({"items": ["Enter a valid domain name to register."]})
    if not domain.endswith(DOMAIN_SUFFIXES[extension]):
        raise ValidationError({"items": ["The domain name must match the selected extension."]})
    return domain


def _active_product(slug):
    try:
        return Product.objects.select_related("service_type").get(
            slug=slug,
            status=Product.Status.ACTIVE,
            service_type__status="active",
        )
    except Product.DoesNotExist as exc:
        raise ValidationError({"items": ["One or more selected services are unavailable."]}) from exc


def _active_price(queryset, interval):
    try:
        return queryset.get(currency="USD", billing_interval=interval)
    except queryset.model.DoesNotExist as exc:
        raise ValidationError({"items": ["Pricing is not configured for one or more selected services."]}) from exc


def create_checkout_order(customer, lines, details, displayed_total):
    priced_lines = []
    subtotal = Decimal("0.00")

    for line in lines:
        product_slug = line["product_id"]
        product = _active_product(product_slug)
        selections = line["options"]
        option_map = OPTION_CHOICES.get(product_slug)
        if option_map is None:
            raise ValidationError({"items": ["One or more selected services are unavailable."]})
        unknown_options = set(selections) - set(option_map) - {"billing"}
        if unknown_options:
            raise ValidationError({"items": ["One or more selected options are unavailable."]})

        yearly = selections.get("billing") == "yearly"
        if "billing" in selections and (selections["billing"] != "yearly" or product_slug not in RECURRING_PRODUCTS):
            raise ValidationError({"items": ["The selected billing interval is unavailable."]})
        interval = "annually" if yearly or product_slug == "domains" else (
            "monthly" if product_slug in RECURRING_PRODUCTS else "one_time"
        )
        base_price = _active_price(
            ProductPrice.objects.filter(product=product, status=ProductPrice.Status.ACTIVE),
            interval,
        )
        quantity = line["quantity"]
        if product_slug == "domains" and quantity != 1:
            raise ValidationError({"items": ["Add each domain as a separate cart item."]})

        domain = None
        if product_slug == "domains":
            extension = selections.get("extension")
            if not extension:
                raise ValidationError({"items": ["Choose a domain extension before continuing."]})
            domain = _domain_name(line.get("domain_name", ""), extension)
        elif line.get("domain_name"):
            raise ValidationError({"items": ["A domain name can only be attached to a domain registration."]})

        item_metadata = {
            "billing_interval": interval,
            "period_months": base_price.period_months,
            "setup_fee": str(base_price.setup_fee),
            "options": selections,
        }
        if domain:
            item_metadata["domain"] = domain
        base_subtotal = (base_price.amount + base_price.setup_fee) * quantity
        priced_lines.append(
            {
                "product": product,
                "addon": None,
                "description": f"{product.name} ({domain})" if domain else product.name,
                "quantity": quantity,
                "unit_price": base_price.amount,
                "subtotal": base_subtotal,
                "metadata": item_metadata,
            }
        )
        subtotal += base_subtotal

        for option, choice in selections.items():
            if option == "billing":
                continue
            addon_slug, choice_quantity = option_map[option].get(choice, (None, None))
            if not addon_slug:
                raise ValidationError({"items": ["One or more selected options are unavailable."]})
            try:
                addon = Addon.objects.get(
                    slug=addon_slug,
                    status=Addon.Status.ACTIVE,
                    productaddon__product=product,
                )
            except Addon.DoesNotExist as exc:
                raise ValidationError({"items": ["One or more selected options are unavailable."]}) from exc
            addon_interval = (
                "annually" if yearly else "monthly"
            ) if addon.billing_type == Addon.BillingType.RECURRING else "one_time"
            addon_price = _active_price(
                AddonPrice.objects.filter(addon=addon),
                addon_interval,
            )
            addon_quantity = choice_quantity * quantity
            addon_subtotal = addon_price.amount * addon_quantity
            priced_lines.append(
                {
                    "product": None,
                    "addon": addon,
                    "description": f"{addon.name} ({domain})" if domain else addon.name,
                    "quantity": addon_quantity,
                    "unit_price": addon_price.amount,
                    "subtotal": addon_subtotal,
                    "metadata": {
                        "billing_interval": addon_interval,
                        "option": option,
                        "choice": choice,
                        **({"domain": domain} if domain else {}),
                    },
                }
            )
            subtotal += addon_subtotal

    if subtotal < Decimal("1.00"):
        raise ValidationError({"items": ["The order total must be at least $1.00."]})
    if subtotal != displayed_total:
        raise ValidationError(
            {"displayed_total": ["Prices have changed. Review the updated cart before paying."]}
        )

    with transaction.atomic():
        order = Order.objects.create(
            customer=customer,
            order_number=f"TI-{uuid.uuid4().hex.upper()}",
            status=Order.Status.AWAITING_PAYMENT,
            currency="USD",
            subtotal=subtotal,
            total=subtotal,
            metadata=details,
        )
        OrderItem.objects.bulk_create(
            [
                OrderItem(order=order, **line)
                for line in priced_lines
            ]
        )
    return order
