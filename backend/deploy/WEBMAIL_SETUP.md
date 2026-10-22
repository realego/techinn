# Personalized domain webmail

Email-only plans still create/reuse the exact domain's CyberPanel website record for mail ownership. No web hosting purchase is required for Roundcube.

`prepare_email_webmail` runs as root because certbot and Nginx configuration require elevated access. Install `techinn-my-webmail.service` and `.timer` into `/etc/systemd/system`, reload systemd and enable the timer. It retries every five minutes and runs immediately for newly provisioned email services. It sends no email and never submits domains to registries.

The reconciler adds a missing apex A record in managed Cloudflare DNS, preserves existing A/AAAA/CNAME records, waits for public DNS to point to this server, obtains an apex certificate using TechInn's certbot issuer, configures `/webmail/`, and checks for a successful HTTPS Roundcube page before marking it ready. Customer-owned external website DNS is never redirected. Such domains require a separately arranged webmail route; the portal uses the shared login while the custom route is pending.

The API uses the verified service webmail URL, or `TECHINN_WEBMAIL_URL` until readiness succeeds. This prevents new mailbox buttons pointing at a nonexistent domain endpoint.

Verify a single domain with `python manage.py prepare_email_webmail --domain example.co.zw` as root. Do not use APIClient tests with the production file cache as root: they create root-owned throttle files. Set a separate `DJANGO_CACHE_DIR` for tests. The API cache permissions drop-in must run its chown with systemd's `+` prefix so repair works before the unprivileged API starts.

2026-10-20: vmsecurity.co.zw was missing the apex DNS record; its panel website and mail hostname already existed. Added the missing record, installed apex TLS, verified Roundcube HTTPS 200. No email was sent for testing.

Mail TLS now runs independently after the webmail check. It prepares missing mail A/MX/SPF records, validates DNS, rejects self-signed or wrong-host certificates, uses a separate `-techinn` certbot lineage when CyberPanel has placed unmanaged certificate files at the usual path, and installs SNI mappings for Dovecot and Postfix under a shared file lock. Configuration validation occurs before reload. Readiness requires hostname-verified TLS on 993, 995, 465 and STARTTLS 587; this sends no email. Errors remain pending for the five-minute retry. Install `reload-techinn-mail` as an executable certbot deploy hook: it rebuilds Postfix's embedded certificate map and reloads mail services after renewals for every domain, not just the TechInn hostname.

Install `techinn-dovecot-config-guard` as `/usr/local/sbin/techinn-dovecot-config-guard` (0755). It backs up the configuration and removes only SNI blocks whose certificate/key files no longer exist. The installer and renewal hook invoke it because Dovecot can return a successful reload exit status even when it rejects the new configuration. Live TLS probes are the readiness gate. CyberPanel can overwrite existing certbot files with self-signed PEMs, so both HTTPS and mail checks validate trust and hostname, not just expiry, and recover using a separate `-techinn` lineage.

## Customer-domain deliverability (2026-10-20)
The five-minute reconciler now calls `mail_authentication.prepare_mail_authentication` for every active hosted domain with managed DNS. It merges the VPS IPv4 into the single existing SPF record, preserving external senders and policy; adds monitoring DMARC only when missing; generates a persistent 2048-bit `techinn` DKIM key; publishes it separately from other providers' selectors; waits for public DNS and verifies the key before switching OpenDKIM's domain signing entry. Duplicate SPF/DMARC records require review rather than destructive guessing. Service `security.mail_auth_status` and `mail_auth_error` record pending/verified state. No messages are sent by this worker.

For this VPS, outgoing Postfix `smtp_helo_name = mail.techinn.co.zw` matches PTR for 5.189.146.229 and its forward A record. On another server configure its own verified forward/reverse hostname through the IP provider. Existing submission sender-login restrictions and rate limits remain enabled. This establishes authentication, not inbox reputation: Gmail placement must be assessed from actual received headers and sender reputation. External-DNS customers need equivalent records published by their DNS operator. Do not overwrite their DNS or configure a relay without verifying its domain authorization.

## Support tickets and Technology Inn mailbox relay
`SUPPORT_TICKET_EMAIL` defaults to `support@technologyinn.co.zw`. New customer tickets and subsequent customer messages queue one admin notification per persisted event in the existing throttled outbox. Reply-To is the customer email. Existing tickets are not backfilled. Staff can review tickets at `/admin/services/supportticket/`. Replies sent from a mailbox are delivered to the customer, but are not imported into dashboard ticket messages; inbound threading requires a separate integration.

Run `manage.py shell < deploy/configure_customer_domain_relay.py` as root to install the domain-specific Postfix relay using the configured Django cPanel credentials. The script verifies TLS and authenticates without sending a message, backs up Postfix config, installs a root-only password map, and uses a dedicated verified TLS transport on port 465. Only envelope senders at technologyinn.co.zw use that route; other customer domains retain their own direct sending route. Incoming MX stays on the VPS. Phone users must submit through TechInn SMTP as the mailbox they are sending from, not through personal Gmail SMTP. The script must be rerun after relay credential changes.

### TechInn inbound forwarding
`configure_techinn_forwarding.py` installs the VPS mail-host forwarding policy for
`techinn.co.zw`. The domain catch-all forwards otherwise-unmatched addresses to
`support@technologyinn.co.zw`, and the existing `info@`, `sales@`, and `support@`
mailboxes also copy messages to support while retaining their mailbox delivery. Exact
`accounts@techinn.co.zw` mappings are preserved and take precedence over the
catch-all, so accounts mail is not forwarded to support. The script creates a
timestamped `e_forwardings` backup under `/root/techinn-backups/` before each
change and reloads Postfix after validating the configuration.

Transactional notifications to support (shop enquiries and ticket alerts) use
the local Postfix listener so they arrive in the VPS mailbox. Customer-facing
replies and service messages continue through the configured cPanel SMTP relay.
