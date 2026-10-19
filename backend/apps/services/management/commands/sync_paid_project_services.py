from django.core.management.base import BaseCommand
from apps.orders.models import Order
from apps.services.customer_services import PAID_SERVICE_TYPES, sync_paid_services


class Command(BaseCommand):
    help = 'Record existing paid services in the customer dashboard.'

    def handle(self, *args, **options):
        orders = Order.objects.filter(status__in=('paid', 'completed'), items__product__service_type__slug__in=PAID_SERVICE_TYPES).distinct()
        count = sum(sync_paid_services(order) for order in orders)
        self.stdout.write(f'Added {count} paid project services awaiting setup.')
