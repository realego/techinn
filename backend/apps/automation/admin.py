from django.contrib import admin

from apps.automation.models import AutomationExecution, AutomationRule


@admin.register(AutomationRule)
class AutomationRuleAdmin(admin.ModelAdmin):
    list_display = ("name", "event_type", "action_type", "status")
    list_filter = ("status", "event_type")
    search_fields = ("name", "slug", "event_type")
    prepopulated_fields = {"slug": ("name",)}


@admin.register(AutomationExecution)
class AutomationExecutionAdmin(admin.ModelAdmin):
    list_display = ("automation_rule", "customer", "customer_service", "scheduled_for", "status")
    list_filter = ("status", "automation_rule")
    readonly_fields = ("automation_rule", "customer", "customer_service", "scheduled_for", "executed_at", "result")
