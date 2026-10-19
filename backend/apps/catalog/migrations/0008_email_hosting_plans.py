from decimal import Decimal

from django.db import migrations


def update_email_catalog(apps, schema_editor):
    Product = apps.get_model("catalog", "Product")
    ProductPrice = apps.get_model("catalog", "ProductPrice")
    Addon = apps.get_model("catalog", "Addon")
    AddonPrice = apps.get_model("catalog", "AddonPrice")
    ProductAddon = apps.get_model("catalog", "ProductAddon")
    database = schema_editor.connection.alias

    plans = {
        "email-essential": ("Essential Email", Decimal("18.95")),
        "email-team": ("Team Email", Decimal("37.90")),
        "email-business-mail": ("Business Email", Decimal("60.00")),
    }
    for slug, (name, annual_amount) in plans.items():
        product = Product.objects.using(database).get(slug=slug)
        product.name = name
        product.save(update_fields=["name", "updated_at"])
        ProductPrice.objects.using(database).filter(product=product, billing_interval="monthly").update(
            status="inactive", is_default=False
        )
        annual, _ = ProductPrice.objects.using(database).get_or_create(
            product=product, currency="USD", billing_interval="annually",
            defaults={"amount": annual_amount, "setup_fee": Decimal("0"), "period_months": 12},
        )
        annual.amount = annual_amount
        annual.period_months = 12
        annual.status = "active"
        annual.is_default = True
        annual.save(update_fields=["amount", "period_months", "status", "is_default", "updated_at"])

    addons = [
        ("email-storage-5gb", "Extra 5 GB email storage", Decimal("5.00"), ("email-essential", "email-team")),
        ("email-mailboxes-10", "Extra 10 email accounts", Decimal("3.00"), ("email-essential",)),
        ("email-mailboxes-20", "Extra 20 email accounts", Decimal("5.00"), ("email-team",)),
        ("email-storage-15gb", "Extra 15 GB email storage", Decimal("15.00"), ("email-business-mail",)),
    ]
    for slug, name, amount, product_slugs in addons:
        addon, _ = Addon.objects.using(database).get_or_create(
            slug=slug,
            defaults={"name": name, "billing_type": "recurring", "status": "active"},
        )
        addon.name = name
        addon.status = "active"
        addon.save(update_fields=["name", "status"])
        annual, _ = AddonPrice.objects.using(database).get_or_create(
            addon=addon, currency="USD", billing_interval="annually",
            defaults={"amount": amount},
        )
        annual.amount = amount
        annual.save(update_fields=["amount"])
        for product_slug in product_slugs:
            product = Product.objects.using(database).get(slug=product_slug)
            ProductAddon.objects.using(database).get_or_create(product=product, addon=addon)


class Migration(migrations.Migration):
    dependencies = [("catalog", "0007_trim_chatbot_addons")]
    operations = [migrations.RunPython(update_email_catalog, migrations.RunPython.noop)]
