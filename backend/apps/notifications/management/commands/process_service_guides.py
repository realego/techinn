"""Deliver purchase guides and domain activation alerts with persisted retries."""
from django.core.management.base import BaseCommand
from django.db import transaction, connection
from django.utils import timezone
from datetime import timedelta
from smtplib import SMTPResponseException

from apps.notifications.models import EmailQueue, EmailLog
from apps.notifications.lifecycle import queue_lifecycle_event
from apps.notifications.lifecycle import ensure_lifecycle_templates
from apps.notifications.emailing import render_queued_email, send_transactional
from apps.notifications.sweep import sweep_email_queue
from apps.orders.models import Order
from apps.services.models import DomainAsset


DELIVERY_GAP = timedelta(minutes=2)
MAX_MESSAGES_PER_RUN = 20


class Command(BaseCommand):
    help = 'Send purchased-service guides and verified domain-activation alerts.'

    def handle(self, *args, **options):
        # One delivery worker per database, including manual invocations.
        locked = False
        if connection.vendor == "mysql":
            with connection.cursor() as cursor:
                cursor.execute("SELECT GET_LOCK('techinn_notification_delivery', 0)")
                locked = cursor.fetchone()[0] == 1
            if not locked:
                self.stdout.write("Another notification worker is already running.")
                return
        try:
            self.deliver(*args, **options)
        finally:
            if locked:
                with connection.cursor() as cursor:
                    cursor.execute("SELECT RELEASE_LOCK('techinn_notification_delivery')")

    def deliver(self, *args, **options):
        ensure_lifecycle_templates()
        for order in Order.objects.filter(status__in=('paid', 'completed')).select_related('customer'):
            items = list(order.items.filter(product__isnull=False).exclude(product__slug='account-balance').select_related('product__service_type'))
            if not items or (order.metadata or {}).get('service_renewal'):
                continue
            lines = []
            for item in items:
                kind = item.product.service_type.slug
                if kind == 'web-hosting':
                    lines.append(f'{item.product.name}: Open Web & hosting, assign your purchased or connected domain, then use File Manager to upload your website. A preview link lets you test while registration is pending. Setup normally starts within a few minutes; any delay is shown in your dashboard.\nhttps://my.techinn.co.zw/dashboard/web/')
                elif kind == 'email-hosting':
                    lines.append(f'{item.product.name}: Assign the domain under Business email. Once the domain is active and mail DNS is ready, create mailboxes with your own passwords.\nWebmail: https://your-domain/webmail\nIMAP: mail.your-domain, port 993, SSL\nSMTP: mail.your-domain, port 465, SSL (or 587 with STARTTLS)\nUse your full mailbox address as the username.\nhttps://my.techinn.co.zw/dashboard/email/')
                elif kind == 'domains':
                    lines.append(f'Domain {(item.metadata or {}).get("domain", "registration")}: Registration is processing. Registry review and DNS propagation can take time; payment does not mean the domain is registered. Track progress in Domains & DNS. We will email when the domain is active.\nhttps://my.techinn.co.zw/dashboard/domains/')
                else:
                    lines.append(f'{item.product.name}: Track setup and dashboard access in My services.\nhttps://my.techinn.co.zw/dashboard/services/')
            queue_lifecycle_event(customer=order.customer, slug='purchased-services-guide',
                key=f'purchase-guide:{order.pk}', context={'message':
                f'Hello {order.customer.first_name},\n\nHere is how to get started with order {order.order_number}.\n\n' + '\n\n'.join(lines)})
        for domain in DomainAsset.objects.filter(status='active', customer_service__order_item__isnull=False).select_related('customer_service__customer'):
            queue_lifecycle_event(customer=domain.customer_service.customer, slug='domain-active',
                key=f'domain-active:{domain.pk}', context={'domain': domain.domain_name, 'message':
                f'Your domain {domain.domain_name} is now active.\n\n'
                f'Webmail: https://{domain.domain_name}/webmail\n'
                f'IMAP: mail.{domain.domain_name}, port 993, SSL\n'
                f'SMTP: mail.{domain.domain_name}, port 465, SSL (or 587 with STARTTLS)\n'
                'Use your full mailbox address as the username. DNS and certificates may take a little time to propagate.\n\n'
                'Manage your services: https://my.techinn.co.zw/dashboard/'})
        # Final duplicate-send safety gate after this run has queued its events.
        swept = sweep_email_queue()
        sent = 0
        # Interrupted SMTP delivery is ambiguous: hold for review, never blindly resend.
        EmailQueue.objects.filter(
            status='processing', scheduled_at__lt=timezone.now() - timedelta(minutes=15)
        ).update(status='failed', last_error='Delivery interrupted; check provider logs before any manual retry.')

        # Keep a customer's inbox from receiving a burst when the worker has
        # been offline and returns with a backlog. One message per recipient
        # is released per worker interval, with a small global cap as well.
        last_sent_by_recipient = {}
        for recipient, sent_at in EmailQueue.objects.filter(
            status='sent', sent_at__gte=timezone.now() - DELIVERY_GAP
        ).order_by('-sent_at').values_list('recipient_email', 'sent_at'):
            key = recipient.casefold()
            if key not in last_sent_by_recipient:
                last_sent_by_recipient[key] = sent_at

        for pk in EmailQueue.objects.filter(
                email_template__status='active', status='pending', scheduled_at__lte=timezone.now()
            ).order_by('scheduled_at', 'created_at', 'pk').values_list('pk', flat=True)[:100]:
            if sent >= MAX_MESSAGES_PER_RUN:
                break
            with transaction.atomic():
                row = EmailQueue.objects.select_for_update().get(pk=pk)
                if row.status != 'pending':
                    continue
                from apps.notifications.delivery_policy import obsolete_reason
                reason = obsolete_reason(row)
                if reason:
                    row.status, row.last_error = 'cancelled', reason
                    row.save(update_fields=('status', 'last_error'))
                    continue
                recipient_key = row.recipient_email.casefold()
                last_sent = last_sent_by_recipient.get(recipient_key)
                now = timezone.now()
                recent_deliveries = list(EmailQueue.objects.filter(
                    recipient_email__iexact=row.recipient_email, status='sent',
                    sent_at__gte=now-timedelta(hours=1),
                ).order_by('sent_at').values_list('sent_at', flat=True))
                if len(recent_deliveries) >= 6:
                    row.scheduled_at = recent_deliveries[-6] + timedelta(hours=1)
                    row.save(update_fields=('scheduled_at',))
                    continue
                if last_sent and last_sent > now - DELIVERY_GAP:
                    next_allowed = last_sent + DELIVERY_GAP
                    if row.scheduled_at < next_allowed:
                        row.scheduled_at = next_allowed
                        row.save(update_fields=('scheduled_at',))
                    continue
                row.status = 'processing'
                row.attempts += 1
                row.scheduled_at = now
                row.save(update_fields=('status', 'attempts', 'scheduled_at'))
            try:
                subject, text, html, security = render_queued_email(
                    row.email_template.slug, row.payload.get('context', {}), row.customer
                )
                count = send_transactional(
                    subject=row.subject or subject,
                    text=text,
                    html=html,
                    security=security,
                    recipient_list=[row.recipient_email],
                    reply_to=row.payload.get("reply_to") if row.email_template.slug in {"support-ticket-admin", "contact-admin"} else None,
                    fail_silently=False,
                )
                if count != 1:
                    raise RuntimeError('SMTP did not accept the message')
                row.status, row.sent_at, row.last_error = 'sent', timezone.now(), ''
                sent += 1
                last_sent_by_recipient[recipient_key] = row.sent_at
            except Exception as error:
                retryable = isinstance(error, SMTPResponseException) and 400 <= error.smtp_code < 500
                row.status = 'pending' if retryable and row.attempts < 5 else 'failed'
                row.last_error = str(error)[:500]
                row.scheduled_at = timezone.now() + timedelta(minutes=min(60, 2 ** row.attempts))
            row.save(update_fields=('status', 'sent_at', 'last_error', 'scheduled_at'))
            if row.status == 'sent':
                EmailLog.objects.create(email_queue=row, provider='smtp', status='sent')
        self.stdout.write(f'Service guide/activation messages sent: {sent}; duplicate/stale rows suppressed: {swept}')
