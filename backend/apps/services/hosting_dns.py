"""Prepare website DNS on a newly purchased domain without replacing records."""
from pathlib import Path
from apps.services.models import DNSRecord, DNSZone, ProviderConnection
from apps.services.domain_registration import _provider_token
from apps.services.providers.cloudflare import CloudflareClient


def prepare_website_dns(account):
    domain = account.primary_domain
    if domain.customer_service.product.service_type.slug != 'domains':
        return
    zone = DNSZone.objects.filter(domain=domain).first()
    if not zone or not zone.external_zone_id:
        return
    client, token = CloudflareClient(), _provider_token()
    records = client.list_dns_records(token, zone.external_zone_id)
    targets = [('A', domain.domain_name, Path('/etc/cyberpanel/machineIP').read_text().strip()),
               ('CNAME', 'www.' + domain.domain_name, domain.domain_name)]
    for kind, name, content in targets:
        current = [r for r in records if r['name'] == name and r['type'] in ('A', 'AAAA', 'CNAME')]
        if current:
            continue
        result = client._request(token, 'POST', f'/zones/{zone.external_zone_id}/dns_records',
            payload={'type': kind, 'name': name, 'content': content, 'ttl': 300, 'proxied': False})
        DNSRecord.objects.update_or_create(zone=zone, external_record_id=result['id'],
            defaults={'name': name, 'record_type': kind, 'content': content, 'ttl': 300, 'proxied': False})
    if not zone.provider_connection_id:
        zone.provider_connection = ProviderConnection.objects.filter(provider='cloudflare', scope='global', status='active').first()
        zone.save(update_fields=('provider_connection', 'updated_at'))
