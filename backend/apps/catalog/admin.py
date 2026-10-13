from django.contrib import admin

from apps.catalog.models import (
    Addon,
    AddonPrice,
    Feature,
    Product,
    ProductAddon,
    ProductFeature,
    ProductPrice,
    ServiceType,
)


class ProductPriceInline(admin.TabularInline):
    model = ProductPrice
    extra = 0


class ProductFeatureInline(admin.TabularInline):
    model = ProductFeature
    extra = 0


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ("name", "service_type", "billing_type", "status", "sort_order")
    list_filter = ("service_type", "billing_type", "status")
    search_fields = ("name", "slug")
    prepopulated_fields = {"slug": ("name",)}
    inlines = (ProductPriceInline, ProductFeatureInline)


@admin.register(ServiceType)
class ServiceTypeAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "status")
    list_filter = ("status",)
    prepopulated_fields = {"slug": ("name",)}


@admin.register(Feature)
class FeatureAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "data_type")
    prepopulated_fields = {"slug": ("name",)}


@admin.register(Addon)
class AddonAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "billing_type", "status")
    list_filter = ("billing_type", "status")
    prepopulated_fields = {"slug": ("name",)}


admin.site.register(AddonPrice)
admin.site.register(ProductAddon)
