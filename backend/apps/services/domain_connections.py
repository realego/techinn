"""Existing-domain onboarding. This module never submits registrations."""
import ipaddress
import json
import re
import secrets
import socket
import ssl
from datetime import timedelta
from decimal import Decimal
from pathlib import Path

import dns.exception
import dns.rdatatype
import dns.resolver
import dns.zone
from django.conf import settings
from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from apps.services.models import (
    CustomerService, DomainAsset, DomainConnection, DNSRecord, DNSZone,
    HostingAccount, HostingResource, ProviderConnection,
)
from apps.services.providers.cloudflare import CloudflareClient, CloudflareError, cloudflare_credentials
from apps.services.providers.hosting_connection import prepare_hosting
from apps.services.providers.cyberpanel import CyberPanelError
from apps.services.storage import set_shared_hosting_disk_quota

SUPPORTED = {"A", "AAAA", "CNAME", "MX", "TXT", "SRV", "CAA", "NS"}


def save_progress(connection):
    # User approval/import fields must survive a concurrent background check.
    DomainConnection.objects.filter(pk=connection.pk).update(**{field: getattr(connection, field) for field in ['domain', 'provider_connection', 'external_zone_id', 'verified_at',
        'status', 'nameservers', 'previous_records', 'required_records', 'dns_applied_at', 'checks',
        'last_error', 'last_checked_at', 'next_check_at', 'updated_at']})


def normalize_domain(value):
    try:
        name = value.strip().rstrip('.').encode('idna').decode('ascii').lower()
    except (AttributeError, UnicodeError):
        raise ValidationError({"domain_name": "Enter a domain name, such as example.co.zw."})
    if len(name) > 253 or not re.fullmatch(r'(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}', name):
        raise ValidationError({"domain_name": "Enter a domain without https://, paths or spaces."})
    return name


def eligible_service(service, domain=None, purpose=None):
    kind = service.product.service_type.slug
    if kind not in ('web-hosting', 'email-hosting') or service.status not in ('active', 'provisioning'):
        raise ValidationError("Choose an active paid hosting or email plan.")
    expiry = service.expires_at or service.next_due_at
    if not expiry or expiry <= timezone.now():
        raise ValidationError("This plan needs an active paid service period before connecting a domain.")
    if purpose and kind == 'email-hosting' and purpose != 'email':
        raise ValidationError("This plan includes email hosting. Choose a web hosting plan to host a website.")
    account = HostingAccount.objects.filter(customer_service=service).select_related('primary_domain').first()
    if domain and account and account.primary_domain and account.primary_domain.domain_name != domain:
        raise ValidationError("This plan is already assigned to another domain. Choose an unused plan for this domain.")


def public_dns(name, kind):
    resolver = dns.resolver.Resolver(configure=False)
    resolver.nameservers = ['1.1.1.1', '8.8.8.8']
    resolver.timeout = 1
    resolver.lifetime = 3
    try:
        answers = resolver.resolve(name + '.', kind, search=False)
    except (dns.resolver.NXDOMAIN, dns.resolver.NoAnswer):
        return []
    except dns.exception.DNSException as error:
        raise CloudflareError("Public DNS could not be checked. We will check again shortly.") from error
    values = []
    for item in answers:
        if kind == 'TXT':
            values.append(b''.join(item.strings).decode('utf-8', errors='replace'))
        else:
            values.append(item.to_text().rstrip('.'))
    return values


def origin_ip():
    value = getattr(settings, 'TECHINN_HOSTING_IPV4', '')
    if not value:
        value = Path('/etc/cyberpanel/machineIP').read_text().strip().splitlines()[0]
    address = ipaddress.ip_address(value)
    if address.version != 4 or not address.is_global:
        raise CyberPanelError("The hosting server's public IPv4 address needs configuration.")
    return str(address)


def provider_token(connection):
    if not connection or connection.status != 'active' or connection.provider != 'cloudflare':
        raise CloudflareError("Reconnect your DNS provider before continuing.")
    try:
        return cloudflare_credentials(json.loads(connection.credentials))
    except (ValueError, TypeError) as error:
        raise CloudflareError("The DNS connection needs to be verified again.") from error


def record(kind, name, content, priority=None):
    row = {'type': kind, 'name': name.lower().rstrip('.'), 'content': content, 'ttl': 300, 'proxied': False}
    if priority is not None:
        row['priority'] = priority
    return row


def snapshot_public_dns(domain):
    rows = []
    for name, kinds in [(domain, ('A', 'AAAA', 'MX', 'TXT', 'CAA')), ('www.' + domain, ('CNAME', 'A', 'AAAA')), ('mail.' + domain, ('A', 'AAAA')), ('_dmarc.' + domain, ('TXT',))]:
        for kind in kinds:
            for value in public_dns(name, kind):
                if kind == 'MX':
                    priority, value = value.split(' ', 1)
                    rows.append(record(kind, name, value, int(priority)))
                else:
                    rows.append(record(kind, name, value))
    # A lookup follows CNAMEs; preserve the alias without duplicate A/AAAA.
    aliases = {row['name'] for row in rows if row['type'] == 'CNAME'}
    return [row for row in rows if row['name'] not in aliases or row['type'] == 'CNAME']


def parse_zone_file(text, domain):
    if not isinstance(text, str) or len(text) > 131072 or re.search(r'\$(INCLUDE|GENERATE)', text, re.I):
        raise ValidationError("Use a DNS zone file under 128 KB without INCLUDE or GENERATE directives.")
    try:
        zone = dns.zone.from_text(text, origin=domain + '.', relativize=False, check_origin=False, allow_include=False)
        rows = []
        for name, node in zone.nodes.items():
            owner = name.to_text().rstrip('.')
            if owner != domain and not owner.endswith('.' + domain):
                raise ValueError('Record outside domain')
            for dataset in node.rdatasets:
                kind = dns.rdatatype.to_text(dataset.rdtype)
                if kind in ('SOA',) or (kind == 'NS' and owner == domain):
                    continue
                if kind not in SUPPORTED:
                    raise ValueError('Unsupported record type: ' + kind)
                for data in dataset:
                    value = b''.join(data.strings).decode() if kind == 'TXT' else data.to_text()
                    if kind == 'MX':
                        row = record(kind, owner, str(data.exchange).rstrip('.'), data.preference)
                    else:
                        row = record(kind, owner, value.rstrip('.') if kind == 'CNAME' else value)
                    rows.append(row)
                    if len(rows) > 500:
                        raise ValueError('Maximum 500 records')
        return rows
    except Exception as error:
        raise ValidationError("The DNS zone file could not be read. Check its format and domain; at most 500 supported records can be imported.") from error


def claim_domain(connection):
    with transaction.atomic():
        DomainConnection.objects.select_for_update().get(pk=connection.pk)
        service = CustomerService.objects.select_for_update().select_related('product__service_type').get(pk=connection.customer_service_id)
        eligible_service(service, connection.domain_name, connection.services)
        domain = DomainAsset.objects.filter(domain_name=connection.domain_name).select_related('customer_service').first()
        if domain and domain.customer_service.customer_id != connection.customer_id:
            raise ValidationError("This domain is already attached to another account. Contact support.")
        if not domain:
            domain = DomainAsset.objects.create(customer_service=service, domain_name=connection.domain_name,
                registrar='External domain', status='active', auto_renew=False)
        if HostingAccount.objects.filter(primary_domain=domain, status='active').exclude(customer_service=service).exists():
            raise ValidationError('This domain already has an active hosting plan. Manage it through that plan or contact support to change plans.')
        account, _ = HostingAccount.objects.get_or_create(customer_service=service)
        if account.primary_domain_id and account.primary_domain_id != domain.pk:
            raise ValidationError("This hosting plan already has a different primary domain.")
        account.primary_domain = domain
        account.save(update_fields=['primary_domain', 'updated_at'])
        connection.domain = domain
        connection.verified_at = timezone.now()
        connection.status = 'preparing'
        connection.save(update_fields=['domain', 'verified_at', 'status', 'updated_at'])


def verify_domain_without_plan(connection):
    with transaction.atomic():
        DomainConnection.objects.select_for_update().get(pk=connection.pk)
        domain = DomainAsset.objects.filter(domain_name=connection.domain_name).select_related(
            'customer_service',
        ).first()
        if domain and domain.customer_service.customer_id != connection.customer_id:
            raise ValidationError("This domain is already attached to another account. Contact support.")
        if DomainConnection.objects.filter(
            domain_name=connection.domain_name,
            verified_at__isnull=False,
        ).exclude(pk=connection.pk).exists():
            raise ValidationError("This domain has already been verified by another connection.")
        connection.verified_at = timezone.now()
        connection.status = 'awaiting_plan'
        connection.checks = {'ownership': True}
        connection.last_error = ''
        connection.next_check_at = None
        connection.save(update_fields=('verified_at', 'status', 'checks', 'last_error', 'next_check_at', 'updated_at'))


def required_records(connection, panel, existing):
    domain, ip = connection.domain_name, origin_ip()
    rows = []
    if connection.services in ('website', 'both'):
        rows.extend([record('A', domain, ip), record('CNAME', 'www.' + domain, domain)])
    if connection.services in ('email', 'both'):
        rows.extend([record('A', 'mail.' + domain, ip), record('MX', domain, 'mail.' + domain, 10),
            record('TXT', domain, f'v=spf1 ip4:{ip} ~all')])
        keys = panel['records']
        if not keys:
            raise CyberPanelError("The mail signing key is not ready yet. Retry setup to check again.")
        for key in keys:
            # Local PowerDNS represents multi-part TXT data in DNS presentation form.
            content = key['content']
            if content.startswith('"'):
                import dns.rdata
                data = dns.rdata.from_text(1, 16, content)
                content = b''.join(data.strings).decode()
            rows.append(record('TXT', key['name'], content))
        dmarc = next((r for r in existing if r['type'] == 'TXT' and r['name'] == '_dmarc.' + domain), None)
        rows.append(record('TXT', '_dmarc.' + domain, dmarc['content'] if dmarc else 'v=DMARC1; p=none'))
    return rows


def conflicts(current, target):
    if current['name'].rstrip('.').lower() != target['name']:
        return False
    kind, want = current['type'], target['type']
    if want in ('A', 'AAAA', 'CNAME'):
        return kind in ('A', 'AAAA', 'CNAME')
    if want == 'TXT' and target['content'].lower().startswith('v=spf1'):
        return kind == 'TXT' and current['content'].strip('"').lower().startswith('v=spf1')
    return kind == want


def same_record(a, b):
    return a['type'] == b['type'] and a['name'].rstrip('.').lower() == b['name'].rstrip('.').lower() and a['content'].strip('"').rstrip('.') == b['content'].strip('"').rstrip('.') and a.get('priority') == b.get('priority')


def apply_dns(connection, client, token):
    current = client.list_dns_records(token, connection.external_zone_id)
    # Import/snapshot additions never remove unrelated records.
    for row in connection.previous_records + connection.imported_records:
        if row['type'] not in SUPPORTED or (row['type'] == 'NS' and row['name'] == connection.domain_name):
            continue
        if any(conflicts(row, target) for target in connection.required_records):
            continue
        if not any(same_record(row, other) for other in current):
            payload = {k: row[k] for k in ('type', 'name', 'content', 'ttl', 'proxied', 'priority') if k in row}
            added = client.create_dns_record(token, connection.external_zone_id, payload)
            current.append(added)
    for target in connection.required_records:
        matches = [r for r in current if conflicts(r, target)]
        identical = next((r for r in matches if same_record(r, target) and not r.get('proxied')), None)
        if not identical:
            replace = next((r for r in matches if r['type'] == target['type']), None)
            if replace:
                identical = client.update_dns_record(token, connection.external_zone_id, replace['id'], target)
                current[current.index(replace)] = identical
        for old in matches:
            if identical and old['id'] == identical['id']:
                continue
            client.delete_dns_record(token, connection.external_zone_id, old['id'])
            current.remove(old)
        if not identical:
            current.append(client.create_dns_record(token, connection.external_zone_id, target))
    zone, _ = DNSZone.objects.update_or_create(domain=connection.domain, defaults={
        'provider_connection': connection.provider_connection, 'external_zone_id': connection.external_zone_id,
        'nameservers': connection.nameservers,
    })
    with transaction.atomic():
        ids = []
        for row in client.list_dns_records(token, connection.external_zone_id):
            if row['type'] not in SUPPORTED:
                continue
            saved, _ = DNSRecord.objects.update_or_create(zone=zone, external_record_id=row['id'], defaults={
                'name': row['name'], 'record_type': row['type'], 'content': row['content'],
                'ttl': row.get('ttl', 300), 'priority': row.get('priority'),
                'proxied': row.get('proxied', False), 'synced_at': timezone.now(),
            })
            ids.append(saved.pk)
        zone.records.exclude(pk__in=ids).delete()
    connection.dns_applied_at = timezone.now()


def check_records(connection, provider_records=None, delegated=False):
    checks = []
    for row in connection.required_records:
        actual = public_dns(row['name'], row['type'])
        expected = f"{row['priority']} {row['content']}" if row['type'] == 'MX' else row['content']
        ok = expected.rstrip('.') in actual
        if row['type'] in ('A', 'AAAA', 'CNAME', 'MX'):
            ok = set(actual) == {expected.rstrip('.')}
        elif row['type'] == 'TXT' and expected.lower().startswith('v=spf1'):
            ok = [value for value in actual if value.lower().startswith('v=spf1')] == [expected]
        if row['type'] in ('A', 'CNAME') and provider_records is not None and delegated:
            # Cloudflare proxy addresses differ from the origin; verify the authorized zone's target.
            ok = ok or any(same_record(row, r) for r in provider_records)
        if row['type'] == 'A' and row['name'].startswith('mail.') and provider_records is not None:
            ok = ok and not any(r.get('proxied') for r in provider_records if r['name'] == row['name'] and r['type'] == 'A')
        if row['type'] in ('A', 'CNAME'):
            # A stale IPv6 record can send some visitors to the former server.
            if provider_records is not None and delegated:
                ok = ok and not any(r['name'] == row['name'] and r['type'] == 'AAAA' for r in provider_records)
            else:
                ok = ok and not public_dns(row['name'], 'AAAA')
        checks.append({**row, 'ready': ok})
    return checks


def https_ready(domain):
    try:
        with socket.create_connection((origin_ip(), 443), timeout=5) as raw:
            with ssl.create_default_context().wrap_socket(raw, server_hostname=domain):
                return True
    except (OSError, ssl.SSLError):
        return False


def process_connection(connection):
    if not connection.verified_at:
        connection.status = 'awaiting_ownership'
        connection.checks = {'ownership': False}
        return
    if connection.customer_service_id:
        eligible_service(connection.customer_service, connection.domain_name, connection.services)
    client, token, live_zone = CloudflareClient(), None, None
    if connection.mode == 'cloudflare':
        provider = connection.provider_connection
        if not provider or provider.customer_id != connection.customer_id or provider.scope != 'customer':
            raise CloudflareError("Choose your own verified Cloudflare connection.")
        token = provider_token(provider)
        live_zone = client.get_zone(token, connection.external_zone_id)
        if live_zone.get('name', '').lower() != connection.domain_name:
            raise CloudflareError("The selected DNS zone does not match this domain.")
    if not connection.verified_at:
        authorized_zone = live_zone and live_zone.get('status') == 'active' and set(public_dns(connection.domain_name, 'NS')) == set(live_zone.get('name_servers', []))
        txt = public_dns('_techinn-verification.' + connection.domain_name, 'TXT') if not authorized_zone else []
        if not authorized_zone and connection.verification_token not in txt:
            connection.status = 'awaiting_ownership'
            connection.checks = {'ownership': False}
            return
        if connection.customer_service_id:
            claim_domain(connection)
        else:
            verify_domain_without_plan(connection)
            return
    if not connection.customer_service_id:
        connection.status = 'awaiting_plan'
        connection.checks = {'ownership': True}
        return
    if not connection.required_records:
        connection.previous_records = client.list_dns_records(token, connection.external_zone_id) if token else snapshot_public_dns(connection.domain_name)
        if connection.mode == 'managed':
            provider = ProviderConnection.objects.filter(provider='cloudflare', scope='global', customer__isnull=True, status='active').first()
            token = provider_token(provider)
            live_zone = client.onboard_zone(token, connection.domain_name)
            connection.provider_connection = provider
            connection.external_zone_id = live_zone['id']
            connection.nameservers = live_zone['nameservers']
            # Preserve existing managed-zone records too, including records public scans cannot enumerate.
            managed_records = client.list_dns_records(token, connection.external_zone_id)
            if managed_records:
                connection.previous_records = managed_records
        elif live_zone:
            connection.nameservers = live_zone.get('name_servers', [])
        save_progress(connection)
        panel = prepare_hosting(connection)
        account = connection.customer_service.hosting_account
        account.username, account.linux_username = panel['username'], panel['linux_username']
        account.external_account_id = connection.domain_name
        account.status = 'active'
        account.save()
        HostingResource.objects.get_or_create(hosting_account=account, resource_type='disk', defaults={
            'limit_value': Decimal(panel['disk_mb']) / 1024, 'used_value': 0, 'unit': 'GB', 'measured_at': timezone.now(),
        })
        HostingResource.objects.get_or_create(hosting_account=account, resource_type='email_accounts', defaults={
            'limit_value': panel['mailboxes'], 'used_value': 0, 'unit': 'mailboxes', 'measured_at': timezone.now(),
        })
        set_shared_hosting_disk_quota(account)
        connection.customer_service.status = 'active'
        connection.customer_service.save(update_fields=['status', 'updated_at'])
        connection.required_records = required_records(connection, panel, connection.previous_records)
        connection.status = 'awaiting_review'
        connection.checks = {'ownership': True, 'hosting': True}
        save_progress(connection)
    if not connection.review_approved_at:
        connection.status = 'awaiting_review'
        return
    records, delegated = None, False
    if connection.mode != 'external':
        token = provider_token(connection.provider_connection)
        zone = client.get_zone(token, connection.external_zone_id)
        if zone.get('name', '').lower() != connection.domain_name:
            raise CloudflareError("The DNS zone no longer matches this domain.")
        if not connection.dns_applied_at:
            apply_dns(connection, client, token)
            save_progress(connection)
        records = client.list_dns_records(token, connection.external_zone_id)
        delegated = zone.get('status') == 'active' and set(public_dns(connection.domain_name, 'NS')) == set(zone.get('name_servers', []))
        DNSZone.objects.filter(domain=connection.domain).update(status='active' if delegated else 'pending', last_synced_at=timezone.now())
        if delegated:
            connection.domain.nameservers = zone.get('name_servers', [])
            connection.domain.save(update_fields=['nameservers', 'updated_at'])
    else:
        delegated = True
    rows = check_records(connection, records, delegated)
    website = all(r['ready'] for r in rows if r['name'] in (connection.domain_name, 'www.' + connection.domain_name) and r['type'] in ('A', 'CNAME')) if connection.services != 'email' else None
    email = all(r['ready'] for r in rows if not (r['name'] in (connection.domain_name, 'www.' + connection.domain_name) and r['type'] in ('A', 'CNAME'))) if connection.services != 'website' else None
    certificate = None
    if connection.services != 'email' and website and delegated:
        certificate = https_ready(connection.domain_name)
        if not certificate:
            prepare_hosting(connection, issue_ssl=True)
            certificate = https_ready(connection.domain_name)
    connection.checks = {'ownership': True, 'hosting': True, 'dns': delegated, 'website': website,
        'email': email, 'https': certificate, 'records': rows}
    connection.status = 'connected' if delegated and website is not False and email is not False and (connection.services == 'email' or certificate) else 'awaiting_dns'


def run_connection(connection):
    if not connection.verified_at:
        connection.status = 'awaiting_ownership'
        connection.checks = {'ownership': False}
        connection.next_check_at = None
        save_progress(connection)
        return
    try:
        connection.last_error = ''
        process_connection(connection)
    except (CloudflareError, CyberPanelError, ValidationError) as error:
        detail = error.detail if isinstance(error, ValidationError) else str(error)
        connection.last_error = ' '.join(map(str, detail)) if isinstance(detail, list) else str(detail)
        connection.status = 'needs_attention'
    except Exception:
        import logging
        logging.getLogger(__name__).exception('Domain connection %s failed', connection.pk)
        connection.last_error = 'Setup could not finish. Retry, or contact support if this continues.'
        connection.status = 'needs_attention'
    connection.last_checked_at = timezone.now()
    if connection.verified_at:
        connection.next_check_at = (
            None if connection.status in ('awaiting_plan', 'preparing')
            else timezone.now() + timedelta(minutes=30 if connection.status == 'connected' else 2)
        )
    else:
        connection.next_check_at = None
    save_progress(connection)
