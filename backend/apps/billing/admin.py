from django.contrib import admin

from apps.billing.models import (
    Invoice,
    InvoiceItem,
    Payment,
    PaymentAttempt,
    PaymentEvent,
    PaymentProvider,
)


class InvoiceItemInline(admin.TabularInline):
    model = InvoiceItem
    extra = 0


@admin.register(Invoice)
class InvoiceAdmin(admin.ModelAdmin):
    list_display = ("invoice_number", "customer", "status", "currency", "total", "due_at")
    list_filter = ("status", "currency")
    search_fields = ("invoice_number", "customer__email")
    inlines = (InvoiceItemInline,)


class PaymentAttemptInline(admin.TabularInline):
    model = PaymentAttempt
    extra = 0
    readonly_fields = ("attempt_number", "request_type", "request_data", "response_data", "attempted_at")


class PaymentEventInline(admin.TabularInline):
    model = PaymentEvent
    extra = 0
    readonly_fields = ("event_type", "provider_status", "payload", "created_at")


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ("reference", "customer", "payment_provider", "status", "amount", "currency")
    list_filter = ("status", "payment_provider", "currency")
    search_fields = ("reference", "provider_reference", "customer__email")
    inlines = (PaymentAttemptInline, PaymentEventInline)


@admin.register(PaymentProvider)
class PaymentProviderAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "provider_type", "status")
    list_filter = ("status", "provider_type")
    search_fields = ("name", "slug")


admin.site.register(InvoiceItem)
