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

from apps.accounts.models import Customer
from apps.services.models import DomainAsset, HostingAccount, HostingWebsite, CustomerService


class HostingFileManagerView(APIView):
    permission_classes = [IsAuthenticated]

    def issue_ticket(self, request, account_id, access_mode):
        if request.user.status != Customer.Status.ACTIVE or request.user.is_staff:
            raise ValidationError({'detail': 'An active customer account is required for hosting access.'})
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
        if access_mode == 'panel' and account.primary_domain.status != DomainAsset.Status.ACTIVE:
            raise ValidationError({'detail': 'Hosting login requires a verified active domain.'})
        child_domain = None
        panel_domain = account.primary_domain.domain_name
        if access_mode == 'file_manager':
            selected_website = request.data.get('website_domain') or panel_domain
            if not isinstance(selected_website, str):
                raise ValidationError({'website_domain': 'Choose a website on this hosting account.'})
            if selected_website.lower() != panel_domain.lower():
                try:
                    child_website = HostingWebsite.objects.get(
                        hosting_account=account,
                        domain_name__iexact=selected_website,
                        status=HostingWebsite.Status.ACTIVE,
                    )
                except HostingWebsite.DoesNotExist as error:
                    raise ValidationError({'website_domain': 'Choose an active website on this hosting account.'}) from error
                child_domain = child_website.domain_name
                panel_domain = child_website.master_domain
        base = settings.CYBERPANEL_API_URL.rstrip('/')
        url = urlsplit(base)
        if url.scheme != 'https' or not url.hostname or url.username or url.password:
            raise ValidationError({'detail': 'Hosting access is not configured.'})
        try:
            secret = Path('/etc/techinn/portal-sso.key').read_bytes()
        except OSError:
            return Response({'detail': 'Hosting access is temporarily unavailable.'}, status=503)
        payload = {
            'domain': panel_domain, 'username': account.username,
            'access_mode': access_mode,
            'issued_at': time.time(), 'nonce': secrets.token_hex(32),
            'plan_expires': expiry.timestamp() if expiry else None,
        }
        if child_domain:
            payload['child_domain'] = child_domain
        encoded = base64.urlsafe_b64encode(json.dumps(payload, separators=(',', ':')).encode()).rstrip(b'=').decode()
        signature = hmac.new(secret, encoded.encode(), hashlib.sha256).hexdigest()
        response = Response({'url': f'{url.scheme}://{url.netloc}/api/techinn/session/', 'ticket': f'{encoded}.{signature}'})
        response['Cache-Control'] = 'no-store'
        return response

    def post(self, request, account_id):
        return self.issue_ticket(request, account_id, 'file_manager')


class HostingPanelLoginView(HostingFileManagerView):
    def post(self, request, account_id):
        return self.issue_ticket(request, account_id, 'panel')
