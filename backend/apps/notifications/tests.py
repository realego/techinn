from unittest.mock import patch
from django.core.mail import EmailMessage
from django.test import SimpleTestCase, override_settings
from apps.notifications.backends import RoutedEmailBackend


@override_settings(DEFAULT_FROM_EMAIL='TechInn Security <security@example.com>', SERVICE_FROM_EMAIL='TechInn Services <services@example.com>', EMAIL_HOST_USER='security@example.com', EMAIL_HOST_PASSWORD='test-security-secret', EMAIL_SERVICE_USER='services@example.com', EMAIL_SERVICE_PASSWORD='test-service-secret', EMAIL_HOST='mail.example.com', EMAIL_PORT=465, EMAIL_USE_SSL=True, EMAIL_USE_TLS=False)
class SenderRoutingTests(SimpleTestCase):
    @patch('apps.notifications.backends.SMTPBackend')
    def test_separate_credentials_and_no_real_network(self, smtp):
        smtp.return_value.__enter__.return_value.send_messages.return_value = 1
        messages = [EmailMessage('Reset password', 'body', 'TechInn Security <security@example.com>', ['test@example.net']), EmailMessage('Invoice', 'body', 'TechInn Services <services@example.com>', ['test@example.net'])]
        self.assertEqual(RoutedEmailBackend().send_messages(messages), 2)
        self.assertEqual([call.kwargs['username'] for call in smtp.call_args_list], ['security@example.com', 'services@example.com'])
        self.assertTrue(all(call.kwargs['use_ssl'] for call in smtp.call_args_list))

    @patch('apps.notifications.backends.SMTPBackend')
    def test_unknown_sender_never_connects(self, smtp):
        with self.assertRaises(ValueError):
            RoutedEmailBackend().send_messages([EmailMessage('Message', 'body', 'unknown@example.com', ['test@example.net'])])
        smtp.assert_not_called()
