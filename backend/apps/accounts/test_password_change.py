from rest_framework.test import APITestCase

from apps.accounts.models import Customer, PasswordResetOTP
from django.contrib.auth.hashers import make_password
from django.utils import timezone
from datetime import timedelta


class PasswordChangeApiTests(APITestCase):
    def setUp(self):
        self.password = "Str0ng-password-not-used-elsewhere"
        self.customer = Customer.objects.create_user(
            email="password-customer@example.com",
            password=self.password,
            first_name="Password",
            status=Customer.Status.ACTIVE,
        )
        self.client.force_authenticate(self.customer)
        PasswordResetOTP.objects.create(customer=self.customer, code_hash=make_password("123456"), expires_at=timezone.now()+timedelta(minutes=10))

    def test_customer_can_change_password_after_otp_check(self):
        response = self.client.post(
            "/api/v1/auth/password/",
            {
                "otp": "123456",
                "new_password": "N3w-unique-password-not-used-elsewhere",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 200, response.data)
        self.customer.refresh_from_db()
        self.assertTrue(self.customer.check_password("N3w-unique-password-not-used-elsewhere"))

    def test_google_account_requires_otp_without_current_password(self):
        self.customer.set_unusable_password()
        self.customer.google_sub = "google-sub-passwordless"
        self.customer.save(update_fields=("password", "google_sub"))

        response = self.client.post(
            "/api/v1/auth/password/",
            {"otp": "123456", "new_password": "N3w-google-password-not-used-elsewhere"},
            format="json",
        )

        self.assertEqual(response.status_code, 200, response.data)
        self.customer.refresh_from_db()
        self.assertTrue(self.customer.check_password("N3w-google-password-not-used-elsewhere"))

    def test_password_change_requires_otp_even_with_current_password(self):
        response = self.client.post(
            "/api/v1/auth/password/",
            {
                "current_password": "incorrect-current-password",
                "new_password": "N3w-unique-password-not-used-elsewhere",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.customer.refresh_from_db()
        self.assertTrue(self.customer.check_password(self.password))

    def test_password_change_rejects_reusing_current_password(self):
        response = self.client.post(
            "/api/v1/auth/password/",
            {
                "otp": "123456",
                "new_password": self.password,
            },
            format="json",
        )

        self.assertEqual(response.status_code, 400)
