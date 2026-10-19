import logging
import secrets
from smtplib import SMTPException

from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone
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
from apps.notifications.emailing import render_queued_email, send_mail, send_transactional

from apps.accounts.password_serializers import PasswordResetConfirmSerializer, PasswordResetRequestSerializer
from apps.accounts.serializers import CustomerSerializer, RegistrationSerializer
from apps.accounts.models import Customer


logger = logging.getLogger(__name__)


def _send_account_welcome(customer, temporary_password=None):
    """Send the account-created message without making authentication fail."""
    try:
        subject, text, html, security = render_queued_email(
            "account-created", {"temporary_password": temporary_password} if temporary_password else {}, customer
        )
        send_transactional(
            subject=subject,
            text=text,
            html=html,
            security=security,
            recipient_list=[customer.email],
            fail_silently=True,
        )
    except Exception:
        logger.exception("Technology Inn account welcome email delivery failed")


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

    def perform_create(self, serializer):
        customer = serializer.save()
        # Registration must never fail because an SMTP provider is slow or
        # unavailable. Send only after the customer transaction commits.
        transaction.on_commit(lambda: _send_account_welcome(customer))


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
    serializer_class = PasswordResetConfirmSerializer

    def post(self, request):
        serializer = self.get_serializer(data={**request.data, "email": request.user.email})
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response({"detail": "Password updated. Sign in again with your new password."}, status=status.HTTP_200_OK)


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

        created_customer = False
        temporary_password = None
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
                        temporary_password = secrets.token_urlsafe(18)
                        customer.set_password(temporary_password)
                        created_customer = True
                    customer.google_sub = subject
                    if customer.email_verified_at is None:
                        customer.email_verified_at = timezone.now()
                    customer.save()
        except IntegrityError as error:
            raise AuthenticationFailed("This Google account could not be linked. Contact TechInn support.") from error

        if created_customer:
            transaction.on_commit(
                lambda customer=customer, temporary_password=temporary_password: _send_account_welcome(customer, temporary_password)
            )

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
            from apps.accounts.otp import issue_otp, OTPCooldown
            try:
                issue_otp(customer)
            except OTPCooldown:
                pass
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
