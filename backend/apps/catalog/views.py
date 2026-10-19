from rest_framework import viewsets
from rest_framework.permissions import AllowAny

from apps.catalog.models import Product, ServiceType
from apps.catalog.serializers import ProductSerializer, ServiceTypeSerializer


class ServiceTypeViewSet(viewsets.ReadOnlyModelViewSet):
    permission_classes = [AllowAny]
    serializer_class = ServiceTypeSerializer
    lookup_field = "slug"

    def get_queryset(self):
        return ServiceType.objects.filter(status=ServiceType.Status.ACTIVE).order_by("name")


class ProductViewSet(viewsets.ReadOnlyModelViewSet):
    permission_classes = [AllowAny]
    serializer_class = ProductSerializer
    lookup_field = "slug"

    def get_queryset(self):
        queryset = Product.objects.filter(
            status=Product.Status.ACTIVE,
            service_type__status=ServiceType.Status.ACTIVE,
        ).select_related("service_type")
        service_type = self.request.query_params.get("service_type")
        if service_type:
            queryset = queryset.filter(service_type__slug=service_type)
        return queryset
