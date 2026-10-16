"""Root-worker-only adapter for verified external domain provisioning."""
import json
import os
import subprocess

from django.conf import settings
from apps.services.providers.cyberpanel import CyberPanelError

PLAN_PACKAGES = {
    "web-basic": "CYBERPANEL_PACKAGE_WEB_BASIC",
    "web-growth": "CYBERPANEL_PACKAGE_WEB_GROWTH",
    "web-business": "CYBERPANEL_PACKAGE_WEB_BUSINESS",
    "email-essential": "CYBERPANEL_PACKAGE_WEB_BASIC",
    "email-team": "CYBERPANEL_PACKAGE_WEB_GROWTH",
    "email-business-mail": "CYBERPANEL_PACKAGE_WEB_BUSINESS",
}

SCRIPT = r'''
import contextlib, json, os, re, secrets, sys
from pathlib import Path
import django
django.setup()
from loginSystem.models import Administrator
from loginSystem.models import ACL
from packages.models import Package
from websiteFunctions.models import Websites, ChildDomains
from plogical import hashPassword
from plogical.virtualHostUtilities import virtualHostUtilities
from dns.models import Records

d = json.load(sys.stdin)
domain = d['domain']
if not re.fullmatch(r'(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}', domain):
    raise ValueError('Invalid domain')
site = Websites.objects.select_related('admin', 'package').filter(domain=domain).first()
if site and site.admin.email.lower() != d['email'].lower():
    print(json.dumps({'error': 'This domain already belongs to a different hosting account. Contact support.'}))
    sys.exit(0)
if ChildDomains.objects.filter(domain=domain).exists():
    print(json.dumps({'error': 'This domain is already a subdomain website. Manage it through its current hosting plan.'}))
    sys.exit(0)
if not site:
    package = Package.objects.get(packageName=d['package'])
    owner = Administrator.objects.filter(email__iexact=d['email'], state='ACTIVE').exclude(userName='admin').first()
    if not owner:
        if Administrator.objects.filter(userName=d['username']).exists():
            raise ValueError('Hosting username is already assigned')
        owner = Administrator.objects.create(userName=d['username'], email=d['email'],
            password=hashPassword.hash_password(secrets.token_urlsafe(32)), type=3,
            owner=Administrator.objects.get(userName='admin').pk, initWebsitesLimit=1,
            acl=ACL.objects.get(name='user'), api=0, state='ACTIVE')
    # One new paid plan permits one new primary website.
    needed = owner.websites_set.count() + 1 + sum(Administrator.objects.filter(owner=owner.pk).values_list('initWebsitesLimit', flat=True))
    if owner.initWebsitesLimit and owner.initWebsitesLimit < needed:
        owner.initWebsitesLimit = needed
        owner.save(update_fields=['initWebsitesLimit'])
    external = 'ti' + secrets.token_hex(5)
    with contextlib.redirect_stdout(sys.stderr):
        result = virtualHostUtilities.createVirtualHost(domain, d['email'], d['php'], external,
            0, 1, 1, owner.userName, package.packageName, 0)
    if not result or result[0] != 1:
        print(json.dumps({'error': 'The hosting server could not finish preparing this domain. Retry setup.'}))
        sys.exit(0)
    site = Websites.objects.select_related('admin', 'package').get(domain=domain)
if site.state != 1:
    print(json.dumps({'error': 'The existing hosting account is suspended. Renew or contact support.'}))
    sys.exit(0)
root = Path('/home') / domain / 'public_html'
if not root.is_dir() or root.resolve() != root:
    raise ValueError('Hosting directory could not be verified')
if d.get('issue_ssl'):
    with contextlib.redirect_stdout(sys.stderr):
        virtualHostUtilities.issueSSL(domain, str(root), site.adminEmail)
# Return public records and verified account identity only.
records = list(Records.objects.filter(name__endswith=domain, type='TXT', disabled=0).values('name', 'type', 'content'))
print(json.dumps({'username': site.admin.userName, 'linux_username': site.externalApp,
    'disk_mb': site.package.diskSpace, 'mailboxes': site.package.emailAccounts or 1000,
    'records': [r for r in records if r['name'].endswith('._domainkey.' + domain)]}))
'''


def prepare_hosting(connection, *, issue_ssl=False):
    service = connection.customer_service
    package = getattr(settings, PLAN_PACKAGES.get(service.product.slug, ""), "")
    if not package:
        raise CyberPanelError("This plan's hosting package needs configuration. Contact support.")
    payload = {
        "domain": connection.domain_name, "email": connection.customer.email,
        "username": "ti" + connection.customer.uuid.hex[:20],
        "package": package, "php": settings.CYBERPANEL_PHP, "issue_ssl": issue_ssl,
    }
    env = os.environ.copy()
    env["DJANGO_SETTINGS_MODULE"] = "CyberCP.settings"
    try:
        result = subprocess.run(
            ["/usr/local/CyberCP/bin/python", "-c", SCRIPT], input=json.dumps(payload),
            text=True, capture_output=True, timeout=240, check=True,
            cwd="/usr/local/CyberCP", env=env,
        )
        data = json.loads(result.stdout.splitlines()[-1])
    except (OSError, subprocess.SubprocessError, ValueError, IndexError) as error:
        raise CyberPanelError("The hosting server could not confirm setup. Retry, or contact support if it continues.") from error
    if data.get("error"):
        raise CyberPanelError(data["error"])
    return data
