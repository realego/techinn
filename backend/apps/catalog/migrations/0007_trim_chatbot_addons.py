from django.db import migrations


def trim(apps, schema_editor):
    Addon = apps.get_model('catalog', 'Addon')
    Addon.objects.using(schema_editor.connection.alias).filter(slug__in=('chatbot-whatsapp', 'chatbot-human-handoff')).update(status='inactive')
    Addon.objects.using(schema_editor.connection.alias).filter(slug='chatbot-flows').update(name='Advanced flows')


class Migration(migrations.Migration):
    dependencies = [('catalog', '0006_chatbot_development_catalog')]
    operations = [migrations.RunPython(trim, migrations.RunPython.noop)]
