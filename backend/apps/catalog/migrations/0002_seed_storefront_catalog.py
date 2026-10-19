from decimal import Decimal

from django.db import migrations


SERVICE_TYPES = (
    ("website-design", "Website Design"),
    ("web-hosting", "Web Hosting"),
    ("email-hosting", "Email Hosting"),
    ("domains", "Domains"),
    ("app-development", "App Development"),
)

PRODUCTS = (
    ("website-basic-website", "Website development", "website-design", "one_time", 6000, None),
    ("web-basic", "Basic Web Hosting", "web-hosting", "recurring", 350, 3780),
    ("web-growth", "Growth Web Hosting", "web-hosting", "recurring", 700, 7560),
    ("web-business", "Business Web Hosting", "web-hosting", "recurring", 1200, 12960),
    ("email-essential", "Essential Email", "email-hosting", "recurring", 150, 1620),
    ("email-team", "Team Email", "email-hosting", "recurring", 350, 3780),
    ("email-business-mail", "Business Mail", "email-hosting", "recurring", 650, 7020),
    ("domains", "Domain registration", "domains", "recurring", 0, 0),
    ("app-development", "App development", "app-development", "one_time", 25000, None),
)

# slug, name, product slugs, billing type, monthly/one-time cents, yearly cents
ADDONS = (
    ("website-extra-page", "Additional page", ("website-basic-website",), "one_time", 1000, None),
    ("website-online-store", "Shopping cart and checkout", ("website-basic-website",), "one_time", 12000, None),
    ("website-booking", "Online booking", ("website-basic-website",), "one_time", 0, None),
    ("website-blog", "Blog or news section", ("website-basic-website",), "one_time", 3500, None),
    ("web-storage-5gb", "Extra 5 GB SSD storage", ("web-basic", "web-growth", "web-business"), "recurring", 150, 1620),
    ("web-storage-10gb", "Extra 10 GB SSD storage", ("web-basic", "web-growth", "web-business"), "recurring", 300, 3240),
    ("web-backup-30days", "30-day backup retention", ("web-basic", "web-growth", "web-business"), "recurring", 100, 1080),
    ("web-backup-90days", "90-day backup retention", ("web-basic", "web-growth", "web-business"), "recurring", 200, 2160),
    ("email-storage-5gb", "Extra 5 GB mailbox storage", ("email-essential", "email-team", "email-business-mail"), "recurring", 100, 1080),
    ("email-storage-10gb", "Extra 10 GB mailbox storage", ("email-essential", "email-team", "email-business-mail"), "recurring", 200, 2160),
    ("email-archive", "Email archiving", ("email-essential", "email-team", "email-business-mail"), "recurring", 100, 1080),
    ("domain-co-zw", ".co.zw domain", ("domains",), "recurring", 1200, None),
    ("domain-com", ".com domain", ("domains",), "recurring", 1400, None),
    ("domain-net", ".net domain", ("domains",), "recurring", 1600, None),
    ("domain-online", ".online domain", ("domains",), "recurring", 800, None),
    ("domain-monitoring", "Domain monitoring", ("domains",), "recurring", 400, None),
    ("domain-dns-assistance", "Managed DNS assistance", ("domains",), "recurring", 600, None),
    ("app-publishing", "App store publishing support", ("app-development",), "one_time", 4500, None),
    ("app-maintenance", "Monthly app maintenance", ("app-development",), "recurring", 2500, None),
)


def seed_storefront_catalog(apps, schema_editor):
    ServiceType = apps.get_model("catalog", "ServiceType")
    Product = apps.get_model("catalog", "Product")
    ProductPrice = apps.get_model("catalog", "ProductPrice")
    Addon = apps.get_model("catalog", "Addon")
    AddonPrice = apps.get_model("catalog", "AddonPrice")
    ProductAddon = apps.get_model("catalog", "ProductAddon")
    database = schema_editor.connection.alias

    service_types = {}
    for slug, name in SERVICE_TYPES:
        service_types[slug], _ = ServiceType.objects.using(database).get_or_create(
            slug=slug,
            defaults={"name": name, "status": "active"},
        )

    products = {}
    for slug, name, service_slug, billing_type, monthly_cents, annual_cents in PRODUCTS:
        products[slug], _ = Product.objects.using(database).get_or_create(
            slug=slug,
            defaults={
                "name": name,
                "service_type": service_types[service_slug],
                "billing_type": billing_type,
                "status": "active",
            },
        )
        intervals = [("one_time", monthly_cents)] if billing_type == "one_time" else [
            ("monthly", monthly_cents),
            ("annually", annual_cents),
        ]
        default_interval = (
            "one_time" if billing_type == "one_time" else "annually" if slug == "domains" else "monthly"
        )
        for interval, amount_cents in intervals:
            ProductPrice.objects.using(database).get_or_create(
                product=products[slug],
                currency="USD",
                billing_interval=interval,
                defaults={
                    "amount": Decimal(amount_cents) / Decimal(100),
                    "setup_fee": Decimal("0.00"),
                    "is_default": interval == default_interval,
                    "status": "active",
                },
            )

    for slug, name, product_slugs, billing_type, monthly_cents, annual_cents in ADDONS:
        addon, _ = Addon.objects.using(database).get_or_create(
            slug=slug,
            defaults={
                "name": name,
                "billing_type": billing_type,
                "status": "active",
            },
        )
        intervals = [("one_time", monthly_cents)] if billing_type == "one_time" else [
            ("monthly", monthly_cents),
            ("annually", annual_cents if annual_cents is not None else monthly_cents),
        ]
        for interval, amount_cents in intervals:
            AddonPrice.objects.using(database).get_or_create(
                addon=addon,
                currency="USD",
                billing_interval=interval,
                defaults={"amount": Decimal(amount_cents) / Decimal(100)},
            )
        for product_slug in product_slugs:
            ProductAddon.objects.using(database).get_or_create(
                product=products[product_slug],
                addon=addon,
            )


class Migration(migrations.Migration):

    dependencies = [
        ("catalog", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(seed_storefront_catalog, migrations.RunPython.noop),
    ]
