from decimal import Decimal

from django.db import migrations


FEATURES = (
    ("Automated replies", "automated-replies", "Answers common customer questions automatically."),
    ("General assistant", "general-assistant", "A general-purpose assistant configured for the business."),
    ("Admin notifications", "admin-notifications", "Notifies administrators when customers need attention."),
    ("Product and service answers", "product-service-answers", "Shares configured product and service information."),
    ("Basic setup and launch", "basic-setup-launch", "Basic setup, testing, and launch support."),
)

ADDONS = (
    ("chatbot-flows", "Custom conversation flows", Decimal("25.00")),
    ("chatbot-payments", "Chatbot payment integration", Decimal("30.00")),
    ("chatbot-booking", "Chatbot booking", Decimal("0.00")),
    ("chatbot-tickets", "Support ticket handling", Decimal("40.00")),
    ("chatbot-whatsapp", "WhatsApp channel setup", Decimal("25.00")),
    ("chatbot-human-handoff", "Human support handoff", Decimal("20.00")),
)


def seed_chatbot_catalog(apps, schema_editor):
    ServiceType = apps.get_model("catalog", "ServiceType")
    Product = apps.get_model("catalog", "Product")
    ProductPrice = apps.get_model("catalog", "ProductPrice")
    Feature = apps.get_model("catalog", "Feature")
    ProductFeature = apps.get_model("catalog", "ProductFeature")
    Addon = apps.get_model("catalog", "Addon")
    AddonPrice = apps.get_model("catalog", "AddonPrice")
    ProductAddon = apps.get_model("catalog", "ProductAddon")
    database = schema_editor.connection.alias

    service_type, _ = ServiceType.objects.using(database).get_or_create(
        slug="chatbot-development",
        defaults={"name": "Chatbot Development", "status": "active"},
    )
    product, _ = Product.objects.using(database).get_or_create(
        slug="chatbot-basic",
        defaults={
            "service_type": service_type,
            "name": "Basic chatbot development",
            "description": (
                "A business chatbot with automated replies, a general assistant, "
                "admin notifications, and product and service information."
            ),
            "billing_type": "one_time",
            "status": "active",
            "sort_order": 10,
        },
    )
    ProductPrice.objects.using(database).get_or_create(
        product=product,
        currency="USD",
        billing_interval="one_time",
        defaults={
            "amount": Decimal("80.00"),
            "setup_fee": Decimal("0.00"),
            "is_default": True,
            "status": "active",
        },
    )

    for sort_order, (name, slug, description) in enumerate(FEATURES):
        feature, _ = Feature.objects.using(database).get_or_create(
            slug=slug,
            defaults={"name": name, "description": description},
        )
        ProductFeature.objects.using(database).get_or_create(
            product=product,
            feature=feature,
            defaults={"display_value": "Included", "sort_order": sort_order},
        )

    for sort_order, (slug, name, amount) in enumerate(ADDONS):
        addon, _ = Addon.objects.using(database).get_or_create(
            slug=slug,
            defaults={
                "name": name,
                "description": "Optional chatbot development feature.",
                "billing_type": "one_time",
                "status": "active",
            },
        )
        AddonPrice.objects.using(database).get_or_create(
            addon=addon,
            currency="USD",
            billing_interval="one_time",
            defaults={"amount": amount},
        )
        ProductAddon.objects.using(database).get_or_create(
            product=product,
            addon=addon,
            defaults={"sort_order": sort_order},
        )


class Migration(migrations.Migration):
    dependencies = [
        ("catalog", "0005_update_hosting_storage_extension_price"),
    ]

    operations = [
        migrations.RunPython(seed_chatbot_catalog, migrations.RunPython.noop),
    ]
