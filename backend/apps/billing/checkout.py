import re
import uuid
from decimal import Decimal

from django.conf import settings
from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from apps.catalog.models import Addon, AddonPrice, Product, ProductPrice
from apps.orders.models import Order, OrderItem
from apps.services.models import CustomerService, HostingAccount, HostingResource


OPTION_CHOICES = {
    "website-basic-website": {
        "extra-page": {str(count): ("website-extra-page", count) for count in range(1, 11)},
        "online-store": {"enabled": ("website-online-store", 1)},
        "booking": {"enabled": ("website-booking", 1)},
        "blog": {"enabled": ("website-blog", 1)},
    },
    "web-basic": {
        "backup-retention": {"30days": ("web-backup-30days", 1), "90days": ("web-backup-90days", 1)},
    },
    "web-growth": {
        "backup-retention": {"30days": ("web-backup-30days", 1), "90days": ("web-backup-90days", 1)},
    },
    "web-business": {
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
    "chatbot-basic": {
        "flows": {"enabled": ("chatbot-flows", 1)},
        "payments": {"enabled": ("chatbot-payments", 1)},
        "booking": {"enabled": ("chatbot-booking", 1)},
        "tickets": {"enabled": ("chatbot-tickets", 1)},
        "whatsapp": {"enabled": ("chatbot-whatsapp", 1)},
        "human-handoff": {"enabled": ("chatbot-human-handoff", 1)},
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
STORAGE_ADDON_PRODUCT_ID = "web-storage-addon"
STORAGE_ADDON_SLUG = "web-storage-5gb"
DOMAIN_PATTERN = re.compile(r"^(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}$")
TEST_CHECKOUT_TOTAL = Decimal("0.01")


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
    test_checkout_email = settings.CHECKOUT_TEST_EMAIL
    test_checkout = bool(
        test_checkout_email
        and customer.email.strip().casefold() == test_checkout_email
    )
    if test_checkout and any(line["product_id"] == "account-balance" for line in lines):
        raise ValidationError({"items": ["Account-balance top-ups are not available at the test checkout price."]})

    priced_lines = []
    subtotal = Decimal("0.00")

    for line in lines:
        product_slug = line["product_id"]
        if product_slug == STORAGE_ADDON_PRODUCT_ID:
            service_uuid = line.get("service_uuid")
            selections = line["options"]
            yearly = selections.get("billing") == "yearly"
            if (
                service_uuid is None
                or set(selections) - {"billing"}
                or ("billing" in selections and not yearly)
                or line.get("domain_name")
            ):
                raise ValidationError({"items": ["Choose an active hosting service and a supported storage billing interval."]})
            try:
                service = CustomerService.objects.select_related(
                    "product__service_type",
                    "hosting_account__primary_domain",
                ).get(
                    uuid=service_uuid,
                    customer=customer,
                    product__service_type__slug="web-hosting",
                    status=CustomerService.Status.ACTIVE,
                    hosting_account__status=HostingAccount.Status.ACTIVE,
                )
            except CustomerService.DoesNotExist as error:
                raise ValidationError({"items": ["The selected active hosting service is unavailable."]}) from error
            if service.expires_at and service.expires_at <= timezone.now():
                raise ValidationError({"items": ["The selected hosting service is outside its paid period."]})
            if not service.hosting_account.primary_domain_id or not service.hosting_account.resources.filter(
                resource_type=HostingResource.ResourceType.DISK,
            ).exists():
                raise ValidationError({"items": ["The selected service does not have a storage allocation to extend."]})
            try:
                addon = Addon.objects.get(
                    slug=STORAGE_ADDON_SLUG,
                    status=Addon.Status.ACTIVE,
                    billing_type=Addon.BillingType.RECURRING,
                    productaddon__product=service.product,
                )
            except Addon.DoesNotExist as error:
                raise ValidationError({"items": ["Storage extension is unavailable for this hosting plan."]}) from error
            interval = "annually" if yearly else "monthly"
            addon_price = _active_price(
                AddonPrice.objects.filter(addon=addon),
                interval,
            )
            quantity = line["quantity"]
            unit_price = addon_price.amount
            line_subtotal = unit_price * quantity
            domain_name = service.hosting_account.primary_domain.domain_name
            priced_lines.append({
                "product": None,
                "addon": addon,
                "description": f"{addon.name} for {domain_name}",
                "quantity": quantity,
                "unit_price": unit_price,
                "subtotal": line_subtotal,
                "metadata": {
                    "type": "hosting_storage_extension",
                    "billing_interval": interval,
                    "period_months": 12 if yearly else 1,
                    "storage_gb": "5",
                    "customer_service_uuid": str(service.uuid),
                },
            })
            subtotal += line_subtotal
            continue

        if line.get("service_uuid") is not None:
            raise ValidationError({"items": ["A hosting service can only be selected for a storage extension."]})
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
    checkout_total = TEST_CHECKOUT_TOTAL if test_checkout else subtotal
    if displayed_total != checkout_total:
        raise ValidationError(
            {"displayed_total": ["Prices have changed. Review the updated cart before paying."]}
        )

    order_details = dict(details)
    discount_total = Decimal("0.00")
    if test_checkout:
        discount_total = subtotal - checkout_total
        order_details["test_checkout"] = {
            "enabled": True,
            "catalog_subtotal": str(subtotal),
            "discount_total": str(discount_total),
            "charged_total": str(checkout_total),
        }

    with transaction.atomic():
        order = Order.objects.create(
            customer=customer,
            order_number=f"TI-{uuid.uuid4().hex.upper()}",
            status=Order.Status.AWAITING_PAYMENT,
            currency="USD",
            subtotal=subtotal,
            discount_total=discount_total,
            total=checkout_total,
            metadata=order_details,
        )
        OrderItem.objects.bulk_create(
            [
                OrderItem(order=order, **line)
                for line in priced_lines
            ]
        )
    return order
