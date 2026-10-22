from types import SimpleNamespace
from django.test import TestCase, override_settings
from apps.accounts.models import Customer
from apps.services.serializers import SupportTicketSerializer
from apps.notifications.models import EmailQueue
from apps.notifications.tickets import queue_ticket_notification
from apps.notifications.emailing import render_queued_email


@override_settings(SUPPORT_TICKET_EMAIL='support@technologyinn.co.zw')
class TicketNotificationTests(TestCase):
    def test_saved_ticket_queues_admin_message_once_with_customer_reply_to(self):
        customer = Customer.objects.create_user(email='customer@example.test', first_name='Customer')
        serializer = SupportTicketSerializer(data={'subject': 'Mailbox help', 'message': 'Please check my mailbox.'},
            context={'request': SimpleNamespace(user=customer)})
        serializer.is_valid(raise_exception=True)
        ticket = serializer.save()
        message = ticket.messages.get()
        queue_ticket_notification(ticket, message)
        row = EmailQueue.objects.get()
        self.assertEqual(row.recipient_email, 'support@technologyinn.co.zw')
        self.assertEqual(row.payload['reply_to'], customer.email)
        subject, text, html, security = render_queued_email(row.email_template.slug, row.payload['context'])
        self.assertIn('Please check my mailbox.', text)
        self.assertIn(f'/admin/services/supportticket/{ticket.pk}/change/', html)
        self.assertFalse(security)
