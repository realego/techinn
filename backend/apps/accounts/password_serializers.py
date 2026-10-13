from django.contrib.auth import password_validation
from django.contrib.auth.tokens import default_token_generator
from django.utils.encoding import force_str
from django.utils.http import urlsafe_base64_decode
from rest_framework import serializers

from apps.accounts.models import Customer


class PasswordChangeSerializer(serializers.Serializer):
    current_password = serializers.CharField(write_only=True, trim_whitespace=False)
    new_password = serializers.CharField(write_only=True, trim_whitespace=False)

    def validate_current_password(self, value):
        if not self.context["request"].user.check_password(value):
            raise serializers.ValidationError("Your current password is incorrect.")
        return value

    def validate_new_password(self, value):
        user = self.context["request"].user
        if user.check_password(value):
            raise serializers.ValidationError("Choose a password you are not already using.")
        password_validation.validate_password(value, user=user)
        return value

    def save(self, **kwargs):
        user = self.context["request"].user
        user.set_password(self.validated_data["new_password"])
        user.save(update_fields=["password"])
        return user


class PasswordResetRequestSerializer(serializers.Serializer):
    email = serializers.EmailField()


class PasswordResetConfirmSerializer(serializers.Serializer):
    uid = serializers.CharField(max_length=100)
    token = serializers.CharField(max_length=256)
    new_password = serializers.CharField(write_only=True, trim_whitespace=False)

    def validate(self, attrs):
        try:
            customer_id = force_str(urlsafe_base64_decode(attrs["uid"]))
            customer = Customer.objects.get(pk=customer_id)
        except (Customer.DoesNotExist, TypeError, ValueError, UnicodeDecodeError) as error:
            raise serializers.ValidationError({"token": "This password reset link is invalid or has expired."}) from error
        if not default_token_generator.check_token(customer, attrs["token"]):
            raise serializers.ValidationError({"token": "This password reset link is invalid or has expired."})
        if customer.check_password(attrs["new_password"]):
            raise serializers.ValidationError({"new_password": "Choose a password you are not already using."})
        password_validation.validate_password(attrs["new_password"], user=customer)
        attrs["customer"] = customer
        return attrs

    def save(self, **kwargs):
        customer = self.validated_data["customer"]
        customer.set_password(self.validated_data["new_password"])
        customer.save(update_fields=["password"])
        return customer
