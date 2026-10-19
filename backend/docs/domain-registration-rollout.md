# Domain registration rollout

## Current release: live submission enabled

The TechInn deployment has explicit authorization to create and send ZISPA
registration requests. `ZISPA_DRAFT_API_KEY` is used to create a draft;
`ZISPA_API_KEY` remains the existing send key. Both
`ZISPA_SUBMISSIONS_ENABLED` and `ZISPA_AUTO_SEND` are enabled, and the
five-minute provisioning timer is active. No paid domain orders were queued
when this was enabled, so activation itself sent no registration requests.
The existing techinn.online deployment is separate and is not modified.

## Workflow

Confirmed payment → registrant validation → pending domain → Cloudflare zone →
registry draft → send → pending registry confirmation.

`registered` requires separate registry confirmation. Creating a DNS zone or
sending a request never changes a pending domain to active. Other extensions
remain a manual registrar workflow.

Credentials remain encrypted in ProviderConnection. `configure_cloudflare --verify`
supports an API token or the existing CLOUDFLARE_EMAIL/CLOUDFLARE_KEY pair;
verification only reads Cloudflare. A successful read does not prove zone-create
permissions; that is validated when an authorized domain is provisioned.

## Retry behavior

- A same-host `flock` per order item prevents concurrent submissions. Lock files
  live in backend/var/domain-registration-locks and must be shared by workers
  running under the API user. This deployment is single-host; use a shared
  database lease before moving workers to multiple hosts.
- Draft keys are saved before the call and use the service UUID with the
  `techinn-my-domain-` prefix, distinct from the legacy site's numeric keys.
- Retriable failures back off for 5, 10, 20, then 40 minutes. Five failures require
  review. Completed, paused, backoff, and review items do not consume batch slots.
- A saved draft can be sent later without creating another draft.
- A send-attempt marker is saved before sending. Any ambiguous send result or
  interrupted process must be checked against the bridge before retrying.

## Manual review

Inspect the service's domain_registration progress, including request ID,
idempotency key, send-attempt timestamp, and bridge records. Never clear a send
marker merely because a local timeout occurred. If the bridge confirms receipt,
record that confirmation and mark the workflow submitted; the domain stays pending.
Only reset a send attempt after the bridge confirms that nothing was sent.
The bridge's confirmation/polling contract has not been established here, so this
release does not invent a status endpoint or automatically mark registrations active.

## Operational notes

Review each new paid order's registrant details and monitor its request through
registry confirmation. Draft creation contacts the live bridge, and auto-send
submits the request using the existing send key. The current setup does not poll
for registry status or mark a domain active automatically.

Tests use an isolated SQLite database and mock providers. They must never run
the provisioning command against production orders to test this workflow.
