from django.contrib.auth import password_validation
from django.conf import settings
from rest_framework import serializers

from apps.accounts.models import Customer


class CustomerSerializer(serializers.ModelSerializer):
    test_checkout_enabled = serializers.SerializerMethodField()

    class Meta:
        model = Customer
        fields = ("uuid", "first_name", "last_name", "email", "phone", "company_name", "test_checkout_enabled")
        read_only_fields = ("uuid", "email")

    def get_test_checkout_enabled(self, customer):
        return bool(
            settings.CHECKOUT_TEST_EMAIL
            and customer.email.strip().casefold() == settings.CHECKOUT_TEST_EMAIL
        )


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
