from decimal import Decimal

from django.db import migrations


def update_storage_extension_price(apps, schema_editor):
    AddonPrice = apps.get_model("catalog", "AddonPrice")
    database = schema_editor.connection.alias
    prices = {
        "monthly": Decimal("2.00"),
        "annually": Decimal("21.60"),
    }
    for interval, amount in prices.items():
        AddonPrice.objects.using(database).filter(
            addon__slug="web-storage-5gb",
            currency="USD",
            billing_interval=interval,
        ).update(amount=amount)


def restore_storage_extension_price(apps, schema_editor):
    AddonPrice = apps.get_model("catalog", "AddonPrice")
    database = schema_editor.connection.alias
    for interval, amount in {
        "monthly": Decimal("1.50"),
        "annually": Decimal("16.20"),
    }.items():
        AddonPrice.objects.using(database).filter(
            addon__slug="web-storage-5gb",
            currency="USD",
            billing_interval=interval,
        ).update(amount=amount)


class Migration(migrations.Migration):
    dependencies = [
        ("catalog", "0004_account_balance_topup"),
    ]

    operations = [
        migrations.RunPython(
            update_storage_extension_price,
            restore_storage_extension_price,
        ),
    ]
