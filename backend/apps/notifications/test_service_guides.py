from io import StringIO
from datetime import timedelta
from smtplib import SMTPDataError
from django.utils import timezone
from unittest.mock import patch
from django.test import TestCase
from django.core.management import call_command
from apps.accounts.models import Customer
from apps.catalog.models import Product
from apps.orders.models import Order, OrderItem
from apps.notifications.models import EmailQueue
from apps.services.models import CustomerService, DomainAsset


class ServiceGuideTests(TestCase):
    def setUp(self):
        self.user = Customer.objects.create_user(email='guide@example.com', password='test-password')
        self.order = Order.objects.create(customer=self.user, order_number='GUIDE', status='paid')
        self.item = OrderItem.objects.create(order=self.order, product=Product.objects.get(slug='web-basic'),
            description='Hosting', unit_price=3.5, subtotal=3.5)

    @patch('apps.notifications.management.commands.process_service_guides.send_transactional', return_value=1)
    def test_guide_and_activation_send_once(self, send):
        call_command('process_service_guides', stdout=StringIO())
        call_command('process_service_guides', stdout=StringIO())
        self.assertEqual(send.call_count, 1)
        service = CustomerService.objects.create(customer=self.user, product=self.item.product, order_item=self.item)
        DomainAsset.objects.create(customer_service=service, domain_name='guide.co.zw', status='active')
        EmailQueue.objects.filter(status='sent').update(sent_at=timezone.now()-timedelta(minutes=3))
        call_command('process_service_guides', stdout=StringIO())
        call_command('process_service_guides', stdout=StringIO())
        self.assertEqual(send.call_count, 2)
        self.assertEqual(EmailQueue.objects.filter(status='sent').count(), 2)

    @patch('apps.notifications.management.commands.process_service_guides.send_transactional', side_effect=SMTPDataError(451, b'SMTP unavailable'))
    def test_delivery_failure_stays_retryable(self, send):
        call_command('process_service_guides', stdout=StringIO())
        row = EmailQueue.objects.get()
        self.assertEqual(row.status, 'pending')
        self.assertEqual(row.attempts, 1)
        self.assertIn('SMTP unavailable', row.last_error)

    @patch('apps.notifications.management.commands.process_service_guides.send_transactional', return_value=1)
    def test_backlog_is_spaced_per_recipient(self, send):
        from apps.notifications.lifecycle import ensure_lifecycle_templates, queue_lifecycle_event
        ensure_lifecycle_templates()
        for i in range(4):
            queue_lifecycle_event(customer=self.user, slug='payment-confirmation', key=f'audit:{i}')
        call_command('process_service_guides', stdout=StringIO())
        call_command('process_service_guides', stdout=StringIO())
        self.assertEqual(send.call_count, 1)
        self.assertEqual(EmailQueue.objects.filter(status='pending').count(), 4)

    @patch('apps.notifications.management.commands.process_service_guides.send_transactional')
    def test_stale_processing_is_cancelled_and_ambiguous_delivery_not_retried(self, send):
        from apps.notifications.lifecycle import ensure_lifecycle_templates, queue_lifecycle_event
        ensure_lifecycle_templates()
        row = queue_lifecycle_event(customer=self.user, slug='domain-processing', key='domain:old', context={'domain':'old.example'})
        self.order.status = 'cancelled'; self.order.save()
        call_command('process_service_guides', stdout=StringIO())
        row.refresh_from_db(); self.assertEqual(row.status, 'cancelled')
        send.assert_not_called()
        row = queue_lifecycle_event(customer=self.user, slug='payment-confirmation', key='payment:interrupted')
        row.status = 'processing'; row.scheduled_at = timezone.now()-timedelta(minutes=20); row.save()
        call_command('process_service_guides', stdout=StringIO())
        row.refresh_from_db(); self.assertEqual(row.status, 'failed')
        send.assert_not_called()

    @patch('apps.notifications.management.commands.process_service_guides.send_transactional')
    def test_hourly_recipient_limit_defers_backlog(self, send):
        from apps.notifications.lifecycle import ensure_lifecycle_templates, queue_lifecycle_event
        ensure_lifecycle_templates()
        for i in range(6):
            row = queue_lifecycle_event(customer=self.user, slug='payment-confirmation', key=f'past:{i}')
            row.status = 'sent'; row.sent_at = timezone.now()-timedelta(minutes=10+i); row.save()
        row = queue_lifecycle_event(customer=self.user, slug='payment-confirmation', key='next:receipt')
        call_command('process_service_guides', stdout=StringIO())
        row.refresh_from_db()
        self.assertEqual(row.status, 'pending')
        self.assertGreater(row.scheduled_at, timezone.now())
        send.assert_not_called()
