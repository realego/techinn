import json
import os
import subprocess

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from apps.services.models import ProviderConnection
from apps.services.providers.cyberpanel import CyberPanelClient, CyberPanelError


PLAN_SPECS = (
    ("web-basic", "CYBERPANEL_PACKAGE_WEB_BASIC", "2GB", 2048, 1),
    ("web-growth", "CYBERPANEL_PACKAGE_WEB_GROWTH", "10GB", 10240, 5),
    ("web-business", "CYBERPANEL_PACKAGE_WEB_BUSINESS", "25GB", 25600, 20),
)


class Command(BaseCommand):
    help = "Create TechInn's web-hosting packages in the local CyberPanel installation."

    def handle(self, *args, **options):
        specs = []
        for slug, setting_name, label, disk_mb, domains in PLAN_SPECS:
            package_name = getattr(settings, setting_name, "").strip()
            if not package_name:
                raise CommandError(f"Set {setting_name} before creating CyberPanel packages.")
            specs.append({
                "slug": slug,
                "name": package_name,
                "label": label,
                "disk_mb": disk_mb,
                "domains": domains,
            })

        script = "\n".join((
            "import json, sys",
            "import os",
            "sys.path.insert(0, '/usr/local/CyberCP')",
            "os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'CyberCP.settings')",
            "import django",
            "django.setup()",
            "from loginSystem.models import Administrator",
            "from packages.models import Package",
            "payload = json.load(sys.stdin)",
            "admin = Administrator.objects.get(userName='admin', state='ACTIVE')",
            "saved = []",
            "for spec in payload:",
            "    current = Package.objects.filter(packageName=spec['name']).first()",
            "    if current and current.admin_id != admin.id:",
            "        raise RuntimeError('A requested package name belongs to another CyberPanel account.')",
            "    package, _ = Package.objects.update_or_create(packageName=spec['name'], defaults={",
            "        'admin': admin, 'diskSpace': spec['disk_mb'], 'bandwidth': 1000000,",
            "        'emailAccounts': 1000, 'dataBases': 1000, 'ftpAccounts': 1000,",
            "        'allowedDomains': spec['domains'], 'allowFullDomain': 1,",
            "        'enforceDiskLimits': 0, 'memoryLimitMB': 1024, 'cpuCores': 1,",
            "        'ioLimitMBPS': 10, 'inodeLimit': 400000, 'maxConnections': 10,",
            "        'procSoftLimit': 400, 'procHardLimit': 500,",
            "    })",
            "    saved.append({'name': package.packageName, 'disk_mb': package.diskSpace, 'domains': package.allowedDomains})",
            "print(json.dumps(saved))",
        ))
        env = os.environ.copy()
        env.pop("DJANGO_SETTINGS_MODULE", None)
        try:
            result = subprocess.run(
                ["/usr/local/CyberCP/bin/python", "-c", script],
                input=json.dumps(specs), capture_output=True, text=True,
                timeout=60, check=True, env=env,
            )
            saved = json.loads(result.stdout.splitlines()[-1])
        except (OSError, subprocess.SubprocessError, ValueError, IndexError) as error:
            details = getattr(error, "stderr", "")
            detail = details.strip().splitlines()[-1] if details and details.strip() else type(error).__name__
            raise CommandError(f"Could not create TechInn packages in CyberPanel ({detail}).") from error

        connection = ProviderConnection.objects.filter(
            provider=ProviderConnection.Provider.CYBERPANEL,
            scope=ProviderConnection.Scope.GLOBAL,
            customer__isnull=True,
            status=ProviderConnection.Status.ACTIVE,
        ).first()
        if not connection:
            raise CommandError("Verify the global CyberPanel connection before creating packages.")
        try:
            available = CyberPanelClient(connection).verify()
        except CyberPanelError as error:
            raise CommandError("CyberPanel package list could not be verified.") from error
        available_names = set(available)
        missing = [spec["name"] for spec in specs if spec["name"] not in available_names]
        if missing:
            raise CommandError("CyberPanel did not return all newly configured packages.")

        self.stdout.write(self.style.SUCCESS(
            "CyberPanel plans configured: " + ", ".join(
                f"{row['name']} ({row['disk_mb'] // 1024} GB, {row['domains']} website(s))"
                for row in saved
            )
        ))
