import json

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from apps.services.models import ProviderConnection
from apps.services.providers.cyberpanel import CyberPanelClient, CyberPanelError


class Command(BaseCommand):
    help = "Save and verify the encrypted TechInn CyberPanel provider connection."

    def handle(self, *args, **options):
        credentials = {
            "api_url": settings.CYBERPANEL_API_URL,
            "api_user": settings.CYBERPANEL_API_USER,
            "api_password": settings.CYBERPANEL_API_PASSWORD,
        }
        if not all(credentials.values()):
            raise CommandError("CyberPanel API settings are incomplete.")
        connection, _ = ProviderConnection.objects.update_or_create(
            provider=ProviderConnection.Provider.CYBERPANEL,
            scope=ProviderConnection.Scope.GLOBAL,
            customer=None,
            name="TechInn CyberPanel",
            defaults={
                "credentials": json.dumps(credentials),
                "status": ProviderConnection.Status.PENDING,
                "external_account_id": "",
            },
        )
        try:
            CyberPanelClient(connection).verify()
        except CyberPanelError as error:
            connection.status = ProviderConnection.Status.ERROR
            connection.save(update_fields=("status", "updated_at"))
            raise CommandError(str(error)) from error
        connection.status = ProviderConnection.Status.ACTIVE
        connection.last_verified_at = timezone.now()
        connection.save(update_fields=("status", "last_verified_at", "updated_at"))
        self.stdout.write(self.style.SUCCESS("CyberPanel connection verified and saved encrypted."))
