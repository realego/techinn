from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [("accounts", "0004_customer_billing_address_and_more")]
    operations = [migrations.CreateModel(
        name="PasswordResetOTP",
        fields=[
            ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
            ("code_hash", models.CharField(max_length=128)),
            ("expires_at", models.DateTimeField(db_index=True)),
            ("attempts", models.PositiveSmallIntegerField(default=0)),
            ("used_at", models.DateTimeField(blank=True, null=True)),
            ("created_at", models.DateTimeField(auto_now_add=True)),
            ("customer", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="password_reset_otps", to="accounts.customer")),
        ],
        options={"ordering": ("-created_at",)},
    )]
