from decimal import Decimal

from django.db import migrations


def update_domain_prices(apps, schema_editor):
    Product = apps.get_model("catalog", "Product")
    ProductPrice = apps.get_model("catalog", "ProductPrice")
    Addon = apps.get_model("catalog", "Addon")
    AddonPrice = apps.get_model("catalog", "AddonPrice")
    ProductAddon = apps.get_model("catalog", "ProductAddon")
    database = schema_editor.connection.alias

    prices = {
        "domain-co-zw": (".co.zw domain", Decimal("2.00")),
        "domain-org-zw": (".org.zw domain", Decimal("3.00")),
        "domain-ac-zw": (".ac.zw domain", Decimal("3.00")),
        "domain-com": (".com domain", Decimal("20.00")),
        "domain-net": (".net domain", Decimal("20.00")),
        "domain-org": (".org domain", Decimal("20.00")),
    }
    domains_product = Product.objects.using(database).get(slug="domains")
    for slug, (name, amount) in prices.items():
        addon, _ = Addon.objects.using(database).get_or_create(
            slug=slug,
            defaults={"name": name, "billing_type": "recurring", "status": "active"},
        )
        addon.name = name
        addon.status = "active"
        addon.save(update_fields=["name", "status"])
        annual, _ = AddonPrice.objects.using(database).get_or_create(
            addon=addon, currency="USD", billing_interval="annually", defaults={"amount": amount}
        )
        annual.amount = amount
        annual.save(update_fields=["amount"])
        ProductAddon.objects.using(database).get_or_create(product=domains_product, addon=addon)

    for slug, (name, amount) in prices.items():
        product_slug = "domains" if slug == "domain-co-zw" else "domains"
        product = domains_product
        # Domain extensions are represented as add-ons; keep the product's base at zero.
        ProductPrice.objects.using(database).filter(product=product, billing_interval="monthly").update(status="inactive")
        annual, _ = ProductPrice.objects.using(database).get_or_create(
            product=product, currency="USD", billing_interval="annually",
            defaults={"amount": Decimal("0.00"), "period_months": 12, "is_default": True, "status": "active"},
        )
        annual.amount = Decimal("0.00")
        annual.period_months = 12
        annual.is_default = True
        annual.status = "active"
        annual.save(update_fields=["amount", "period_months", "is_default", "status", "updated_at"])

    old = Addon.objects.using(database).filter(slug="domain-online").first()
    if old:
        old.status = "inactive"
        old.save(update_fields=["status"])


class Migration(migrations.Migration):
    dependencies = [("catalog", "0008_email_hosting_plans")]
    operations = [migrations.RunPython(update_domain_prices, migrations.RunPython.noop)]
