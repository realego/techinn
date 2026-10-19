from rest_framework import serializers

from apps.catalog.models import Feature, Product, ProductFeature, ProductPrice, ServiceType


class ProductPriceSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductPrice
        fields = (
            "id",
            "currency",
            "billing_interval",
            "period_months",
            "amount",
            "setup_fee",
            "trial_days",
            "is_default",
        )


class ProductFeatureSerializer(serializers.ModelSerializer):
    name = serializers.CharField(source="feature.name", read_only=True)
    slug = serializers.CharField(source="feature.slug", read_only=True)

    class Meta:
        model = ProductFeature
        fields = ("name", "slug", "display_value", "value_text", "value_number", "value_boolean", "value_json")


class ProductSerializer(serializers.ModelSerializer):
    service_type = serializers.SlugRelatedField(read_only=True, slug_field="slug")
    prices = serializers.SerializerMethodField()
    features = serializers.SerializerMethodField()

    class Meta:
        model = Product
        fields = ("id", "name", "slug", "description", "billing_type", "service_type", "prices", "features")

    def get_prices(self, product):
        prices = product.prices.filter(status=ProductPrice.Status.ACTIVE).order_by("currency", "billing_interval")
        return ProductPriceSerializer(prices, many=True).data

    def get_features(self, product):
        features = product.feature_values.select_related("feature").all()
        return ProductFeatureSerializer(features, many=True).data


class ServiceTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = ServiceType
        fields = ("id", "name", "slug", "description")
