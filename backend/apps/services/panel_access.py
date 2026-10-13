import base64
import hashlib
import hmac
import json
import secrets
import time
from pathlib import Path
from urllib.parse import urlsplit

from django.conf import settings
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.services.models import HostingAccount, CustomerService


class HostingFileManagerView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, account_id):
        account = get_object_or_404(
            HostingAccount.objects.select_related('customer_service__product__service_type', 'primary_domain'),
            pk=account_id, customer_service__customer=request.user,
        )
        service = account.customer_service
        expiry = service.expires_at or service.next_due_at
        if (service.status != CustomerService.Status.ACTIVE or account.status != HostingAccount.Status.ACTIVE
                or service.product.service_type.slug != 'web-hosting'
                or (expiry and expiry <= timezone.now()) or not account.primary_domain or not account.username):
            raise ValidationError({'detail': 'File Manager requires an active web hosting plan and domain.'})
        base = settings.CYBERPANEL_API_URL.rstrip('/')
        url = urlsplit(base)
        if url.scheme != 'https' or not url.hostname or url.username or url.password:
            raise ValidationError({'detail': 'Hosting access is not configured.'})
        try:
            secret = Path('/etc/techinn/portal-sso.key').read_bytes()
        except OSError:
            return Response({'detail': 'Hosting access is temporarily unavailable.'}, status=503)
        payload = {
            'domain': account.primary_domain.domain_name, 'username': account.username,
            'issued_at': time.time(), 'nonce': secrets.token_hex(32),
            'plan_expires': expiry.timestamp() if expiry else None,
        }
        encoded = base64.urlsafe_b64encode(json.dumps(payload, separators=(',', ':')).encode()).rstrip(b'=').decode()
        signature = hmac.new(secret, encoded.encode(), hashlib.sha256).hexdigest()
        response = Response({'url': f'{url.scheme}://{url.netloc}/api/techinn/session/', 'ticket': f'{encoded}.{signature}'})
        response['Cache-Control'] = 'no-store'
        return response
