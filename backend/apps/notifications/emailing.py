"""Shared transactional email rendering and delivery for TechInn."""

from email.utils import parseaddr
from html import escape
import hashlib
import re

from django.conf import settings
from django.core.cache import cache
from django.core.mail import EmailMultiAlternatives


PORTAL = "https://my.techinn.co.zw"
SUPPORT = getattr(settings, "EMAIL_REPLY_TO", "support@techinn.co.zw")
PUBLIC_SITE = "https://techinn.co.zw"
LOGO_URL = f"{PUBLIC_SITE}/techinn-logo-ntxuir.png"


def _sender(security=False):
    return settings.DEFAULT_FROM_EMAIL if security else settings.SERVICE_FROM_EMAIL


def _name(customer):
    return (getattr(customer, "first_name", "") or "there").strip() or "there"


def _row(label, value):
    return f"<tr><td style=\"padding:8px 0;color:#667085;font-size:13px;\">{escape(label)}</td><td style=\"padding:8px 0;text-align:right;color:#111827;font-weight:600;font-size:14px;\">{escape(str(value))}</td></tr>"


def render_email(*, title, intro, customer=None, rows=(), action_label=None, action_url=None, note="", guide_url=None, security=False):
    greeting = f"Hello {escape(_name(customer))},"
    row_html = "".join(_row(label, value) for label, value in rows)
    action_html = (
        f'<p style="margin:28px 0;"><a href="{escape(action_url)}" style="display:inline-block;background:#e87518;color:#ffffff;text-decoration:none;padding:12px 18px;border-radius:7px;font-weight:700;font-size:14px;">{escape(action_label)}</a></p>'
        if action_label and action_url else ""
    )
    note_html = f'<p style="margin:22px 0 0;color:#667085;font-size:13px;line-height:1.6;">{escape(note)}</p>' if note else ""
    guide_html = (
        f'<p style="margin:12px 0 0;font-size:13px;"><a href="{escape(guide_url)}" style="color:#c45709;text-decoration:underline;">Read the step-by-step guide</a></p>'
        if guide_url else ""
    )
    html = f'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{escape(title)}</title></head>
<body style="margin:0;background:#f4f6f8;color:#172033;font-family:Arial,Helvetica,sans-serif;line-height:1.55;">
<div style="display:none;max-height:0;overflow:hidden;opacity:0;">{escape(title)}</div>
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#f4f6f8;padding:28px 12px;"><tr><td align="center">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="max-width:620px;background:#ffffff;border:1px solid #e5e7eb;border-radius:12px;overflow:hidden;">
<tr><td style="padding:18px 28px 16px;border-bottom:1px solid #273244;background:#111827;"><a href="{PUBLIC_SITE}" style="display:inline-block;text-decoration:none;"><img src="{LOGO_URL}" width="170" alt="TechInn" style="display:block;width:170px;height:auto;max-height:86px;object-fit:contain;"></a><div style="font-size:12px;color:#d0d5dd;margin-top:7px;">TechInn <span style="color:#98a2b3;">· Technology Inn Hosting &amp; Digital Services</span></div></td></tr>
<tr><td style="padding:30px 28px;"><h1 style="margin:0 0 15px;font-size:25px;line-height:1.2;color:#111827;">{escape(title)}</h1><p style="margin:0 0 18px;font-size:15px;">{greeting}</p><p style="margin:0;font-size:15px;">{escape(intro).replace(chr(10), '<br>')}</p>
{f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="margin-top:22px;border-top:1px solid #eef0f3;border-bottom:1px solid #eef0f3;">{row_html}</table>' if row_html else ''}
{action_html}{note_html}{guide_html}</td></tr>
<tr><td style="padding:20px 28px;background:#fafafa;color:#667085;font-size:12px;line-height:1.6;">TechInn · Technology Inn · techinn.co.zw<br>Questions? <a href="mailto:{escape(SUPPORT)}" style="color:#c45709;">{escape(SUPPORT)}</a></td></tr>
</table></td></tr></table></body></html>'''
    return html


def render_queued_email(slug, context, customer=None):
    """Return (subject, text, html, security) for a queued notification."""
    context = context or {}
    first = _name(customer)
    details = []
    security = slug in {"password-reset", "account-created"}
    action_label, action_url = "Open dashboard", f"{PORTAL}/dashboard/"
    guide_url = f"{PORTAL}/how-to/getting-started/"
    note = "This is an automated TechInn message. If you did not expect it, contact support."
    if slug == "contact-admin":
        subject = title = "New TechInn shop enquiry"
        intro = context.get("message", "New enquiry received")
        details = [("Reference", context.get("reference", "")), ("Name", context.get("name", "")),
                   ("Email", context.get("customer_email", "")), ("Phone", context.get("phone", "") or "Not provided"),
                   ("Source", context.get("source", "shop"))]
        action_label, action_url = "Open Django admin", f"{PORTAL}/admin/notifications/contactrequest/"
        guide_url = None
        note = "Reply to this email to respond to the enquirer."
    elif slug == "support-ticket-admin":
        subject = title = f"Support ticket {context.get('reference', '')}"
        intro = context.get("message", "New support request")
        details = [("Customer", context.get("customer_email", "")), ("Subject", context.get("subject", ""))]
        action_label = "Open ticket admin"
        action_url = f"{PORTAL}/admin/services/supportticket/{int(context['ticket_id'])}/change/"
        guide_url = None
        note = "Reply to this email to contact the customer. Email replies are not imported into the dashboard ticket thread."
    elif slug == "contact-acknowledgement":
        subject, title = "We received your TechInn enquiry", "Your enquiry is with our team"
        intro = "Thank you for contacting TechInn. We have received your request from our shop. Our team will review what you need and respond using the contact details you provided."
        details = [("Enquiry reference", context.get("reference", "Recorded with our team"))]
        action_label, action_url = "Visit TechInn", PUBLIC_SITE
        guide_url = None
        note = "You can reply to this email if you need to add anything. If you did not submit an enquiry, contact support."
    elif slug == "invoice-ready":
        subject, title, intro = "Your TechInn invoice is ready", "Your invoice is ready", "Open Billing to review this invoice. Use the matching payment or renewal action; choose Add balance only for general funds."
        details = [("Invoice", context.get("invoice_number", "Available in your billing area")), ("Due date", context.get("due_date", "Shown in your billing area")), ("Amount due", context.get("amount_due", "Shown in your billing area"))]
        action_label, action_url = "View invoice", f"{PORTAL}/dashboard/billing/"
        guide_url = f"{PORTAL}/how-to/billing-renewals/"
    elif slug == "account-created":
        temporary_password = context.get("temporary_password")
        subject, title = "Your TechInn account is ready", "Welcome to TechInn"
        if temporary_password:
            intro = "Your customer portal account is ready. Google sign-in is connected, and we generated an email sign-in password for you. Use it to sign in with your email address, then change it from Account & security."
            details = [("Email sign-in", getattr(customer, "email", "Your account email")), ("Current password", temporary_password)]
            note = "Keep this password private and change it after your first email sign-in. TechInn will never ask you to send it back."
        else:
            intro = "Your customer portal account is ready. Use the dashboard to manage domains, hosting, email and billing."
        action_label, action_url = "Access dashboard", f"{PORTAL}/dashboard/"
        guide_url = f"{PORTAL}/how-to/getting-started/"
    elif slug == "payment-confirmation":
        subject, title, intro = "Your TechInn payment is confirmed", "Payment confirmed", "Your payment has been received and your services are being prepared."
        details = [("Invoice", context.get("invoice_number", "Available in your billing area")), ("Status", "Paid")]
        if context.get("amount"):
            details.append(("Amount", context["amount"]))
        if context.get("service_lines"):
            intro += " Services: " + "; ".join(str(item).lstrip("- ").split(":", 1)[0] for item in context["service_lines"])
        action_label, action_url = "View receipt", f"{PORTAL}/dashboard/billing/"
        guide_url = f"{PORTAL}/how-to/checkout/"
    elif slug == "cart-payment-reminder":
        subject, title, intro = "Your TechInn payment is waiting", "Payment reminder", "Open Billing to complete this payment. For a service renewal, choose Renew on that service; for general funds, choose Add balance."
        details = [("Order", context.get("order_number", "Your pending order"))]
        action_label, action_url = "Open billing", f"{PORTAL}/dashboard/billing/"
        guide_url = f"{PORTAL}/how-to/billing-renewals/"
    elif slug == "balance-deposit-confirmation":
        subject, title, intro = "Your TechInn deposit is confirmed", "Deposit confirmed", "Your deposited funds are now recorded in your TechInn balance."
        details = [("Reference", context.get("payment_uuid", "Recorded in billing"))]
        action_label, action_url = "View billing", f"{PORTAL}/dashboard/billing/"
        guide_url = f"{PORTAL}/how-to/billing-renewals/"
    elif slug == "service-processing":
        subject, title, intro = "Your TechInn service is being prepared", "Service processing", "Your service is paid and setup is in progress. We will update your dashboard as it moves forward."
        details = [("Service", context.get("service_uuid", "Your purchased service")), ("Status", "Processing")]
        action_label, action_url = "View services", f"{PORTAL}/dashboard/services/"
        guide_url = f"{PORTAL}/how-to/notifications-activity/"
    elif slug == "domain-processing":
        domain = context.get("domain", "your domain")
        subject, title, intro = f"Your domain {domain} is processing", "Domain processing", "Your domain request is being checked with the registry."
        details = [("Domain", domain), ("Status", "Processing")]
        action_label, action_url = "View domains", f"{PORTAL}/dashboard/domains/"
        guide_url = f"{PORTAL}/how-to/domains/"
    elif slug == "domain-expiry-reminder":
        domain = context.get("domain", "your domain")
        days = context.get("days", "the upcoming")
        subject, title, intro = f"Renew {domain} before it expires", "Domain renewal reminder", f"Open Billing and choose Renew beside {domain}. Use Add balance only when you are depositing general funds."
        details = [("Domain", domain), ("Time remaining", f"About {days} days")]
        action_label, action_url = "Renew domain", f"{PORTAL}/dashboard/billing/"
        guide_url = f"{PORTAL}/how-to/billing-renewals/"
    elif slug == "service-expiry-reminder":
        days = context.get("days", "the upcoming")
        subject, title, intro = "Renew your TechInn service", "Service renewal reminder", f"Open Billing and choose Renew beside this service. Use Add balance only for general funds. It is due in about {days} days."
        details = [("Service", context.get("service_uuid", "Your service")), ("Time remaining", f"About {days} days")]
        action_label, action_url = "Renew service", f"{PORTAL}/dashboard/billing/"
        guide_url = f"{PORTAL}/how-to/billing-renewals/"
    elif slug == "service-overdue-suspension":
        subject, title, intro = "Action required: service renewal overdue", "Service action required", "Open Billing and renew the affected service. Use its service-specific deposit so the payment is applied to the correct renewal."
        details = [("Service", context.get("service_uuid", context.get("domain", "Your service"))), ("Status", "Renewal required")]
        action_label, action_url = "Manage billing", f"{PORTAL}/dashboard/billing/"
        guide_url = f"{PORTAL}/how-to/service-expiry-suspension/"
    elif slug == "purchased-services-guide":
        subject, title, intro = "Getting started with your TechInn services", "Your services are ready to set up", context.get("message", "Open your dashboard to continue setting up your services.")
        action_label, action_url = "Access dashboard", f"{PORTAL}/dashboard/"
        guide_url = f"{PORTAL}/how-to/getting-started/"
    elif slug == "domain-active":
        domain = context.get("domain", "your domain")
        subject, title, intro = f"Your domain {domain} is active", "Domain active", context.get("message", f"{domain} is now active and ready for the next setup steps.")
        details = [("Domain", domain), ("Status", "Active")]
        action_label, action_url = "Manage domains", f"{PORTAL}/dashboard/domains/"
        guide_url = f"{PORTAL}/how-to/pending-domain-preview/"
    elif slug == "password-reset":
        code = context.get("code", "")
        subject, title, intro = "Your TechInn password reset code", "Reset your password", "Use the verification code below to reset your password. It expires in 10 minutes."
        details = [("Verification code", code)]
        action_label, action_url = "Reset password", f"{PORTAL}/reset-password/"
        if context.get("mailbox"):
            subject, title = "Your TechInn mailbox verification code", "Reset your mailbox password"
            intro = "Enter this code in the mailbox password reset window in your dashboard. It expires in 10 minutes and only authorizes the mailbox you selected."
            action_label, action_url = "Open business email", f"{PORTAL}/dashboard/email/"
        guide_url = f"{PORTAL}/how-to/account-security-notifications/"
        note = "If you did not request this code, you can safely ignore this email. TechInn will never ask for your password."
    else:
        subject = context.get("subject", "TechInn account update")
        title, intro = subject, context.get("message", "There is an update in your TechInn account.")
    text_lines = [f"TechInn — Technology Inn Hosting & Digital Services", "", title, "", f"Hello {first},", "", intro]
    for label, value in details:
        text_lines.append(f"{label}: {value}")
    text_lines.extend(["", f"{action_label}: {action_url}", "", note, "", f"TechInn · Technology Inn · techinn.co.zw", f"Questions? {SUPPORT}"])
    text_lines.extend(["", f"How-to guide: {guide_url}"] if guide_url else [])
    html = render_email(title=title, intro=intro, customer=customer, rows=details, action_label=action_label, action_url=action_url, note=note, guide_url=guide_url, security=security)
    return subject, "\n".join(text_lines), html, security


def send_transactional(*, subject, text, recipient_list, html=None, security=False, reply_to=None, fail_silently=False):
    from_email = _sender(security=security)
    # Request retries must not create an identical inbox burst. The key
    # includes the complete message content, so a legitimate state change or
    # a newly generated OTP is still delivered. Failed sends release the key
    # so the caller can retry safely.
    recipients = tuple(sorted(str(address).casefold() for address in recipient_list))
    fingerprint = hashlib.sha256(
        "\0".join((str(from_email), str(subject), str(text), str(html or ""), *recipients)).encode("utf-8")
    ).hexdigest()
    dedupe_key = f"techinn:email:dedupe:{fingerprint}"
    if not cache.add(dedupe_key, True, timeout=15 * 60):
        return 0
    message = EmailMultiAlternatives(
        subject=subject,
        body=text,
        from_email=from_email,
        to=recipient_list,
        reply_to=[reply_to or SUPPORT],
        headers={"X-Mailer": "TechInn Transactional Mailer"},
    )
    if html:
        message.attach_alternative(html, "text/html")
    try:
        result = message.send(fail_silently=fail_silently)
    except Exception:
        cache.delete(dedupe_key)
        raise
    if result != 1:
        cache.delete(dedupe_key)
    return result


def send_mail(subject, message, from_email, recipient_list, fail_silently=False, **kwargs):
    """Drop-in replacement for Django's send_mail with HTML and plain text."""
    sender = parseaddr(from_email)[1].casefold()
    security = sender == parseaddr(settings.DEFAULT_FROM_EMAIL)[1].casefold()
    if "password reset code" in subject.casefold():
        code_match = re.search(r"\b(\d{6})\b", message)
        _, _, html, _ = render_queued_email("password-reset", {"code": code_match.group(1) if code_match else ""})
    else:
        html = render_email(
            title=subject,
            intro=message,
            action_label="Open dashboard",
            action_url=f"{PORTAL}/dashboard/",
            note="If you did not expect this message, contact TechInn support.",
            guide_url=f"{PORTAL}/how-to/notifications-activity/",
            security=security,
        )
    return send_transactional(
        subject=subject,
        text=message,
        html=html,
        security=security,
        recipient_list=recipient_list,
        fail_silently=fail_silently,
        reply_to=kwargs.get("reply_to"),
    )
