from datetime import timedelta

from django.db import migrations, models
from django.utils import timezone


def initialize_ownership_check_windows(apps, schema_editor):
    DomainConnection = apps.get_model("services", "DomainConnection")
    now = timezone.now()
    updates = []
    for connection in DomainConnection.objects.filter(verified_at__isnull=True).iterator():
        connection.ownership_checks_until = now + timedelta(hours=48)
        if connection.ownership_checks_until > now and connection.next_check_at is None:
            connection.next_check_at = now
        elif connection.ownership_checks_until <= now:
            connection.next_check_at = None
        updates.append(connection)
        if len(updates) == 500:
            DomainConnection.objects.bulk_update(updates, ("ownership_checks_until", "next_check_at"))
            updates.clear()
    if updates:
        DomainConnection.objects.bulk_update(updates, ("ownership_checks_until", "next_check_at"))


class Migration(migrations.Migration):
    dependencies = [
        ("services", "0015_alter_domainconnection_customer_service_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="domainconnection",
            name="ownership_checks_until",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.RunPython(initialize_ownership_check_windows, migrations.RunPython.noop),
    ]
