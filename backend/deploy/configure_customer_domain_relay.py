"""Run as root via manage.py shell < this file. Uses existing relay secrets.
Routes only technologyinn.co.zw envelope senders; never sends a test email.
"""
import os
import shutil
import smtplib
import ssl
import subprocess
from datetime import datetime
from pathlib import Path
from django.conf import settings

host, port = settings.EMAIL_HOST, settings.EMAIL_PORT
if host != 'blackroot.empirehost.co.zw' or port != 465:
    raise RuntimeError('Review relay host and implicit TLS port before deployment.')
# Verify credentials and TLS only. No MAIL FROM/RCPT TO/DATA commands.
with smtplib.SMTP_SSL(host, port, context=ssl.create_default_context(), timeout=20) as smtp:
    smtp.login(settings.EMAIL_HOST_USER, settings.EMAIL_HOST_PASSWORD)
backup = Path('/root/techinn-backups') / ('support-relay-' + datetime.now().strftime('%Y%m%d-%H%M%S'))
backup.mkdir(parents=True, mode=0o700)
for name in ('main.cf', 'master.cf'):
    shutil.copy2('/etc/postfix/' + name, backup / name)
password_file = Path('/etc/postfix/techinn-relay-passwords')
fd = os.open(password_file, os.O_CREAT | os.O_WRONLY | os.O_TRUNC, 0o600)
with os.fdopen(fd, 'w') as out:
    out.write(f'[{host}]:{port} {settings.EMAIL_HOST_USER}:{settings.EMAIL_HOST_PASSWORD}\n')
password_file.chmod(0o600)
transport = Path('/etc/postfix/techinn-sender-transports')
transport.write_text(f'@technologyinn.co.zw techinnrelay:[{host}]:{port}\n')
def run(*args):
    subprocess.run(args, check=True, capture_output=True)
run('postmap', str(password_file))
Path(str(password_file)+'.db').chmod(0o600)
run('postmap', str(transport))
run('postconf', '-M', 'techinnrelay/unix=techinnrelay unix - - n - - smtp')
for setting in ('smtp_tls_wrappermode=yes', 'smtp_tls_security_level=verify',
                'smtp_tls_CAfile=/etc/ssl/certs/ca-certificates.crt',
                'smtp_sasl_auth_enable=yes', 'smtp_sasl_security_options=noanonymous',
                'smtp_sasl_password_maps=hash:/etc/postfix/techinn-relay-passwords'):
    run('postconf', '-P', 'techinnrelay/unix/' + setting)
existing = subprocess.check_output(['postconf','-h','sender_dependent_default_transport_maps'], text=True).strip()
new_map = 'hash:/etc/postfix/techinn-sender-transports'
if new_map not in existing:
    run('postconf', '-e', 'sender_dependent_default_transport_maps = ' + new_map + (', '+existing if existing else ''))
run('postfix', 'check')
run('systemctl', 'reload', 'postfix')
print('Relay TLS/authentication verified; technologyinn.co.zw routing installed. No message sent.')
