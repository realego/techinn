from django.urls import path

from apps.orders.views import OrderDetailView, OrderListCreateView


urlpatterns = [
    path("", OrderListCreateView.as_view(), name="order-list"),
    path("<uuid:uuid>/", OrderDetailView.as_view(), name="order-detail"),
]
