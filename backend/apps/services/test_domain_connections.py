import json
from datetime import timedelta
from unittest.mock import patch, Mock
from django.core.cache import cache
from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APITestCase
from apps.accounts.models import Customer
from apps.catalog.models import Product, ServiceType
from apps.orders.models import Order, OrderItem
from apps.services.models import CustomerService, DomainAsset, DomainConnection, HostingAccount, ProviderConnection
from apps.services.management.commands.process_domain_connections import (
    MAX_CONNECTIONS_PER_RUN,
    bounded_connection_limit,
)
from apps.services.domain_connections import run_connection, process_connection, conflicts, parse_zone_file, apply_dns, record, claim_domain


class DomainConnectionTests(APITestCase):
    def setUp(self):
        cache.clear()
        self.user = Customer.objects.create_user(email='connect@example.com', password='test-pass-123', status='active')
        self.other = Customer.objects.create_user(email='other-connect@example.com', password='test-pass-123', status='active')
        kind, _ = ServiceType.objects.get_or_create(slug='web-hosting', defaults={'name': 'Web Hosting'})
        self.product = Product.objects.create(name='Connect basic', slug='connect-basic', service_type=kind, billing_type='recurring')
        self.service = CustomerService.objects.create(customer=self.user, product=self.product, status='active', expires_at=timezone.now()+timedelta(days=30))
        self.client.force_authenticate(self.user)
        self.path = '/api/v1/services/domain-connections/'

    def create_connection(self, **extra):
        data = {'domain_name': 'customer-example.com', 'plan': 'service:' + str(self.service.uuid), 'mode': 'external', 'services': 'both', **extra}
        return self.client.post(self.path, data, format='json')

    def test_background_domain_dns_batch_is_hard_capped(self):
        self.assertEqual(MAX_CONNECTIONS_PER_RUN, 1)
        self.assertEqual(bounded_connection_limit(1000), 1)
        self.assertEqual(bounded_connection_limit(1), 1)
        self.assertEqual(bounded_connection_limit(0), 1)

    def test_background_worker_never_checks_unverified_ownership(self):
        connection = self.claim()

        with patch('apps.services.domain_connections.public_dns') as lookup:
            run_connection(connection)

        lookup.assert_not_called()
        connection.refresh_from_db()
        self.assertEqual(connection.status, 'awaiting_ownership')
        self.assertIsNone(connection.next_check_at)

    def claim(self):
        response = self.create_connection()
        self.assertEqual(response.status_code, 201, response.data)
        return DomainConnection.objects.get(pk=response.data['id'])

    def test_create_does_not_claim_or_provision_before_unique_txt(self):
        connection = self.claim()
        self.assertIsNone(connection.next_check_at)
        self.assertFalse(DomainAsset.objects.exists())
        with patch('apps.services.domain_connections.public_dns', return_value=[]), patch('apps.services.domain_connections.prepare_hosting') as prepare:
            run_connection(connection)
        self.assertIsNone(connection.next_check_at)
        prepare.assert_not_called()
        self.assertFalse(DomainAsset.objects.exists())
        connection.refresh_from_db()
        self.assertEqual(connection.status, 'awaiting_ownership')
        self.assertTrue(connection.verification_token.startswith('techinn-'))

    def test_domain_can_be_verified_without_assigning_or_provisioning_a_plan(self):
        response = self.create_connection(plan='')
        self.assertEqual(response.status_code, 201, response.data)
        connection = DomainConnection.objects.get(pk=response.data['id'])
        self.assertIsNone(connection.customer_service_id)
        self.assertEqual(response.data['plan'], '')
        with patch(
            'apps.services.connection_views.public_dns',
            return_value=[connection.verification_token],
        ), patch('apps.services.domain_connections.prepare_hosting') as prepare:
            result = self.client.post(f'{self.path}{connection.pk}/verify/', {}, format='json')
        self.assertTrue(result.data['verified'])
        prepare.assert_not_called()
        connection.refresh_from_db()
        self.assertIsNotNone(connection.verified_at)
        self.assertEqual(connection.status, 'awaiting_plan')
        self.assertIsNone(connection.next_check_at)
        self.assertTrue(connection.checks['ownership'])
        self.assertFalse(DomainAsset.objects.exists())
        self.assertEqual(len(self.client.get(self.path).data['plans']), 1)

    def test_ownership_check_returns_dns_result_immediately_without_queueing(self):
        response = self.create_connection(plan='')
        self.assertEqual(response.status_code, 201, response.data)
        connection = DomainConnection.objects.get(pk=response.data['id'])

        with patch('apps.services.connection_views.public_dns', return_value=[]) as lookup:
            response = self.client.post(f'{self.path}{connection.pk}/verify/', {}, format='json')

        self.assertEqual(response.status_code, 200, response.data)
        self.assertFalse(response.data['verified'])
        self.assertIn('not visible yet', response.data['detail'])
        self.assertFalse(response.data['connection']['verified_at'])
        self.assertFalse(response.data['connection']['checks']['ownership'])
        connection.refresh_from_db()
        self.assertEqual(connection.status, 'awaiting_ownership')
        self.assertIsNone(connection.next_check_at)
        self.assertEqual(lookup.call_count, 1)
        self.assertFalse(DomainAsset.objects.exists())

    def test_immediate_ownership_dns_checks_are_rate_limited_per_customer(self):
        response = self.create_connection(plan='')
        connection = DomainConnection.objects.get(pk=response.data['id'])
        cache.clear()

        try:
            with patch('apps.services.connection_views.public_dns', return_value=[]):
                results = [
                    self.client.post(f'{self.path}{connection.pk}/verify/', {}, format='json')
                    for _ in range(7)
                ]
        finally:
            cache.clear()

        self.assertEqual([result.status_code for result in results[:6]], [200] * 6)
        self.assertEqual(results[6].status_code, 429)

    def test_manual_ownership_verification_is_available_without_automatic_window(self):
        connection = self.claim()

        with patch('apps.services.connection_views.public_dns', return_value=[]) as lookup:
            response = self.client.post(
                f'{self.path}{connection.pk}/verify/',
                {},
                format='json',
            )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.data['verified'])
        lookup.assert_called_once()
        connection.refresh_from_db()
        self.assertIsNone(connection.next_check_at)

    def test_successful_immediate_verification_returns_verified_result_and_waits_for_plan(self):
        response = self.create_connection(plan='')
        connection = DomainConnection.objects.get(pk=response.data['id'])

        with patch(
            'apps.services.connection_views.public_dns',
            return_value=[connection.verification_token],
        ):
            response = self.client.post(f'{self.path}{connection.pk}/verify/', {}, format='json')

        self.assertEqual(response.status_code, 200, response.data)
        self.assertTrue(response.data['verified'])
        self.assertIn('choose a paid plan', response.data['detail'])
        self.assertTrue(response.data['connection']['verified_at'])
        self.assertEqual(response.data['connection']['status'], 'awaiting_plan')
        connection.refresh_from_db()
        self.assertEqual(connection.status, 'awaiting_plan')
        self.assertIsNone(connection.next_check_at)

    def test_immediate_verification_of_planned_domain_queues_only_post_verification_setup(self):
        connection = self.claim()
        with patch(
            'apps.services.connection_views.public_dns',
            return_value=[connection.verification_token],
        ):
            response = self.client.post(f'{self.path}{connection.pk}/verify/', {}, format='json')

        self.assertEqual(response.status_code, 200, response.data)
        self.assertTrue(response.data['verified'])
        self.assertEqual(response.data['connection']['status'], 'preparing')
        connection.refresh_from_db()
        self.assertTrue(connection.next_check_at)
        self.assertEqual(connection.domain.domain_name, connection.domain_name)

    def test_verified_domain_can_later_be_assigned_an_available_paid_plan(self):
        response = self.create_connection(plan='')
        connection = DomainConnection.objects.get(pk=response.data['id'])
        connection.verified_at = timezone.now()
        connection.status = 'awaiting_plan'
        connection.checks = {'ownership': True}
        connection.save(update_fields=('verified_at', 'status', 'checks'))

        response = self.client.post(
            f'{self.path}{connection.pk}/select-plan/',
            {'plan': 'service:' + str(self.service.uuid)},
            format='json',
        )

        self.assertEqual(response.status_code, 202, response.data)
        connection.refresh_from_db()
        self.assertEqual(connection.customer_service_id, self.service.pk)
        self.assertEqual(connection.status, 'preparing')
        self.assertEqual(connection.domain.domain_name, connection.domain_name)
        self.assertEqual(connection.domain.customer_service_id, self.service.pk)
        self.assertIsNotNone(connection.next_check_at)

    def test_verified_domain_can_be_attached_to_a_plan_purchased_later(self):
        response = self.create_connection(plan='')
        connection = DomainConnection.objects.get(pk=response.data['id'])
        connection.verified_at = timezone.now()
        connection.status = 'awaiting_plan'
        connection.save(update_fields=('verified_at', 'status'))
        order = Order.objects.create(customer=self.user, order_number='CONNECT-LATER-TEST', status='paid')
        item = OrderItem.objects.create(
            order=order,
            product=self.product,
            description='Hosting purchased after domain verification',
            unit_price=3.5,
            subtotal=3.5,
            metadata={'period_months': 12},
        )

        response = self.client.post(
            f'{self.path}{connection.pk}/select-plan/',
            {'plan': f'order:{item.pk}'},
            format='json',
        )

        self.assertEqual(response.status_code, 202, response.data)
        connection.refresh_from_db()
        self.assertEqual(connection.customer_service.order_item_id, item.pk)
        self.assertEqual(item.customer_services.count(), 1)
        self.assertEqual(connection.status, 'preparing')

    def test_verified_domain_without_a_plan_can_be_removed_safely(self):
        response = self.create_connection(plan='')
        connection = DomainConnection.objects.get(pk=response.data['id'])
        connection.verified_at = timezone.now()
        connection.status = 'awaiting_plan'
        connection.save(update_fields=('verified_at', 'status'))

        self.assertEqual(self.client.delete(f'{self.path}{connection.pk}/').status_code, 204)
        self.assertFalse(DomainAsset.objects.exists())
        self.assertFalse(DomainConnection.objects.filter(pk=connection.pk).exists())

    def test_second_customer_cannot_verify_an_already_claimed_unassigned_domain(self):
        response = self.create_connection(plan='')
        connection = DomainConnection.objects.get(pk=response.data['id'])
        with patch(
            'apps.services.connection_views.public_dns',
            return_value=[connection.verification_token],
        ):
            verified = self.client.post(f'{self.path}{connection.pk}/verify/', {}, format='json')
        self.assertTrue(verified.data['verified'])

        self.client.force_authenticate(self.other)
        second = self.client.post(self.path, {
            'domain_name': connection.domain_name,
            'mode': 'external',
            'services': 'website',
        }, format='json')
        self.assertEqual(second.status_code, 201, second.data)
        other_connection = DomainConnection.objects.get(pk=second.data['id'])
        with patch(
            'apps.services.connection_views.public_dns',
            return_value=[other_connection.verification_token],
        ):
            result = self.client.post(f'{self.path}{other_connection.pk}/verify/', {}, format='json')

        other_connection.refresh_from_db()
        self.assertEqual(result.status_code, 400)
        self.assertIsNone(other_connection.verified_at)
        self.assertEqual(other_connection.status, 'awaiting_ownership')

    def test_paid_plan_and_ownership_scope_enforced(self):
        self.service.customer = self.other
        self.service.save()
        self.assertEqual(self.create_connection().status_code, 400)
        self.service.customer = self.user
        self.service.expires_at = timezone.now()-timedelta(days=1)
        self.service.save()
        self.assertEqual(self.create_connection().status_code, 400)
        self.assertEqual(self.client.get(self.path).data['plans'], [])

    def test_a_plan_cannot_be_reused_for_a_different_primary_domain(self):
        domain = DomainAsset.objects.create(domain_name='already.example.com', customer_service=self.service, status='active')
        HostingAccount.objects.create(customer_service=self.service, primary_domain=domain, status='active')
        self.assertEqual(self.create_connection().status_code, 400)

    def test_other_customer_cannot_read_approve_check_or_remove_connection(self):
        connection = self.claim()
        self.client.force_authenticate(self.other)
        for path in ('check/', 'approve/'):
            self.assertEqual(self.client.post(f'{self.path}{connection.pk}/{path}', {'confirm': True}, format='json').status_code, 404)
        self.assertEqual(self.client.get(f'{self.path}{connection.pk}/').status_code, 404)
        self.assertEqual(self.client.delete(f'{self.path}{connection.pk}/').status_code, 404)

    def test_unverified_claim_does_not_block_a_different_customer(self):
        self.claim()
        self.client.force_authenticate(self.other)
        second = CustomerService.objects.create(customer=self.other, product=self.product, status='active', expires_at=self.service.expires_at)
        response = self.client.post(self.path, {'domain_name':'customer-example.com','plan':'service:'+str(second.uuid),'mode':'external','services':'website'}, format='json')
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(DomainConnection.objects.count(), 2)
        self.assertFalse(DomainAsset.objects.exists())

    def test_verified_owner_cannot_take_over_existing_customer_domain(self):
        connection = self.claim()
        other = CustomerService.objects.create(customer=self.other, product=self.product, status='active', expires_at=self.service.expires_at)
        DomainAsset.objects.create(customer_service=other, domain_name=connection.domain_name, status='active')
        with patch('apps.services.connection_views.public_dns', return_value=[connection.verification_token]), patch('apps.services.domain_connections.prepare_hosting') as prepare:
            response = self.client.post(f'{self.path}{connection.pk}/verify/', {}, format='json')
        prepare.assert_not_called()
        self.assertEqual(response.status_code, 400)
        connection.refresh_from_db()
        self.assertIsNone(connection.verified_at)

    def test_dns_approval_requires_verified_ownership_and_prepared_records(self):
        connection = self.claim()
        self.assertEqual(self.client.post(f'{self.path}{connection.pk}/approve/', {'confirm':True}, format='json').status_code, 400)
        connection.verified_at=timezone.now();connection.required_records=[record('A',connection.domain_name,'203.0.113.10')];connection.save()
        self.assertEqual(self.client.post(f'{self.path}{connection.pk}/approve/', {}, format='json').status_code, 400)
        response = self.client.post(f'{self.path}{connection.pk}/approve/', {'confirm': True}, format='json')
        self.assertEqual(response.status_code, 202)
        connection.refresh_from_db();self.assertIsNotNone(connection.review_approved_at)

    def test_customer_can_cancel_unverified_connection_without_losing_paid_plan(self):
        connection=self.claim()
        self.assertEqual(self.client.delete(f'{self.path}{connection.pk}/').status_code, 204)
        self.service.refresh_from_db()
        self.assertEqual(self.service.status,'active')
        self.assertEqual(len(self.client.get(self.path).data['plans']),1)

    def test_verified_connection_cannot_be_removed_by_cancel_button(self):
        connection=self.claim();connection.verified_at=timezone.now();connection.save()
        self.assertEqual(self.client.delete(f'{self.path}{connection.pk}/').status_code,400)

    def test_public_ip_is_not_ownership_proof(self):
        connection=self.claim()
        with patch('apps.services.connection_views.public_dns',return_value=['203.0.113.10']):
            response=self.client.post(f'{self.path}{connection.pk}/verify/',{},format='json')
        self.assertFalse(response.data['verified'])
        self.assertIsNone(connection.verified_at)

    def test_pending_cloudflare_zone_is_not_proof_of_ownership(self):
        provider=ProviderConnection.objects.create(customer=self.user,provider='cloudflare',scope='customer',name='Mine',status='active',credentials=json.dumps({'api_token':'fake'}))
        response=self.create_connection(mode='cloudflare',connection_id=provider.pk,zone_id='a'*32)
        connection=DomainConnection.objects.get(pk=response.data['id'])
        with patch('apps.services.connection_views.CloudflareClient.get_zone',return_value={'name':connection.domain_name,'status':'pending','name_servers':['ns.cloudflare.com']}), patch('apps.services.connection_views.public_dns',return_value=[]),patch('apps.services.domain_connections.prepare_hosting') as prepare:
            response=self.client.post(f'{self.path}{connection.pk}/verify/',{},format='json')
        prepare.assert_not_called();self.assertFalse(response.data['verified']);self.assertIsNone(connection.verified_at)

    def test_email_only_plan_cannot_enable_website(self):
        kind,_=ServiceType.objects.get_or_create(slug='email-hosting',defaults={'name':'Email Hosting'})
        self.product.service_type=kind;self.product.save()
        self.assertEqual(self.create_connection().status_code,400)
        self.assertEqual(self.create_connection(services='email').status_code,201)

    def test_txt_verified_setup_prepares_hosting_but_waits_for_dns_approval(self):
        connection=self.claim()
        claim_domain(connection)
        panel={'username':'owner','linux_username':'owner','disk_mb':2048,'mailboxes':1000,'records':[{'name':'default._domainkey.'+connection.domain_name,'content':'v=DKIM1; p=publickey'}]}
        with patch('apps.services.domain_connections.snapshot_public_dns',return_value=[]),patch('apps.services.domain_connections.prepare_hosting',return_value=panel),patch('apps.services.domain_connections.origin_ip',return_value='203.0.113.10'),patch('apps.services.domain_connections.set_shared_hosting_disk_quota'),patch('apps.services.domain_connections.apply_dns') as apply:
            run_connection(connection)
        self.assertEqual(connection.status,'awaiting_review',connection.last_error)
        self.assertTrue(connection.verified_at)
        self.assertEqual(connection.customer_service.hosting_account.status,'active')
        self.assertTrue(any(r['type']=='MX' for r in connection.required_records))
        apply.assert_not_called()

    def test_dns_changes_preserve_unrelated_txt_and_email_when_website_only(self):
        connection=self.claim();claim_domain(connection)
        provider=ProviderConnection.objects.create(provider='cloudflare',scope='global',name='TechInn',status='active',credentials='{}')
        connection.provider_connection=provider;connection.external_zone_id='a'*32
        connection.required_records=[record('A',connection.domain_name,'203.0.113.10')]
        current=[dict(record('A',connection.domain_name,'203.0.113.20'),id='old'),dict(record('MX',connection.domain_name,'old-mail.example.com',10),id='mail'),dict(record('TXT',connection.domain_name,'google-site-verification=keep'),id='txt')]
        client=Mock();client.list_dns_records.side_effect=[current, [current[1], current[2],dict(connection.required_records[0],id='new')]];client.update_dns_record.return_value=dict(connection.required_records[0],id='old')
        apply_dns(connection,client,'secret')
        client.delete_dns_record.assert_not_called()
        client.update_dns_record.assert_called_once_with('secret','a'*32,'old',connection.required_records[0])
        self.assertTrue(connection.dns_applied_at)

    def test_spf_changes_do_not_remove_unrelated_txt(self):
        self.assertFalse(conflicts(record('TXT','example.com','google-site-verification=keep'), record('TXT','example.com','v=spf1 ip4:203.0.113.10 ~all')))
        self.assertTrue(conflicts(record('TXT','example.com','v=spf1 include:old ~all'), record('TXT','example.com','v=spf1 ip4:203.0.113.10 ~all')))

    def test_zone_import_parses_chunked_txt_and_rejects_include(self):
        rows=parse_zone_file('$ORIGIN example.com.\n@ 300 IN TXT "one" "two"\n@ 300 IN MX 10 mail.example.com.\n', 'example.com')
        self.assertEqual(rows[0]['content'],'onetwo')
        self.assertEqual(rows[1]['priority'],10)
        from rest_framework.exceptions import ValidationError
        with self.assertRaises(ValidationError):
            parse_zone_file('$INCLUDE /etc/passwd','example.com')

    def test_worker_does_not_overwrite_concurrent_user_approval(self):
        connection=self.claim()
        claim_domain(connection)
        DomainConnection.objects.filter(pk=connection.pk).update(review_approved_at=timezone.now())
        with patch('apps.services.domain_connections.public_dns',return_value=[]):
            run_connection(connection)
        connection.refresh_from_db();self.assertIsNotNone(connection.review_approved_at)

    def test_new_paid_order_can_be_selected_once_and_uses_its_billing_period(self):
        order=Order.objects.create(customer=self.user,order_number='CONNECT-PAID-TEST',status='paid')
        item=OrderItem.objects.create(order=order,product=self.product,description='Hosting',unit_price=3.5,subtotal=3.5,metadata={'period_months':12})
        response=self.create_connection(plan=f'order:{item.pk}')
        self.assertEqual(response.status_code,201,response.data)
        connection=DomainConnection.objects.get(pk=response.data['id'])
        self.assertGreater(connection.customer_service.expires_at,timezone.now()+timedelta(days=360))
        self.assertEqual(item.customer_services.count(),1)
        response=self.create_connection(domain_name='second-customer.com',plan=f'order:{item.pk}')
        self.assertEqual(response.status_code,400)
        self.assertEqual(item.customer_services.count(),1)

    def test_unpaid_order_cannot_provision_hosting(self):
        order=Order.objects.create(customer=self.user,order_number='CONNECT-UNPAID-TEST',status='awaiting_payment')
        item=OrderItem.objects.create(order=order,product=self.product,description='Hosting',unit_price=3.5,subtotal=3.5,metadata={'period_months':1})
        self.assertEqual(self.create_connection(plan=f'order:{item.pk}').status_code,400)
        self.assertFalse(item.customer_services.exists())

    def test_mixed_old_and_new_addresses_do_not_pass_readiness(self):
        from apps.services.domain_connections import check_records
        connection=self.claim();connection.required_records=[record('A',connection.domain_name,'203.0.113.10')]
        with patch('apps.services.domain_connections.public_dns',side_effect=[['203.0.113.10','203.0.113.20'],[]]):
            rows=check_records(connection)
        self.assertFalse(rows[0]['ready'])
