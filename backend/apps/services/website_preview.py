"""A separate HTTPS origin per customer preview, serving the site's real files."""
import fcntl
import re
import subprocess
from pathlib import Path

from apps.services.domain_registration import _provider_token
from apps.services.providers.cloudflare import CloudflareClient


def ensure_preview(service):
    data = dict(service.provisioning_data or {})
    if data.get('preview_url'):
        return data['preview_url']
    account = service.hosting_account
    domain = account.primary_domain.domain_name
    if not re.fullmatch(r'[a-z0-9.-]+', domain):
        raise ValueError('Invalid preview domain')
    host = f'preview-{service.uuid.hex[:16]}.techinn.co.zw'
    client = CloudflareClient()
    token = _provider_token()
    zones = client._request(token, 'GET', '/zones', query={'name': 'techinn.co.zw'})
    if not zones:
        raise ValueError('Preview DNS zone is unavailable')
    zone_id = zones[0]['id']
    records = client._request(token, 'GET', f'/zones/{zone_id}/dns_records', query={'name': host})
    ip = Path('/etc/cyberpanel/machineIP').read_text().strip().splitlines()[0]
    if not records:
        client._request(token, 'POST', f'/zones/{zone_id}/dns_records', payload={
            'name': host, 'type': 'A', 'content': ip, 'ttl': 300, 'proxied': False})
    elif any(record.get('type') != 'A' or record.get('content') != ip for record in records):
        raise ValueError('Preview hostname already has different DNS records')
    source = Path(f'/usr/local/lsws/conf/vhosts/{domain}/vhost.conf').read_text()
    # Reuse the customer's PHP handler and document root; never execute files
    # under the portal's user or share cookies/origin with another preview.
    source = re.sub(r'vhssl\s*\{[^}]*\}', '', source, flags=re.S)
    source = source.replace('$VH_ROOT', f'/home/{domain}').replace('$VH_NAME', domain)
    source = re.sub(r'^vhDomain\s+.*$', f'vhDomain {host}', source, flags=re.M)
    source = re.sub(r'^vhAliases\s+.*$', 'vhAliases', source, flags=re.M)
    preview_dir = Path('/usr/local/lsws/conf/vhosts') / host
    preview_dir.mkdir(exist_ok=True)
    config = preview_dir / 'vhost.conf'
    certificate = Path('/etc/letsencrypt/live') / host
    with open('/run/techinn-preview-config.lock', 'w') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        main = Path('/usr/local/lsws/conf/httpd_config.conf')
        original = main.read_text()
        updated = original
        if f'virtualhost {host} ' not in updated:
            updated += (f'\nvirtualhost {host} {{\n vhRoot /home/{domain}\n configFile {config}\n'
                        ' allowSymbolLink 1\n enableScript 1\n restrained 1\n}\n')
            updated = re.sub(r'(listener\s+[^\n{]+\s*\{)',
                             lambda m: m.group(0) + f'\n  map {host} {host}', updated)
        config.write_text(source)
        main.write_text(updated)
        checked = subprocess.run(['/usr/local/lsws/bin/openlitespeed', '-t'], capture_output=True, text=True, timeout=60)
        preview_errors = [line for line in (checked.stdout + checked.stderr).splitlines()
                          if '[ERROR]' in line and f'vhost:{host}' in line]
        if preview_errors:
            main.write_text(original)
            raise ValueError('Preview server configuration could not be validated: ' + preview_errors[0][-200:])
        subprocess.run(['systemctl', 'reload', 'lsws'], check=True, timeout=30)
    if not (certificate / 'fullchain.pem').exists():
        issued = subprocess.run(['certbot', 'certonly', '--webroot', '-w',
            '/var/www/html', '-d', host, '--non-interactive', '--agree-tos',
            '--register-unsafely-without-email'], capture_output=True, text=True, timeout=180)
        if issued.returncode:
            raise ValueError('Preview certificate is waiting for DNS; setup will retry')
    source += (f'\nvhssl {{\n keyFile {certificate}/privkey.pem\n'
               f' certFile {certificate}/fullchain.pem\n certChain 1\n}}\n')
    config.write_text(source)
    subprocess.run(['systemctl', 'reload', 'lsws'], check=True, timeout=30)
    front = Path('/etc/nginx/conf.d') / f'techinn-{host}.conf'
    front.write_text(f'''server {{
    listen 443 ssl;
    listen [::]:443 ssl;
    server_name {host};
    ssl_certificate {certificate}/fullchain.pem;
    ssl_certificate_key {certificate}/privkey.pem;
    add_header X-Robots-Tag "noindex, nofollow" always;
    client_max_body_size 100m;
    location / {{
        proxy_pass http://127.0.0.1:8080;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-Proto https;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    }}
}}
''')
    subprocess.run(['nginx', '-t'], check=True, capture_output=True, timeout=20)
    subprocess.run(['systemctl', 'reload', 'nginx'], check=True, timeout=30)
    data['preview_url'] = f'https://{host}/'
    data.pop('preview_error', None)
    service.provisioning_data = data
    service.save(update_fields=('provisioning_data', 'updated_at'))
    return data['preview_url']
