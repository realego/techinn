"""Queue support notifications once per saved customer ticket event."""
from django.conf import settings
from django.db import transaction
from apps.notifications.models import EmailQueue, EmailTemplate
from apps.services.models import SupportTicket


def queue_ticket_notification(ticket, message=None):
    with transaction.atomic():
        SupportTicket.objects.select_for_update().get(pk=ticket.pk)
        template, _ = EmailTemplate.objects.get_or_create(slug='support-ticket-admin', defaults={
            'name': 'Support ticket notification', 'subject': 'TechInn support ticket',
            'body_text': '{{ message }}', 'body_html': ''})
        key = f'ticket:{ticket.pk}:message:{message.pk}' if message else f'ticket:{ticket.pk}:created'
        recipient = settings.SUPPORT_TICKET_EMAIL.lower()
        if EmailQueue.objects.filter(email_template=template, payload__event_key=key).exists():
            return
        EmailQueue.objects.create(email_template=template, recipient_email=recipient,
            subject=f'[{ticket.ticket_number}] {ticket.subject}'[:255],
            payload={'event_key': key, 'reply_to': ticket.customer.email, 'context': {
                'reference': ticket.ticket_number, 'subject': ticket.subject,
                'customer_email': ticket.customer.email, 'message': message.body if message else 'New support ticket.',
                'ticket_id': ticket.pk}})
