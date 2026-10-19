"""Separate authenticated SMTP identities for security and service messages."""
from email.utils import parseaddr
from django.conf import settings
from django.core.mail.backends.base import BaseEmailBackend
from django.core.mail.backends.smtp import EmailBackend as SMTPBackend


class RoutedEmailBackend(BaseEmailBackend):
    def send_messages(self, email_messages):
        if not email_messages:
            return 0
        security = parseaddr(settings.DEFAULT_FROM_EMAIL)[1].casefold()
        services = parseaddr(settings.SERVICE_FROM_EMAIL)[1].casefold()
        groups = {security: [], services: []}
        for message in email_messages:
            sender = parseaddr(message.from_email)[1].casefold()
            if sender not in groups:
                raise ValueError("Use a configured TechInn sender identity.")
            groups[sender].append(message)
        sent = 0
        for sender, messages in groups.items():
            if not messages:
                continue
            username = settings.EMAIL_SERVICE_USER if sender == services else settings.EMAIL_HOST_USER
            password = settings.EMAIL_SERVICE_PASSWORD if sender == services else settings.EMAIL_HOST_PASSWORD
            if not username or not password:
                raise ValueError("The selected email sender is not configured.")
            with SMTPBackend(host=settings.EMAIL_HOST, port=settings.EMAIL_PORT,
                             username=username, password=password,
                             use_tls=settings.EMAIL_USE_TLS, use_ssl=settings.EMAIL_USE_SSL,
                             timeout=settings.EMAIL_TIMEOUT, fail_silently=self.fail_silently) as connection:
                sent += connection.send_messages(messages) or 0
        return sent
