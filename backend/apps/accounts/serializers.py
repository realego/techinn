from django.contrib.auth import password_validation
from django.conf import settings
from rest_framework import serializers

from apps.accounts.models import Customer


class AddressSerializer(serializers.Serializer):
    line1 = serializers.CharField(max_length=255, allow_blank=True, required=False)
    line2 = serializers.CharField(max_length=255, allow_blank=True, required=False)
    city = serializers.CharField(max_length=100, allow_blank=True, required=False)
    region = serializers.CharField(max_length=100, allow_blank=True, required=False)
    postal_code = serializers.CharField(max_length=30, allow_blank=True, required=False)
    country = serializers.CharField(max_length=100, allow_blank=True, required=False)


class NotificationPreferencesSerializer(serializers.Serializer):
    service_updates = serializers.BooleanField(required=False, default=True)
    billing_reminders = serializers.BooleanField(required=False, default=True)
    product_news = serializers.BooleanField(required=False, default=False)


class CustomerSerializer(serializers.ModelSerializer):
    billing_address = AddressSerializer(required=False)
    postal_address = AddressSerializer(required=False)
    notification_preferences = NotificationPreferencesSerializer(required=False)
    test_checkout_enabled = serializers.SerializerMethodField()
    has_usable_password = serializers.SerializerMethodField()

    class Meta:
        model = Customer
        fields = ("uuid", "first_name", "last_name", "email", "phone", "company_name", "billing_address", "postal_address", "notification_preferences", "test_checkout_enabled", "has_usable_password")
        read_only_fields = ("uuid", "email")

    def update(self, instance, validated_data):
        for field in ("billing_address", "postal_address", "notification_preferences"):
            if field in validated_data:
                validated_data[field] = {**getattr(instance, field), **validated_data[field]}
        return super().update(instance, validated_data)

    def get_test_checkout_enabled(self, customer):
        return bool(
            settings.CHECKOUT_TEST_EMAIL
            and customer.email.strip().casefold() == settings.CHECKOUT_TEST_EMAIL
        )

    def get_has_usable_password(self, customer):
        return customer.has_usable_password()


class RegistrationSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, trim_whitespace=False)

    class Meta:
        model = Customer
        fields = ("uuid", "first_name", "last_name", "email", "phone", "company_name", "password")
        read_only_fields = ("uuid",)

    def validate_password(self, value):
        password_validation.validate_password(value)
        return value

    def create(self, validated_data):
        password = validated_data.pop("password")
        return Customer.objects.create_user(password=password, **validated_data)
