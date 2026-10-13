from decimal import Decimal

from django.db import migrations


def seed_balance_topup(apps, schema_editor):
    ServiceType = apps.get_model("catalog", "ServiceType")
    Product = apps.get_model("catalog", "Product")
    ProductPrice = apps.get_model("catalog", "ProductPrice")
    database = schema_editor.connection.alias

    service_type, _ = ServiceType.objects.using(database).get_or_create(
        slug="account-balance",
        defaults={"name": "Account balance", "description": "Add funds to your TechInn balance."},
    )
    product, _ = Product.objects.using(database).get_or_create(
        slug="account-balance",
        defaults={
            "service_type": service_type,
            "name": "Account balance top-up",
            "description": "Add $10 to your TechInn account balance. Increase the quantity to add more.",
            "billing_type": "one_time",
            "status": "active",
            "sort_order": 100,
        },
    )
    ProductPrice.objects.using(database).get_or_create(
        product=product,
        currency="USD",
        billing_interval="one_time",
        defaults={
            "amount": Decimal("10.00"),
            "setup_fee": Decimal("0.00"),
            "is_default": True,
            "status": "active",
        },
    )


class Migration(migrations.Migration):
    dependencies = [("catalog", "0003_productprice_period_months")]

    operations = [migrations.RunPython(seed_balance_topup, migrations.RunPython.noop)]
