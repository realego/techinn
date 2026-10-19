import re
import ipaddress
from decimal import Decimal

from rest_framework import serializers

from django.conf import settings

from apps.billing.models import Invoice, InvoiceItem


class InvoiceItemSummarySerializer(serializers.ModelSerializer):
    class Meta:
        model = InvoiceItem
        fields = ("description", "quantity", "unit_price", "subtotal")


class CustomerInvoiceSerializer(serializers.ModelSerializer):
    items = InvoiceItemSummarySerializer(many=True, read_only=True)
    is_test = serializers.SerializerMethodField()
    payment_method = serializers.SerializerMethodField()

    class Meta:
        model = Invoice
        fields = (
            "invoice_number",
            "status",
            "currency",
            "subtotal",
            "discount_total",
            "tax_total",
            "total",
            "amount_paid",
            "due_at",
            "paid_at",
            "created_at",
            "is_test",
            "payment_method",
            "items",
        )

    def get_is_test(self, invoice):
        return any(
            payment.payment_provider.slug == "internal-test"
            or (payment.provider_data or {}).get("test_checkout", False)
            for payment in invoice.payments.all()
        )

    def get_payment_method(self, invoice):
        payments = [payment for payment in invoice.payments.all() if payment.status == "successful"]
        payment = max(payments, key=lambda row: (row.completed_at or row.created_at, row.pk), default=None)
        if payment is None:
            return None
        if payment.payment_provider.slug == "internal-test":
            return "test"
        return (payment.provider_data or {}).get("method")


class CheckoutLineSerializer(serializers.Serializer):
    product_id = serializers.SlugField(max_length=150)
    service_uuid = serializers.UUIDField(required=False)
    quantity = serializers.IntegerField(min_value=1, max_value=100)
    options = serializers.DictField(
        child=serializers.CharField(max_length=50),
        required=False,
        default=dict,
    )
    domain_name = serializers.CharField(max_length=253, required=False, allow_blank=True, default="")


class CheckoutCreateSerializer(serializers.Serializer):
    checkout_key = serializers.UUIDField()
    payment_method = serializers.ChoiceField(choices=("ecocash", "onemoney", "card"))
    displayed_total = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=0)
    phone = serializers.CharField(max_length=50)
    payment_phone = serializers.CharField(max_length=50, required=False, allow_blank=True, default="")
    items = CheckoutLineSerializer(many=True, allow_empty=False, max_length=50)
    details = serializers.DictField(
        child=serializers.CharField(max_length=255, allow_blank=True),
        required=False,
        default=dict,
    )
    attribution = serializers.DictField(
        child=serializers.CharField(max_length=255, allow_blank=True),
        required=False,
        default=dict,
    )

    def validate(self, attrs):
        if attrs["payment_method"] in {"ecocash", "onemoney"} and not attrs["payment_phone"].strip():
            raise serializers.ValidationError({"payment_phone": "Enter the mobile money number to charge."})
        if attrs["payment_method"] in {"ecocash", "onemoney"}:
            digits = re.sub(r"\D", "", attrs["payment_phone"])
            if digits.startswith("00"):
                digits = digits[2:]
            if digits.startswith("263"):
                digits = digits[3:]
            if len(digits) == 9 and digits.startswith("7"):
                digits = f"0{digits}"
            if not re.fullmatch(r"07\d{8}", digits):
                raise serializers.ValidationError({
                    "payment_phone": (
                        "Enter a valid Zimbabwe mobile number, such as 0771234567 "
                        "or +263 77 123 4567."
                    )
                })
            attrs["payment_phone"] = digits
        allowed_details = {
            "business_name",
            "business_type",
            "preferred_domain",
            "registrant_name",
            "registrant_business_name",
            "physical_address",
            "physical_city",
            "physical_country",
            "postal_same_as_physical",
            "postal_address",
            "postal_city",
            "postal_country",
            "nameserver_type",
            "nameserver_1",
            "nameserver_2",
            "nameserver_3",
            "nameserver_4",
            "nameserver_ip_1",
            "nameserver_ip_2",
            "nameserver_ip_3",
            "nameserver_ip_4",
        }
        if set(attrs["details"]) - allowed_details:
            raise serializers.ValidationError({"details": "One or more checkout details are invalid."})
        has_domain = any(line["product_id"] == "domains" for line in attrs["items"])
        if has_domain:
            details = attrs["details"]
            required_domain_fields = (
                "business_name",
                "registrant_name",
                "registrant_business_name",
                "physical_address",
                "physical_city",
                "physical_country",
            )
            missing = [field for field in required_domain_fields if not details.get(field, "").strip()]
            if missing:
                raise serializers.ValidationError({
                    "details": "Enter the business name, registrant details, and physical address, city, and country."
                })
            postal_fields = ("postal_address", "postal_city", "postal_country")
            if not all(details.get(field, "").strip() for field in postal_fields):
                raise serializers.ValidationError({
                    "details": "Enter a separate postal address, postal city, and postal country for Address 2."
                })
            physical_address = " ".join(details.get("physical_address", "").lower().split())
            postal_address = " ".join(details.get("postal_address", "").lower().split())
            physical_city = " ".join(details.get("physical_city", "").lower().split())
            postal_city = " ".join(details.get("postal_city", "").lower().split())
            physical_country = " ".join(details.get("physical_country", "").lower().split())
            postal_country = " ".join(details.get("postal_country", "").lower().split())
            if (physical_address, physical_city, physical_country) == (postal_address, postal_city, postal_country):
                raise serializers.ValidationError({
                    "details": "Address 2 must be a separate postal address from Address 1."
                })
            nameserver_type = details.get("nameserver_type", "techinn")
            if nameserver_type not in {"techinn", "custom"}:
                raise serializers.ValidationError({"details": "Choose valid domain nameservers."})
            if nameserver_type == "custom":
                defaults = {
                    str(item["hostname"]).strip().rstrip(".").lower(): item["ip"].strip()
                    for item in settings.ZISPA_DEFAULT_NAMESERVERS
                }
                for index in range(1, 5):
                    hostname = details.get(f"nameserver_{index}", "").strip().rstrip(".").lower()
                    address = details.get(f"nameserver_ip_{index}", "").strip()
                    if index <= 2 and not hostname:
                        raise serializers.ValidationError({"details": "Enter at least two custom nameservers."})
                    if not hostname and address:
                        raise serializers.ValidationError({"details": "Enter a hostname for each nameserver IP."})
                    if not hostname:
                        continue
                    if len(hostname) > 253 or not re.fullmatch(
                        r"(?=.{1,253}$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}",
                        hostname,
                    ):
                        raise serializers.ValidationError({"details": "Enter valid custom nameserver hostnames."})
                    if not address and hostname not in defaults:
                        raise serializers.ValidationError({
                            "details": f"Enter the IP address for custom nameserver {hostname}."
                        })
                    if address:
                        try:
                            nameserver_ip = ipaddress.ip_address(address)
                        except ValueError as error:
                            raise serializers.ValidationError({
                                "details": f"Enter a valid IP address for custom nameserver {hostname}."
                            }) from error
                        if not nameserver_ip.is_global:
                            raise serializers.ValidationError({
                                "details": f"Enter a public IP address for custom nameserver {hostname}."
                            })
        allowed_attribution = {
            "source",
            "medium",
            "referrer",
            "utm_source",
            "utm_medium",
            "utm_campaign",
            "utm_term",
            "utm_content",
            "gclid",
            "fbclid",
            "landing_path",
        }
        if set(attrs["attribution"]) - allowed_attribution:
            raise serializers.ValidationError({"attribution": "One or more attribution fields are invalid."})
        return attrs


class WalletTopUpSerializer(serializers.Serializer):
    checkout_key = serializers.UUIDField()
    amount = serializers.DecimalField(max_digits=8, decimal_places=2, min_value=Decimal("0.01"), max_value=10000)
    payment_method = serializers.ChoiceField(choices=("ecocash", "onemoney", "card"))
    payment_phone = serializers.CharField(max_length=50, required=False, allow_blank=True, default="")
    service_uuid = serializers.UUIDField(required=False)
    billing_interval = serializers.ChoiceField(choices=("monthly", "yearly"), required=False, default="monthly")

    def validate(self, attrs):
        if attrs["payment_method"] in {"ecocash", "onemoney"} and not attrs["payment_phone"].strip():
            raise serializers.ValidationError({"payment_phone": "Enter the mobile money number to charge."})
        if attrs["payment_method"] in {"ecocash", "onemoney"}:
            digits = re.sub(r"\D", "", attrs["payment_phone"])
            if digits.startswith("00"):
                digits = digits[2:]
            if digits.startswith("263"):
                digits = digits[3:]
            if len(digits) == 9 and digits.startswith("7"):
                digits = f"0{digits}"
            if not re.fullmatch(r"07\d{8}", digits):
                raise serializers.ValidationError({
                    "payment_phone": "Enter a valid Zimbabwe mobile number, such as 0771234567 or +263 77 123 4567."
                })
            attrs["payment_phone"] = digits
        return attrs
