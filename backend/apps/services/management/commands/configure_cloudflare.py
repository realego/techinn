import json
import os

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from apps.services.models import ProviderConnection
from apps.services.providers.cloudflare import CloudflareClient, CloudflareError, cloudflare_credentials


class Command(BaseCommand):
    help = "Create or update TechInn's encrypted global Cloudflare connection from environment variables."

    def add_arguments(self, parser):
        parser.add_argument("--verify", action="store_true")

    def handle(self, *args, **options):
        token = os.getenv("CLOUDFLARE_API_TOKEN", "").strip()
        credentials = {"api_token": token} if token else {
            "email": os.getenv("CLOUDFLARE_EMAIL", "").strip(),
            "api_key": os.getenv("CLOUDFLARE_KEY", "").strip(),
        }
        try:
            authentication = cloudflare_credentials(credentials)
        except CloudflareError as error:
            raise CommandError("Set CLOUDFLARE_API_TOKEN or CLOUDFLARE_EMAIL and CLOUDFLARE_KEY.") from error
        name = os.getenv("CLOUDFLARE_CONNECTION_NAME", "TechInn Cloudflare")
        connection, _ = ProviderConnection.objects.update_or_create(
            provider=ProviderConnection.Provider.CLOUDFLARE,
            scope=ProviderConnection.Scope.GLOBAL,
            customer=None,
            name=name,
            defaults={
                "credentials": json.dumps(credentials),
                "status": ProviderConnection.Status.PENDING,
                "external_account_id": "",
            },
        )
        if options["verify"]:
            try:
                CloudflareClient().verify_token(authentication)
            except CloudflareError as error:
                connection.status = ProviderConnection.Status.ERROR
                connection.save(update_fields=("status", "updated_at"))
                raise CommandError(str(error)) from error
            connection.status = ProviderConnection.Status.ACTIVE
            connection.last_verified_at = timezone.now()
            connection.save(update_fields=("status", "last_verified_at", "updated_at"))
        self.stdout.write(
            self.style.SUCCESS(
                f"Saved encrypted global Cloudflare connection '{connection.name}' "
                f"with status '{connection.status}'."
            )
        )
