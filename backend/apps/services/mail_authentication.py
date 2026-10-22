"""Reconcile hosted mailbox authentication without sending messages.

A separate selector preserves DKIM used by external senders such as cPanel.
Only switch the local signer after the matching public key resolves.
"""
import base64
import fcntl
import ipaddress
import re
import shutil
import subprocess
from pathlib import Path

import dns.resolver

from apps.services.domain_registration import _provider_token
from apps.services.models import DNSRecord
from apps.services.providers.cloudflare import CloudflareClient


def authorize_spf(value, ip):
    ipaddress.IPv4Address(ip)
    parts = value.strip().strip('"').split()
    if not parts or parts[0].lower() != 'v=spf1':
        raise ValueError('Invalid existing SPF policy; manual review required.')
    mechanism = 'ip4:' + ip
    if mechanism not in parts:
        # Authorization must precede all/redirect, preserving other senders.
        index = next((i for i, p in enumerate(parts) if p.lstrip('+-~?').lower() == 'all' or p.lower().startswith('redirect=')), len(parts))
        parts.insert(index, mechanism)
    return ' '.join(parts)


def txt_values(name):
    try:
        return [''.join(part.decode() for part in row.strings) for row in dns.resolver.resolve(name, 'TXT', lifetime=8)]
    except (dns.resolver.NXDOMAIN, dns.resolver.NoAnswer):
        return []


def run(*args):
    return subprocess.run(args, check=True, capture_output=True, timeout=30)


def enable_signer(domain, key):
    key_table, signing = Path('/etc/opendkim/KeyTable'), Path('/etc/opendkim/SigningTable')
    selector = 'techinn._domainkey.' + domain
    entries = [(key_table, selector, f'{selector} {domain}:techinn:{key}'),
               (signing, '*@' + domain, f'*@{domain} {selector}')]
    backups = {}
    for path, name, entry in entries:
        old = path.read_text()
        rows = [line for line in old.splitlines() if not line.split() or line.split()[0] != name]
        # First match wins in refile tables.
        new = entry + '\n' + '\n'.join(rows) + '\n'
        if new != old:
            backups[path] = old
            path.write_text(new)
    if backups:
        try:
            run('opendkim', '-n', '-x', '/etc/opendkim.conf')
            run('systemctl', 'reload', 'opendkim')
        except Exception:
            for path, old in backups.items():
                path.write_text(old)
            raise


def prepare_mail_authentication(domain, zone, ip):
    name = domain.domain_name
    if not re.fullmatch(r'(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}', name):
        raise ValueError('Invalid mail domain.')
    if not zone or not zone.external_zone_id:
        raise RuntimeError('Managed DNS is required for automatic mail authentication.')
    with Path('/run/techinn-mail-auth.lock').open('w') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        directory = Path('/etc/opendkim/keys') / name
        directory.mkdir(parents=True, exist_ok=True)
        key = directory / 'techinn.private'
        if not key.exists():
            run('opendkim-genkey', '-b', '2048', '-d', name, '-s', 'techinn', '-D', str(directory))
        shutil.chown(key, user='opendkim', group='opendkim')
        key.chmod(0o600)
        public = base64.b64encode(run('openssl', 'pkey', '-in', str(key), '-pubout', '-outform', 'DER').stdout).decode()
        dkim = 'v=DKIM1; k=rsa; p=' + public
        client, token = CloudflareClient(), _provider_token()
        rows = client.list_dns_records(token, zone.external_zone_id)

        def matching(host):
            return [r for r in rows if r.get('type') == 'TXT' and r.get('name', '').rstrip('.').lower() == host]

        def save(host, value, existing=None):
            payload = {'type': 'TXT', 'name': host, 'content': value, 'ttl': 300}
            if existing and existing['content'].strip('"') == value:
                return
            result = (client.update_dns_record(token, zone.external_zone_id, existing['id'], payload) if existing
                      else client.create_dns_record(token, zone.external_zone_id, payload))
            DNSRecord.objects.update_or_create(zone=zone, external_record_id=result['id'], defaults={
                'name': host, 'record_type': 'TXT', 'content': value, 'ttl': 300, 'proxied': False})

        spf = [r for r in matching(name) if r['content'].strip('"').lower().startswith('v=spf1')]
        if len(spf) > 1:
            raise RuntimeError('Multiple SPF records exist; review required before enabling mail authentication.')
        save(name, authorize_spf(spf[0]['content'] if spf else 'v=spf1 ~all', ip), spf[0] if spf else None)
        dmarc_name = '_dmarc.' + name
        dmarc = [r for r in matching(dmarc_name) if r['content'].strip('"').lower().startswith('v=dmarc1')]
        if len(dmarc) > 1:
            raise RuntimeError('Multiple DMARC policies exist; review required.')
        if not dmarc:
            save(dmarc_name, 'v=DMARC1; p=none; adkim=r; aspf=r')
        host = 'techinn._domainkey.' + name
        existing = matching(host)
        if len(existing) > 1:
            raise RuntimeError('Multiple TechInn DKIM records exist; review required.')
        save(host, dkim, existing[0] if existing else None)
        # Do not change the active signer until DNS propagation completes.
        if not any('p=' + public in value.replace(' ', '') for value in txt_values(host)):
            raise RuntimeError('Waiting for the TechInn DKIM public key to propagate.')
        run('opendkim-testkey', '-d', name, '-s', 'techinn', '-k', str(key))
        enable_signer(name, key)
        policies = [v for v in txt_values(name) if v.lower().startswith('v=spf1')]
        if len(policies) != 1 or 'ip4:' + ip not in policies[0].split():
            raise RuntimeError('Waiting for SPF authorization to propagate.')
        if len([v for v in txt_values(dmarc_name) if v.lower().startswith('v=dmarc1')]) != 1:
            raise RuntimeError('Waiting for DMARC policy to propagate.')
        return {'selector': 'techinn', 'spf': 'verified', 'dkim': 'verified', 'dmarc': 'published'}
