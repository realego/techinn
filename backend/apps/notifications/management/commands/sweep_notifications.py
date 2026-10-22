from django.core.management.base import BaseCommand

from apps.notifications.sweep import sweep_email_queue


class Command(BaseCommand):
    help = "Suppress stale and duplicate transactional email outbox rows without sending email."

    def handle(self, *args, **options):
        cancelled = sweep_email_queue()
        self.stdout.write(f"Notification sweep complete; rows suppressed: {cancelled}")
