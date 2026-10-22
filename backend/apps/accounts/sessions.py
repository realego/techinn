"""Server-enforced six-hour idle sessions, independent of background API polling."""
from datetime import timedelta

from django.utils import timezone
from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer, TokenRefreshSerializer
from rest_framework_simplejwt.tokens import RefreshToken

from apps.accounts.models import Customer, PortalSession

IDLE_LIMIT = timedelta(hours=6)


def new_refresh(customer):
    session = PortalSession.objects.create(customer=customer, last_active_at=timezone.now())
    refresh = RefreshToken.for_user(customer)
    refresh['sid'] = str(session.pk)
    return refresh


def session_for(token, customer_id):
    # Treat malformed or legacy tokens as an expired session.  Accessing a
    # missing claim must never bubble up as a 500 from dashboard/activity.
    if token is None or not hasattr(token, "get"):
        raise AuthenticationFailed('Your session expired. Please sign in again.')
    sid = token.get('sid')
    if not sid:
        # Existing short-lived access tokens remain usable during the rollout.
        issued_at = token.get('iat')
        try:
            age = timezone.now().timestamp() - float(issued_at)
        except (TypeError, ValueError):
            raise AuthenticationFailed('Your session expired. Please sign in again.')
        if age >= IDLE_LIMIT.total_seconds():
            raise AuthenticationFailed('Your session expired. Please sign in again.')
        return None
    session = PortalSession.objects.filter(pk=sid, customer_id=customer_id, revoked=False).first()
    if not session or session.last_active_at <= timezone.now() - IDLE_LIMIT:
        raise AuthenticationFailed('Your session expired. Please sign in again.')
    return session


class IdleJWTAuthentication(JWTAuthentication):
    def get_user(self, validated_token):
        user = super().get_user(validated_token)
        session_for(validated_token, user.pk)
        return user


class LoginSerializer(TokenObtainPairSerializer):
    @classmethod
    def get_token(cls, user):
        return new_refresh(user)


class IdleRefreshSerializer(TokenRefreshSerializer):
    def validate(self, attrs):
        old = RefreshToken(attrs['refresh'])
        try:
            customer = Customer.objects.get(pk=old['user_id'])
        except Customer.DoesNotExist:
            raise AuthenticationFailed('This account is unavailable.')
        if not customer.is_active:
            raise AuthenticationFailed('This account is unavailable.')
        session = session_for(old, customer.pk)
        if session is None:
            old = new_refresh(customer)
        else:
            old.set_jti()
            old.set_iat()
            old.set_exp()
        # Refreshing or polling does not count as user activity.
        return {'access': str(old.access_token), 'refresh': str(old)}
