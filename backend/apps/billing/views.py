import uuid
from decimal import Decimal, InvalidOperation
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from django.conf import settings
from apps.notifications.emailing import render_queued_email, send_transactional
from django.db import transaction
from django.db.models import Max
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.urls import reverse
from django.utils import timezone
from rest_framework import generics, status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.billing.checkout import create_checkout_order, ensure_invoice_for_order
from apps.billing.models import (
    Invoice,
    InvoiceItem,
    Payment,
    PaymentAttempt,
    PaymentEvent,
    PaymentProvider,
    WalletAccount,
    WalletTransaction,
)
from apps.billing.paynow import (
    PaynowNetworkError,
    PaynowProtocolError,
    PaynowRejected,
    check_payment_status,
    initiate_payment,
    is_configured,
    verify_response_hash,
)
from apps.services.models import CustomerService
from apps.services.periods import _add_months
from apps.services.website_suspension import WebsiteSuspensionError, restore_websites
from apps.billing.serializers import (
    CheckoutCreateSerializer,
    CustomerInvoiceSerializer,
    WalletTopUpSerializer,
)
from apps.catalog.models import Product
from apps.orders.models import Order, OrderItem
from apps.services.models import CustomerService


FINAL_PAYMENT_STATUSES = {
    Payment.Status.SUCCESSFUL,
    Payment.Status.FAILED,
    Payment.Status.CANCELLED,
    Payment.Status.EXPIRED,
    Payment.Status.REFUNDED,
}


def _send_paid_order_update(order):
    """Send one useful confirmation without making payment dependent on mail delivery."""
    lines = []
    for item in order.items.select_related("product"):
        label = item.product.name if item.product_id else item.description
        domain = (item.metadata or {}).get("domain")
        lines.append(f"- {label}{f' ({domain})' if domain else ''}")
    try:
        subject, text, html, security = render_queued_email(
            "payment-confirmation",
            {
                "invoice_number": order.order_number,
                "service_lines": lines,
                "amount": f"{order.currency} {order.total}",
            },
            order.customer,
        )
        send_transactional(
            subject=subject,
            text=text,
            html=html,
            security=security,
            recipient_list=[order.customer.email],
            fail_silently=True,
        )
    except Exception:
        return


def _status_message(payment):
    if payment.status == Payment.Status.SUCCESSFUL:
        return "Payment confirmed. Your order is now paid."
    if payment.status == Payment.Status.FAILED:
        return "Paynow could not complete this payment. You can start a new checkout."
    if payment.status == Payment.Status.CANCELLED:
        return (
            "This payment was cancelled in TechInn. The current Paynow integration cannot revoke the request, "
            "so its prompt or hosted page may remain active. If Paynow confirms payment later, your order will be updated."
        )
    if payment.status == Payment.Status.EXPIRED:
        return "This payment request expired. Your order has not been paid."
    return "We’re still checking your payment. You can safely check again."


def _payment_data(payment, *, redirect_url=""):
    provider_data = payment.provider_data or {}
    return {
        "uuid": str(payment.uuid),
        "status": payment.status,
        "message": _status_message(payment),
        "amount": str(payment.amount),
        "currency": payment.currency,
        "order_uuid": str(payment.order.uuid) if payment.order_id else None,
        "order_number": payment.order.order_number if payment.order_id else None,
        "redirect_url": redirect_url or provider_data.get("redirect_url", ""),
    }


def _create_attempt(payment, request_type, status_value, request_data=None, response_data=None):
    with transaction.atomic():
        locked_payment = Payment.objects.select_for_update().get(pk=payment.pk)
        max_number = locked_payment.attempts.aggregate(value=Max("attempt_number"))["value"] or 0
        return PaymentAttempt.objects.create(
            payment=locked_payment,
            attempt_number=max_number + 1,
            request_type=request_type,
            request_data=request_data,
            response_data=response_data,
            status=status_value,
            completed_at=timezone.now(),
        )


def _invoice_for_paid_order(order):
    invoice = Invoice.objects.filter(invoice_number=f"INV-{order.order_number}").first()
    if invoice is None:
        invoice = Invoice.objects.filter(payments__order=order).first()
    if invoice is None:
        invoice = Invoice.objects.create(
            customer=order.customer,
            invoice_number=f"INV-{order.order_number}",
            status=Invoice.Status.PAID,
            currency=order.currency,
            subtotal=order.subtotal,
            discount_total=order.discount_total,
            tax_total=order.tax_total,
            total=order.total,
            amount_paid=order.total,
            paid_at=timezone.now(),
        )
    else:
        invoice.status = Invoice.Status.PAID
        invoice.discount_total = order.discount_total
        invoice.amount_paid = invoice.total
        invoice.paid_at = invoice.paid_at or timezone.now()
        invoice.save(update_fields=("status", "discount_total", "amount_paid", "paid_at", "updated_at"))

    if not invoice.items.exists():
        items = OrderItem.objects.filter(order=order).select_related("product", "addon").prefetch_related("customer_services")
        invoice_items = []
        for item in items:
            customer_service = item.customer_services.first()
            if not customer_service:
                service_uuid = (item.metadata or {}).get("customer_service_uuid")
                if service_uuid:
                    customer_service = CustomerService.objects.filter(
                        uuid=service_uuid,
                        customer=order.customer,
                    ).first()
            invoice_items.append(InvoiceItem(
                invoice=invoice,
                customer_service=customer_service,
                product=item.product,
                addon=item.addon,
                description=item.description,
                quantity=item.quantity,
                unit_price=item.unit_price,
                subtotal=item.subtotal,
            ))
        InvoiceItem.objects.bulk_create(invoice_items)
    return invoice


def _credit_wallet_balance_products(order, *, is_test=False):
    items = OrderItem.objects.filter(order=order, product__slug="account-balance").select_related("product")
    for item in items:
        wallet, _ = WalletAccount.objects.get_or_create(customer=order.customer, currency=order.currency)
        wallet = WalletAccount.objects.select_for_update().get(pk=wallet.pk)
        _, created = WalletTransaction.objects.get_or_create(
            reference=f"paid-order-item:{item.pk}",
            defaults={
                "wallet": wallet,
                "transaction_type": WalletTransaction.Type.CREDIT,
                "amount": item.subtotal,
                "description": "Test account balance top-up" if is_test else "Account balance top-up",
                "order_item": item,
                "is_test": is_test,
            },
        )
        if created:
            wallet.balance += item.subtotal
            wallet.save(update_fields=("balance", "updated_at"))


def _mark_payment_status(payment, provider_status, provider_reference=""):
    normalized = provider_status.strip().lower()
    with transaction.atomic():
        locked_payment = Payment.objects.select_for_update().select_related("order").get(pk=payment.pk)
        if locked_payment.status in FINAL_PAYMENT_STATUSES and not (
            normalized == "paid"
            and locked_payment.status in {
                Payment.Status.FAILED,
                Payment.Status.CANCELLED,
                Payment.Status.EXPIRED,
            }
        ):
            return
        if normalized == "paid":
            locked_payment.status = Payment.Status.SUCCESSFUL
        elif normalized in {"failed", "cancelled", "expired", "refunded"}:
            locked_payment.status = normalized
        else:
            locked_payment.status = Payment.Status.PROCESSING
        if provider_reference:
            locked_payment.provider_reference = provider_reference
        if locked_payment.status in FINAL_PAYMENT_STATUSES:
            locked_payment.completed_at = timezone.now()
        locked_payment.save(
            update_fields=("status", "provider_reference", "completed_at", "updated_at")
        )

        if locked_payment.order_id:
            order = locked_payment.order
            if locked_payment.status == Payment.Status.SUCCESSFUL:
                order.status = order.Status.PAID
            elif locked_payment.status == Payment.Status.FAILED:
                order.status = order.Status.FAILED
            elif locked_payment.status in {Payment.Status.CANCELLED, Payment.Status.EXPIRED}:
                order.status = order.Status.CANCELLED
            order.save(update_fields=("status", "updated_at"))

            if locked_payment.status == Payment.Status.SUCCESSFUL:
                from apps.services.customer_services import sync_paid_services
                sync_paid_services(order)
                _send_paid_order_update(order)
                invoice = _invoice_for_paid_order(order)
                if locked_payment.invoice_id != invoice.id:
                    locked_payment.invoice = invoice
                    locked_payment.save(update_fields=("invoice", "updated_at"))
                renewal = (order.metadata or {}).get("service_renewal")
                if not renewal:
                    _credit_wallet_balance_products(
                        order,
                        is_test=locked_payment.payment_provider.slug == "internal-test",
                    )
                if renewal:
                    service = CustomerService.objects.select_for_update().filter(
                        uuid=renewal.get("service_uuid"), customer=order.customer,
                    ).first()
                    if service:
                        months = 12 if renewal.get("billing_interval") == "yearly" else 1
                        start = max(timezone.now(), service.expires_at) if service.expires_at else timezone.now()
                        service.started_at = service.started_at or start
                        service.expires_at = _add_months(start, months)
                        service.next_due_at = service.expires_at
                        service.status = CustomerService.Status.ACTIVE
                        data = dict(service.provisioning_data or {})
                        data["renewed_from_payment"] = locked_payment.uuid.hex
                        service.provisioning_data = data
                        service.save(update_fields=("started_at", "expires_at", "next_due_at", "status", "provisioning_data", "updated_at"))
                        if hasattr(service, "hosting_account"):
                            account = service.hosting_account
                            account.status = account.Status.ACTIVE
                            account.save(update_fields=("status", "updated_at"))
                            try:
                                restore_websites(service)
                            except WebsiteSuspensionError:
                                # Renewal remains paid; the next enforcement worker retries restoration.
                                service.provisioning_data = {**(service.provisioning_data or {}), "website_restore_pending": True}
                                service.save(update_fields=("provisioning_data", "updated_at"))
                        service.domains.filter(status=service.domains.model.Status.SUSPENDED).update(status=service.domains.model.Status.ACTIVE, updated_at=timezone.now())

        elif locked_payment.invoice_id and locked_payment.status == Payment.Status.SUCCESSFUL:
            invoice = locked_payment.invoice
            invoice.status = Invoice.Status.PAID
            invoice.amount_paid = invoice.total
            invoice.paid_at = invoice.paid_at or timezone.now()
            invoice.save(update_fields=("status", "amount_paid", "paid_at", "updated_at"))

        PaymentEvent.objects.create(
            payment=locked_payment,
            event_type="provider_status",
            provider_status=normalized[:100],
            payload={"provider_reference": provider_reference} if provider_reference else {},
        )


def _check_provider_fields(payment, fields):
    if fields.get("reference") != payment.reference:
        raise PaynowProtocolError("Paynow returned a mismatched payment reference.")
    try:
        amount = Decimal(fields.get("amount", ""))
    except InvalidOperation as exc:
        raise PaynowProtocolError("Paynow returned an invalid payment amount.") from exc
    if amount != payment.amount:
        raise PaynowProtocolError("Paynow returned a mismatched payment amount.")


def _payment_return_url(payment_uuid, base_url=None):
    base_url = base_url or settings.PAYNOW_RETURN_URL or f"{settings.FRONTEND_BASE_URL}/checkout/"
    parsed = urlparse(base_url)
    query = parse_qsl(parsed.query, keep_blank_values=True)
    query.append(("payment", str(payment_uuid)))
    return urlunparse(parsed._replace(query=urlencode(query)))


class CustomerCheckoutView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = CheckoutCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        payload = serializer.validated_data
        if not is_configured():
            return Response(
                {"detail": "Online payments are not available right now. Please try again later."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        result_url = settings.PAYNOW_RESULT_URL or request.build_absolute_uri(
            reverse("paynow-result")
        )
        if not settings.DEBUG and urlparse(result_url).scheme != "https":
            return Response(
                {"detail": "Online payments are not available right now. Please try again later."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        provider, _ = PaymentProvider.objects.get_or_create(
            slug="paynow",
            defaults={
                "name": "Paynow",
                "provider_type": "paynow",
                "status": PaymentProvider.Status.ACTIVE,
            },
        )
        if provider.status != PaymentProvider.Status.ACTIVE:
            return Response(
                {"detail": "Online payments are temporarily unavailable."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        with transaction.atomic():
            customer = type(request.user).objects.select_for_update().get(pk=request.user.pk)
            payment = Payment.objects.filter(
                customer=customer,
                checkout_key=payload["checkout_key"],
            ).select_related("order").first()
            is_new = payment is None
            if is_new:
                order = create_checkout_order(
                    customer,
                    payload["items"],
                    {
                        **payload["details"],
                        "contact_phone": payload["phone"],
                        "attribution": payload["attribution"],
                    },
                    payload["displayed_total"],
                )
                payment = Payment.objects.create(
                    customer=customer,
                    order=order,
                    payment_provider=provider,
                    checkout_key=payload["checkout_key"],
                    reference=order.order_number,
                    amount=order.total,
                    currency=order.currency,
                    status=Payment.Status.PENDING,
                    provider_data={
                        "method": payload["payment_method"],
                        **({"test_checkout": True} if order.metadata.get("test_checkout") else {}),
                    },
                )
                _create_attempt(
                    payment,
                    PaymentAttempt.RequestType.INITIATE,
                    "started",
                    request_data={"method": payload["payment_method"]},
                )

        if not is_new:
            return Response(_payment_data(payment), status=status.HTTP_200_OK)

        try:
            result = initiate_payment(
                payment,
                payload["payment_method"],
                payload["payment_phone"].strip(),
                _payment_return_url(payment.uuid),
                result_url,
            )
        except PaynowRejected as exc:
            _mark_payment_status(payment, "failed")
            _create_attempt(
                payment,
                PaymentAttempt.RequestType.VERIFY,
                "rejected",
                response_data={"status": "rejected", "reason": str(exc)[:240]},
            )
            return Response(
                {"detail": f"Paynow rejected the request: {exc}"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        except (PaynowNetworkError, PaynowProtocolError):
            payment.status = Payment.Status.PROCESSING
            payment.save(update_fields=("status", "updated_at"))
            _create_attempt(
                payment,
                PaymentAttempt.RequestType.VERIFY,
                "outcome_unknown",
                response_data={"status": "checking"},
            )
            return Response(_payment_data(payment), status=status.HTTP_202_ACCEPTED)

        payment.status = Payment.Status.PROCESSING
        payment.provider_reference = result.provider_reference or None
        payment.provider_data = {
            **(payment.provider_data or {}),
            "poll_url": result.poll_url,
            "redirect_url": result.redirect_url,
            "method": payload["payment_method"],
        }
        payment.save(
            update_fields=("status", "provider_reference", "provider_data", "updated_at")
        )
        _create_attempt(
            payment,
            PaymentAttempt.RequestType.INITIATE,
            "accepted",
            response_data={
                "status": result.status,
                "provider_reference": result.provider_reference,
            },
        )
        return Response(
            _payment_data(
                payment,
                redirect_url=result.redirect_url,
            ),
            status=status.HTTP_201_CREATED,
        )


class CustomerPaymentPollView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, uuid):
        payment = get_object_or_404(
            Payment.objects.select_related("order"),
            uuid=uuid,
            customer=request.user,
        )
        if payment.status in FINAL_PAYMENT_STATUSES:
            return Response(_payment_data(payment))

        poll_url = (payment.provider_data or {}).get("poll_url")
        if not poll_url:
            return Response(_payment_data(payment))
        _create_attempt(payment, PaymentAttempt.RequestType.POLL, "started")
        try:
            fields = check_payment_status(poll_url)
            _check_provider_fields(payment, fields)
        except (PaynowNetworkError, PaynowProtocolError):
            return Response(_payment_data(payment))

        provider_status = fields["status"]
        provider_reference = fields.get("paynowreference", "")
        _mark_payment_status(payment, provider_status, provider_reference)
        _create_attempt(
            payment,
            PaymentAttempt.RequestType.POLL,
            provider_status[:50],
            response_data={"status": provider_status[:50]},
        )
        payment.refresh_from_db()
        return Response(_payment_data(payment))


class CustomerPaymentCancelView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, uuid):
        payment = get_object_or_404(
            Payment.objects.select_related("order"),
            uuid=uuid,
            customer=request.user,
        )
        if payment.status in FINAL_PAYMENT_STATUSES:
            return Response(_payment_data(payment))

        poll_url = (payment.provider_data or {}).get("poll_url")
        if poll_url:
            _create_attempt(payment, PaymentAttempt.RequestType.VERIFY, "cancel_check_started")
            try:
                fields = check_payment_status(poll_url)
                _check_provider_fields(payment, fields)
            except (PaynowNetworkError, PaynowProtocolError):
                _create_attempt(
                    payment,
                    PaymentAttempt.RequestType.VERIFY,
                    "cancel_check_unknown",
                    response_data={"status": "unknown"},
                )
                return Response(
                    {"detail": "We couldn't confirm the Paynow status, so the payment was not cancelled. Try again."},
                    status=status.HTTP_503_SERVICE_UNAVAILABLE,
                )

            _mark_payment_status(
                payment,
                fields.get("status", ""),
                fields.get("paynowreference", ""),
            )
            payment.refresh_from_db()
            if payment.status in FINAL_PAYMENT_STATUSES:
                return Response(_payment_data(payment))

        with transaction.atomic():
            locked_payment = Payment.objects.select_for_update().select_related("order").get(pk=payment.pk)
            if locked_payment.status in FINAL_PAYMENT_STATUSES:
                return Response(_payment_data(locked_payment))

            locked_payment.status = Payment.Status.CANCELLED
            locked_payment.completed_at = timezone.now()
            locked_payment.save(update_fields=("status", "completed_at", "updated_at"))
            if locked_payment.order_id:
                locked_payment.order.status = locked_payment.order.Status.CANCELLED
                locked_payment.order.save(update_fields=("status", "updated_at"))
            PaymentEvent.objects.create(
                payment=locked_payment,
                event_type="customer_cancelled",
                provider_status="cancelled",
                payload={"provider_cancel_supported": False},
            )
            _create_attempt(
                locked_payment,
                PaymentAttempt.RequestType.VERIFY,
                "cancelled_locally",
                response_data={"status": "cancelled", "provider_cancel_supported": False},
            )

        return Response(_payment_data(locked_payment))


class PaynowResultView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    def post(self, request):
        fields = request.data
        if not is_configured() or not verify_response_hash(fields):
            return HttpResponse("Invalid payment result.", status=400)
        payment = Payment.objects.select_related("order").filter(
            reference=fields.get("reference", ""),
            payment_provider__slug="paynow",
        ).first()
        if payment is None:
            return HttpResponse("Payment not found.", status=404)
        try:
            _check_provider_fields(payment, fields)
        except PaynowProtocolError:
            return HttpResponse("Invalid payment result.", status=400)
        late_success_after_local_cancel = (
            fields.get("status", "").strip().lower() == "paid"
            and payment.status in {
                Payment.Status.FAILED,
                Payment.Status.CANCELLED,
                Payment.Status.EXPIRED,
            }
        )
        if payment.status not in FINAL_PAYMENT_STATUSES or late_success_after_local_cancel:
            _mark_payment_status(
                payment,
                fields.get("status", ""),
                fields.get("paynowreference", ""),
            )
        _create_attempt(
            payment,
            PaymentAttempt.RequestType.CALLBACK,
            "accepted",
            response_data={"status": fields.get("status", "")[:50]},
        )
        return HttpResponse("OK")


class CustomerInvoiceListView(generics.ListAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = CustomerInvoiceSerializer

    def get_queryset(self):
        return Invoice.objects.filter(customer=self.request.user).prefetch_related(
            "items",
            "payments__payment_provider",
        ).order_by("-created_at")


class CustomerWalletView(APIView):
    permission_classes = [IsAuthenticated]

    def _serialize_wallet(self, wallet):
        transactions = wallet.transactions.order_by("-created_at")[:20]
        return {
            "balance": str(wallet.balance),
            "currency": wallet.currency,
            "transactions": [{
                "type": transaction.transaction_type,
                "amount": str(transaction.amount),
                "description": transaction.description,
                "is_test": transaction.is_test,
                "created_at": transaction.created_at,
            } for transaction in transactions],
        }

    def get(self, request):
        wallet, _ = WalletAccount.objects.get_or_create(customer=request.user, currency="USD")
        return Response(self._serialize_wallet(wallet))
class CustomerWalletTopUpView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = WalletTopUpSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        payload = serializer.validated_data
        if payload.get("service_uuid"):
            service = CustomerService.objects.filter(uuid=payload["service_uuid"], customer=request.user).first()
            if not service:
                return Response({"detail": "The selected service renewal is not available."}, status=status.HTTP_404_NOT_FOUND)
            suspension = (service.provisioning_data or {}).get("manual_suspension")
            if service.status == CustomerService.Status.SUSPENDED and suspension and suspension.get("reason") == "customer":
                return Response({"detail": "Restore this service before starting its renewal."}, status=status.HTTP_409_CONFLICT)
        if not is_configured():
            return Response(
                {"detail": "Online payments are not available right now. Please try again later."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        result_url = settings.PAYNOW_RESULT_URL or request.build_absolute_uri(reverse("paynow-result"))
        if not settings.DEBUG and urlparse(result_url).scheme != "https":
            return Response(
                {"detail": "Online payments are not available right now. Please try again later."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        provider, _ = PaymentProvider.objects.get_or_create(
            slug="paynow",
            defaults={
                "name": "Paynow",
                "provider_type": "paynow",
                "status": PaymentProvider.Status.ACTIVE,
            },
        )
        if provider.status != PaymentProvider.Status.ACTIVE:
            return Response(
                {"detail": "Online payments are temporarily unavailable."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        with transaction.atomic():
            customer = type(request.user).objects.select_for_update().get(pk=request.user.pk)
            payment = Payment.objects.filter(customer=customer, checkout_key=payload["checkout_key"]).select_related("order").first()
            is_new = payment is None
            if payment and (
                not (payment.provider_data or {}).get("wallet_top_up")
                or payment.amount != payload["amount"]
                or (payment.provider_data or {}).get("method") != payload["payment_method"]
            ):
                return Response({"detail": "This payment request key was already used for another order."}, status=status.HTTP_409_CONFLICT)
            if is_new:
                product = Product.objects.filter(slug="account-balance", status=Product.Status.ACTIVE).first()
                if product is None:
                    return Response({"detail": "Balance deposits are temporarily unavailable."}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
                order = Order.objects.create(
                    customer=customer,
                    order_number=f"WALLET-{uuid.uuid4().hex[:16].upper()}",
                    status=Order.Status.AWAITING_PAYMENT,
                    currency="USD",
                    subtotal=payload["amount"],
                    total=payload["amount"],
                    metadata={"wallet_top_up": not payload.get("service_uuid"), "service_renewal": {
                        "service_uuid": str(payload["service_uuid"]),
                        "billing_interval": payload["billing_interval"],
                    } if payload.get("service_uuid") else {}},
                )
                OrderItem.objects.create(
                    order=order,
                    product=product,
                    description="Account balance deposit",
                    quantity=1,
                    unit_price=payload["amount"],
                    subtotal=payload["amount"],
                    metadata={"wallet_top_up": not payload.get("service_uuid"), "service_renewal": bool(payload.get("service_uuid")), "billing_interval": payload["billing_interval"]},
                )
                ensure_invoice_for_order(order)
                payment = Payment.objects.create(
                    customer=customer,
                    order=order,
                    payment_provider=provider,
                    checkout_key=payload["checkout_key"],
                    reference=order.order_number,
                    amount=order.total,
                    currency=order.currency,
                    status=Payment.Status.PENDING,
                    provider_data={"method": payload["payment_method"], "wallet_top_up": not payload.get("service_uuid"), "service_renewal": bool(payload.get("service_uuid"))},
                )
                _create_attempt(
                    payment,
                    PaymentAttempt.RequestType.INITIATE,
                    "started",
                    request_data={"method": payload["payment_method"], "wallet_top_up": True},
                )

        if not is_new:
            return Response(_payment_data(payment), status=status.HTTP_200_OK)

        try:
            result = initiate_payment(
                payment,
                payload["payment_method"],
                payload["payment_phone"].strip(),
                _payment_return_url(
                    payment.uuid,
                    f"{settings.FRONTEND_BASE_URL.rstrip('/')}/dashboard/billing/",
                ),
                result_url,
            )
        except PaynowRejected as exc:
            _mark_payment_status(payment, "failed")
            _create_attempt(payment, PaymentAttempt.RequestType.VERIFY, "rejected", response_data={"status": "rejected", "reason": str(exc)[:240]})
            return Response({"detail": f"Paynow rejected the request: {exc}"}, status=status.HTTP_400_BAD_REQUEST)
        except (PaynowNetworkError, PaynowProtocolError):
            payment.status = Payment.Status.PROCESSING
            payment.save(update_fields=("status", "updated_at"))
            _create_attempt(payment, PaymentAttempt.RequestType.VERIFY, "outcome_unknown", response_data={"status": "checking"})
            return Response(_payment_data(payment), status=status.HTTP_202_ACCEPTED)

        payment.status = Payment.Status.PROCESSING
        payment.provider_reference = result.provider_reference or None
        payment.provider_data = {
            **(payment.provider_data or {}),
            "poll_url": result.poll_url,
            "redirect_url": result.redirect_url,
            "method": payload["payment_method"],
            "wallet_top_up": True,
        }
        payment.save(update_fields=("status", "provider_reference", "provider_data", "updated_at"))
        _create_attempt(
            payment,
            PaymentAttempt.RequestType.INITIATE,
            "accepted",
            response_data={"status": result.status, "provider_reference": result.provider_reference},
        )
        return Response(_payment_data(payment, redirect_url=result.redirect_url), status=status.HTTP_201_CREATED)
