import logging
from smtplib import SMTPException
from urllib.parse import urlencode

from django.conf import settings
from django.contrib.auth.tokens import default_token_generator
from django.core.mail import send_mail
from django.db import IntegrityError, transaction
from django.utils import timezone
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode
from google.auth.exceptions import GoogleAuthError
from google.auth.transport.requests import Request as GoogleRequest
from google.oauth2 import id_token
from rest_framework import generics, status
from rest_framework.exceptions import APIException, AuthenticationFailed
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle, ScopedRateThrottle
from rest_framework_simplejwt.views import TokenObtainPairView
from apps.accounts.sessions import LoginSerializer, new_refresh

from apps.accounts.password_serializers import PasswordChangeSerializer
from apps.accounts.password_serializers import PasswordResetConfirmSerializer, PasswordResetRequestSerializer
from apps.accounts.serializers import CustomerSerializer, RegistrationSerializer
from apps.accounts.models import Customer


logger = logging.getLogger(__name__)


class ProviderUnavailable(APIException):
    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    default_detail = "The authentication provider is not configured yet."
    default_code = "provider_unavailable"


class AuthenticationThrottleMixin:
    throttle_classes = [AnonRateThrottle, ScopedRateThrottle]
    throttle_scope = "auth"


class RegisterView(AuthenticationThrottleMixin, generics.CreateAPIView):
    permission_classes = [AllowAny]
    serializer_class = RegistrationSerializer


class LoginView(AuthenticationThrottleMixin, TokenObtainPairView):
    permission_classes = [AllowAny]
    serializer_class = LoginSerializer


class CurrentCustomerView(generics.RetrieveUpdateAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = CustomerSerializer

    def get_object(self):
        return self.request.user


class PasswordChangeView(generics.GenericAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = PasswordChangeSerializer

    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response({"detail": "Password updated."}, status=status.HTTP_200_OK)


class PublicAuthThrottleMixin:
    permission_classes = [AllowAny]
    throttle_classes = [AnonRateThrottle, ScopedRateThrottle]
    throttle_scope = "auth"


class GoogleLoginView(PublicAuthThrottleMixin, generics.GenericAPIView):
    def post(self, request):
        client_id = settings.GOOGLE_OAUTH_CLIENT_ID
        if not client_id:
            raise ProviderUnavailable("Google sign-in is not configured yet.")
        credential = request.data.get("credential")
        if not isinstance(credential, str) or not credential:
            raise AuthenticationFailed("Google did not return a valid sign-in credential.")
        try:
            claims = id_token.verify_oauth2_token(credential, GoogleRequest(), client_id)
        except (GoogleAuthError, ValueError) as error:
            raise AuthenticationFailed("Google sign-in could not be verified. Please try again.") from error

        email = claims.get("email")
        subject = claims.get("sub")
        if claims.get("email_verified") is not True or not isinstance(email, str) or not isinstance(subject, str):
            raise AuthenticationFailed("Use a Google account with a verified email address.")

        try:
            with transaction.atomic():
                customer = Customer.objects.filter(google_sub=subject).first()
                if customer is None:
                    customer = Customer.objects.filter(email__iexact=email).first()
                    if customer is None:
                        customer = Customer(
                            email=Customer.objects.normalize_email(email),
                            first_name=str(claims.get("given_name") or email.split("@", 1)[0])[:100],
                            last_name=str(claims.get("family_name") or "")[:100],
                            status=Customer.Status.ACTIVE,
                            email_verified_at=timezone.now(),
                        )
                        customer.set_unusable_password()
                    customer.google_sub = subject
                    if customer.email_verified_at is None:
                        customer.email_verified_at = timezone.now()
                    customer.save()
        except IntegrityError as error:
            raise AuthenticationFailed("This Google account could not be linked. Contact TechInn support.") from error

        if not customer.is_active:
            raise AuthenticationFailed("This TechInn account is not active.")
        refresh = new_refresh(customer)
        return Response({"access": str(refresh.access_token), "refresh": str(refresh)})


class PasswordResetRequestView(PublicAuthThrottleMixin, generics.GenericAPIView):
    serializer_class = PasswordResetRequestSerializer

    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        if not settings.EMAIL_HOST or not settings.DEFAULT_FROM_EMAIL:
            return Response(
                {"detail": "Password reset email is not configured yet. Contact TechInn support."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        customer = Customer.objects.filter(email__iexact=serializer.validated_data["email"]).first()
        if customer and customer.is_active:
            uid = urlsafe_base64_encode(force_bytes(customer.pk))
            token = default_token_generator.make_token(customer)
            reset_url = f"{settings.FRONTEND_BASE_URL}/reset-password/?{urlencode({'uid': uid, 'token': token})}"
            try:
                send_mail(
                    subject="Reset your TechInn password",
                    message=(
                        f"Hello {customer.first_name},\n\n"
                        f"Use this link to set a new TechInn password:\n{reset_url}\n\n"
                        "If you did not request this, you can ignore this email."
                    ),
                    from_email=settings.DEFAULT_FROM_EMAIL,
                    recipient_list=[customer.email],
                    fail_silently=False,
                )
            except (SMTPException, OSError):
                logger.exception("TechInn password reset email delivery failed")

        return Response(
            {"detail": "If an active account matches that email, password reset instructions have been sent."},
            status=status.HTTP_200_OK,
        )


class PasswordResetConfirmView(PublicAuthThrottleMixin, generics.GenericAPIView):
    serializer_class = PasswordResetConfirmSerializer

    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response({"detail": "Password reset successfully. You can now sign in."})
