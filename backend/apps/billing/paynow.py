import hashlib
import hmac
from dataclasses import dataclass
from decimal import Decimal
from urllib.parse import parse_qsl, quote_plus, urlparse

import requests
from django.conf import settings


INITIATE_URL = "https://www.paynow.co.zw/interface/initiatetransaction"
MOBILE_INITIATE_URL = "https://www.paynow.co.zw/interface/remotetransaction"
PAYNOW_HOSTS = {"paynow.co.zw", "www.paynow.co.zw"}


class PaynowError(Exception):
    pass


class PaynowNetworkError(PaynowError):
    pass


class PaynowProtocolError(PaynowError):
    pass


class PaynowRejected(PaynowError):
    pass


@dataclass(frozen=True)
class PaynowInitiation:
    status: str
    poll_url: str
    instructions: str
    redirect_url: str
    provider_reference: str


def is_configured():
    return bool(settings.PAYNOW_ID and settings.PAYNOW_KEY)


def _validate_paynow_url(value):
    parsed = urlparse(value)
    if parsed.scheme != "https" or parsed.hostname not in PAYNOW_HOSTS:
        raise PaynowProtocolError("Paynow returned an invalid payment URL.")
    return value


def _hash_values(fields):
    payload = "".join(
        str(value)
        for key, value in fields.items()
        if key.lower() != "hash"
    )
    payload += settings.PAYNOW_KEY.lower()
    return hashlib.sha512(payload.encode("utf-8")).hexdigest().upper()


def verify_response_hash(fields):
    supplied_hash = fields.get("hash", "")
    if not supplied_hash:
        return False
    return hmac.compare_digest(supplied_hash.upper(), _hash_values(fields))


def _parse_response(response):
    response.raise_for_status()
    fields = {}
    for key, value in parse_qsl(response.text, keep_blank_values=True):
        if key in fields:
            raise PaynowProtocolError("Paynow returned an invalid response.")
        fields[key] = value
    if not fields.get("status"):
        raise PaynowProtocolError("Paynow returned an incomplete response.")
    return fields


def initiate_payment(payment, method, phone, return_url, result_url):
    auth_email = payment.customer.email or settings.PAYNOW_EMAIL
    if not auth_email:
        raise PaynowProtocolError("A payer email address is required.")
    fields = {
        "resulturl": result_url,
        "returnurl": return_url,
        "reference": payment.reference,
        "amount": format(payment.amount.quantize(Decimal("0.01")), ".2f"),
        "id": settings.PAYNOW_ID,
        "additionalinfo": f"TechInn order {payment.order.order_number}",
        "authemail": auth_email,
    }
    url = INITIATE_URL
    if method in {"ecocash", "onemoney"}:
        fields["phone"] = phone
        fields["method"] = method
        url = MOBILE_INITIATE_URL
    fields["status"] = "Message"

    form_data = {
        key: value if key in {"resulturl", "returnurl", "authemail"} else quote_plus(str(value))
        for key, value in fields.items()
    }
    form_data["hash"] = _hash_values(form_data)
    try:
        response = requests.post(url, data=form_data, timeout=(5, 20))
    except requests.RequestException as exc:
        raise PaynowNetworkError("Unable to confirm whether Paynow received the request.") from exc
    try:
        response_fields = _parse_response(response)
    except requests.RequestException as exc:
        raise PaynowNetworkError("Unable to confirm whether Paynow received the request.") from exc

    status = response_fields["status"].lower()
    if status == "error":
        error_message = " ".join(response_fields.get("error", "").split())[:240]
        raise PaynowRejected(error_message or "Paynow could not start this payment.")
    if not verify_response_hash(response_fields):
        raise PaynowProtocolError("Paynow returned an invalid response.")

    poll_url = _validate_paynow_url(response_fields.get("pollurl", ""))
    redirect_url = response_fields.get("browserurl", "")
    if redirect_url:
        _validate_paynow_url(redirect_url)
    return PaynowInitiation(
        status=status,
        poll_url=poll_url,
        instructions=response_fields.get("instructions", ""),
        redirect_url=redirect_url,
        provider_reference=response_fields.get("paynowreference", ""),
    )


def check_payment_status(poll_url):
    _validate_paynow_url(poll_url)
    try:
        response = requests.post(poll_url, data={}, timeout=(5, 15))
        fields = _parse_response(response)
    except requests.RequestException as exc:
        raise PaynowNetworkError("Payment status is still being checked.") from exc
    if not verify_response_hash(fields):
        raise PaynowProtocolError("Paynow returned an invalid status response.")
    return fields
