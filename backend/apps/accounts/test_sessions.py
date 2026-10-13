from datetime import timedelta

from django.utils import timezone
from rest_framework.test import APITestCase
from rest_framework_simplejwt.tokens import RefreshToken

from apps.accounts.models import Customer, PortalSession
from apps.accounts.sessions import new_refresh


class IdleSessionTests(APITestCase):
    def setUp(self):
        self.customer = Customer.objects.create_user(email='idle@example.com', password='test-pass-123', first_name='Idle', status='active')
        self.refresh = new_refresh(self.customer)
        self.session = PortalSession.objects.get(pk=self.refresh['sid'])
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {self.refresh.access_token}')

    def test_activity_extends_session_but_reads_do_not(self):
        earlier = timezone.now() - timedelta(hours=5)
        PortalSession.objects.filter(pk=self.session.pk).update(last_active_at=earlier)
        self.assertEqual(self.client.get('/api/v1/auth/me/').status_code, 200)
        self.session.refresh_from_db()
        self.assertEqual(self.session.last_active_at, earlier)
        response = self.client.post('/api/v1/auth/activity/')
        self.assertEqual(response.status_code, 200)
        renewed = RefreshToken(response.data['refresh'])
        self.assertEqual(renewed['exp'] - renewed['iat'], 21600)
        self.assertEqual(renewed['sid'], str(self.session.pk))
        self.session.refresh_from_db()
        self.assertGreater(self.session.last_active_at, earlier)

    def test_expired_idle_session_rejects_access_refresh_and_activity(self):
        PortalSession.objects.filter(pk=self.session.pk).update(last_active_at=timezone.now() - timedelta(hours=6, seconds=1))
        self.assertEqual(self.client.get('/api/v1/auth/me/').status_code, 401)
        self.assertEqual(self.client.post('/api/v1/auth/activity/').status_code, 401)
        self.client.credentials()
        self.assertEqual(self.client.post('/api/v1/auth/token/refresh/', {'refresh': str(self.refresh)}).status_code, 401)

    def test_logout_revokes_tokens(self):
        self.assertEqual(self.client.post('/api/v1/auth/logout/').status_code, 204)
        self.assertEqual(self.client.get('/api/v1/auth/me/').status_code, 401)
        self.client.credentials()
        self.assertEqual(self.client.post('/api/v1/auth/token/refresh/', {'refresh': str(self.refresh)}).status_code, 401)

    def test_login_tokens_have_idle_session_and_six_hour_refresh(self):
        self.client.credentials()
        response = self.client.post('/api/v1/auth/token/', {'email': self.customer.email, 'password': 'test-pass-123'})
        self.assertEqual(response.status_code, 200)
        token = RefreshToken(response.data['refresh'])
        self.assertTrue(PortalSession.objects.filter(pk=token['sid']).exists())
        self.assertEqual(token['exp'] - token['iat'], 21600)
