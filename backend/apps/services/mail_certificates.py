"""Install and verify per-domain mail TLS through TechInn's root worker."""
import fcntl
import re
import smtplib
import socket
import ssl
import subprocess
from pathlib import Path

from apps.services.custom_certificates import issue_certificate


def run(*args):
    return subprocess.run(args, check=True, capture_output=True, text=True, timeout=40)


def install_mail_certificate(hostname, directory):
    key, cert = directory / 'privkey.pem', directory / 'fullchain.pem'
    dovecot = Path('/etc/dovecot/dovecot.conf')
    mapping = Path('/etc/postfix/vmail_ssl.map')
    with Path('/run/techinn-mail-tls.lock').open('w') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        # CyberPanel can leave certificate blocks pointing at deleted files.
        # Dovecot's reload command can exit successfully while rejecting these.
        guarded = run('/usr/local/sbin/techinn-dovecot-config-guard')
        old_dove, old_map = dovecot.read_text(), mapping.read_text()
        block = f'local_name {hostname} {{\n  ssl_cert = <{cert}\n  ssl_key = <{key}\n}}'
        pattern = rf'local_name\s+{re.escape(hostname)}\s*\{{[^}}]*\}}'
        new_dove = re.sub(pattern, lambda match: block, old_dove) if re.search(pattern, old_dove) else old_dove + '\n' + block + '\n'
        lines = [line for line in old_map.splitlines() if not line.split() or line.split()[0] != hostname]
        new_map = '\n'.join(lines) + f'\n{hostname} {key} {cert}\n'
        if new_dove == old_dove and new_map == old_map:
            if guarded.stdout.strip():
                run('systemctl', 'reload', 'dovecot')
            return
        try:
            dovecot.write_text(new_dove)
            mapping.write_text(new_map)
            run('doveconf', '-n')
            run('postmap', '-F', str(mapping))
            run('postfix', 'check')
        except Exception:
            dovecot.write_text(old_dove)
            mapping.write_text(old_map)
            run('postmap', '-F', str(mapping))
            raise
        run('systemctl', 'reload', 'dovecot')
        run('systemctl', 'reload', 'postfix')


def verify_mail_tls(hostname):
    context = ssl.create_default_context()
    for port in (993, 995, 465):
        with socket.create_connection((hostname, port), timeout=12) as raw:
            with context.wrap_socket(raw, server_hostname=hostname) as secure:
                secure.getpeercert()
    with smtplib.SMTP(hostname, 587, timeout=12) as client:
        client.ehlo()
        client.starttls(context=context)
        client.ehlo()
        if not client.has_extn('auth'):
            raise RuntimeError('Mail submission does not advertise authentication.')


def prepare_mail_tls(domain, server_ip):
    hostname = f'mail.{domain}'
    if not re.fullmatch(r'(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}', hostname):
        raise ValueError('Invalid mail hostname.')
    addresses = {row[4][0] for row in socket.getaddrinfo(hostname, 443, type=socket.SOCK_STREAM)}
    if server_ip not in addresses:
        raise RuntimeError('Mail DNS is not pointing to TechInn yet.')
    directory = Path('/etc/letsencrypt/live') / hostname
    if directory.with_name(hostname + '-0001').exists():
        directory = directory.with_name(hostname + '-0001')
    if directory.with_name(hostname + '-techinn').exists():
        directory = directory.with_name(hostname + '-techinn')
    cert = directory / 'fullchain.pem'
    valid = cert.exists() and subprocess.run(['openssl', 'x509', '-checkend', '2592000', '-noout', '-in', str(cert)], capture_output=True, timeout=10).returncode == 0
    if valid:
        valid = subprocess.run(['openssl', 'verify', '-verify_hostname', hostname, '-CApath', '/etc/ssl/certs', '-untrusted', str(cert), str(cert)], capture_output=True, timeout=10).returncode == 0
    if not valid:
        result = issue_certificate(hostname)
        directory = Path(result['certificate']).parent
    install_mail_certificate(hostname, directory)
    verify_mail_tls(hostname)
    return hostname
