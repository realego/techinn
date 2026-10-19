"""Database-serialized, purpose-bound reset challenges; no background OTP retries."""
from datetime import timedelta
import secrets
from django.db import transaction
from django.utils import timezone
from django.contrib.auth.hashers import make_password, check_password
from apps.accounts.models import Customer, PasswordResetOTP
from apps.notifications.emailing import render_queued_email, send_transactional


class OTPCooldown(Exception):
    pass


def issue_otp(customer, *, purpose="account", target=""):
    with transaction.atomic():
        customer = Customer.objects.select_for_update().get(pk=customer.pk)
        now = timezone.now()
        recent = PasswordResetOTP.objects.filter(customer=customer)
        if recent.filter(created_at__gte=now-timedelta(minutes=2)).exists() or recent.filter(created_at__gte=now-timedelta(hours=1)).count() >= 5:
            raise OTPCooldown("A code was recently requested. Wait two minutes between requests; at most five codes can be requested per hour.")
        code = f"{secrets.randbelow(1_000_000):06d}"
        PasswordResetOTP.objects.filter(customer=customer, purpose=purpose, target=target, used_at__isnull=True).update(used_at=now)
        challenge = PasswordResetOTP.objects.create(customer=customer, purpose=purpose, target=target, code_hash=make_password(code), expires_at=now+timedelta(minutes=10))
    # Persist before SMTP so ambiguous delivery failures cannot cause a burst.
    subject, text, html, security = render_queued_email("password-reset", {"code": code, "mailbox": target if purpose == "mailbox" else ""}, customer)
    if send_transactional(subject=subject, text=text, html=html, security=security, recipient_list=[customer.email], fail_silently=False) != 1:
        raise OSError("SMTP did not accept the verification message")
    return challenge


def consume_otp(customer, code, *, purpose="account", target=""):
    """Caller holds an atomic transaction; False must not roll back attempts."""
    challenge = PasswordResetOTP.objects.select_for_update().filter(customer=customer, purpose=purpose, target=target, used_at__isnull=True, expires_at__gt=timezone.now()).first()
    if not challenge or challenge.attempts >= 5:
        return False
    challenge.attempts += 1
    valid = isinstance(code, str) and len(code) == 6 and code.isascii() and code.isdigit() and check_password(code, challenge.code_hash)
    if valid or challenge.attempts >= 5:
        challenge.used_at = timezone.now()
    challenge.save(update_fields=("attempts", "used_at"))
    return valid
