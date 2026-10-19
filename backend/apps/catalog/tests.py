from decimal import Decimal

from rest_framework.test import APITestCase

from apps.catalog.models import Product, ProductPrice, ServiceType


class CatalogApiTests(APITestCase):
    def test_public_catalog_returns_active_product_prices(self):
        service_type, _ = ServiceType.objects.get_or_create(
            name="Web Hosting",
            slug="web-hosting",
        )
        product, _ = Product.objects.get_or_create(
            slug="catalog-test-basic",
            defaults={
                "service_type": service_type,
                "name": "Catalog test basic",
                "billing_type": Product.BillingType.RECURRING,
                "status": Product.Status.ACTIVE,
            },
        )
        ProductPrice.objects.create(
            product=product,
            currency="USD",
            billing_interval=ProductPrice.BillingInterval.MONTHLY,
            amount=Decimal("3.50"),
        )
        Product.objects.create(
            service_type=service_type,
            name="Unpublished",
            slug="unpublished",
            billing_type=Product.BillingType.RECURRING,
            status=Product.Status.DRAFT,
        )

        response = self.client.get("/api/v1/catalog/products/?service_type=web-hosting")

        self.assertEqual(response.status_code, 200)
        returned_products = {item["slug"]: item for item in response.data["results"]}
        self.assertIn("catalog-test-basic", returned_products)
        self.assertNotIn("unpublished", returned_products)
        self.assertEqual(returned_products["catalog-test-basic"]["prices"][0]["amount"], "3.50")
