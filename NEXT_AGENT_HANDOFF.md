# TechInn Hosting — coding handoff

## Product and working style

This repository powers the TechInn Hosting customer portal at `my.techinn.co.zw`. The user is building a web hosting company and wants the existing Launch UI / shadcn blocks used as the visual foundation. Preserve the established look and improve it in small, reviewable steps. Orange is the brand accent; controls and outlines with the same orange treatment should read as one task group. Avoid adding generic card piles or unnecessary mobile padding.

The user wants implementation, not another plan, when they say “go”, “finish”, or give a direct edit request. Keep communicating briefly while working. Do not send ZISPA registration requests: prior instructions explicitly said not to submit them.

## Repository and deployment

- App: Next.js static export, React, Tailwind, shadcn UI components.
- API: Django REST Framework under `backend/`.
- CyberPanel adapter and async service jobs: `backend/apps/services/providers/cyberpanel.py` and `backend/apps/services/management/commands/`.
- Main customer dashboard: `components/customer-dashboard.tsx`.
- Shop/domain UI: `components/shop-experience.tsx`.
- Shared inputs/selects: `components/ui/input.tsx`, `components/ui/select.tsx`.
- Static deployment: run `npm run deploy:production` as root. It builds the export, backs up, and syncs `out/` to both `/home/techinn.co.zw/public_html/` (`techinn.co.zw`) and `/home/my.techinn.co.zw/public_html/` (`my.techinn.co.zw`), preserving each document root's owner. Never deploy only one hostname.
- API service: `techinn-my-api.service`; scheduled expiry worker: `techinn-my-expired-services.timer`.
- Backend checks: from `backend/`, use `./.venv/bin/python manage.py check`, `makemigrations --check --dry-run`, and `compileall`.
- Never print or copy secrets from `.env` into code, logs, handoff docs, or chat.

## Current implementation

- User dashboard provides nameserver, DNS-record, and per-domain mailbox tables. DNS records support CRUD and Cloudflare sync; mailbox controls include webmail links, reset, delete, and retry after setup errors.
- On phones, tables are collapsed behind toggles; domain selection is expandable. Email and DNS forms use orange grouped controls and reduced container padding.
- New mailboxes require a customer-chosen password (minimum 8 characters). The password is Fernet-encrypted in the queued action, decrypted only by the worker, and removed from the action after processing. It is never sent by email. Reset-password still issues a temporary password by email.
- A failed mailbox row displays the provider error and allows retry with a newly chosen password. The dashboard polls while mailbox creation is pending.
- Paid web hosting provisioning calls CyberPanel `createWebsite`, which creates the CyberPanel website owner as part of a paid hosting activation. A portal-only registration does not create a free standalone CyberPanel panel user.
- Catalog price periods are stored in the database and copied to services. An expiry timer suspends paid web hosting in CyberPanel and disables mailbox access at expiry; renewal reactivates services.
- DNS/email and CyberPanel credentials are encrypted at rest. Cloudflare/DNS/mailbox actions are queued, not executed synchronously from the browser.

## Latest user request / completed changes

The user asked to remove provider branding from dashboard copy, make mailbox allocation visibly use MB/GB units, shorten long mailbox-domain suffixes, fix the recurring mailbox create error, and copy the working nameserver refresh behavior from `/home/techinn.online`.

- Dashboard creation now uses the supported local `createEmail` command, then independently verifies the mailbox with `listEmailsJson`, matching `techinn.online`'s proven flow. The child process explicitly gets `DJANGO_SETTINGS_MODULE=CyberCP.settings`.
- Mailbox allocation is labeled “Mailbox disk allocation”, has MB/GB selection, and converts GB to MB before calling the existing validated API.
- The `@domain` suffix is a truncated flex segment with the full domain available on hover/focus; error text replaces provider branding with “mail server”. Dashboard API emits a generic hosting-server label.
- DNS sync fetches the live Cloudflare zone nameservers as well as DNS records, updates both `DNSZone.nameservers` and `DomainAsset.nameservers`, and returns the nameserver list. The customer table now describes these as assigned nameservers, rather than claiming to read registrar delegation.
- Prior improvements from the previous handoff (orange field grouping, bottom status feedback, password visibility, pending refresh and failed-mailbox retry) remain in place.

The historic failed mailbox action cannot be repaired from stored data: the earlier worker discarded the actionable provider response. After deploy, the customer can retry it with a new password; the supported CLI flow and independent confirmation should provide a specific failure if it still cannot create. Never report customer addresses or passwords in handoff/logs.

## 2026-10-18: password OTP and dual-host deployment

- Login, registration, and public password-reset errors use orange readable alert panels with a light outline in dark mode instead of red text on the black surface.
- Account password changes in the dashboard now request a six-digit OTP by email, then confirm the OTP with the new password. Successful confirmation revokes sessions and returns the customer to sign-in.
- Mailbox password resets use the same account-email OTP gate before queuing the chosen mailbox password. Use `request-password-reset` followed by `reset-password` with `otp` and `password`.
- Google-linked accounts with no usable password can still set one through the OTP flow. Newly created Google accounts receive a generated email-login password in their welcome email.
- Run `npm run deploy:production` as root for every frontend change. It builds and synchronizes both `techinn.co.zw` and `my.techinn.co.zw`, with per-site backups.

## Verify and deploy

1. `npm run build` completed successfully.
2. Django `check`, `makemigrations --check --dry-run`, `compileall`, and all 40 `apps.services` tests passed.
3. Static output deployed to `/home/my.techinn.co.zw/public_html/`; `techinn-my-api.service` restarted. The API health endpoint and `/dashboard/` both returned HTTP 200; the expiry timer is active.

## 2026-10-13: `joat.co.zw` storage and DNS repair

- The active `web-basic` service had the generic 1 GB server package assigned even though TechInn Basic is configured as 2 GB. The site was moved to `TechInn-Basic-2GB`; the portal disk allocation now matches at 2 GB.
- Its previous mailbox setup is marked failed in the portal, but the mailbox exists on the mail server. Retrying that mailbox now applies the newly chosen password to the existing mailbox and verifies it, then completes portal setup.
- The active global DNS connection was used to find the existing Cloudflare zone for `joat.co.zw`. The zone is linked to the domain and synced: all 17 Cloudflare records and both assigned nameservers are available in the dashboard table. DNS list fetching now paginates beyond 100 records, and queued record updates accept either stored Cloudflare token or legacy email/key credentials.
- Dashboard storage copy shows the MB remaining for mailbox allocations and reports the actionable remaining amount on validation errors.
- Verified API dashboard data for `joat.co.zw`: 17 DNS records, two nameservers, 2 GB plan allocation. The recorded website disk use is 2.4834 GB, above its 2 GB plan. Read-only directory inspection showed most space under the site's `frontend` build/dependency directories and an old backup; no files were removed. Discuss cleanup or plan upgrade with the customer before changing those files or plan.
- Current changes passed `npm run build`, Django checks, migration check, compileall, and 42 services tests. Static export is deployed and API health returned HTTP 200.

## 2026-10-13: Mailbox UX and dashboard layout

- Reduced mailbox create/retry password minimum to 8 characters in frontend validation, API serializer/retry endpoint, provider adapter, and provisioning worker validation.
- Mailbox setup failures now use red styling and explanatory copy; the retry password field and full “Retry setup” button stay readable without clipping.
- Dashboard mutations refresh data silently instead of replacing the page with a loading skeleton, preserving the current form, scroll position, and keyboard focus. Successful mailbox actions clear their password fields; failed requests retain user input.
- Domains and email mailboxes are shown in separate collapsed cards per domain. Opening one domain collapses the previously open domain.
- DNS, nameserver, and mailbox tables use minimum widths inside horizontal overflow wrappers so their columns and controls keep their intended shape on narrow screens. Mobile table visibility remains toggleable.
- Verified: `npm run build`; `npx eslint components/customer-dashboard.tsx`; Django `check`; `compileall`; and all 42 `apps.services` tests passed. Static output is deployed, API service restarted, and `/api/v1/health/` returned HTTP 200.
- Mailbox creation now starts at a 100 MB allocation. Owners can edit active mailbox allocations up or down in the customer dashboard; the API checks the total hosting allocation, any per-mailbox product cap, and current mailbox usage. The allocation is saved in TechInn's portal database; CyberPanel's current Dovecot configuration does not enable per-mailbox disk enforcement, so do not describe this as an enforced mail-server storage cap without configuring and verifying that separately.
- Verified the allocation editor with a backend test covering increase, decrease, and rejecting a reduction below current usage. The test suite now has 43 passing `apps.services` tests; frontend build/lint passed and both dashboard and API health return HTTP 200 after deployment.

## 2026-10-13: Billing test scenario and wallet

- Billing now creates a paid invoice, including itemized order lines, as soon as Paynow confirms an order. Invoice creation and wallet top-up credits are idempotent.
- Balance deposits are initiated directly from Billing: the customer enters `$0.01`–`$10,000` (minimum lowered for user-requested testing), selects EcoCash, OneMoney, or card, and pays through Paynow without going through TechInn's Shop or checkout page. The wallet is credited only after Paynow confirms the payment. The internal catalog product remains only to itemize the deposit order; it is hidden from the Shop and rejected by generic checkout.
- For the authorized Ezekiel testing scenario, three existing active `web-basic` hosting services are attached to clearly marked internal-test orders and invoices at the catalog monthly rate. Their one-month service periods start on 2026-10-13. The existing CyberPanel sites remain the same; provisioning workers skip these service items because each order item is linked to its existing service.
- The internal test payment provider is inactive and never contacts Paynow. Test invoices and test wallet credits are visibly identified as simulations; no real payment was collected.
- Do not state that wallet funds are automatically deducted for renewals yet; that debit flow is not implemented. Renew links still take customers to the matching service in Shop.
- Billing follows the shadcn dashboard-block pattern: a compact TechInn balance card with the real customer name, actual balance, and active-service count; invoice and balance-activity tables; a tab-filtered invoice list; an inline Paynow deposit form using the checkout EcoCash/OneMoney/card assets; and a separate reminders section. No saved customer payment credentials exist; Paynow handles the payment details and TechInn does not store them.
- Latest layout correction: balance card is capped at 320 × 202 px and cannot stretch with the deposit form. Outstanding amount and reminder count are plain text beside it; the deposit form uses compact controls. Invoice and balance-record tables span the content width with the same bordered wrapper, muted toolbar, and row styling used by DNS. Removed the deposit-protection panel and general explanatory text. Keep this header small; do not reintroduce tall summary cards or side-column record cards.
- Verified after the direct-deposit UI revision: all 27 billing tests pass, including amount validation, idempotency, and only crediting after Paynow confirmation; Django checks and migration checks pass; ESLint and `npm run build` pass. Static output is deployed, `techinn-my-api.service` is active, `/api/v1/health/` returns HTTP 200, and `/dashboard/billing/` returns HTTP 200.
3. Verify `/dashboard/` and `/api/v1/health/` return HTTP 200 and the expiry timer is active.
4. Check that the failed-mailbox retry endpoint resolves and the customer-facing message does not expose a password.

## 2026-10-13: File Manager handoff, panel branding, six-hour idle sessions

- Deposit button explicitly disables the shared button gradient (`bg-none`) and sets orange backgrounds/white text for both themes and screen sizes.
- Hosting owners with active web-hosting services can choose **Open File Manager**. The portal checks ownership, service/account status, product type, and expiry before issuing a 60-second HMAC-signed ticket. The browser POSTs it to the panel in a new tab; no passwords or tokens go into URLs.
- Portal endpoint: `POST /api/v1/services/hosting-accounts/<id>/file-manager/` in `backend/apps/services/panel_access.py`.
- Panel extension source: `backend/deploy/cyberpanel/techinn_sso.py`; installed at `/usr/local/CyberCP/CyberCP/techinn_sso.py`. The panel verifies ticket signature, origin, age, current site ownership, site status, and plan expiry. A unique session-table insert rejects replay across workers. It creates a fresh secure HttpOnly session and rotates the CSRF cookie before redirecting to that domain's File Manager.
- Existing CP users include reseller accounts. Handoff sessions are restricted by middleware to the selected site's file-manager routes and paths; they cannot visit user/admin/reseller pages, root file manager, other domains, or arbitrary API endpoints. Administrator ACLs are rejected outright. Standard direct panel logins retain their usual permissions.
- Panel branding adds the existing transparent TechInn logo and orange TechInn text in the base header/sidebar and File Manager header. Original files were backed up at `/root/techinn-backups/panel-20261013-132645/`.
- Reapply after a CyberPanel upgrade using `python3 backend/deploy/cyberpanel/install.py` as root, review upstream compatibility, then restart `lscpd`. This installer does not rotate existing keys. The signing-key copies are `/etc/techinn/portal-sso.key` (root:mytec3641, 0640) and `/etc/techinn/cyberpanel-sso.key` (root:cyberpanel, 0640). Never put their contents into logs, code, or chat.
- Portal login now creates a `PortalSession` (migration `accounts.0003_portalsession`) tied to JWT claims. Server checks enforce a six-hour idle limit. Customer interactions send a throttled activity request, renew the session and six-hour refresh token; ordinary reads/polling/refreshes do not extend the idle timestamp. Logout revokes that portal session. Frontend auth is persisted in localStorage with idle expiry, including after closing a tab; old sessionStorage auth is migrated. Concurrent token refreshes share one request.
- CyberPanel uses secure session cookies, six-hour expiry, and saves session activity on requests. SSO also stops access at the hosting plan's signed expiry; reopen from the dashboard after renewal to obtain a new grant.
- Verification: frontend ESLint/build passed; 61 account/service tests passed, then four focused idle-session tests passed after activity-token renewal was added. Panel checks passed for single-use tickets, expiry, origin, ownership, secure cookies, site/path/admin isolation and branding. Live HTTPS handoff opened joat.co.zw's File Manager and successfully listed public_html with CSRF; cross-site/admin access and ticket reuse were denied. Test sessions were logged out; website files were not changed.
- Deployment: portal session migration applied, static export published, API and lscpd restarted. API health, hosting page and panel logo returned HTTP 200.
- File Manager logo refinement: removed the “TechInn Files” header text, enlarged the image from 30 to 48 px, and removed the icon container's purple gradient, border, shadow, and hover lift. Keep the `domainNameInitial` domain label because the existing file-manager JavaScript reads it. Updated both the live template and the upgrade installer; panel restarted and rendered HTML checked over HTTPS.

## 2026-10-15: mailbox creation, deletion responses and queued storage changes

- Root cause of first-mailbox creation failure: CyberPanel `listEmailsJson` prints `0` with exit success when no `mailServer.Domains` row exists. Old adapter treated it as invalid JSON. Replaced the CLI preflight/create with a structured local Python helper using `django.setup()`, `EUsers`, and native `mailUtilities`. Passwords travel through stdin. Creation and retry verify the stored bcrypt password. Existing-account retry applies the newly chosen password. Do not restore CLI list-based existence checking.
- DELETE previously returned an empty HTTP 202 and `lib/api.ts` called `.json()` unconditionally. It now returns JSON `{detail,status:"deleting"}`; shared API parsing supports empty success responses and gives a controlled error for malformed nonempty data.
- Dashboard payload now includes pending mailbox action names. Email view polls pending creation, clearing, deleting, quota changes and password resets without a page reload. Pending controls are disabled; quota/password changes show Updating. API rejects conflicting queued actions under a mailbox row lock and clears stale errors when a change is queued. Worker uses the queued quota value.
- Deletion remains deleted once the mail account is removed, even if later quota cleanup fails. Unexpected mailbox processing exceptions become a sanitized, visible failure instead of leaving the row stuck pending. Failed allocation changes restore prior mail and website quotas where possible.
- Live verification used ONLY two unique `techinn-probe-*` temporary mailboxes on communities.applications.co.zw (portal rows 6 and 7, both now deleted). First test started with no mail domain row. Both passed creation at100MB, increases150MB, reductions75MB, Dovecot quota readback, empty mailbox clear, JSON deletion, and removal of their storage directories. The second also verified existing-account retry with an eight-character password. Customer notification sending was mocked only within these test calls. Customer mail contents were untouched. No ZISPA submission was made.
- Original failed mailbox id5 was never created on the mail server; its password was already wiped from the old failed queue action. User must enter a chosen password in Retry setup. Do not invent a replacement password for it. Historical failed actions remain for auditing.
- Five active existing subdomains and their folders verified against CyberPanel. Authenticated create-child endpoint can re-confirm these existing sites idempotently.
- Regression tests cover nonempty delete202, polling payload, overlapping operations, password exclusion from argv, partial-delete cleanup failure, and unexpected mailbox errors. Frontend ESLint/build passed. API client exercised with empty200/202/204, valid202 JSON, and malformed replies.
- Pre-edit backups: `/root/techinn-backups/mailbox-20261015/`. Live verification scripts: `/tmp/verify-techinn-mail.py`, `/tmp/check-techinn-subdomain.py` (no stored credentials).

### Previous File Manager upload fix (completed during preceding task)

- Fixed multipart request handling in installed CyberPanel security middleware; it had tried reading the raw body after POST parsing, causing `RawPostDataException` and HTTP500.
- Repeatable patch lives in `backend/deploy/cyberpanel/patch_uploads.py`; upload JS refreshes CSRF and displays useful non-JSON errors. Template asset cache key is `techinn-upload-2`. SSO denial responses include JSON upload fields.
- Verified a real signed File Manager session uploaded a unique28-byte probe, checked exact contents and deleted only that probe. Backup `/root/techinn-backups/uploads-20261013-135712/`.
- Final verification: all68 `apps.services` tests passed; Django checks passed; production API health and dashboard returned HTTP200; API service and provisioning timer active. Signed provisioning endpoint confirmed all five existing child sites. Original failed mailbox confirmed absent upstream; zero probe mailboxes and zero pending/processing mailbox actions remain. Frontend exported files deployed to `public_html`; API restarted. No GitHub push.

## 2026-10-15: verified external domain connection workflow

Live at `/dashboard/connections/`. Customer options are TechInn-managed Cloudflare DNS, existing external DNS, and their authorized Cloudflare account. The existing provider/token controls are collapsed under Advanced provider settings. Each connection expands separately with ownership challenge, service status, proposed DNS table, preservation/import review, nameservers, check/retry and in-place polling.

Implementation:
- `services.DomainConnection`, migration0014: customer-scoped claim tied to one hosting plan, unique random TXT token, provider/zone binding, verified domain, prior/imported/required records, explicit review approval, applied timestamp and readiness checks.
- `connection_views.py`: owned plan selection (including unassigned paid order items), paid-period validation, website/email entitlement, duplicate/foreign ownership protection, async check and approval endpoints. No provisioning before ownership. Cancelling an unverified connection preserves the paid plan.
- `domain_connections.py`: public TXT verification via external resolvers; authorized Cloudflare proof requires active zone and actual delegation. Claiming a domain is transactional. Pending zones and a shared hosting IP never prove ownership. No ZISPA registration calls.
- `providers/hosting_connection.py`: root-worker native hosting setup, customer-email ownership checks, stable customer owner identity, per-plan package mapping and actual filesystem-owner verification. New primary sites are provisioned only for verified, eligible paid plans; existing plan/domain bindings cannot be silently changed.
- Managed DNS uses the existing global Cloudflare provider and onboarding adapter. Current records are preserved; optional BIND zone-file import (128KB/500record limit, no INCLUDE/GENERATE). Selected website/email changes require explicit review approval. Website-only preserves MX and other mail records; email-only preserves website routing. MX targets are DNS-only. SPF replacement preserves unrelated apex TXT. Existing records of the same type are updated before deleting surplus records. Public DNS checks distinguish website/email readiness; HTTPS checks connect to the configured origin with domain SNI, and certificate issuance runs in the background.
- Existing `/cloudflare/zones/connect/` entry point now creates a pending verified workflow rather than instantly activating an external domain.
- `process_domain_connections` runs through new `techinn-my-domain-connections.timer` each minute; per-connection checks every2min while pending and30min once connected. Global flock prevents overlapping workers. Runs as root for native hosting operations; the API only schedules work. User approval fields are protected from worker overwrite.
- `TECHINN_HOSTING_IPV4` optional env setting; falls back to `/etc/cyberpanel/machineIP`. `TECHINN_WEBMAIL_URL` defaults to verified working `https://techinn.co.zw/webmail/`. Dashboard links and new mailbox notices use it so email-only customers can keep an external website. Standard public DNS cannot enumerate every record; UI makes review/import explicit. Website files and existing messages are not migrated automatically.
- Added `dnspython>=2.7,<3`; installed into backend venv. Cloudflare zone listing now paginates beyond50 zones.

Verification/deployment:
- All88 services tests passed, including20 new connection tests: ownership isolation, no A-record ownership proof, pending Cloudflare rejection, paid/unpaid periods, plan reuse prevention, selected-service DNS preservation, safe import, and concurrent approval preservation.
- ESLint and production build passed. Existing live joat hosting identity, filesystem owner and generated DKIM record were checked through the new adapter; shared webmail returned the actual Webmail login page. No customer nameservers or live DNS routing were changed for testing.
- Migration0014 applied as mytec3641; static export deployed; API restarted; new worker timer enabled. Production health successful. Additional visual/browser checks use intercepted fixture APIs, not customer mutations.
- Backups under `/root/techinn-backups/domain-connections-20261015/`. No GitHub push; no ZISPA submissions.

## 2026-10-17: Services dashboard and chatbot shop cleanup

- Finished the Services section at `/dashboard/services/`, linked in the sidebar. Uses existing shadcn Tabs, Input, Badge and Button components in a compact list, with All services / Chatbots tabs, search, setup status, period dates and configured dashboard links. Hosting/domain/email services retain their existing management destinations. Empty states use actual account data.
- Dashboard API now includes service type/name and a restricted `dashboards` list from ServiceInstance. New typed `display_name` and `dashboard_url` fields (migration services0018) are configurable through the existing ServiceInstance admin/inline. Only active, unexpired services/instances expose HTTPS links, and only owners or members with hosting-management permission receive them. Arbitrary instance JSON/secrets are never exposed. These are dashboard/login links, not a fabricated SSO integration. No real service dashboard URLs currently exist; asked user asynchronously which chatbot platform/URL to connect.
- Confirmed payment handling records chatbot, website-design and app-development purchases as pending CustomerServices via `sync_paid_services`. One service per purchased quantity, transactionally idempotent, respects DB billing periods. Does not falsely mark a project deployed. Backfill command `sync_paid_project_services` ran and found0 missing paid project services. Unpaid orders stay absent.
- Shop chatbot add-ons now only Advanced flows ($25), Payment integration ($30), Booking (free), Support tickets ($40). Removed WhatsApp channel and human-handoff options from frontend and backend checkout allowlist. Catalog migration0007 deactivates legacy add-ons while preserving historical purchases; flow label renamed. Base chatbot remains$80. Allfour totals$175. Existing cart normalization drops removed selections.
- Verification:29 focused service/payment tests passed, then5 service tests passed including quantity/idempotency. ESLint, production build and Django checks/migration consistency passed. Production migrations applied, export deployed and API restarted; health returned200. Browser checks use mocked owned-service fixtures; dashboard links and Chatbots filtering checked on desktop/mobile, shop uses deployed actual config. No ZISPA submissions or GitHub push.

## 2026-10-17 — Website and app categories in My Services
- Added Website development and App development tabs alongside Chatbots in `components/customer-services.tsx`.
- Website filter accepts both website-design and website-development service types. Each category has its own empty state and matching shop link. Existing saved dashboard links and paid-project setup flow apply to all three categories.
- Mobile categories use a two-column layout to avoid horizontal overflow.
- Deployed static export to public_html. ESLint and production build passed. Browser checks with intercepted service fixtures passed category filtering and 1440/390/360px layouts on the deployed UI.

## 2026-10-17 — Account, security, team roles, notification settings
- Added persisted billing_address/postal_address JSON fields and validated address serializers; notification_preferences supports service_updates (default true), billing_reminders (true), product_news (false). Migration accounts.0004 applied using the running API service environment/app user.
- New CustomerSettings component supplies address forms in Account and email preference checkboxes in Notifications & activity. Local save/error messages; PATCH updates session profile without reloading.
- New ServiceTeam component lists members per owned service, adds registered customers, changes role, confirms/revokes access, and updates locally. API detail endpoint now supports owner-only PATCH. Duplicate invitations return validation errors. Named roles force their permission presets even when conflicting booleans are submitted; changing roles removes previous permissions. Custom memberships remain supported by API/admin.
- Billing roles can see their assigned service's catalog unit price/renewal date in My Services. Account-wide invoices and wallet stay private to their owner (do not expose a multi-service invoice to one service member).
- Technical hosting members may queue child website creation/certificate requests after server-side permission checks. Provider panel/file-manager SSO remains owner-only because provider owner sessions can span more services. Dashboard hides DNS content/mailbox lists/hosting username where relevant permissions are absent.
- Password changes revoke other PortalSessions while preserving the current one; reset completion revokes all. Account has a forgot-password link. Existing reset email endpoints remain ready; unconfigured SMTP returns an explicit unavailable message. No emails were sent during verification.
- notifications/preferences.py provides a shared optional-email gate, wired to mailbox-ready notifications. Security/access credential emails remain mandatory. Billing reminder/news preferences are saved for their future delivery workers; no new reminder/news scheduler was added.
- Verification: 26 account/project tests and 53 settings/control-panel tests passed (overlapping settings coverage), ESLint/build/Django checks passed. Deployed static output and restarted API. Intercepted browser fixtures verified save/preferences/role/revoke and 1440/390/360px layouts. No real customer memberships or services were changed for testing.

## 2026-10-17 — Sticky portal header and production sender mailboxes
- SiteHeader is sticky top-0 with an opaque/translucent background and z-index. Built/deployed; browser scrolling verified header remains at top at 1440/390/360px.
- Created CyberPanel mailboxes security@techinn.co.zw (authentication/password/access credentials) and services@techinn.co.zw (billing/general service updates), 100 MB each. Independent 48-character random passwords. No pre-existing mailboxes with those names were modified.
- Credentials are in backend/.env (0600, app owner). Protected recovery backup at /root/techinn-backups/sender-mailboxes-20261017-071851/mailbox-credentials.json. Never print these credentials or commit them. Prechange environment and Postfix config also backed up there.
- Production EMAIL_BACKEND=apps.notifications.backends.RoutedEmailBackend. Security uses EMAIL_HOST_USER/PASSWORD and DEFAULT_FROM_EMAIL; service identity uses EMAIL_SERVICE_USER/PASSWORD and SERVICE_FROM_EMAIL. Both authenticate to mail.techinn.co.zw:465 with certificate verification. Sender routing rejects unknown identities. Mailbox-ready messages use service sender; password/reset/access messages remain security. Billing templates/workers can use SERVICE_FROM_EMAIL when implemented.
- Verified successful SMTP AUTH for both accounts, TLSv1.3/valid certificate on 465/587/993, matching forward/reverse DNS, existing SPF, existing DKIM public/private match, existing DMARC p=none. No DNS policy changed because other production senders exist. New mailboxes share the same server/domain reputation; inbox placement has NOT been tested or guaranteed.
- Hardened Postfix smtpd_tls_auth_only=yes, reloaded. AUTH not advertised before encryption on port 587, present after verified TLS. No test emails, SMTP MAIL/RCPT/DATA, or ZISPA submissions were sent. All SMTP verification was connect/EHLO/TLS/AUTH/QUIT only. Keep the user's no-test-email instruction in future work.
- Two isolated mock SMTP routing tests passed; lint/build passed; running API confirms both configured identities and health is OK. Backend restarted. Templates are the user's intended next step, not implemented in this change.

## 2026-10-17 — Lifecycle notifications, renewals, and overdue state wiring
- Added inactive empty lifecycle templates through notifications migration 0003: cart payment reminder, payment confirmation, domain processing, service processing, balance deposit confirmation, domain expiry reminder, service expiry reminder, overdue suspension. Admin can fill subjects/body later; no email tests or bulk queue run was performed.
- Added idempotent `process_lifecycle_notifications` command. It records one EmailQueue row per stable lifecycle key for unpaid carts after 24h, paid invoices, deposits, pending service/domain processing, yearly domain/service reminders at 30/15/5 days, monthly service reminders at 10/5 days, and overdue events. It respects notification preferences and does not send directly.
- Enabled hourly `techinn-my-lifecycle-notifications.timer` under the API project app user. The timer is waiting and will run the command; templates are inactive until copy is authored.
- Renewal links in My Services/Billing now point to `/dashboard/billing/?renew=<service_uuid>#billing-payment` rather than Shop. The billing form recognizes this special target and submits a service-scoped renewal payment. The endpoint validates ownership, records service UUID and monthly/yearly interval, and successful Paynow confirmation extends only that service, restores its account/domain state, and does not credit general wallet balance. Ordinary deposits retain existing behavior.
- Domain expiry handling now supports both `domains` and `domain-registration` service slugs. On overdue domain expiry it preserves original nameservers in `suspension_data`, replaces active nameservers with suspension nameservers, marks the DNS zone error, and blocks normal active-domain editing. Web hosting suspension continues through CyberPanel and marks the service/account suspended before the final expired state.
- Production migration 0003 notifications templates and 0019 DomainAsset suspension_data applied. API health is OK; Django checks, notification tests, build/typecheck, and migration checks passed. Backend restarted and frontend deployed.
- Renewal payment orders are excluded from wallet crediting; only ordinary balance deposits credit the wallet. Renewal service UUID is validated against the authenticated customer before Paynow is started. Monthly/yearly selector is present in billing; amount remains user-editable until catalog-specific renewal pricing is formalized.
- The lifecycle timer initially ran before the production migration and failed on the missing suspension_data column; migration was then applied and the service was started successfully (Lifecycle events queued: 0). Future hourly runs use the migrated schema.

## 2026-10-17 — TechInn-owned suspension enforcement
- Added `backend/apps/services/website_suspension.py`. Expiry enforcement now writes a reversible TechInn guard into every recorded primary/child document root: existing `.htaccess` is moved to `.techinn-original.htaccess`, `.techinn-suspension.htaccess` rewrites all traffic to a local `techinn-suspended.html` page with a TechInn Billing renewal link, and restoration removes the guard and restores the original file. Paths are resolved and restricted below `/home`; writes are idempotent and errors prevent the service from being marked fully expired until retried.
- `process_expired_services` invokes this guard for web hosting in addition to the CyberPanel API. Renewal payment and the CyberPanel reactivation worker remove the guard and restore the original site. Existing dashboard/API checks remain database-enforced and block access while inactive.
- Domain expiry handles both `domains` and `domain-registration` service slugs and retains original nameservers in `suspension_data`. Email suspension continues to rotate mailbox passwords and mark mailbox/account state unavailable in TechInn; reactivation rotates fresh credentials through the existing worker.
- Verified guard apply/idempotence/restore with an isolated temporary document root; compile, Django checks, focused service/notification tests, build, deployment and API health passed. No real customer website was suspended, no live document root was altered, and no email was sent.
# Pending-domain hosting and previews — 2026-10-17

- Current realego purchase: domain service 8 (`technologyinn.co.zw`), hosting service 9 (`web-growth`). Website is now created, Linux owner `techn1552`, panel user `tirealego01`; hosting service stays `provisioning` until domain active. Do not reset this account again without a new instruction.
- Verified Cloudflare zone exists, status pending. No ZISPA request ID, send-attempt marker or sent marker. Registration logs report draft creation failure. User requested verification only; no manual registry submission was made during this work.
- Provisioning worker now runs as root (like existing importer/provisioning workers) to verify local website ownership and apply filesystem quotas. `CyberPanelClient.create_website` verifies owner email and actual `externalApp` using the local panel ORM. Failed/provisioning records are resumed with the existing HostingAccount. Email delivery no longer gates website creation; access is dashboard SSO.
- Paid `provisioning` hosting accounts with active server accounts can open File Manager/panel and create subdomains. Suspended/expired services stay blocked. Mailboxes still require active service/domain.
- `website_preview.ensure_preview` creates a unique `preview-<service uuid prefix>.techinn.co.zw` hostname for each explicitly assigned purchased web service. Uses Cloudflare A DNS, a separate OLS vhost pointing at the customer's real root/PHP user, Certbot webroot `/var/www/html` (Nginx terminates port 80), and its own Nginx HTTPS vhost. Certbot deploy hook reloads Nginx/OLS. Preview link saved only after successful HTTPS setup. The preview has noindex/nofollow. Existing unrelated OLS mail vhosts have PHP73 config errors; preview validation checks errors specific to the new vhost.
- `hosting_dns.prepare_website_dns` adds missing root A/www CNAME to purchased-domain Cloudflare zones and links the DNS provider, preserving existing records. Connected domains continue their existing DNS review workflow.
- New `techinn-my-service-guides.timer` runs every two minutes. `process_service_guides` sends idempotent purchased-service guides and domain-active alerts via SERVICE_FROM_EMAIL with persisted retries. Purchased pending domains are checked via read-only Cloudflare status; active delegation updates domain status and queues an alert. Realego guide SMTP accepted 2026-10-17 16:20 UTC. No test emails were sent.
- UI: pending domain info correctly labels Processing with upload/preview instructions, web page filters to web hosting, mobile dashboard gutters 8px and card inner padding 12px. Email list retains included mail from web hosting once active.
- Verified 50 customer control panel API tests and 2 notification tests; Next build passed. Browser layout with API snapshot: 320/375/1440px, no page overflow and both File Manager/Preview visible. Actual customer SSO returned 302 then File Manager page 200; preview HTTPS 200. Frontend deployed to public_html, API restarted.

## 2026-10-18 OTP and notification audit

Mailbox password reset now opens `components/mailbox-password-dialog.tsx` using Radix Dialog (portal/focus trap/Escape). Opening does NOT send mail. Explicit Send verification code sends; form has local errors/status, password visibility, local 120s resend countdown, and keeps inputs on failures. Submit queues encrypted provisioning only after OTP verification; no page navigation or reload.

`backend/apps/accounts/otp.py` centralizes account and mailbox codes: purpose + target fields (accounts migration 0006 applied), hashed code, 10-minute expiry, 5 verification attempts, single use, 120-second resend floor and 5 requests/hour across purposes. Scope includes requesting authenticated user and specific mailbox ID. Mailbox permission checks remain on request and confirmation. Issuance locks the account; attempts persist before SMTP, including uncertain SMTP failures. Verification commits failed attempts, and successful consumption is atomic with password update / provisioning queue. Legacy authenticated `/auth/password/` also requires OTP now; Google users do not need a current password but DO need OTP. All account sessions are revoked after reset.

Notification audit: delivery worker uses MySQL GET_LOCK to serialize concurrent runs; per-recipient two-minute gap and six queued messages/hour, max 20 successful messages/run. Lifecycle queue insertion serializes on customer. Interrupted processing rows are marked failed for manual provider-log review, never blindly retried. Only explicit transient SMTP 4xx errors auto retry (up to 5 attempts); ambiguous failures are held. Stale domain/service processing, paid-cart reminders and already-paid invoice notices cancel before sending. Balance top-ups no longer generate purchased-service setup guides. Production queue was empty during audit; no old messages replayed.

Verification WITHOUT sending email: 25 focused tests passed, then the added hourly queue-cap test and all 5 queue tests passed. Use `.venv/bin/python manage.py test apps.accounts.test_otp_audit apps.accounts.tests.PasswordResetApiTests apps.accounts.test_password_change apps.accounts.test_settings apps.notifications.test_service_guides apps.notifications.tests --settings=techinn_api.audit_test_settings --noinput`. This settings module uses isolated in-memory SQLite, memory cache and local-memory email; SMTP calls in targeted tests are mocked. These tests do not establish real inbox placement, TLS end-to-end delivery, or exercise MariaDB locking under concurrent load. Build/TypeScript and Django checks passed. Both frontend roots deployed; API restarted. Do not send testing emails unless explicitly authorized again.

DNS audit: Google public resolver returned NOERROR and expected MX for technologyinn.co.zw. Reply-to remains support@techinn.co.zw; mailbox mapping exists. Earlier claims of a guaranteed 30-minute cache expiry and a proven temporary DNS gap were not established by the evidence. Do not promise those. cPanel SMTP remains configured on port 465/SSL. Do not print credentials in tools or reports.

## 2026-10-18 Shop enquiry acknowledgements and loading states

Shop contact submissions now save and queue a branded HTML/plain-text contact-acknowledgement with a TI-ENQ reference, receipt confirmation and promise of a team response. Existing service SMTP identity and support Reply-To apply. No old enquiries backfilled. Public endpoint limits 5 requests/IP/hour, exact duplicate submissions within 10 minutes are reused, and at most one acknowledgement per recipient/hour is queued. MySQL recipient advisory lock protects concurrent submissions. Existing delivery worker handles delivery and recipient pacing. No test emails sent.

Dashboard, domain connections, mailbox OTP dialog and service team action spinners now use action/record identifiers instead of shared busy flags. Existing busy disabling remains to prevent conflicting requests. Mailbox access sharing key includes service UUID. Nine focused notification tests passed using isolated audit settings and mocked SMTP; Django checks, TypeScript and production build passed. Frontend deployed to both domains; API restarted. Real inbox delivery was not tested.
