"""Reconcile domain webmail DNS and HTTPS independently of mailbox creation."""
import re
import socket
import subprocess
from pathlib import Path

import requests
from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.services.models import CustomerService, DNSZone
from apps.services.custom_certificates import issue_certificate, WEBMAIL_LOCATIONS
from apps.services.management.commands.check_domain_activations import _server_ip, _upsert_records


def prepare_webmail(service):
    domain = service.hosting_account.primary_domain
    if not domain or domain.status != 'active':
        return
    name = domain.domain_name
    data = dict(service.provisioning_data or {})
    security = dict(data.get('security', {}))
    ip = _server_ip()
    try:
        zone = DNSZone.objects.filter(domain=domain).first()
        if zone and zone.external_zone_id:
            _upsert_records(domain, zone, [
                {'type': 'A', 'name': f'mail.{name}', 'content': ip, 'ttl': 300, 'proxied': False},
                {'type': 'MX', 'name': name, 'content': f'mail.{name}', 'priority': 10, 'ttl': 300},
                {'type': 'TXT', 'name': name, 'content': f'v=spf1 ip4:{ip} ~all', 'ttl': 300},
            ])
            # Preserve a customer's existing website, including an apex CNAME.
            # Only add the root record when there is no address for it at all.
            from apps.services.domain_registration import _provider_token
            from apps.services.providers.cloudflare import CloudflareClient
            records = CloudflareClient().list_dns_records(_provider_token(), zone.external_zone_id)
            if not any(r.get('name', '').rstrip('.').lower() == name and r.get('type') in {'A', 'AAAA', 'CNAME'} for r in records):
                _upsert_records(domain, zone, [{'type': 'A', 'name': name, 'content': ip, 'ttl': 300, 'proxied': False}])
            # Publish the public key used by this server's existing DKIM signer.
            public_key = Path('/etc/opendkim/keys') / name / 'default.txt'
            if public_key.is_file():
                key_value = ''.join(re.findall(r'"([^"\n]*)"', public_key.read_text()))
                if key_value.startswith('v=DKIM1;') and 'p=' in key_value:
                    _upsert_records(domain, zone, [{'type': 'TXT', 'name': f'default._domainkey.{name}', 'content': key_value, 'ttl': 300}])
        addresses = {row[4][0] for row in socket.getaddrinfo(name, 443, type=socket.SOCK_STREAM)}
        if ip not in addresses:
            raise RuntimeError('Domain DNS does not yet resolve to the TechInn server. Existing website DNS has been preserved.')
        cert_dir = Path('/etc/letsencrypt/live') / name
        if cert_dir.with_name(name + '-0001').exists():
            cert_dir = cert_dir.with_name(name + '-0001')
        if cert_dir.with_name(name + '-techinn').exists():
            cert_dir = cert_dir.with_name(name + '-techinn')
        conf = Path('/etc/nginx/conf.d') / f'techinn-certificate-{name}.conf'
        if not conf.exists():
            for candidate in Path('/etc/nginx/sites-enabled').glob('*'):
                content = candidate.read_text()
                names = [item for group in re.findall(r'server_name\s+([^;]+);', content) for item in group.split()]
                if name in names and 'ssl_certificate ' in content:
                    conf = candidate
                    break
        cert = cert_dir / 'fullchain.pem'
        valid = cert.exists() and subprocess.run(['openssl', 'x509', '-checkend', '2592000', '-noout', '-in', str(cert)], capture_output=True).returncode == 0
        if valid:
            valid = subprocess.run(['openssl', 'verify', '-verify_hostname', name, '-CApath', '/etc/ssl/certs', '-untrusted', str(cert), str(cert)], capture_output=True, timeout=10).returncode == 0
        if not valid or not conf.exists():
            issue_certificate(name)
        elif 'location /webmail/' not in conf.read_text():
            original = conf.read_text()
            updated = original.replace('    location / {', WEBMAIL_LOCATIONS + '    location / {')
            conf.write_text(updated)
            try:
                subprocess.run(['nginx', '-t'], check=True, capture_output=True, timeout=30)
            except Exception:
                conf.write_text(original)
                raise
            subprocess.run(['systemctl', 'reload', 'nginx'], check=True, timeout=30)
        response = requests.get(f'https://{name}/webmail/', timeout=20)
        if response.status_code != 200 or 'roundcube' not in response.text.lower():
            raise RuntimeError('The secure webmail login page did not pass its readiness check.')
        security.update(webmail_status='active', webmail_url=f'https://{name}/webmail/', webmail_checked_at=timezone.now().isoformat())
        security.pop('webmail_error', None)
    except Exception as error:
        security.update(webmail_status='pending', webmail_error=str(error)[:800], webmail_checked_at=timezone.now().isoformat())
    try:
        from apps.services.mail_certificates import prepare_mail_tls
        hostname = prepare_mail_tls(name, ip)
        security.update(mail_tls_status='active', mail_hostname=hostname, mail_certificate_at=timezone.now().isoformat())
        security.pop('mail_tls_error', None)
    except Exception as error:
        security.update(mail_tls_status='pending', mail_tls_error=str(error)[:800])
    try:
        from apps.services.mail_authentication import prepare_mail_authentication
        auth = prepare_mail_authentication(domain, DNSZone.objects.filter(domain=domain).first(), ip)
        security.update(mail_auth_status='active', mail_auth=auth, mail_auth_checked_at=timezone.now().isoformat())
        security.pop('mail_auth_error', None)
    except Exception as error:
        security.update(mail_auth_status='pending', mail_auth_error=str(error)[:800])
    # Fetch again so certificate/provisioning workers cannot lose unrelated data.
    service.refresh_from_db(fields=['provisioning_data'])
    data = dict(service.provisioning_data or {})
    data['security'] = {**data.get('security', {}), **security}
    if security.get('webmail_status') == 'active':
        data['security'].pop('webmail_error', None)
    if security.get('mail_tls_status') == 'active':
        data['security'].pop('mail_tls_error', None)
    if security.get('mail_auth_status') == 'active':
        data['security'].pop('mail_auth_error', None)
    service.provisioning_data = data
    service.save(update_fields=['provisioning_data', 'updated_at'])
    return security


class Command(BaseCommand):
    help = 'Prepare and verify personalized HTTPS webmail for active hosting services. Run as root; sends no email.'

    def add_arguments(self, parser):
        parser.add_argument('--domain')

    def handle(self, *args, **options):
        services = CustomerService.objects.filter(status='active', hosting_account__status='active', hosting_account__primary_domain__status='active', product__service_type__slug__in=['email-hosting', 'web-hosting']).select_related('hosting_account__primary_domain', 'product__service_type')
        if options.get('domain'):
            services = services.filter(hosting_account__primary_domain__domain_name=options['domain'])
        for service in services:
            result = prepare_webmail(service)
            self.stdout.write(f"{service.hosting_account.primary_domain.domain_name}: {result.get('webmail_status')} {result.get('webmail_error', '')}; mail TLS: {result.get('mail_tls_status')} {result.get('mail_tls_error', '')}; mail authentication: {result.get('mail_auth_status')} {result.get('mail_auth_error', '')}")
