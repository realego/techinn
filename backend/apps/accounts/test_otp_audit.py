from datetime import timedelta
from unittest.mock import patch
from django.db import transaction
from django.test import TestCase, override_settings
from django.utils import timezone
from django.contrib.auth.hashers import make_password
from rest_framework.test import APIClient
from apps.accounts.models import Customer, PasswordResetOTP
from apps.accounts.otp import issue_otp, consume_otp, OTPCooldown


@override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
class OTPAuditTests(TestCase):
    def setUp(self):
        self.user = Customer.objects.create_user(email='audit@example.test', password='Original-secret', status='active')

    def challenge(self, **kwargs):
        return PasswordResetOTP.objects.create(customer=self.user, code_hash=make_password('123456'), expires_at=timezone.now()+timedelta(minutes=10), **kwargs)

    def verify(self, **kwargs):
        with transaction.atomic():
            return consume_otp(self.user, '123456', **kwargs)

    @patch('apps.accounts.otp.send_transactional', return_value=1)
    def test_delivery_wiring_and_cross_purpose_resend_limit(self, send):
        issue_otp(self.user)
        self.assertEqual(send.call_args.kwargs['recipient_list'], [self.user.email])
        self.assertIn('Verification code:', send.call_args.kwargs['text'])
        with self.assertRaises(OTPCooldown):
            issue_otp(self.user, purpose='mailbox', target='4')
        self.assertEqual(send.call_count, 1)

    @patch('apps.accounts.otp.send_transactional', side_effect=OSError('ambiguous SMTP timeout'))
    def test_failed_delivery_still_limits_repeat_requests(self, send):
        with self.assertRaises(OSError): issue_otp(self.user)
        with self.assertRaises(OTPCooldown): issue_otp(self.user)
        self.assertEqual(send.call_count, 1)

    def test_scope_expiry_and_reuse(self):
        row = self.challenge(purpose='mailbox', target='7')
        self.assertFalse(self.verify())
        self.assertFalse(self.verify(purpose='mailbox', target='8'))
        self.assertTrue(self.verify(purpose='mailbox', target='7'))
        self.assertFalse(self.verify(purpose='mailbox', target='7'))
        row = self.challenge()
        row.expires_at = timezone.now()-timedelta(seconds=1); row.save()
        self.assertFalse(self.verify())

    def test_five_bad_attempts_invalidate_code(self):
        row = self.challenge()
        for i in range(5):
            with transaction.atomic(): self.assertFalse(consume_otp(self.user, '999999'))
        row.refresh_from_db()
        self.assertEqual(row.attempts, 5)
        self.assertIsNotNone(row.used_at)
        self.assertFalse(self.verify())

    @patch('apps.accounts.otp.send_transactional', return_value=1)
    def test_hourly_limit(self, send):
        for i in range(5):
            row = self.challenge()
            PasswordResetOTP.objects.filter(pk=row.pk).update(created_at=timezone.now()-timedelta(minutes=3+i))
        with self.assertRaises(OTPCooldown): issue_otp(self.user)
        send.assert_not_called()

    def test_account_endpoint_commits_bad_attempts_and_rejects_reuse(self):
        self.challenge()
        client = APIClient()
        payload = {'email': self.user.email, 'otp': '999999', 'new_password': 'NewSecret-wonder-238'}
        with patch('rest_framework.throttling.ScopedRateThrottle.allow_request', return_value=True), patch('rest_framework.throttling.AnonRateThrottle.allow_request', return_value=True):
            self.assertEqual(client.post('/api/v1/auth/password/reset/confirm/', payload).status_code, 400)
            self.assertEqual(PasswordResetOTP.objects.get().attempts, 1)
            payload['otp'] = '123456'
            self.assertEqual(client.post('/api/v1/auth/password/reset/confirm/', payload).status_code, 200)
            payload['new_password'] = 'AnotherSecret-wonder-238'
            self.assertEqual(client.post('/api/v1/auth/password/reset/confirm/', payload).status_code, 400)

    @override_settings(EMAIL_HOST='smtp.example.test')
    @patch('apps.accounts.otp.send_transactional', return_value=1)
    def test_mailbox_endpoints_are_scoped_and_queue_selected_password(self, send):
        from apps.catalog.models import Product
        from apps.services.models import CustomerService, DomainAsset, HostingAccount, Mailbox, ProvisioningAction
        service = CustomerService.objects.create(customer=self.user, product=Product.objects.get(slug='web-basic'), status='active')
        domain = DomainAsset.objects.create(customer_service=service, domain_name='audit.example', status='active')
        hosting = HostingAccount.objects.create(customer_service=service, primary_domain=domain, status='active', username='audit')
        mailbox = Mailbox.objects.create(hosting_account=hosting, domain=domain, local_part='hello', quota_mb=100, status='active')
        client = APIClient(); client.force_authenticate(self.user)
        url = f'/api/v1/services/mailboxes/{mailbox.pk}/'
        self.assertEqual(client.post(url+'request-password-reset/').status_code, 202)
        self.assertEqual(client.post(url+'request-password-reset/').status_code, 429)
        row = PasswordResetOTP.objects.get(); row.code_hash = make_password('123456'); row.save()
        payload = {'otp':'999999', 'password':'My-new-mail-password'}
        self.assertEqual(client.post(url+'reset-password/', payload).status_code, 400)
        row.refresh_from_db(); self.assertEqual(row.attempts, 1)
        payload['otp']='123456'
        response = client.post(url+'reset-password/', payload)
        self.assertEqual(response.status_code, 202, response.data)
        self.assertEqual(ProvisioningAction.objects.filter(action_type=ProvisioningAction.ActionType.MAILBOX_PASSWORD_RESET).count(), 1)
        self.assertNotEqual(client.post(url+'reset-password/', payload).status_code, 202)
