from django.db.models import Q
from rest_framework.exceptions import PermissionDenied

from apps.services.models import CustomerService, ServiceMember


def accessible_services_for(customer):
    return CustomerService.objects.filter(
        Q(customer=customer) | Q(members__customer=customer)
    ).distinct()


def require_service_permission(customer, service, permission):
    if service.customer_id == customer.id:
        return
    membership = ServiceMember.objects.filter(
        customer_service=service,
        customer=customer,
    ).first()
    if membership and getattr(membership, permission, False):
        return
    raise PermissionDenied("You do not have permission to manage this service.")
