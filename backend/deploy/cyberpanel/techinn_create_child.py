#!/usr/local/CyberCP/bin/python
import contextlib
import grp
import json
import os
import pwd
import re
import sys

os.environ['DJANGO_SETTINGS_MODULE'] = 'CyberCP.settings'
sys.path.insert(0, '/usr/local/CyberCP')

import django
django.setup()

from CyberCP.techinn_sso import _decode_ticket, owned_site
from django.db import IntegrityError
from plogical.virtualHostUtilities import virtualHostUtilities
from websiteFunctions.models import ChildDomains, Websites


class ChildSiteError(Exception):
    pass


def create_child(ticket):
    _, data = _decode_ticket(ticket)
    master_domain = data.get('master_domain')
    child_domain = data.get('child_domain')
    username = data.get('username')
    if not all(isinstance(value, str) for value in (master_domain, child_domain, username)):
        raise ChildSiteError('Invalid website details.')

    site = owned_site({
        'domain': master_domain,
        'username': username,
        'plan_expires': data.get('plan_expires'),
    })
    suffix = '.' + site.domain
    if (
        not child_domain.endswith(suffix)
        or child_domain.count('.') != site.domain.count('.') + 1
        or not re.fullmatch(r'[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?', child_domain[:-len(suffix)])
    ):
        raise ChildSiteError('Invalid subdomain.')

    label = child_domain[:-len(suffix)]
    expected_path = os.path.abspath(os.path.join('/home', site.domain, 'public_html', label))
    public_root = os.path.realpath(os.path.join('/home', site.domain, 'public_html'))
    if os.path.commonpath([public_root, expected_path]) != public_root or expected_path == public_root:
        raise ChildSiteError('Invalid website path.')

    child = ChildDomains.objects.filter(domain=child_domain).first()
    if child and child.master_id != site.id:
        raise ChildSiteError('Subdomain already belongs to another website.')
    if not child:
        if Websites.objects.filter(domain=child_domain).exists():
            raise ChildSiteError('Subdomain already exists.')
        allowed_domains = site.package.allowedDomains
        if allowed_domains and ChildDomains.objects.filter(master=site).count() >= allowed_domains:
            raise ChildSiteError('Your hosting plan has reached its subdomain website limit.')
        owner = site.externalApp
        if not isinstance(owner, str) or not re.fullmatch(r'[a-z_][a-z0-9_-]{0,31}', owner):
            raise ChildSiteError('Website ownership could not be verified.')
        try:
            pwd.getpwnam(owner)
        except KeyError as error:
            raise ChildSiteError('Website ownership could not be verified.') from error

        with contextlib.redirect_stdout(sys.stderr):
            result = virtualHostUtilities.createDomain(
                site.domain,
                child_domain,
                'PHP ' + site.phpSelection.removeprefix('PHP ').strip(),
                expected_path,
                0,
                0,
                1,
                site.admin.userName,
                0,
            )
        if not isinstance(result, (tuple, list)) or not result or result[0] != 1:
            message = str(result[1]).lower() if isinstance(result, (tuple, list)) and len(result) > 1 else ''
            if 'maximum number of domains' in message:
                raise ChildSiteError('Your hosting plan has reached its subdomain website limit.')
            raise ChildSiteError('The subdomain website could not be created. Check your hosting plan and try again.')
        child = ChildDomains.objects.get(master=site, domain=child_domain)
    if child.master_id != site.id or os.path.abspath(child.path) != expected_path:
        raise ChildSiteError('The website path could not be verified.')

    if not os.path.lexists(expected_path):
        try:
            owner = pwd.getpwnam(site.externalApp)
            try:
                group = grp.getgrnam('nogroup')
            except KeyError:
                group = grp.getgrnam('nobody')
            os.mkdir(expected_path, 0o750)
            os.chown(expected_path, owner.pw_uid, group.gr_gid)
            os.chmod(expected_path, 0o750)
        except (OSError, KeyError) as error:
            raise ChildSiteError('The website folder could not be prepared.') from error

    document_root = os.path.realpath(expected_path)
    if (
        os.path.commonpath([public_root, document_root]) != public_root
        or document_root == public_root
        or not os.path.isdir(document_root)
    ):
        raise ChildSiteError('The website folder could not be verified.')
    return {'success': True, 'domain': child_domain, 'document_root': document_root}


def main():
    try:
        if len(sys.argv) != 1:
            raise ChildSiteError('Invalid website request.')
        request = json.load(sys.stdin)
        ticket = request.get('ticket') if isinstance(request, dict) else None
        if not isinstance(ticket, str):
            raise ChildSiteError('Invalid website request.')
        response = create_child(ticket)
    except ChildSiteError as error:
        response = {'success': False, 'detail': str(error)}
    except (ValueError, KeyError, TypeError, OSError, IntegrityError, Websites.DoesNotExist, ChildDomains.DoesNotExist):
        response = {
            'success': False,
            'detail': 'The subdomain website could not be created. Check your hosting plan and try again.',
        }
    print(json.dumps(response, separators=(',', ':')))
    return 0 if response.get('success') is True else 1


if __name__ == '__main__':
    sys.exit(main())
