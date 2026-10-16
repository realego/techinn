from django.db import migrations


def stop_pending_ownership_checks(apps, schema_editor):
    DomainConnection = apps.get_model("services", "DomainConnection")
    DomainConnection.objects.using(schema_editor.connection.alias).filter(
        verified_at__isnull=True,
    ).update(next_check_at=None)


class Migration(migrations.Migration):
    dependencies = [
        ("services", "0016_domainconnection_ownership_checks_until"),
    ]

    operations = [
        migrations.RunPython(stop_pending_ownership_checks, migrations.RunPython.noop),
        migrations.RemoveField(
            model_name="domainconnection",
            name="ownership_checks_until",
        ),
    ]
