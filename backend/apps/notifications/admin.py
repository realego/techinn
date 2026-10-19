from django.contrib import admin

from apps.notifications.models import ContactRequest, EmailLog, EmailQueue, EmailTemplate, EmailTemplateVariable


@admin.register(ContactRequest)
class ContactRequestAdmin(admin.ModelAdmin):
    list_display = ("name", "email", "source", "status", "created_at")
    list_filter = ("status", "source")
    search_fields = ("name", "email", "phone", "message")
    readonly_fields = ("created_at",)


class EmailTemplateVariableInline(admin.TabularInline):
    model = EmailTemplateVariable
    extra = 0


@admin.register(EmailTemplate)
class EmailTemplateAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "status", "updated_at")
    list_filter = ("status",)
    search_fields = ("name", "slug", "subject")
    prepopulated_fields = {"slug": ("name",)}
    inlines = (EmailTemplateVariableInline,)


@admin.register(EmailQueue)
class EmailQueueAdmin(admin.ModelAdmin):
    list_display = ("recipient_email", "subject", "status", "attempts", "scheduled_at")
    list_filter = ("status",)
    search_fields = ("recipient_email", "subject")
    readonly_fields = ("attempts", "sent_at", "last_error", "created_at")


@admin.register(EmailLog)
class EmailLogAdmin(admin.ModelAdmin):
    list_display = ("email_queue", "provider", "status", "created_at")
    list_filter = ("status", "provider")
    readonly_fields = ("email_queue", "provider", "provider_message_id", "status", "response_data", "created_at")


admin.site.register(EmailTemplateVariable)
