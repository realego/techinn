from unittest.mock import patch

from django.test import override_settings
from rest_framework.test import APITestCase

from apps.accounts.models import Customer


class CustomerApiTests(APITestCase):
    def test_registration_hashes_password_and_returns_customer(self):
        response = self.client.post(
            "/api/v1/auth/register/",
            {
                "first_name": "Ada",
                "last_name": "Lovelace",
                "email": "ada@example.com",
                "password": "Str0ng-password-not-used-elsewhere",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 201)
        customer = Customer.objects.get(email="ada@example.com")
        self.assertTrue(customer.check_password("Str0ng-password-not-used-elsewhere"))
        self.assertNotIn("password", response.data)

    def test_authenticated_customer_can_read_own_profile(self):
        customer = Customer.objects.create_user(
            email="customer@example.com",
            password="Str0ng-password-not-used-elsewhere",
            first_name="Customer",
            status=Customer.Status.ACTIVE,
        )
        response = self.client.post(
            "/api/v1/auth/token/",
            {"email": customer.email, "password": "Str0ng-password-not-used-elsewhere"},
            format="json",
        )
        self.assertEqual(response.status_code, 200)

        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {response.data['access']}")
        profile = self.client.get("/api/v1/auth/me/")
        self.assertEqual(profile.status_code, 200)
        self.assertEqual(profile.data["email"], customer.email)


class GoogleLoginApiTests(APITestCase):
    @override_settings(GOOGLE_OAUTH_CLIENT_ID="")
    def test_google_login_reports_missing_provider_configuration(self):
        response = self.client.post(
            "/api/v1/auth/google/",
            {"credential": "test-id-token"},
            format="json",
        )

        self.assertEqual(response.status_code, 503)

    @override_settings(GOOGLE_OAUTH_CLIENT_ID="techinn-client-id")
    @patch("apps.accounts.views.id_token.verify_oauth2_token")
    def test_google_login_creates_verified_customer_and_returns_jwts(self, verify_token):
        verify_token.return_value = {
            "sub": "google-sub-1001",
            "email": "google-customer@example.com",
            "email_verified": True,
            "given_name": "Google",
            "family_name": "Customer",
        }

        response = self.client.post(
            "/api/v1/auth/google/",
            {"credential": "valid-id-token"},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("access", response.data)
        self.assertIn("refresh", response.data)
        customer = Customer.objects.get(email="google-customer@example.com")
        self.assertEqual(customer.google_sub, "google-sub-1001")
        self.assertTrue(customer.has_usable_password())
        verify_token.assert_called_once()

    @override_settings(GOOGLE_OAUTH_CLIENT_ID="techinn-client-id")
    @patch("apps.accounts.views.id_token.verify_oauth2_token")
    def test_google_login_rejects_unverified_google_email(self, verify_token):
        verify_token.return_value = {
            "sub": "google-sub-unverified",
            "email": "unverified@example.com",
            "email_verified": False,
        }

        response = self.client.post(
            "/api/v1/auth/google/",
            {"credential": "unverified-id-token"},
            format="json",
        )

        self.assertEqual(response.status_code, 401)
        self.assertFalse(Customer.objects.filter(email="unverified@example.com").exists())

    @override_settings(GOOGLE_OAUTH_CLIENT_ID="techinn-client-id")
    @patch("apps.accounts.views.id_token.verify_oauth2_token")
    def test_google_login_links_google_identity_to_matching_verified_email(self, verify_token):
        customer = Customer.objects.create_user(
            email="existing@example.com",
            password="Str0ng-password-not-used-elsewhere",
            first_name="Existing",
            status=Customer.Status.ACTIVE,
        )
        verify_token.return_value = {
            "sub": "google-sub-existing",
            "email": "EXISTING@example.com",
            "email_verified": True,
        }

        response = self.client.post(
            "/api/v1/auth/google/",
            {"credential": "valid-id-token"},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        customer.refresh_from_db()
        self.assertEqual(customer.google_sub, "google-sub-existing")
        self.assertTrue(customer.check_password("Str0ng-password-not-used-elsewhere"))


class PasswordResetApiTests(APITestCase):
    def setUp(self):
        self.customer = Customer.objects.create_user(
            email="reset-customer@example.com",
            password="Str0ng-password-not-used-elsewhere",
            first_name="Reset",
            status=Customer.Status.ACTIVE,
        )

    @override_settings(EMAIL_HOST="", DEFAULT_FROM_EMAIL="accounts@example.com")
    @patch("rest_framework.throttling.ScopedRateThrottle.allow_request", return_value=True)
    @patch("rest_framework.throttling.AnonRateThrottle.allow_request", return_value=True)
    def test_reset_request_reports_unconfigured_email_delivery(self, _allow_anon_request, _allow_scoped_request):
        response = self.client.post(
            "/api/v1/auth/password/reset/",
            {"email": self.customer.email},
            format="json",
        )

        self.assertEqual(response.status_code, 503)

    @override_settings(
        EMAIL_HOST="smtp.example.com",
        DEFAULT_FROM_EMAIL="TechInn <accounts@example.com>",
        FRONTEND_BASE_URL="https://my.techinn.co.zw",
    )
    @patch("apps.accounts.otp.send_transactional", return_value=1)
    @patch("rest_framework.throttling.ScopedRateThrottle.allow_request", return_value=True)
    @patch("rest_framework.throttling.AnonRateThrottle.allow_request", return_value=True)
    def test_reset_request_emails_a_short_lived_otp_without_user_enumeration(
        self,
        _allow_anon_request,
        _allow_scoped_request,
        send_mail_mock,
    ):
        response = self.client.post(
            "/api/v1/auth/password/reset/",
            {"email": self.customer.email},
            format="json",
        )
        unknown_response = self.client.post(
            "/api/v1/auth/password/reset/",
            {"email": "unknown@example.com"},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, unknown_response.data)
        send_mail_mock.assert_called_once()
        message = send_mail_mock.call_args.kwargs["text"]
        self.assertRegex(message, r"Verification code: \d{6}")

    @override_settings(
        EMAIL_HOST="smtp.example.com",
        DEFAULT_FROM_EMAIL="TechInn <accounts@example.com>",
    )
    @patch("apps.accounts.otp.send_transactional", side_effect=OSError("SMTP is unavailable"))
    @patch("rest_framework.throttling.ScopedRateThrottle.allow_request", return_value=True)
    @patch("rest_framework.throttling.AnonRateThrottle.allow_request", return_value=True)
    def test_reset_request_keeps_unknown_and_delivery_failure_responses_generic(
        self,
        _allow_anon_request,
        _allow_scoped_request,
        _send_mail_mock,
    ):
        existing_response = self.client.post(
            "/api/v1/auth/password/reset/",
            {"email": self.customer.email},
            format="json",
        )
        unknown_response = self.client.post(
            "/api/v1/auth/password/reset/",
            {"email": "unknown@example.com"},
            format="json",
        )

        self.assertEqual(existing_response.status_code, 200)
        self.assertEqual(existing_response.data, unknown_response.data)

    def test_reset_confirmation_changes_password_and_rejects_reused_otp(self):
        from datetime import timedelta
        from django.contrib.auth.hashers import make_password
        from django.utils import timezone
        from apps.accounts.models import PasswordResetOTP

        otp = "123456"
        PasswordResetOTP.objects.create(
            customer=self.customer,
            code_hash=make_password(otp),
            expires_at=timezone.now() + timedelta(minutes=10),
        )

        payload = {
            "email": self.customer.email,
            "otp": otp,
            "new_password": "N3w-reset-password-not-used-elsewhere",
        }

        response = self.client.post("/api/v1/auth/password/reset/confirm/", payload, format="json")
        reused_response = self.client.post("/api/v1/auth/password/reset/confirm/", payload, format="json")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(reused_response.status_code, 400)
        self.customer.refresh_from_db()
        self.assertTrue(self.customer.check_password(payload["new_password"]))
