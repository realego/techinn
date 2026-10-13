from rest_framework.test import APITestCase

from apps.accounts.models import Customer


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

    def test_customer_can_change_password_after_current_password_check(self):
        response = self.client.post(
            "/api/v1/auth/password/",
            {
                "current_password": self.password,
                "new_password": "N3w-unique-password-not-used-elsewhere",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 200, response.data)
        self.customer.refresh_from_db()
        self.assertTrue(self.customer.check_password("N3w-unique-password-not-used-elsewhere"))

    def test_password_change_rejects_incorrect_current_password(self):
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
                "current_password": self.password,
                "new_password": self.password,
            },
            format="json",
        )

        self.assertEqual(response.status_code, 400)
