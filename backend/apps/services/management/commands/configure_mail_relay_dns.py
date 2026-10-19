"""Idempotently publish the cPanel relay's SPF, DKIM and DMARC records."""

from django.core.management.base import BaseCommand, CommandError

from apps.services.domain_registration import _provider_token
from apps.services.models import DNSRecord, DNSZone
from apps.services.providers.cloudflare import CloudflareClient, CloudflareError


CPANEL_IP = "23.175.49.229"
DKIM_VALUE = (
    "v=DKIM1; k=rsa; p="
    "MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEAqPe3WG+jJ+nDwHRoDa0ZGO9Fiv4RsS4QlP8luCtLtueKbsBPJCNIO2WD+Jlwfx/mrtFWo8YeYfZO+6eSFT8c+41gmaaqtCmQioJBNEiruubTOrdvKxkfgIaAfR8LuwBbCEoLolZk+faJorXwaqwCJFcbDqlh102/mdUujcNY31vKfn5K2GKxcn4zR+0DJY24ZBaugDDqtPH2/WEPJThR2OH8NSiq4Qi2IvcGXwnz8YGqBrhVSFjLf612mIe3tZG0WbXtN6iKKPRu4swZgky/fiwSwRKmKR7WrtHY+DEmeiJTiIgi9S1bOVlowUJKDqY38amBby0Y3qs2FQqwIA9/HQIDAQAB;"
)


def _txt(value):
    return str(value or "").strip().strip('"')


class Command(BaseCommand):
    help = "Configure the cPanel SMTP relay DNS records in the TechInn Cloudflare zone."

    def add_arguments(self, parser):
        parser.add_argument("domain", nargs="?", default="technologyinn.co.zw")
        parser.add_argument("--cpanel-ip", default=CPANEL_IP)

    def handle(self, *args, **options):
        domain = options["domain"].strip().lower().rstrip(".")
        cpanel_ip = options["cpanel_ip"].strip()
        zone = DNSZone.objects.filter(domain__domain_name=domain).select_related("domain").first()
        if not zone or not zone.external_zone_id:
            raise CommandError(f"No active Cloudflare zone is linked to {domain}.")
        token = _provider_token()
        client = CloudflareClient()
        try:
            current = client.list_dns_records(token, zone.external_zone_id)
        except CloudflareError as error:
            raise CommandError(str(error)) from error

        def matches(row, name):
            return row.get("type") == "TXT" and row.get("name", "").rstrip(".").lower() == name

        def upsert_txt(name, content):
            rows = [row for row in current if matches(row, name)]
            payload = {"type": "TXT", "name": name, "content": content, "ttl": 300, "proxied": False}
            if rows:
                primary = rows[0]
                if _txt(primary.get("content")) != content:
                    primary = client.update_dns_record(token, zone.external_zone_id, primary["id"], payload)
                for duplicate in rows[1:]:
                    client.delete_dns_record(token, zone.external_zone_id, duplicate["id"])
            else:
                primary = client.create_dns_record(token, zone.external_zone_id, payload)
            current[:] = [row for row in current if not matches(row, name)] + [primary]
            DNSRecord.objects.update_or_create(
                zone=zone,
                external_record_id=primary["id"],
                defaults={
                    "name": name,
                    "record_type": "TXT",
                    "content": content,
                    "ttl": 300,
                    "priority": None,
                    "proxied": False,
                },
            )

        spf_rows = [row for row in current if matches(row, domain) and _txt(row.get("content")).lower().startswith("v=spf1")]
        if spf_rows:
            mechanisms = _txt(spf_rows[0]["content"]).split()[1:]
            mechanisms = [item for item in mechanisms if item.lower() not in {"~all", "-all", "?all", "+all"}]
            if not any(item.lower() == f"ip4:{cpanel_ip}".lower() for item in mechanisms):
                mechanisms.append(f"ip4:{cpanel_ip}")
            spf = "v=spf1 " + " ".join(mechanisms) + " ~all"
        else:
            spf = f"v=spf1 ip4:{cpanel_ip} ~all"
        upsert_txt(domain, spf)
        upsert_txt(f"_dmarc.{domain}", "v=DMARC1; p=none;")
        upsert_txt(f"default._domainkey.{domain}", DKIM_VALUE)
        self.stdout.write(self.style.SUCCESS(
            f"Configured SPF, DKIM and DMARC for {domain}; MX records were not changed."
        ))
