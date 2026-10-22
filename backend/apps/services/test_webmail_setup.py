from types import SimpleNamespace
from unittest.mock import patch, MagicMock
from django.test import SimpleTestCase

from apps.services.management.commands.prepare_email_webmail import prepare_webmail
from apps.services.custom_certificates import WEBMAIL_LOCATIONS, issue_certificate


class WebmailSetupTests(SimpleTestCase):
    def setUp(self):
        auth = patch('apps.services.mail_authentication.prepare_mail_authentication', side_effect=RuntimeError('DNS pending'))
        auth.start()
        self.addCleanup(auth.stop)
        patcher = patch('apps.services.mail_certificates.prepare_mail_tls', side_effect=RuntimeError('DNS pending'))
        patcher.start()
        self.addCleanup(patcher.stop)

    def service(self):
        domain = SimpleNamespace(domain_name='example.co.zw', status='active')
        return SimpleNamespace(hosting_account=SimpleNamespace(primary_domain=domain), provisioning_data={},
                               refresh_from_db=MagicMock(), save=MagicMock())

    def test_missing_root_is_added_before_waiting_for_dns(self):
        service = self.service()
        with patch('apps.services.management.commands.prepare_email_webmail.DNSZone') as zones, \
             patch('apps.services.domain_registration._provider_token', return_value='test'), \
             patch('apps.services.providers.cloudflare.CloudflareClient') as client, \
             patch('apps.services.management.commands.prepare_email_webmail._upsert_records') as upsert, \
             patch('apps.services.management.commands.prepare_email_webmail._server_ip', return_value='192.0.2.1'), \
             patch('apps.services.management.commands.prepare_email_webmail.socket.getaddrinfo', return_value=[]):
            zones.objects.filter.return_value.first.return_value = SimpleNamespace(external_zone_id='zone')
            client.return_value.list_dns_records.return_value = [{'type':'MX', 'name':'example.co.zw'}]
            result = prepare_webmail(service)
            self.assertTrue(any(record['name'] == 'example.co.zw' and record['type'] == 'A' for call in upsert.call_args_list for record in call.args[2]))
            self.assertEqual(result['webmail_status'], 'pending')
            service.save.assert_called_once()

    def test_existing_external_website_is_never_repointed(self):
        service = self.service()
        with patch('apps.services.management.commands.prepare_email_webmail.DNSZone') as zones, \
             patch('apps.services.domain_registration._provider_token', return_value='test'), \
             patch('apps.services.providers.cloudflare.CloudflareClient') as client, \
             patch('apps.services.management.commands.prepare_email_webmail._upsert_records') as upsert, \
             patch('apps.services.management.commands.prepare_email_webmail._server_ip', return_value='192.0.2.1'), \
             patch('apps.services.management.commands.prepare_email_webmail.socket.getaddrinfo', return_value=[(None,None,None,None,('192.0.2.2',443))]), \
             patch('apps.services.management.commands.prepare_email_webmail.issue_certificate') as issue:
            zones.objects.filter.return_value.first.return_value = SimpleNamespace(external_zone_id='zone')
            client.return_value.list_dns_records.return_value = [{'type':'CNAME', 'name':'example.co.zw'}]
            result = prepare_webmail(service)
            self.assertFalse(any(record['name'] == 'example.co.zw' and record['type'] == 'A' for call in upsert.call_args_list for record in call.args[2]))
            issue.assert_not_called()
            self.assertEqual(result['webmail_status'], 'pending')

    def test_pending_domain_does_not_trigger_dns_or_certificate(self):
        service = self.service()
        service.hosting_account.primary_domain.status = 'pending'
        with patch('apps.services.management.commands.prepare_email_webmail.DNSZone') as zones:
            self.assertIsNone(prepare_webmail(service))
            zones.objects.filter.assert_not_called()

    def test_invalid_certificate_hostname_is_rejected_before_commands(self):
        with patch('apps.services.custom_certificates.subprocess.run') as run:
            with self.assertRaises(ValueError):
                issue_certificate('../invalid')
            run.assert_not_called()
        self.assertIn('location /webmail/', WEBMAIL_LOCATIONS)
        self.assertIn('fastcgi_pass unix:/run/php/php8.3-fpm.sock;', WEBMAIL_LOCATIONS)


class MailTLSVerificationTests(SimpleTestCase):
    def test_all_mail_protocols_are_checked_without_sending_mail(self):
        from apps.services.mail_certificates import verify_mail_tls
        with patch('apps.services.mail_certificates.socket.create_connection') as connect, \
             patch('apps.services.mail_certificates.ssl.create_default_context') as context, \
             patch('apps.services.mail_certificates.smtplib.SMTP') as smtp:
            client = smtp.return_value.__enter__.return_value
            client.has_extn.return_value = True
            verify_mail_tls('mail.example.co.zw')
            self.assertEqual([call.args[0][1] for call in connect.call_args_list], [993, 995, 465])
            self.assertTrue(all(call.kwargs['server_hostname'] == 'mail.example.co.zw' for call in context.return_value.wrap_socket.call_args_list))
            client.starttls.assert_called_once_with(context=context.return_value)
            client.sendmail.assert_not_called()
            client.send_message.assert_not_called()

    def test_missing_submission_authentication_is_not_ready(self):
        from apps.services.mail_certificates import verify_mail_tls
        with patch('apps.services.mail_certificates.socket.create_connection'), \
             patch('apps.services.mail_certificates.ssl.create_default_context'), \
             patch('apps.services.mail_certificates.smtplib.SMTP') as smtp:
            smtp.return_value.__enter__.return_value.has_extn.return_value = False
            with self.assertRaisesMessage(RuntimeError, 'does not advertise authentication'):
                verify_mail_tls('mail.example.co.zw')
