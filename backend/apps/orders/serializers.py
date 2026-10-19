from rest_framework import serializers

from apps.orders.models import Order, OrderItem


class OrderItemSerializer(serializers.ModelSerializer):
    product_slug = serializers.CharField(source="product.slug", read_only=True, allow_null=True)
    addon_slug = serializers.CharField(source="addon.slug", read_only=True, allow_null=True)

    class Meta:
        model = OrderItem
        fields = ("id", "product", "product_slug", "addon", "addon_slug", "description", "quantity", "unit_price", "subtotal", "metadata")


class OrderSerializer(serializers.ModelSerializer):
    items = OrderItemSerializer(many=True, read_only=True)

    class Meta:
        model = Order
        fields = (
            "uuid",
            "order_number",
            "status",
            "currency",
            "subtotal",
            "discount_total",
            "tax_total",
            "total",
            "metadata",
            "items",
            "created_at",
        )


class OrderLineInputSerializer(serializers.Serializer):
    price_id = serializers.IntegerField(min_value=1)
    quantity = serializers.IntegerField(min_value=1, max_value=100, default=1)
    metadata = serializers.DictField(child=serializers.JSONField(), required=False, default=dict)


class OrderCreateSerializer(serializers.Serializer):
    currency = serializers.RegexField(regex=r"^[A-Za-z]{3}$", max_length=3, default="USD")
    items = OrderLineInputSerializer(many=True, allow_empty=False)

    def validate_currency(self, value):
        return value.upper()
