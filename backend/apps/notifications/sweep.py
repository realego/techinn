"""Safety sweep for the transactional email outbox."""

import json

from apps.notifications.delivery_policy import obsolete_reason
from apps.notifications.models import EmailQueue


def _fingerprint(row):
    payload = row.payload or {}
    lifecycle_key = payload.get("lifecycle_key")
    if lifecycle_key:
        event = f"key:{lifecycle_key}"
    else:
        context = payload.get("context") or {}
        event = "context:" + json.dumps(context, sort_keys=True, default=str, separators=(",", ":"))
    return row.recipient_email.casefold(), row.email_template.slug, event


def sweep_email_queue():
    """Cancel stale and duplicate outbox rows before any SMTP call."""
    rows = list(
        EmailQueue.objects.select_related("email_template")
        .filter(status__in=(EmailQueue.Status.SENT, EmailQueue.Status.PENDING, EmailQueue.Status.PROCESSING))
        .order_by("created_at", "pk")
    )
    seen = {_fingerprint(row) for row in rows if row.status == EmailQueue.Status.SENT}
    cancelled = 0
    for row in rows:
        if row.status not in (EmailQueue.Status.PENDING, EmailQueue.Status.PROCESSING):
            continue
        reason = obsolete_reason(row)
        fingerprint = _fingerprint(row)
        if reason:
            row.status = EmailQueue.Status.CANCELLED
            row.last_error = reason
        elif fingerprint in seen:
            row.status = EmailQueue.Status.CANCELLED
            row.last_error = "Duplicate transactional notification suppressed by the outbox sweep."
        else:
            seen.add(fingerprint)
            continue
        row.save(update_fields=("status", "last_error"))
        cancelled += 1
    return cancelled
