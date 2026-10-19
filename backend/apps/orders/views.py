import uuid
from decimal import Decimal

from django.db import transaction
from rest_framework import generics, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.catalog.models import ProductPrice
from apps.orders.models import Order, OrderItem
from apps.orders.serializers import OrderCreateSerializer, OrderSerializer


class OrderListCreateView(generics.ListCreateAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = OrderSerializer

    def get_queryset(self):
        return (
            Order.objects.filter(customer=self.request.user)
            .prefetch_related("items__product", "items__addon")
            .order_by("-created_at")
        )

    def create(self, request, *args, **kwargs):
        serializer = OrderCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        payload = serializer.validated_data
        lines = payload["items"]
        price_ids = {line["price_id"] for line in lines}
        prices = {
            price.id: price
            for price in ProductPrice.objects.select_related("product").filter(
                id__in=price_ids,
                status=ProductPrice.Status.ACTIVE,
                product__status="active",
                product__service_type__status="active",
            )
        }
        if len(prices) != len(price_ids):
            return Response(
                {"items": ["One or more selected prices are unavailable."]},
                status=status.HTTP_400_BAD_REQUEST,
            )

        currency = payload["currency"]
        if any(price.currency != currency for price in prices.values()):
            return Response(
                {"currency": ["Selected product prices must use the requested currency."]},
                status=status.HTTP_400_BAD_REQUEST,
            )

        with transaction.atomic():
            order = Order.objects.create(
                customer=request.user,
                order_number=f"TI-{uuid.uuid4().hex.upper()}",
                currency=currency,
            )
            order_items = []
            subtotal = Decimal("0.00")
            for line in lines:
                price = prices[line["price_id"]]
                quantity = line["quantity"]
                line_total = (price.amount + price.setup_fee) * quantity
                metadata = {
                    **line["metadata"],
                    "billing_interval": price.billing_interval,
                    "setup_fee": str(price.setup_fee),
                }
                order_items.append(
                    OrderItem(
                        order=order,
                        product=price.product,
                        description=price.product.name,
                        quantity=quantity,
                        unit_price=price.amount,
                        subtotal=line_total,
                        metadata=metadata,
                    )
                )
                subtotal += line_total
            OrderItem.objects.bulk_create(order_items)
            order.subtotal = subtotal
            order.total = subtotal
            order.save(update_fields=("subtotal", "total", "updated_at"))

        order = self.get_queryset().get(pk=order.pk)
        return Response(OrderSerializer(order).data, status=status.HTTP_201_CREATED)


class OrderDetailView(generics.RetrieveAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = OrderSerializer
    lookup_field = "uuid"

    def get_queryset(self):
        return Order.objects.filter(customer=self.request.user).prefetch_related("items__product", "items__addon")
