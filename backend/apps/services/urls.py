from django.urls import include, path
from rest_framework.routers import DefaultRouter

from apps.services.panel_access import HostingFileManagerView

from apps.services.views import (
    DNSRecordViewSet,
    DNSZoneViewSet,
    CloudflareZoneLinkView,
    CloudflareZoneListView,
    DashboardView,
    DomainAvailabilityView,
    CloudflareZoneConnectView,
    DomainListView,
    HostingPrimaryDomainView,
    HostingAccountListView,
    MailboxViewSet,
    MailboxAccessDetailView,
    MailboxAccessListCreateView,
    ProvisioningActionListView,
    ProviderConnectionViewSet,
    ServiceAuditEventListView,
    ServiceMemberDetailView,
    ServiceMemberListCreateView,
)


router = DefaultRouter()
router.register("dns-records", DNSRecordViewSet, basename="dns-record")
router.register("dns-zones", DNSZoneViewSet, basename="dns-zone")
router.register("mailboxes", MailboxViewSet, basename="mailbox")
router.register("provider-connections", ProviderConnectionViewSet, basename="provider-connection")

urlpatterns = [
    path("hosting-accounts/<int:account_id>/file-manager/", HostingFileManagerView.as_view(), name="hosting-file-manager"),
    path("dashboard/", DashboardView.as_view(), name="service-dashboard"),
    path("domains/", DomainListView.as_view(), name="customer-domains"),
    path("domains/search/", DomainAvailabilityView.as_view(), name="domain-availability"),
    path("hosting-accounts/", HostingAccountListView.as_view(), name="hosting-accounts"),
    path(
        "hosting-accounts/<int:account_id>/primary-domain/",
        HostingPrimaryDomainView.as_view(),
        name="hosting-primary-domain",
    ),
    path("provisioning-actions/", ProvisioningActionListView.as_view(), name="provisioning-actions"),
    path("audit-events/", ServiceAuditEventListView.as_view(), name="service-audit-events"),
    path("cloudflare/zones/link/", CloudflareZoneLinkView.as_view(), name="cloudflare-zone-link"),
    path("cloudflare/zones/connect/", CloudflareZoneConnectView.as_view(), name="cloudflare-zone-connect"),
    path("cloudflare/zones/", CloudflareZoneListView.as_view(), name="cloudflare-zone-list"),
    path(
        "<uuid:service_uuid>/members/",
        ServiceMemberListCreateView.as_view(),
        name="service-members",
    ),
    path(
        "<uuid:service_uuid>/members/<int:pk>/",
        ServiceMemberDetailView.as_view(),
        name="service-member-detail",
    ),
    path(
        "mailboxes/<int:mailbox_id>/access/",
        MailboxAccessListCreateView.as_view(),
        name="mailbox-access-list",
    ),
    path(
        "mailboxes/<int:mailbox_id>/access/<int:pk>/",
        MailboxAccessDetailView.as_view(),
        name="mailbox-access-detail",
    ),
    path("", include(router.urls)),
]
