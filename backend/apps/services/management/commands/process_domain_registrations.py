from django.core.management.base import BaseCommand, CommandError

from apps.orders.models import OrderItem
from apps.services.domain_registration import DomainRegistrationError, process_paid_domain_item, registration_ready


class Command(BaseCommand):
    help = "Create Cloudflare zones and submit paid .co.zw registrations to ZISPA."

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=25)

    def handle(self, *args, **options):
        limit = options["limit"]
        if limit < 1 or limit > 500:
            raise CommandError("--limit must be between 1 and 500.")

        items = (
            OrderItem.objects.filter(
                order__status__in=["paid", "processing", "completed"],
                product__slug="domains",
                metadata__has_key="domain",
            )
            .select_related("order__customer", "product")
            .prefetch_related("customer_services")
            .order_by("created_at", "id")
        )
        processed = 0
        failed = 0
        for item in items.iterator(chunk_size=100):
            if processed + failed >= limit:
                break
            service = next(iter(item.customer_services.all()), None)
            progress = (service.provisioning_data or {}).get("domain_registration", {}) if service else {}
            if not registration_ready(progress):
                continue
            domain = (item.metadata or {}).get("domain", "unknown domain")
            try:
                service = process_paid_domain_item(item)
            except (DomainRegistrationError, ValueError) as error:
                failed += 1
                self.stderr.write(self.style.WARNING(f"{domain}: {error}"))
                continue
            progress = (service.provisioning_data or {}).get("domain_registration", {})
            processed += 1
            self.stdout.write(
                self.style.SUCCESS(f"{domain}: {progress.get('status', 'provisioning')}")
            )

        self.stdout.write(f"Paid domains processed: {processed}; awaiting retry or details: {failed}.")
