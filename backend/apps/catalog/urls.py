from rest_framework.routers import DefaultRouter

from apps.catalog.views import ProductViewSet, ServiceTypeViewSet


router = DefaultRouter()
router.register("service-types", ServiceTypeViewSet, basename="service-type")
router.register("products", ProductViewSet, basename="product")

urlpatterns = router.urls
