from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.forms import UserChangeForm, UserCreationForm

from apps.accounts.models import Customer


class CustomerCreationForm(UserCreationForm):
    class Meta:
        model = Customer
        fields = ("email", "first_name", "last_name", "status", "is_staff")


class CustomerChangeForm(UserChangeForm):
    class Meta:
        model = Customer
        fields = "__all__"


@admin.register(Customer)
class CustomerAdmin(UserAdmin):
    model = Customer
    add_form = CustomerCreationForm
    form = CustomerChangeForm
    ordering = ("email",)
    list_display = ("email", "first_name", "last_name", "status", "is_staff")
    list_filter = ("status", "is_staff", "is_superuser")
    search_fields = ("email", "first_name", "last_name", "company_name")
    fieldsets = (
        (None, {"fields": ("email", "password")}),
        ("Customer details", {"fields": ("first_name", "last_name", "phone", "company_name")}),
        ("Account status", {"fields": ("status", "email_verified_at", "phone_verified_at")}),
        ("Permissions", {"fields": ("is_staff", "is_superuser", "groups", "user_permissions")}),
        ("Dates", {"fields": ("last_login", "created_at", "updated_at")}),
    )
    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": ("email", "first_name", "password1", "password2", "status", "is_staff"),
            },
        ),
    )
    readonly_fields = ("created_at", "updated_at")
