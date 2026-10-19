"""TechInn file-manager handoff. Install as CyberCP/techinn_sso.py.

Signed tickets expire in 60 seconds, are consumed once, and create only a
site-scoped session. No panel password or administrator session is exposed.
"""
import base64
import hashlib
import hmac
import json
import logging
import os
import re
import subprocess
import time
from datetime import timedelta
from pathlib import Path
from urllib.parse import urlencode

from django.contrib.sessions.models import Session
from django.db import IntegrityError, transaction
from django.http import HttpResponseForbidden, HttpResponseRedirect, JsonResponse
from django.middleware.csrf import rotate_token
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from websiteFunctions.models import ChildDomains, Websites

ORIGIN = 'https://my.techinn.co.zw'
IDLE_SECONDS = 6 * 60 * 60
KEY_PATH = '/etc/techinn/cyberpanel-sso.key'
logger = logging.getLogger(__name__)


def owned_site(data):
    site = Websites.objects.select_related('admin__acl').get(domain=data['domain'])
    if (site.admin.userName != data['username'] or site.admin.acl.adminStatus != 0
            or site.admin.state != 'ACTIVE' or site.state != 1):
        raise ValueError('Hosting ownership or status changed')
    if data.get('plan_expires') and time.time() >= data['plan_expires']:
        raise ValueError('Hosting plan expired')
    return site


def _decode_ticket(ticket):
    try:
        encoded, signature = ticket.split('.')
        if len(encoded) > 4096 or not re.fullmatch(r'[a-f0-9]{64}', signature):
            raise ValueError('Invalid ticket')
        expected = hmac.new(Path(KEY_PATH).read_bytes(), encoded.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(signature, expected):
            raise ValueError('Invalid ticket')
        data = json.loads(base64.urlsafe_b64decode(encoded + '=' * (-len(encoded) % 4)))
        if not isinstance(data, dict) or not 0 <= time.time() - data['issued_at'] <= 60:
            raise ValueError('Expired ticket')
        if not re.fullmatch(r'[a-f0-9]{64}', data['nonce']):
            raise ValueError('Invalid nonce')
        return encoded, data
    except (ValueError, KeyError, TypeError, OSError):
        raise ValueError('Invalid or expired ticket')


def _consume_nonce(nonce):
    Session.objects.create(
        session_key=hashlib.sha256(nonce.encode()).hexdigest()[:32],
        session_data='', expire_date=timezone.now() + timedelta(seconds=120),
    )


def _child_document_root(site, child_domain):
    child = ChildDomains.objects.get(master=site, domain=child_domain)
    root = os.path.realpath('/home/' + site.domain)
    public_root = os.path.realpath(os.path.join(root, 'public_html'))
    document_root = os.path.realpath(child.path)
    if (
        os.path.commonpath([public_root, document_root]) != public_root
        or document_root == public_root
    ):
        raise ValueError('Invalid child website path')
    return child, document_root


@csrf_exempt
@require_POST
def consume(request):
    if request.headers.get('Origin') != ORIGIN:
        return HttpResponseForbidden('Open File Manager from your TechInn dashboard.')
    try:
        _, data = _decode_ticket(request.POST.get('ticket', ''))
        access_mode = data.get('access_mode', 'file_manager')
        if access_mode not in ('file_manager', 'panel'):
            raise ValueError('Invalid hosting access mode')
        site = owned_site(data)
        child_domain = data.get('child_domain')
        target_path = None
        if child_domain:
            _, target_path = _child_document_root(site, child_domain)
        with transaction.atomic():
            _consume_nonce(data['nonce'])
    except (ValueError, KeyError, TypeError, OSError, Websites.DoesNotExist,
            ChildDomains.DoesNotExist, IntegrityError):
        return HttpResponseForbidden('This link expired or was used. Open File Manager again from TechInn.')
    request.session.flush()
    rotate_token(request)
    request.session['userID'] = site.admin_id
    address = request.META.get('HTTP_CF_CONNECTING_IP') or request.META.get('REMOTE_ADDR', '')
    request.session['ipAddr'] = ':'.join(address.split(':')[:3]) if ':' in address else address
    request.session['techinn_site'] = {
        key: data.get(key) for key in ('domain', 'username', 'plan_expires', 'child_domain')
    }
    request.session['techinn_site']['access_mode'] = access_mode
    request.session.set_expiry(IDLE_SECONDS)
    destination = '/' if access_mode == 'panel' else '/filemanager/' + site.domain
    if target_path:
        destination += '?' + urlencode({'path': target_path})
    response = HttpResponseRedirect(destination)
    response['Cache-Control'] = 'no-store'
    response['Referrer-Policy'] = 'no-referrer'
    return response


def create_website(request):
    grant = _customer_site_grant(request)
    if grant:
        response = render(
            request,
            'websiteFunctions/techinnCreateWebsite.html',
            {'domain': grant.get('domain', ''), 'techinn_origin': ORIGIN},
        )
        response['Cache-Control'] = 'no-store'
        return response

    from websiteFunctions.views import createWebsite
    return createWebsite(request)

def submit_website_creation(request):
    if _customer_site_grant(request):
        return JsonResponse({
            'status': 0,
            'error_message': (
                'Create or attach primary websites through TechInn Connections so '
                'the paid plan, domain, website allowance, and storage stay linked.'
            ),
        }, status=403)

    from websiteFunctions.views import submitWebsiteCreation
    return submitWebsiteCreation(request)


def _customer_site_grant(request):
    grant = request.session.get('techinn_site')
    if grant and grant.get('access_mode') == 'panel':
        return grant

    user_id = request.session.get('userID')
    if not user_id:
        return None
    from loginSystem.models import Administrator
    account = Administrator.objects.select_related('acl').filter(pk=user_id).first()
    if not account or not account.acl_id or account.acl.adminStatus != 0:
        return None
    domain = Websites.objects.filter(admin=account).order_by('domain').values_list('domain', flat=True).first()
    return {'domain': domain or ''}


@csrf_exempt
@require_POST
def create_child(request):
    if request.headers.get('Origin') != ORIGIN:
        return HttpResponseForbidden('Subdomain creation must be requested from TechInn.')
    try:
        request_data = json.loads(request.body)
        _, data = _decode_ticket(request_data['ticket'])
        master_domain = data['master_domain']
        child_domain = data['child_domain']
        username = data['username']
        if not all(isinstance(value, str) for value in (master_domain, child_domain, username)):
            raise ValueError('Invalid website details')
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
            raise ValueError('Invalid subdomain')

        with transaction.atomic():
            _consume_nonce(data['nonce'])

        try:
            result = subprocess.run(
                ['/usr/bin/sudo', '-n', '/usr/local/sbin/techinn-create-child'],
                input=json.dumps({'ticket': request_data['ticket']}),
                capture_output=True,
                text=True,
                timeout=90,
                check=False,
            )
        except (OSError, subprocess.SubprocessError) as error:
            raise ValueError('The subdomain website could not be created. Check your hosting plan and try again.') from error
        try:
            output_lines = [line.strip() for line in result.stdout.splitlines() if line.strip()]
            command_result = json.loads(output_lines[-1])
        except json.JSONDecodeError as error:
            raise ValueError('CyberPanel could not verify the subdomain website setup.') from error
        except IndexError as error:
            raise ValueError('CyberPanel could not verify the subdomain website setup.') from error
        if not isinstance(command_result, dict) or result.returncode != 0 or command_result.get('success') is not True:
            detail = command_result.get('detail') if isinstance(command_result, dict) else None
            if not isinstance(detail, str):
                detail = 'The subdomain website could not be created. Check your hosting plan and try again.'
            response = JsonResponse({'success': False, 'detail': detail}, status=400)
            response['Cache-Control'] = 'no-store'
            return response
        child, document_root = _child_document_root(site, child_domain)
        response = JsonResponse({
            'success': True,
            'domain': child.domain,
            'document_root': document_root,
        })
        response['Cache-Control'] = 'no-store'
        return response
    except (ValueError, KeyError, TypeError, OSError, Websites.DoesNotExist,
            ChildDomains.DoesNotExist, IntegrityError):
        logger.exception('TechInn subdomain provisioning failed')
        response = JsonResponse({
            'success': False,
            'detail': 'The subdomain website could not be created. Check your hosting plan and try again.',
        }, status=400)
        response['Cache-Control'] = 'no-store'
        return response


@csrf_exempt
@require_POST
def install_certificate(request):
    if request.headers.get('Origin') != ORIGIN:
        return HttpResponseForbidden('Certificate installation must be requested from TechInn.')
    try:
        request_data = json.loads(request.body)
        _, data = _decode_ticket(request_data['ticket'])
        master_domain = data['master_domain']
        child_domain = data['child_domain']
        username = data['username']
        if not all(isinstance(value, str) for value in (master_domain, child_domain, username)):
            raise ValueError('Invalid website details')
        site = owned_site({
            'domain': master_domain,
            'username': username,
            'plan_expires': data.get('plan_expires'),
        })
        _, document_root = _child_document_root(site, child_domain)
        with transaction.atomic():
            _consume_nonce(data['nonce'])

        from plogical.virtualHostUtilities import virtualHostUtilities
        result = virtualHostUtilities.issueSSL(child_domain, document_root, site.adminEmail)
        if not result or result[0] != 1:
            response = JsonResponse({
                'success': False,
                'detail': 'Certificate installation failed. Confirm DNS points to this server and retry.',
            }, status=400)
        else:
            response = JsonResponse({'success': True, 'domain': child_domain})
        response['Cache-Control'] = 'no-store'
        return response
    except (ValueError, KeyError, TypeError, OSError, Websites.DoesNotExist,
            ChildDomains.DoesNotExist, IntegrityError):
        response = JsonResponse({
            'success': False,
            'detail': 'Certificate installation failed. Confirm DNS points to this server and retry.',
        }, status=400)
        response['Cache-Control'] = 'no-store'
        return response


class SiteSessionMiddleware:
    """Enforce the purchased site's scope or CyberPanel's native account permissions."""
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        grant = request.session.get('techinn_site')
        if grant and request.path not in ('/api/techinn/session/', '/logout'):
            try:
                site = owned_site(grant)
                if request.session.get('userID') != site.admin_id:
                    raise ValueError('Owner changed')
                if grant.get('access_mode') == 'panel':
                    request.session.set_expiry(IDLE_SECONDS)
                    return self.get_response(request)
                child_domain = grant.get('child_domain')
                if child_domain:
                    _child_document_root(site, child_domain)
                if request.path in ('/', '/base/', '/websites/' + site.domain):
                    return HttpResponseRedirect('/filemanager/' + site.domain)
                allowed = {'controller', 'upload', 'downloadFile', 'editFile', site.domain}
                if not request.path.startswith('/filemanager/') or request.path[len('/filemanager/'):] not in allowed:
                    raise ValueError('Outside file manager')
                data = request.GET
                if request.method == 'POST':
                    data = json.loads(request.body) if request.content_type == 'application/json' else request.POST
                if not hasattr(data, 'get'):
                    raise ValueError('Invalid request')
                if request.path != '/filemanager/' + site.domain:
                    if data.get('domainName') != site.domain:
                        raise ValueError('Wrong domain')
                    root = os.path.realpath('/home/' + site.domain)
                    # Strengthen directory boundaries before passing paths to the panel.
                    for key in ('path', 'basePath', 'newPath', 'fileToDownload',
                                'completePath', 'completeStartingPath', 'extractionLocation', 'fileToExtract',
                                'permissionsPath'):
                        value = data.get(key)
                        if value and (not isinstance(value, str) or os.path.commonpath([root, os.path.realpath(value)]) != root):
                            raise ValueError('Path outside site')
                    names = list(data.get('fileAndFolders', [])) + list(data.get('listOfFiles', []))
                    names += [data[key] for key in ('fileName', 'folderName', 'existingName',
                                                     'newFileName', 'compressedFileName') if data.get(key)]
                    for name in names:
                        if not isinstance(name, str) or '/' in name or name in ('.', '..'):
                            raise ValueError('Invalid filename')
                        base = data.get('basePath') or data.get('path') or root
                        if os.path.commonpath([root, os.path.realpath(os.path.join(base, name))]) != root:
                            raise ValueError('File outside site')
                request.session.set_expiry(IDLE_SECONDS)
            except (ValueError, TypeError, KeyError, Websites.DoesNotExist):
                message = 'This session can only manage the active hosting site opened from TechInn.'
                if request.method == 'POST':
                    return JsonResponse({'status': 0, 'uploadStatus': 0, 'error_message': message, 'errorMessage': message}, status=403)
                return HttpResponseForbidden(message)
        return self.get_response(request)
