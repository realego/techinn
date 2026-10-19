from django.contrib.auth import password_validation
from django.contrib.auth.hashers import check_password
from django.utils import timezone
from rest_framework import serializers

from apps.accounts.models import Customer, PasswordResetOTP, PortalSession


class PasswordChangeSerializer(serializers.Serializer):
    current_password = serializers.CharField(write_only=True, trim_whitespace=False, required=False, allow_blank=True)
    new_password = serializers.CharField(write_only=True, trim_whitespace=False)

    def validate(self, attrs):
        user = self.context["request"].user
        if user.has_usable_password() and not user.check_password(attrs.get("current_password", "")):
            raise serializers.ValidationError({"current_password": "Your current password is incorrect."})
        return attrs

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
        sessions = PortalSession.objects.filter(customer=user, revoked=False)
        token = self.context["request"].auth
        if token and token.get("sid"):
            sessions = sessions.exclude(pk=token["sid"])
        sessions.update(revoked=True)
        return user


class PasswordResetRequestSerializer(serializers.Serializer):
    email = serializers.EmailField()


class PasswordResetConfirmSerializer(serializers.Serializer):
    email = serializers.EmailField()
    otp = serializers.CharField(min_length=6, max_length=6)
    new_password = serializers.CharField(write_only=True, trim_whitespace=False)

    def validate(self, attrs):
        customer = Customer.objects.filter(email__iexact=attrs["email"], status__in=(Customer.Status.ACTIVE, Customer.Status.PENDING)).first()
        if not customer:
            raise serializers.ValidationError({"otp": "That verification code is invalid or has expired."})
        if customer.check_password(attrs["new_password"]):
            raise serializers.ValidationError({"new_password": "Choose a password you are not already using."})
        password_validation.validate_password(attrs["new_password"], user=customer)
        attrs["customer"] = customer
        return attrs

    def save(self, **kwargs):
        from django.db import transaction
        from apps.accounts.otp import consume_otp
        with transaction.atomic():
            customer = Customer.objects.select_for_update().get(pk=self.validated_data["customer"].pk)
            valid = consume_otp(customer, self.validated_data["otp"])
            if valid:
                customer.set_password(self.validated_data["new_password"])
                customer.save(update_fields=["password"])
                PortalSession.objects.filter(customer=customer).update(revoked=True)
        if not valid:
            raise serializers.ValidationError({"otp": "That verification code is invalid, expired, or has reached its attempt limit."})
        return customer
