from datetime import timedelta
import hashlib
from django.db import connection, transaction
from django.conf import settings
from django.utils import timezone
from apps.notifications.models import EmailQueue, EmailTemplate
from rest_framework import serializers, status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle
from rest_framework.views import APIView

from apps.notifications.models import ContactRequest


class ContactRequestSerializer(serializers.ModelSerializer):
    class Meta:
        model = ContactRequest
        fields = ("name", "email", "phone", "message", "source")

    def validate_message(self, value):
        value = value.strip()
        if len(value) < 10:
            raise serializers.ValidationError("Tell us a little more about what you need.")
        return value


class ContactRequestThrottle(AnonRateThrottle):
    scope = "contact"
    rate = "5/hour"


class ContactRequestView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [ContactRequestThrottle]

    def post(self, request):
        serializer = ContactRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        email = serializer.validated_data["email"].strip().lower()
        lock_name = "contact:" + hashlib.sha256(email.encode()).hexdigest()[:48]
        locked = False
        if connection.vendor == "mysql":
            with connection.cursor() as cursor:
                cursor.execute("SELECT GET_LOCK(%s, 5)", [lock_name])
                locked = cursor.fetchone()[0] == 1
            if not locked:
                return Response({"detail": "A request is already being saved. Please wait a moment."}, status=429)
        try:
            with transaction.atomic():
                now = timezone.now()
                recent = ContactRequest.objects.filter(email__iexact=email, created_at__gte=now-timedelta(minutes=10), message=serializer.validated_data["message"], name=serializer.validated_data["name"], phone=serializer.validated_data.get("phone", ""), source=serializer.validated_data.get("source", "shop")).first()
                if not recent:
                    enquiry = serializer.save(email=email)
                    # Public forms must not turn repeated submissions into an email flood.
                    if not EmailQueue.objects.filter(recipient_email__iexact=email, email_template__slug="contact-acknowledgement", created_at__gte=now-timedelta(hours=1)).exists():
                        template, _ = EmailTemplate.objects.get_or_create(slug="contact-acknowledgement", defaults={"name": "Enquiry received", "subject": "We received your TechInn enquiry", "body_html": "", "body_text": ""})
                        if template.status == EmailTemplate.Status.ACTIVE:
                            EmailQueue.objects.create(email_template=template, recipient_email=email, subject=template.subject, payload={"lifecycle_key": f"contact-received:{enquiry.pk}", "context": {"reference": f"TI-ENQ-{enquiry.pk:06d}"}})
                    admin_template, _ = EmailTemplate.objects.get_or_create(
                        slug="contact-admin",
                        defaults={"name": "Shop enquiry for support", "subject": "New TechInn shop enquiry", "body_html": "", "body_text": ""},
                    )
                    admin_key = f"contact-admin:{enquiry.pk}"
                    if admin_template.status == EmailTemplate.Status.ACTIVE and not EmailQueue.objects.filter(
                        email_template=admin_template, payload__lifecycle_key=admin_key
                    ).exists():
                        EmailQueue.objects.create(
                            email_template=admin_template,
                            recipient_email=getattr(settings, "SUPPORT_TICKET_EMAIL", "support@technologyinn.co.zw"),
                            subject=f"New TechInn enquiry from {enquiry.name}"[:255],
                            payload={"lifecycle_key": admin_key, "reply_to": enquiry.email, "context": {
                                "reference": f"TI-ENQ-{enquiry.pk:06d}", "name": enquiry.name,
                                "customer_email": enquiry.email, "phone": enquiry.phone,
                                "message": enquiry.message, "source": enquiry.source,
                            }},
                        )
        finally:
            if locked:
                with connection.cursor() as cursor:
                    cursor.execute("SELECT RELEASE_LOCK(%s)", [lock_name])
        return Response({"detail": "Your request has been received. Our team will review it and respond using your contact details."}, status=status.HTTP_201_CREATED)
