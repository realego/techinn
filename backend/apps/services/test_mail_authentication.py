from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from django.test import SimpleTestCase
from apps.services.mail_authentication import authorize_spf, enable_signer


class MailAuthenticationTests(SimpleTestCase):
    def test_preserves_external_senders_and_strict_policy(self):
        self.assertEqual(authorize_spf('v=spf1 include:relay.example ip4:192.0.2.2 -all', '192.0.2.1'),
                         'v=spf1 include:relay.example ip4:192.0.2.2 ip4:192.0.2.1 -all')

    def test_authorizes_before_redirect(self):
        self.assertEqual(authorize_spf('v=spf1 redirect=example.com', '192.0.2.1'),
                         'v=spf1 ip4:192.0.2.1 redirect=example.com')

    def test_repeated_sync_does_not_duplicate_authorization(self):
        policy = 'v=spf1 ip4:192.0.2.1 ~all'
        self.assertEqual(authorize_spf(policy, '192.0.2.1'), policy)

    def test_invalid_policy_is_not_replaced(self):
        with self.assertRaises(ValueError):
            authorize_spf('google-site-verification=keep', '192.0.2.1')

    def test_signer_keeps_other_domains_and_is_idempotent(self):
        with TemporaryDirectory() as root:
            key_table, signing = Path(root) / 'KeyTable', Path(root) / 'SigningTable'
            key_table.write_text('old.example example.com:default:/key\nother other.com:default:/other\n')
            signing.write_text('*@example.com old.example\n*@other.com other\n')
            paths = {'/etc/opendkim/KeyTable': key_table, '/etc/opendkim/SigningTable': signing}
            with patch('apps.services.mail_authentication.Path', side_effect=lambda p: paths[p]), \
                 patch('apps.services.mail_authentication.run') as run:
                enable_signer('example.com', '/new-key')
                self.assertIn('*@other.com other', signing.read_text())
                self.assertTrue(signing.read_text().startswith('*@example.com techinn._domainkey.example.com'))
                run.reset_mock()
                enable_signer('example.com', '/new-key')
                run.assert_not_called()

    def test_failed_configuration_restores_previous_signer(self):
        with TemporaryDirectory() as root:
            key_table, signing = Path(root) / 'KeyTable', Path(root) / 'SigningTable'
            key_table.write_text('old example.com:default:/key\n')
            signing.write_text('*@example.com old\n')
            paths = {'/etc/opendkim/KeyTable': key_table, '/etc/opendkim/SigningTable': signing}
            with patch('apps.services.mail_authentication.Path', side_effect=lambda p: paths[p]), \
                 patch('apps.services.mail_authentication.run', side_effect=RuntimeError('bad config')):
                with self.assertRaises(RuntimeError):
                    enable_signer('example.com', '/new-key')
            self.assertEqual(signing.read_text(), '*@example.com old\n')
            self.assertEqual(key_table.read_text(), 'old example.com:default:/key\n')
