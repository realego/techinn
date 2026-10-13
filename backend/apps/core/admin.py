from django.contrib import admin

from apps.core.models import Setting, SystemEvent


@admin.register(SystemEvent)
class SystemEventAdmin(admin.ModelAdmin):
    list_display = ("event_type", "customer", "customer_service", "processed", "created_at")
    list_filter = ("event_type", "processed")
    search_fields = ("event_type", "customer__email", "entity_type")
    readonly_fields = ("event_type", "customer", "customer_service", "entity_type", "entity_id", "payload", "created_at")


@admin.register(Setting)
class SettingAdmin(admin.ModelAdmin):
    list_display = ("setting_key", "value_type", "is_secret", "updated_at")
    list_filter = ("value_type", "is_secret")
    search_fields = ("setting_key", "description")
