from django.db import migrations


def update_default_subjects(apps, schema_editor):
    EmailTemplate = apps.get_model("notifications", "EmailTemplate")
    replacements = {
        "Your Technology Inn invoice is ready": "Your TechInn invoice is ready",
        "Your Technology Inn account is ready": "Your TechInn account is ready",
        "Your Technology Inn password reset code": "Your TechInn password reset code",
        "Getting started with your Technology Inn services": "Getting started with your TechInn services",
        "Your Technology Inn domain is active": "Your TechInn domain is active",
        "Your Technology Inn payment is waiting": "Your TechInn payment is waiting",
        "Your Technology Inn payment is confirmed": "Your TechInn payment is confirmed",
        "Your Technology Inn domain is processing": "Your TechInn domain is processing",
        "Your Technology Inn service is being prepared": "Your TechInn service is being prepared",
        "Your Technology Inn deposit is confirmed": "Your TechInn deposit is confirmed",
        "Renew your Technology Inn domain": "Renew your TechInn domain",
        "Renew your Technology Inn service": "Renew your TechInn service",
    }
    for old_subject, new_subject in replacements.items():
        EmailTemplate.objects.filter(subject=old_subject).update(subject=new_subject)


class Migration(migrations.Migration):
    dependencies = [("notifications", "0004_contactrequest")]
    operations = [migrations.RunPython(update_default_subjects, migrations.RunPython.noop)]
