from django.contrib import admin

from apps.orders.models import Order, OrderItem


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    readonly_fields = ("product", "addon", "description", "quantity", "unit_price", "subtotal", "metadata")


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ("order_number", "customer", "status", "currency", "total", "created_at")
    list_filter = ("status", "currency")
    search_fields = ("order_number", "customer__email")
    readonly_fields = ("uuid", "customer", "order_number", "currency", "subtotal", "discount_total", "tax_total", "total")
    inlines = (OrderItemInline,)
