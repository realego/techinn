"""Shared opt-in gate for optional email; security/access messages are mandatory."""
from apps.notifications.emailing import send_mail

DEFAULTS = {"service_updates": True, "billing_reminders": True, "product_news": False}


def notification_enabled(customer, category):
    if category not in DEFAULTS:
        raise ValueError("Unknown notification category")
    return customer.notification_preferences.get(category, DEFAULTS[category]) is True


def send_customer_notification(customer, category, *args, **kwargs):
    if not notification_enabled(customer, category):
        return 0
    return send_mail(*args, **kwargs)
