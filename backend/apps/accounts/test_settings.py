from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APITestCase
from apps.accounts.models import Customer, PortalSession
from apps.catalog.models import Product
from apps.services.models import CustomerService, ServiceMember
from apps.notifications.preferences import notification_enabled


class SettingsTests(APITestCase):
    def setUp(self):
        self.owner = Customer.objects.create_user(email='settings-owner@example.com', password='owner-safe-12345')
        self.member = Customer.objects.create_user(email='settings-member@example.com', password='member-safe-12345')
        self.service = CustomerService.objects.create(customer=self.owner, product=Product.objects.get(slug='chatbot-basic'), status='active')
        self.path = f'/api/v1/services/{self.service.uuid}/members/'
        self.client.force_authenticate(self.owner)

    def test_profile_addresses_preferences_persist_and_remain_private(self):
        result = self.client.patch('/api/v1/auth/me/', {'company_name': 'Test Business', 'billing_address': {'line1': '1 Main Street', 'city': 'Harare'}, 'postal_address': {'line1': 'PO Box 1'}, 'notification_preferences': {'service_updates': False, 'product_news': True}}, format='json')
        self.assertEqual(result.status_code, 200, result.data)
        self.owner.refresh_from_db()
        self.assertEqual(self.owner.billing_address['city'], 'Harare')
        self.assertFalse(notification_enabled(self.owner, 'service_updates'))
        self.assertTrue(notification_enabled(self.owner, 'billing_reminders'))
        self.client.patch('/api/v1/auth/me/', {'billing_address': {'city': 'Bulawayo'}}, format='json')
        self.owner.refresh_from_db()
        self.assertEqual(self.owner.billing_address['line1'], '1 Main Street')
        self.client.force_authenticate(self.member)
        self.assertEqual(self.client.get('/api/v1/auth/me/').data['billing_address'], {})

    def test_roles_update_and_revocation_remove_access(self):
        response = self.client.post(self.path, {'email': self.member.email, 'role': 'admin'}, format='json')
        self.assertEqual(response.status_code, 201, response.data)
        detail = f'{self.path}{response.data["id"]}/'
        duplicate = self.client.post(self.path, {'email': self.member.email, 'role': 'admin'}, format='json')
        self.assertEqual(duplicate.status_code, 400)
        response = self.client.patch(detail, {'role': 'billing', 'can_manage_dns': True}, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        self.assertFalse(response.data['can_manage_dns'])
        self.assertTrue(response.data['can_view_billing'])
        self.client.force_authenticate(self.member)
        self.assertEqual(self.client.patch(detail, {'role': 'admin'}, format='json').status_code, 403)
        self.assertEqual(self.client.delete(detail).status_code, 403)
        from apps.services.permissions import require_service_permission
        from rest_framework.exceptions import PermissionDenied
        with self.assertRaises(PermissionDenied):
            require_service_permission(self.member, self.service, 'can_manage_dns')
        self.assertEqual(len(self.client.get('/api/v1/services/dashboard/').data['services']), 1)
        self.client.force_authenticate(self.owner)
        response = self.client.patch(detail, {'role': 'technical'}, format='json')
        self.assertTrue(response.data['can_manage_dns'])
        self.assertFalse(response.data['can_view_billing'])
        self.assertEqual(self.client.delete(detail).status_code, 204)
        self.client.force_authenticate(self.member)
        self.assertEqual(self.client.get('/api/v1/services/dashboard/').data['services'], [])

    def test_password_change_revokes_other_sessions(self):
        current = PortalSession.objects.create(customer=self.owner, last_active_at=timezone.now())
        other = PortalSession.objects.create(customer=self.owner, last_active_at=timezone.now())
        self.client.force_authenticate(self.owner, token={'sid': str(current.pk)})
        from apps.accounts.models import PasswordResetOTP
        from django.contrib.auth.hashers import make_password
        from datetime import timedelta
        PasswordResetOTP.objects.create(customer=self.owner, code_hash=make_password('123456'), expires_at=timezone.now()+timedelta(minutes=10))
        result = self.client.post('/api/v1/auth/password/', {'otp': '123456', 'new_password': 'new-owner-safe-98765'}, format='json')
        self.assertEqual(result.status_code, 200, result.data)
        current.refresh_from_db(); other.refresh_from_db()
        self.assertTrue(current.revoked)
        self.assertTrue(other.revoked)

    @override_settings(EMAIL_HOST='')
    def test_reset_is_honest_when_email_is_not_configured(self):
        self.client.force_authenticate(None)
        response = self.client.post('/api/v1/auth/password/reset/', {'email': self.owner.email}, format='json')
        self.assertEqual(response.status_code, 503)
