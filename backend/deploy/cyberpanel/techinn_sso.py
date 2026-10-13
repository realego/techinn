"""TechInn file-manager handoff. Install as CyberCP/techinn_sso.py.

Signed tickets expire in 60 seconds, are consumed once, and create only a
site-scoped session. No panel password or administrator session is exposed.
"""
import base64
import hashlib
import hmac
import json
import os
import re
import time
from datetime import timedelta
from pathlib import Path

from django.contrib.sessions.models import Session
from django.db import IntegrityError, transaction
from django.http import HttpResponseForbidden, HttpResponseRedirect, JsonResponse
from django.middleware.csrf import rotate_token
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from websiteFunctions.models import Websites

ORIGIN = 'https://my.techinn.co.zw'
IDLE_SECONDS = 6 * 60 * 60
KEY_PATH = '/etc/techinn/cyberpanel-sso.key'


def owned_site(data):
    site = Websites.objects.select_related('admin__acl').get(domain=data['domain'])
    if (site.admin.userName != data['username'] or site.admin.acl.adminStatus != 0
            or site.admin.state != 'ACTIVE' or site.state != 1):
        raise ValueError('Hosting ownership or status changed')
    if data.get('plan_expires') and time.time() >= data['plan_expires']:
        raise ValueError('Hosting plan expired')
    return site


@csrf_exempt
@require_POST
def consume(request):
    if request.headers.get('Origin') != ORIGIN:
        return HttpResponseForbidden('Open File Manager from your TechInn dashboard.')
    try:
        encoded, signature = request.POST.get('ticket', '').split('.')
        if len(encoded) > 4096:
            raise ValueError('Invalid ticket')
        expected = hmac.new(Path(KEY_PATH).read_bytes(), encoded.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(signature, expected):
            raise ValueError('Invalid ticket')
        data = json.loads(base64.urlsafe_b64decode(encoded + '=' * (-len(encoded) % 4)))
        if not 0 <= time.time() - data['issued_at'] <= 60:
            raise ValueError('Expired ticket')
        if not re.fullmatch(r'[a-f0-9]{64}', data['nonce']):
            raise ValueError('Invalid nonce')
        site = owned_site(data)
        # A unique DB insert prevents simultaneous replays across panel workers.
        with transaction.atomic():
            Session.objects.create(
                session_key=hashlib.sha256(data['nonce'].encode()).hexdigest()[:32],
                session_data='', expire_date=timezone.now() + timedelta(seconds=120),
            )
    except (ValueError, KeyError, TypeError, OSError, Websites.DoesNotExist, IntegrityError):
        return HttpResponseForbidden('This link expired or was used. Open File Manager again from TechInn.')
    request.session.flush()
    rotate_token(request)
    request.session['userID'] = site.admin_id
    address = request.META.get('HTTP_CF_CONNECTING_IP') or request.META.get('REMOTE_ADDR', '')
    request.session['ipAddr'] = ':'.join(address.split(':')[:3]) if ':' in address else address
    request.session['techinn_site'] = {key: data.get(key) for key in ('domain', 'username', 'plan_expires')}
    request.session.set_expiry(IDLE_SECONDS)
    response = HttpResponseRedirect('/filemanager/' + site.domain)
    response['Cache-Control'] = 'no-store'
    response['Referrer-Policy'] = 'no-referrer'
    return response


class SiteSessionMiddleware:
    """Limit handoff sessions to the purchased site's file manager."""
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        grant = request.session.get('techinn_site')
        if grant and request.path not in ('/api/techinn/session/', '/logout'):
            try:
                site = owned_site(grant)
                if request.session.get('userID') != site.admin_id:
                    raise ValueError('Owner changed')
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
                    for key in ('path', 'basePath', 'newPath', 'fileName', 'folderName', 'fileToDownload',
                                'completePath', 'completeStartingPath', 'extractionLocation', 'fileToExtract'):
                        value = data.get(key)
                        if value and (not isinstance(value, str) or os.path.commonpath([root, os.path.realpath(value)]) != root):
                            raise ValueError('Path outside site')
                    names = list(data.get('fileAndFolders', [])) + list(data.get('listOfFiles', []))
                    names += [data[key] for key in ('existingName', 'newFileName', 'compressedFileName', 'permissionsPath') if data.get(key)]
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
