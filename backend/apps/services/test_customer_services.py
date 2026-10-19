from datetime import timedelta
from django.utils import timezone
from rest_framework.test import APITestCase
from apps.accounts.models import Customer
from apps.catalog.models import Product
from apps.orders.models import Order, OrderItem
from apps.services.models import CustomerService, ServiceInstance
from apps.services.customer_services import sync_paid_services, service_dashboard_links


class CustomerServicesTests(APITestCase):
    def setUp(self):
        self.user = Customer.objects.create_user(email='project-test@example.com',password='testing123')
        self.product = Product.objects.get(slug='chatbot-basic')
        self.order = Order.objects.create(customer=self.user,order_number='PROJECT-TEST',status='paid')
        self.item = OrderItem.objects.create(order=self.order,product=self.product,description='Chatbot',unit_price=80,subtotal=80)

    def test_paid_projects_are_created_once_and_await_real_setup(self):
        self.assertEqual(sync_paid_services(self.order),1)
        self.assertEqual(sync_paid_services(self.order),0)
        service=CustomerService.objects.get(order_item=self.item)
        self.assertEqual(service.status,'pending')
        self.assertFalse(service.auto_renew)

    def test_unpaid_projects_are_not_activated(self):
        self.order.status='awaiting_payment';self.order.save()
        self.assertEqual(sync_paid_services(self.order),0)
        self.assertFalse(CustomerService.objects.exists())

    def test_links_are_scoped_and_private_instance_data_is_not_exposed(self):
        sync_paid_services(self.order)
        service=CustomerService.objects.get(order_item=self.item);service.status='active';service.save()
        ServiceInstance.objects.create(customer_service=service,instance_type='chatbot',display_name='Chatbot dashboard',dashboard_url='https://chat.example.com/login',data={'password':'private-value','api_key':'secret'})
        self.client.force_authenticate(self.user)
        response=self.client.get('/api/v1/services/dashboard/')
        row=response.data['services'][0]
        self.assertEqual(row['service_type'],'chatbot-development')
        self.assertEqual(row['dashboards'],[{'name':'Chatbot dashboard','url':'https://chat.example.com/login'}])
        self.assertNotIn('private-value',str(response.data))
        other=Customer.objects.create_user(email='other-project-test@example.com',password='testing123')
        self.client.force_authenticate(other)
        self.assertEqual(self.client.get('/api/v1/services/dashboard/').data['services'],[])
        self.assertEqual(service_dashboard_links(service,False),[])

    def test_suspended_expired_and_unsafe_links_are_not_offered(self):
        sync_paid_services(self.order);service=CustomerService.objects.get(order_item=self.item)
        instance=ServiceInstance.objects.create(customer_service=service,instance_type='chatbot',dashboard_url='https://chat.example.com/login')
        self.assertEqual(service_dashboard_links(service,True),[])
        service.status='active';service.expires_at=timezone.now()-timedelta(days=1)
        self.assertEqual(service_dashboard_links(service,True),[])
        service.expires_at=None;instance.dashboard_url='javascript:alert(1)';instance.save()
        self.assertEqual(service_dashboard_links(service,True),[])

    def test_quantity_and_repeated_payment_sync_do_not_duplicate_projects(self):
        self.item.quantity=2;self.item.save()
        self.assertEqual(sync_paid_services(self.order),2)
        self.assertEqual(sync_paid_services(self.order),0)
        self.assertEqual(CustomerService.objects.filter(order_item=self.item).count(),2)
