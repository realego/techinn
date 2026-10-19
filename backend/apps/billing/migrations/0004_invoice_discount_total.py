from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("billing", "0003_walletaccount_wallettransaction"),
    ]

    operations = [
        migrations.AddField(
            model_name="invoice",
            name="discount_total",
            field=models.DecimalField(decimal_places=2, default=0, max_digits=12),
        ),
    ]
