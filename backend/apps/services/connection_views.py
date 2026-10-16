import secrets
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.utils import timezone
from rest_framework import serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import UserRateThrottle

from apps.orders.models import OrderItem
from apps.services.models import CustomerService, DomainAsset, DomainConnection, HostingAccount, ProviderConnection
from apps.services.periods import extend_service_period, period_months_for_order_item
from apps.services.domain_connections import (
    eligible_service,
    normalize_domain,
    parse_zone_file,
    provider_token,
    public_dns,
    verify_domain_without_plan,
    claim_domain,
)
from apps.services.providers.cloudflare import CloudflareClient, CloudflareError


class DomainVerificationThrottle(UserRateThrottle):
    scope = 'domain_verification'


class ConnectInput(serializers.Serializer):
    domain_name = serializers.CharField(max_length=253)
    plan = serializers.CharField(max_length=80, required=False, allow_blank=True)
    mode = serializers.ChoiceField(choices=DomainConnection.Mode.choices)
    services = serializers.ChoiceField(choices=('website', 'email', 'both'))
    connection_id = serializers.IntegerField(min_value=1, required=False)
    zone_id = serializers.RegexField(r'^[a-fA-F0-9]{32}$', required=False)

    def validate_domain_name(self, value):
        return normalize_domain(value)


class SelectPlanInput(serializers.Serializer):
    plan = serializers.CharField(max_length=80)


class DomainConnectionSerializer(serializers.ModelSerializer):
    plan = serializers.SerializerMethodField()
    verification_name = serializers.SerializerMethodField()
    verification_value = serializers.CharField(source='verification_token', read_only=True)

    class Meta:
        model = DomainConnection
        fields = ('id', 'domain_name', 'plan', 'mode', 'services', 'status', 'verification_name',
            'verification_value', 'verified_at', 'nameservers', 'required_records', 'previous_records',
            'imported_records', 'review_approved_at', 'dns_applied_at', 'checks', 'last_error', 'last_checked_at',
            'next_check_at', 'created_at')
        read_only_fields = fields

    def get_verification_name(self, obj):
        return '_techinn-verification.' + obj.domain_name

    def get_plan(self, obj):
        return obj.customer_service.product.name if obj.customer_service_id else ''


def selectable_plans(customer):
    services = CustomerService.objects.filter(customer=customer,
        product__service_type__slug__in=('web-hosting', 'email-hosting'),
        status__in=('active', 'provisioning'), domain_connection__isnull=True,
    ).select_related('product__service_type', 'hosting_account__primary_domain')
    rows = []
    for service in services:
        try:
            eligible_service(service)
        except ValidationError:
            continue
        account = getattr(service, 'hosting_account', None)
        domain = account.primary_domain.domain_name if account and account.primary_domain else None
        rows.append({'id': 'service:' + str(service.uuid), 'name': service.product.name,
            'kind': service.product.service_type.slug, 'domain': domain})
    items = OrderItem.objects.filter(order__customer=customer, order__status__in=('paid', 'completed'),
        product__service_type__slug__in=('web-hosting', 'email-hosting'), customer_services__isnull=True,
    ).select_related('product__service_type', 'order')
    for item in items:
        if period_months_for_order_item(item):
            rows.append({'id': f'order:{item.pk}', 'name': item.product.name + ' · ' + item.order.order_number,
                'kind': item.product.service_type.slug, 'domain': None})
    return rows


class DomainConnectionViewSet(viewsets.GenericViewSet):
    permission_classes = [IsAuthenticated]
    serializer_class = DomainConnectionSerializer

    def get_queryset(self):
        return DomainConnection.objects.filter(customer=self.request.user).select_related('customer_service__product')

    def list(self, request):
        return Response({'connections': self.get_serializer(self.get_queryset(), many=True).data,
            'plans': selectable_plans(request.user)})

    def retrieve(self, request, pk=None):
        return Response(self.get_serializer(self.get_object()).data)

    @transaction.atomic
    def create(self, request):
        serializer = ConnectInput(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        domain = data['domain_name']
        if self.get_queryset().filter(domain_name=domain).exists():
            raise ValidationError('This domain already has a connection. Continue its setup below.')
        if DomainAsset.objects.filter(domain_name=domain).exclude(customer_service__customer=request.user).exists():
            raise ValidationError('This domain is already connected to another account. Contact support.')
        if self.get_queryset().filter(Q(verified_at__isnull=True) | Q(customer_service__isnull=True)).count() >= 10:
            raise ValidationError('Complete or remove an unfinished connection before adding another.')
        service = self._resolve_plan(request.user, data['plan']) if data.get('plan') else None
        if service:
            eligible_service(service, domain, data['services'])
            if DomainConnection.objects.filter(customer_service=service).exists():
                raise ValidationError('This plan already has a domain connection.')
        provider = None
        if data['mode'] == 'cloudflare':
            provider = ProviderConnection.objects.filter(id=data.get('connection_id'), customer=request.user,
                scope='customer', provider='cloudflare', status='active').first()
            if not provider or not data.get('zone_id'):
                raise ValidationError('Choose your verified Cloudflare account and a domain zone.')
        connection = DomainConnection.objects.create(customer=request.user, customer_service=service, domain_name=domain,
            mode=data['mode'], services=data['services'], provider_connection=provider,
            external_zone_id=data.get('zone_id', ''), verification_token='techinn-' + secrets.token_urlsafe(32),
            next_check_at=None)
        return Response(self.get_serializer(connection).data, status=status.HTTP_201_CREATED)

    @staticmethod
    def _resolve_plan(customer, selection):
        try:
            kind, key = selection.split(':', 1)
            if kind == 'order':
                item = OrderItem.objects.select_for_update().select_related(
                    'order', 'product__service_type',
                ).get(
                    pk=int(key),
                    order__customer=customer,
                    order__status__in=('paid', 'completed'),
                    product__service_type__slug__in=('web-hosting', 'email-hosting'),
                )
                if item.customer_services.exists() or not period_months_for_order_item(item):
                    raise ValidationError('This paid plan is already assigned or its billing period is unavailable.')
                service = CustomerService.objects.create(
                    customer=customer, product=item.product, order_item=item, status='provisioning',
                )
                extend_service_period(service, item)
                return service
            if kind == 'service':
                return CustomerService.objects.select_for_update().select_related(
                    'product__service_type',
                ).get(uuid=key, customer=customer)
        except (ValueError, CustomerService.DoesNotExist, OrderItem.DoesNotExist):
            raise ValidationError('Choose one of your available paid plans.')
        raise ValidationError('Choose one of your available paid plans.')

    @action(detail=True, methods=['post'], url_path='select-plan')
    @transaction.atomic
    def select_plan(self, request, pk=None):
        connection = self.get_queryset().select_for_update().get(pk=self.get_object().pk)
        if not connection.verified_at:
            raise ValidationError('Verify domain ownership before selecting a hosting plan.')
        if connection.customer_service_id:
            raise ValidationError('A paid plan is already assigned to this domain.')
        serializer = SelectPlanInput(data=request.data)
        serializer.is_valid(raise_exception=True)
        service = self._resolve_plan(request.user, serializer.validated_data['plan'])
        eligible_service(service, connection.domain_name, connection.services)
        if DomainConnection.objects.filter(customer_service=service).exclude(pk=connection.pk).exists():
            raise ValidationError('This plan already has a domain connection.')
        connection.customer_service = service
        connection.save(update_fields=('customer_service', 'updated_at'))
        from apps.services.domain_connections import claim_domain
        claim_domain(connection)
        DomainConnection.objects.filter(pk=connection.pk).update(next_check_at=timezone.now())
        connection.refresh_from_db()
        return Response(self.get_serializer(connection).data, status=status.HTTP_202_ACCEPTED)

    @action(detail=True, methods=['post'], throttle_classes=[DomainVerificationThrottle])
    def verify(self, request, pk=None):
        connection = self.get_object()
        if connection.verified_at:
            return Response({
                'verified': True,
                'detail': 'Domain ownership is already verified.',
                'connection': self.get_serializer(connection).data,
            })
        client = CloudflareClient()
        live_zone = None
        try:
            if connection.mode == DomainConnection.Mode.CLOUDFLARE:
                provider = connection.provider_connection
                if (
                    not provider
                    or provider.customer_id != connection.customer_id
                    or provider.scope != ProviderConnection.Scope.CUSTOMER
                ):
                    raise CloudflareError("Choose your own verified Cloudflare connection.")
                token = provider_token(provider)
                live_zone = client.get_zone(token, connection.external_zone_id)
                if live_zone.get('name', '').lower() != connection.domain_name:
                    raise CloudflareError("The selected DNS zone does not match this domain.")
        except CloudflareError as error:
            raise ValidationError(str(error)) from error

        authorized_zone = False
        if live_zone:
            try:
                authorized_zone = (
                    live_zone.get('status') == 'active'
                    and set(public_dns(connection.domain_name, 'NS'))
                    == set(live_zone.get('name_servers', []))
                )
            except CloudflareError:
                authorized_zone = False
        try:
            txt_records = [] if authorized_zone else public_dns(
                '_techinn-verification.' + connection.domain_name, 'TXT',
            )
        except CloudflareError as error:
            raise ValidationError(str(error)) from error

        if not authorized_zone and connection.verification_token not in txt_records:
            DomainConnection.objects.filter(
                pk=connection.pk,
                verified_at__isnull=True,
            ).update(
                status='awaiting_ownership',
                checks={'ownership': False},
                last_error='',
                last_checked_at=timezone.now(),
                next_check_at=None,
            )
            connection.refresh_from_db()
            return Response({
                'verified': False,
                'detail': 'The verification TXT record is not visible yet. Check the record name and value, wait for DNS propagation, then try again.',
                'connection': self.get_serializer(connection).data,
            })

        connection.refresh_from_db()
        if not connection.verified_at:
            if connection.customer_service_id:
                claim_domain(connection)
                DomainConnection.objects.filter(pk=connection.pk).update(next_check_at=timezone.now())
            else:
                verify_domain_without_plan(connection)
        connection.refresh_from_db()
        return Response({
            'verified': True,
            'detail': (
                'Domain ownership is verified. Hosting preparation has started.'
                if connection.customer_service_id
                else 'Domain ownership is verified. You can choose a paid plan whenever you are ready.'
            ),
            'connection': self.get_serializer(connection).data,
        })

    @action(detail=True, methods=['post'], throttle_classes=[DomainVerificationThrottle])
    def check(self, request, pk=None):
        connection = self.get_object()
        if not connection.verified_at:
            return self.verify(request, pk)
        # Scheduling is cheap; DNS and server work run outside the HTTP request.
        DomainConnection.objects.filter(pk=connection.pk).update(next_check_at=timezone.now())
        return Response({'detail': 'Connection check queued. This page updates automatically.'}, status=202)

    @action(detail=True, methods=['post'])
    def approve(self, request, pk=None):
        connection = self.get_object()
        if not connection.verified_at or not connection.required_records:
            raise ValidationError('Verify ownership and wait for hosting preparation first.')
        if connection.review_approved_at:
            return Response({'detail': 'DNS setup is already approved.'}, status=202)
        if request.data.get('confirm') is not True:
            raise ValidationError('Review your existing records and confirm the selected website/email changes.')
        # Import at approval time; the worker merges these with the existing zone.
        imported = parse_zone_file(request.data['zone_file'], connection.domain_name) if request.data.get('zone_file') else []
        DomainConnection.objects.filter(pk=connection.pk, review_approved_at__isnull=True).update(
            imported_records=imported, review_approved_at=timezone.now(), next_check_at=timezone.now())
        return Response({'detail': 'DNS setup approved. We are checking your connection.'}, status=202)

    @transaction.atomic
    def destroy(self, request, pk=None):
        connection = self.get_queryset().select_for_update().get(pk=self.get_object().pk)
        if connection.verified_at and (connection.customer_service_id or connection.domain_id):
            raise ValidationError('This domain is attached to hosting. Contact support to remove or move it safely.')
        # Cancellation never deletes a paid service. A verified no-plan claim has no domain asset to detach.
        self.get_queryset().filter(pk=connection.pk).delete()
        return Response(status=204)
