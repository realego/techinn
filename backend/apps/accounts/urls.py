from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView

from apps.accounts.session_views import SessionActivityView, SessionLogoutView

from apps.accounts.views import (
    CurrentCustomerView,
    GoogleLoginView,
    LoginView,
    PasswordChangeView,
    PasswordResetConfirmView,
    PasswordResetRequestView,
    RegisterView,
)


urlpatterns = [
    path("activity/", SessionActivityView.as_view(), name="session-activity"),
    path("logout/", SessionLogoutView.as_view(), name="session-logout"),
    path("register/", RegisterView.as_view(), name="register"),
    path("token/", LoginView.as_view(), name="token_obtain_pair"),
    path("token/refresh/", TokenRefreshView.as_view(), name="token_refresh"),
    path("me/", CurrentCustomerView.as_view(), name="current_customer"),
    path("password/", PasswordChangeView.as_view(), name="password_change"),
    path("password/reset/", PasswordResetRequestView.as_view(), name="password_reset"),
    path("password/reset/confirm/", PasswordResetConfirmView.as_view(), name="password_reset_confirm"),
    path("google/", GoogleLoginView.as_view(), name="google_login"),
]
