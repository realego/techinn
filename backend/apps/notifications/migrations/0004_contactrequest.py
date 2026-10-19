from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("notifications", "0003_lifecycle_templates")]
    operations = [migrations.CreateModel(
        name="ContactRequest",
        fields=[
            ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
            ("name", models.CharField(max_length=120)),
            ("email", models.EmailField(max_length=255)),
            ("phone", models.CharField(blank=True, max_length=40)),
            ("message", models.TextField(max_length=4000)),
            ("source", models.CharField(default="shop", max_length=80)),
            ("status", models.CharField(choices=[("pending", "Pending"), ("handled", "Handled")], db_index=True, default="pending", max_length=10)),
            ("created_at", models.DateTimeField(auto_now_add=True)),
            ("handled_at", models.DateTimeField(blank=True, null=True)),
        ],
        options={"ordering": ("-created_at",)},
    )]
