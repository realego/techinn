from django.db import migrations


def create_templates(apps, schema_editor):
    EmailTemplate = apps.get_model("notifications", "EmailTemplate")
    names = {
        "cart-payment-reminder": "Cart payment reminder",
        "payment-confirmation": "Payment confirmation",
        "domain-processing": "Domain processing update",
        "service-processing": "Service processing update",
        "balance-deposit-confirmation": "Balance deposit confirmation",
        "domain-expiry-reminder": "Domain expiry reminder",
        "service-expiry-reminder": "Service expiry reminder",
        "service-overdue-suspension": "Service suspended for overdue renewal",
    }
    for slug, name in names.items():
        EmailTemplate.objects.get_or_create(slug=slug, defaults={"name": name, "subject": "", "body_html": "", "body_text": "", "status": "inactive"})


class Migration(migrations.Migration):
    dependencies = [("notifications", "0002_alter_emailqueue_scheduled_at")]
    operations = [migrations.RunPython(create_templates, migrations.RunPython.noop)]
