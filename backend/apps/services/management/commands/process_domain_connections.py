import fcntl
from pathlib import Path
from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone
from apps.services.models import DomainConnection
from apps.services.domain_connections import run_connection

MAX_CONNECTIONS_PER_RUN = 1


def bounded_connection_limit(requested):
    return max(1, min(requested, MAX_CONNECTIONS_PER_RUN))


class Command(BaseCommand):
    help = 'Verify existing domain connections, prepare hosting and check DNS. Never registers domains.'

    def add_arguments(self, parser):
        parser.add_argument('--limit', type=int, default=MAX_CONNECTIONS_PER_RUN)
        parser.add_argument('--connection', type=int)

    def handle(self, *args, **options):
        path = settings.BASE_DIR / 'var' / 'domain-connections.lock'
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open('a') as lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                self.stdout.write('A connection worker is already running.')
                return
            rows = DomainConnection.objects.select_related('customer', 'customer_service__product__service_type', 'provider_connection', 'domain')
            if options['connection']:
                rows = rows.filter(pk=options['connection'])
            else:
                rows = rows.filter(next_check_at__lte=timezone.now())
            count = 0
            limit = bounded_connection_limit(options['limit'])
            for connection in rows.order_by('next_check_at')[:limit]:
                run_connection(connection)
                count += 1
            self.stdout.write(f'Checked {count} domain connections.')
