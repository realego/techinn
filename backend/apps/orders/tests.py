from decimal import Decimal

from rest_framework.test import APITestCase

from apps.accounts.models import Customer
from apps.catalog.models import Product, ProductPrice, ServiceType
from apps.orders.models import Order, OrderItem


class OrderApiTests(APITestCase):
    def setUp(self):
        self.customer = Customer.objects.create_user(
            email="buyer@example.com",
            password="Str0ng-password-not-used-elsewhere",
            first_name="Buyer",
            status=Customer.Status.ACTIVE,
        )
        self.service_type, _ = ServiceType.objects.get_or_create(
            name="Web Hosting",
            slug="web-hosting",
        )
        self.product = Product.objects.create(
            service_type=self.service_type,
            name="Starter",
            slug="starter",
            billing_type=Product.BillingType.RECURRING,
            status=Product.Status.ACTIVE,
        )
        self.price = ProductPrice.objects.create(
            product=self.product,
            currency="USD",
            billing_interval=ProductPrice.BillingInterval.MONTHLY,
            amount=Decimal("5.00"),
            setup_fee=Decimal("2.00"),
        )
        self.client.force_authenticate(self.customer)

    def test_order_uses_database_price_and_snapshots_total(self):
        response = self.client.post(
            "/api/v1/orders/",
            {
                "items": [
                    {
                        "price_id": self.price.id,
                        "quantity": 2,
                        "metadata": {"domain": "example.co.zw", "unit_price": 0},
                    }
                ]
            },
            format="json",
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["total"], "14.00")
        self.assertEqual(response.data["items"][0]["unit_price"], "5.00")
        self.assertEqual(response.data["items"][0]["metadata"]["billing_interval"], "monthly")
        self.assertEqual(Order.objects.get().customer, self.customer)

    def test_inactive_price_cannot_be_ordered(self):
        self.price.status = ProductPrice.Status.INACTIVE
        self.price.save()

        response = self.client.post(
            "/api/v1/orders/",
            {"items": [{"price_id": self.price.id}]},
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(Order.objects.count(), 0)

    def test_order_list_is_scoped_to_authenticated_customer(self):
        another_customer = Customer.objects.create_user(
            email="other@example.com",
            password="Str0ng-password-not-used-elsewhere",
            first_name="Other",
            status=Customer.Status.ACTIVE,
        )
        other_order = Order.objects.create(
            customer=another_customer,
            order_number="TI-OTHER-CUSTOMER-ORDER",
        )
        OrderItem.objects.create(
            order=other_order,
            product=self.product,
            description=self.product.name,
            quantity=1,
            unit_price=Decimal("5.00"),
            subtotal=Decimal("5.00"),
        )

        response = self.client.get("/api/v1/orders/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 0)
        detail = self.client.get(f"/api/v1/orders/{other_order.uuid}/")
        self.assertEqual(detail.status_code, 404)
