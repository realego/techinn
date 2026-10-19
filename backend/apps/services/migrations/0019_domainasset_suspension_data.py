from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("services", "0018_serviceinstance_dashboard_url_and_more")]
    operations = [migrations.AddField(model_name="domainasset", name="suspension_data", field=models.JSONField(blank=True, default=dict))]
