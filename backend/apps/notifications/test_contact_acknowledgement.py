from io import StringIO
from unittest.mock import patch
from django.core.cache import cache
from django.core.management import call_command
from django.test import TestCase
from rest_framework.test import APIClient
from apps.notifications.models import ContactRequest, EmailQueue
from apps.notifications.emailing import render_queued_email


class ContactAcknowledgementTests(TestCase):
    def setUp(self):
        cache.clear()
        self.client = APIClient()
        self.payload = {'name':'Customer', 'email':'customer@example.test', 'phone':'123', 'message':'Please help with a custom integration.', 'source':'shop'}

    @patch('apps.notifications.management.commands.process_service_guides.send_transactional', return_value=1)
    def test_saved_enquiry_queues_customer_acknowledgement_and_admin_notification(self, send):
        self.assertEqual(self.client.post('/api/v1/contact-requests/', self.payload).status_code, 201)
        send.assert_not_called()
        row = EmailQueue.objects.get(email_template__slug='contact-acknowledgement')
        self.assertEqual(row.recipient_email, self.payload['email'])
        self.assertEqual(row.status, 'pending')
        subject, text, html, security = render_queued_email(row.email_template.slug, row.payload['context'])
        self.assertIn('respond', text)
        self.assertIn('TI-ENQ-', text)
        self.assertIn('support@', html)
        self.assertFalse(security)
        call_command('process_service_guides', stdout=StringIO())
        call_command('process_service_guides', stdout=StringIO())
        self.assertEqual(send.call_count, 2)
        admin_call = next(call for call in send.call_args_list if call.kwargs.get('local_delivery'))
        self.assertEqual(admin_call.kwargs['recipient_list'], ['support@technologyinn.co.zw'])
        row.refresh_from_db(); self.assertEqual(row.status, 'sent')
        admin = EmailQueue.objects.get(email_template__slug='contact-admin')
        self.assertEqual(admin.recipient_email, 'support@technologyinn.co.zw')
        self.assertEqual(admin.payload['reply_to'], self.payload['email'])

    def test_retries_deduplicate_and_new_enquiries_do_not_flood_address(self):
        for i in range(2):
            self.assertEqual(self.client.post('/api/v1/contact-requests/', self.payload).status_code, 201)
        self.assertEqual(ContactRequest.objects.count(), 1)
        self.payload['message'] = 'Another enquiry about booking systems.'
        self.assertEqual(self.client.post('/api/v1/contact-requests/', self.payload).status_code, 201)
        self.assertEqual(ContactRequest.objects.count(), 2)
        self.assertEqual(EmailQueue.objects.count(), 3)

    def test_invalid_form_never_queues_email(self):
        self.payload['message'] = 'short'
        self.assertEqual(self.client.post('/api/v1/contact-requests/', self.payload).status_code, 400)
        self.assertFalse(EmailQueue.objects.exists())

    def test_public_form_has_request_rate_limit(self):
        for i in range(5):
            self.assertEqual(self.client.post('/api/v1/contact-requests/', self.payload).status_code, 201)
        self.assertEqual(self.client.post('/api/v1/contact-requests/', self.payload).status_code, 429)
