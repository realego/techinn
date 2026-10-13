# TechInn backend

This directory contains a Django REST API for the hosting-commerce backend.
The Next.js site remains a static export, and its existing dashboard now
consumes this API. The normalized schema guide supplied for this task is saved
at [`docs/hosting-company-database-schema.md`](docs/hosting-company-database-schema.md).

## Structure

```text
backend/
├── apps/
│   ├── accounts/       Customer accounts, registration and JWT auth
│   ├── catalog/        Service types, products, prices, features and add-ons
│   ├── orders/         Orders and immutable order-line price snapshots
│   ├── billing/        Invoices, payment providers, payments and attempts
│   ├── services/       Customer services and provisioning instances
│   ├── notifications/  Email templates, queue and delivery logs
│   ├── automation/     Rules and scheduled executions
│   └── core/           System events and application settings
├── techinn_api/        Django settings, URLs and server entry points
├── docs/               The original database design instructions
├── manage.py
└── requirements.txt
```

The API covers registration, JWT authentication, customer profiles, public
catalog reads, authenticated order creation/list/detail, Paynow checkout and
payment status, and a customer-scoped service dashboard. Hosting allocations, mailbox/DNS
management, service-member permissions, encrypted Cloudflare connections,
auditing, and a Cloudflare DNS provisioning worker are included. Registrar
operations, cPanel/CyberPanel account provisioning, and mail-server
provisioning still need provider credentials and their respective adapters.

## Run locally

Python 3.11 or newer is recommended. From this directory:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
export DJANGO_DEBUG=true
export DJANGO_SECRET_KEY=local-development-only-key-at-least-32-characters
export DATA_ENCRYPTION_KEY="$(python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())')"
python manage.py makemigrations accounts catalog orders services billing notifications automation core
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

For local development, the database defaults to SQLite and the API is available
at `http://127.0.0.1:8000/api/v1/`. Configure variables from `.env.example` in
your shell or hosting control panel; Django does not load `.env` files itself.
The Django admin is at `/admin/`.

## API

| Method | Endpoint | Access |
| --- | --- | --- |
| `GET` | `/api/v1/health/` | Public |
| `POST` | `/api/v1/auth/register/` | Public |
| `POST` | `/api/v1/auth/token/` | Public; returns access and refresh JWTs |
| `POST` | `/api/v1/auth/token/refresh/` | Public |
| `GET`, `PATCH` | `/api/v1/auth/me/` | Customer JWT |
| `POST` | `/api/v1/auth/password/` | Customer JWT; verifies current password |
| `POST` | `/api/v1/auth/password/reset/` | Public; emails a short-lived password reset link |
| `POST` | `/api/v1/auth/password/reset/confirm/` | Public; validates a one-time password reset token |
| `POST` | `/api/v1/auth/google/` | Public; verifies Google ID token and returns customer JWTs |
| `GET` | `/api/v1/billing/invoices/` | Customer JWT; only the signed-in customer's invoices |
| `POST` | `/api/v1/billing/checkout/` | Customer JWT; creates an order and starts a Paynow payment |
| `POST` | `/api/v1/billing/payments/{uuid}/poll/` | Owning customer JWT; safely checks Paynow status |
| `POST` | `/api/v1/billing/payments/paynow/result/` | Public; Paynow callback, accepted only with a valid signature |
| `GET` | `/api/v1/catalog/service-types/` | Public |
| `GET` | `/api/v1/catalog/service-types/{slug}/` | Public |
| `GET` | `/api/v1/catalog/products/` | Public; optional `?service_type=web-hosting` |
| `GET` | `/api/v1/catalog/products/{slug}/` | Public |
| `GET`, `POST` | `/api/v1/orders/` | Customer JWT |
| `GET` | `/api/v1/orders/{uuid}/` | Owning customer JWT |
| `GET` | `/api/v1/services/dashboard/` | Customer or service member JWT |
| `GET` | `/api/v1/services/domains/` | Customer or service member JWT |
| `GET` | `/api/v1/services/domains/search/?domain=example.com` | Public, rate-limited; DNS/WHOIS/HTTP estimate |
| `GET` | `/api/v1/services/hosting-accounts/` | Customer or service member JWT |
| `GET` | `/api/v1/services/dns-zones/` | Customer or service member JWT |
| `POST`, `PATCH`, `DELETE` | `/api/v1/services/dns-records/` | Owner or member with DNS permission |
| `GET`, `POST`, `PATCH`, `DELETE` | `/api/v1/services/mailboxes/` | Owner or member with email permission |
| `GET`, `POST` | `/api/v1/services/mailboxes/{id}/access/` | Owner or member with email permission |
| `GET`, `POST`, `DELETE` | `/api/v1/services/provider-connections/` | Customer JWT; personal Cloudflare token |
| `POST` | `/api/v1/services/provider-connections/{id}/verify/` | Connection owner |
| `GET` | `/api/v1/services/provider-connections/{id}/zones/` | Verified connection owner |
| `GET` | `/api/v1/services/cloudflare/zones/` | Customer JWT; returns only owned matching domains |
| `POST` | `/api/v1/services/cloudflare/zones/link/` | Domain owner or member with DNS permission |
| `POST` | `/api/v1/services/dns-zones/{id}/sync/` | Owner or member with DNS permission |
| `GET` | `/api/v1/services/provisioning-actions/` | Customer or service member JWT |
| `GET` | `/api/v1/services/audit-events/` | Customer or service member JWT |
| `GET`, `POST` | `/api/v1/services/{service-uuid}/members/` | Service owner |
| `DELETE` | `/api/v1/services/{service-uuid}/members/{id}/` | Service owner |

`.co.zw` availability queries ZISPA's `domain_lookup.pl` endpoint and reports available only when ZISPA returns “is available for registration”; registered-domain details are reported as taken. Lookup failures or unrecognized responses remain unconfirmed. Other supported extensions use DNS/WHOIS/HTTP estimates. Availability is not a reservation.

After a paid domain order, `process_domain_registrations` creates or reuses its Cloudflare zone, stores the assigned Cloudflare nameservers, and submits complete `.co.zw` registrant details to the ZISPA bridge. It sends physical and postal addresses, nameservers, and their IP addresses; IPs are taken from `ZISPA_DEFAULT_NAMESERVERS`, entered for custom nameservers, or resolved from DNS. A submitted request remains pending until registration is confirmed. Other domain extensions get a Cloudflare zone but require a registrar adapter/manual registration.

Live submission is separately gated by `ZISPA_SUBMISSIONS_ENABLED` (default false).
`ZISPA_DRAFT_API_KEY` creates registration drafts; `ZISPA_API_KEY` remains the
separate send key used to submit them. Keep both `ZISPA_SUBMISSIONS_ENABLED` and
`ZISPA_AUTO_SEND` false until real submissions are authorized. With the
release gate off, `.co.zw` registrations queue for review without provider calls.
See [domain-registration-rollout.md](docs/domain-registration-rollout.md) for
retry behavior, ambiguous-send handling, and the activation checklist.

Domain checkout requires an owner name and physical address. The postal address can be the physical address or a separate address. Custom nameservers require public IP addresses unless they already match a nameserver configured in `ZISPA_DEFAULT_NAMESERVERS`.

Create an order with product price IDs, not client-supplied prices:

```json
{
  "currency": "USD",
  "items": [
    {
      "price_id": 1,
      "quantity": 1,
      "metadata": {"domain": "example.co.zw"}
    }
  ]
}
```

The API loads active catalog prices from the database, computes totals on the
server, and snapshots price and billing interval into the order. Customers can
only list or retrieve their own orders. Catalog entries are maintained in the
Django admin and inactive products/prices are not exposed or orderable.

The storefront catalog migration seeds the current shop items and prices,
including supported add-ons. Checkout accepts storefront product/option IDs but
calculates all amounts from active database catalog prices. The browser's
displayed total is only compared with the server total to detect stale prices;
it is never used as the payment amount. If prices change in the admin, update
the storefront display prices in `config/shop-products.ts` in the same release
so customers see the same amount they are charged.

Paynow checkout is available to signed-in customers. EcoCash and OneMoney start
mobile express requests; card payments continue through Paynow's hosted payment
page. Payment initiation and status checks are recorded without storing raw
provider responses or exposing the private poll URL to the browser. A timeout
or network failure leaves the payment processing and does not trigger a second
charge when the same checkout request is retried. Only a Paynow-confirmed
`Paid` status marks the order paid. The signed callback is an additional status
path; customers can also poll from the checkout page.
Payment confirmation does not itself register a domain or provision hosting,
email, or website services; those operations still require their separate
provider workflows.

## Hosting dashboard and provider operations

The dashboard groups each customer's services, domains, DNS records, hosting
accounts, resource allocations/usage, mailboxes, and provider-connection
statuses. Service owners can grant existing customer accounts role-based
service permissions; `admin` and `technical` role defaults are explicitly
scoped to domains, DNS, hosting, email, and billing flags. Mailbox creation,
quota changes, deletion, and DNS record changes are recorded and queued rather
than executed inside an HTTP request. Mailbox passwords are generated by the
mail provider adapter, not accepted or stored by this API. Per-mailbox access
grants are restricted to members already invited to the service.

DNS zones are created in the staff admin when a domain service is provisioned.
A customer may connect their own Cloudflare API token through the API; tokens
are encrypted at rest with `DATA_ENCRYPTION_KEY`, never included in API
responses, and can be revoked. Cloudflare tokens should be restricted to the
necessary zones with `Zone:Read` and `DNS:Edit` permissions. After verification,
the owner can link an exact matching domain zone and import its DNS records.
TechInn-managed Cloudflare access is configured out-of-band with
`CLOUDFLARE_API_TOKEN` and `python manage.py configure_cloudflare --verify`;
the command stores the credential encrypted and does not print it.

CyberPanel is configured from `CYBERPANEL_API_URL`, `CYBERPANEL_API_USER`, and
`CYBERPANEL_API_PASSWORD` with `python manage.py configure_cyberpanel`. The
connection is verified with CyberPanel's read-only package-list endpoint and
stored encrypted. Use the panel hostname with a valid TLS certificate. Run
`python manage.py sync_cyberpanel_services` to import active sites whose panel
owner email matches a TechInn customer. In production the
`techinn-my-cyberpanel-import.timer` refreshes these links every ten minutes.
`python manage.py configure_cyberpanel_packages` creates the Basic 2 GB, Growth
10 GB, and Business 25 GB packages from the `CYBERPANEL_PACKAGE_WEB_*` names.
The sync imports package storage usage and active mailbox addresses into the
customer dashboard, without copying panel passwords.
Paid web-hosting orders are provisioned by `process_cyberpanel_hosting` only
when the order selects an active domain owned by the same customer. Mailbox
create and delete requests use CyberPanel's local mail utilities; generated
mailbox access details are sent to the customer and never stored in the API.
Paid email plans link to an existing CyberPanel site on the selected active
domain, and mailbox create/delete requests provision there. Paid price rows
carry their term in `period_months`; checkout snapshots that term onto each
order item, and the service stores its calculated `expires_at` and
`next_due_at`. Renewals extend the same service from the later of now or its
current expiry. `process_expired_services` reads those stored expiry dates
every five minutes, suspends web sites in CyberPanel, and locks email mailbox
passwords while preserving mailbox data. A paid email renewal restores
mailboxes with new temporary passwords sent to the account owner. The import,
hosting, provisioning, and expiry timers are in
`deploy/techinn-my-*.{service,timer}`. Webmail links use each site's `/webmail` path.
Disk-space values are displayed as package allocations; this VPS currently has
filesystem quotas disabled, so CyberPanel does not enforce those disk caps at
the filesystem layer.

Run `python manage.py process_domain_registrations --limit 25` periodically
after payment callbacks are active. In production, use a systemd timer so paid
orders are processed even if no customer is visiting the site. The example
units are in `deploy/techinn-my-domain-provision.{service,timer}`; review their
user, project path, virtualenv, and environment-file paths before installing
them under `/etc/systemd/system`, then run `systemctl daemon-reload`,
`systemctl enable --now techinn-my-domain-provision.timer`. Command output and
errors are available with `journalctl -u techinn-my-domain-provision.service`.

The worker processes DNS actions only. Run it periodically from a protected
worker/cron environment after database migrations and provider configuration:

```bash
python manage.py process_provisioning --limit 50
```

Mailbox quota changes remain pending until CyberPanel quota updates are
implemented. Worker failures are marked failed with sanitized error messages;
operators should investigate before retrying an action. Provider credentials
must never be written into action payloads, application logs, or support tickets.
Domain registration remains separately gated by `ZISPA_SUBMISSIONS_ENABLED`
and `ZISPA_AUTO_SEND`; this CyberPanel connection does not submit registrations.

The `/dashboard/` customer portal consumes these APIs; it is no longer the
original sample chart/table dashboard. It shows service and domain renewals,
invoice balances, provisioning activity, hosting resource usage, profile
editing, and password changes. Old dashboard and sign-in links redirect to
their clean `/dashboard/` and `/login/` routes. Traffic analytics and
payment-link processing are not integrated yet; the portal identifies these
as unavailable rather than presenting sample data.
Set `NEXT_PUBLIC_API_BASE_URL` and `NEXT_PUBLIC_GOOGLE_CLIENT_ID` in the
Next.js build environment. Set the matching `GOOGLE_OAUTH_CLIENT_ID` in Django
and add `https://my.techinn.co.zw` as an authorized JavaScript origin in the
Google Cloud web OAuth client. The Google Identity Services credential flow
does not use a redirect URI. Configure `EMAIL_HOST`, `EMAIL_PORT`,
`EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`, `EMAIL_USE_TLS` or `EMAIL_USE_SSL`,
and `DEFAULT_FROM_EMAIL` to enable password reset emails. For the current
static hosting setup, configure the web server to proxy `/api/v1/` to Django
before publishing the updated frontend.
Without a running API and these production credentials, login, Google
sign-in, password-reset email delivery, and dashboard requests are unavailable.
Paynow checkout is also unavailable until the backend receives `PAYNOW_ID`
and `PAYNOW_KEY`; `PAYNOW_EMAIL` is an optional fallback payer email. Configure
these only in the backend environment or a secrets manager; never place them
in the frontend or source control. `PAYNOW_RESULT_URL` may be left empty when the API is reached through
a correctly configured HTTPS reverse proxy; otherwise set it to the public
HTTPS URL for `/api/v1/billing/payments/paynow/result/`. The default return
URL points to `/checkout/`; `PAYNOW_RETURN_URL` can override it. Do not reuse
legacy Paynow callback URLs.

## MySQL/MariaDB and production

The supplied schema is MySQL-oriented. Local SQLite is only a convenience;
set `DB_ENGINE=mysql` plus `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_HOST`, and
`DB_PORT` for MySQL/MariaDB. Install the dependencies in `requirements.txt`
and run migrations against the target database before serving requests.

Before production, set `DJANGO_DEBUG=false`, provide a unique strong
`DJANGO_SECRET_KEY`, restrict `DJANGO_ALLOWED_HOSTS` to the API host, and set
`CORS_ALLOWED_ORIGINS` to the actual frontend origins. Set a stable
`DATA_ENCRYPTION_KEY` generated with `Fernet.generate_key()` and back it up
securely; losing it makes stored provider credentials unreadable. Keep payment
credentials in environment variables or a secrets manager—do not put secrets
in provider configuration JSON or the database settings table. Deploy this
Django app as an application/service with Python support; copying it into the
static `public_html` export will not run the API.

Run the API tests with:

```bash
python manage.py test
```
