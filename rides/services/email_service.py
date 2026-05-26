from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.conf import settings
import logging

logger = logging.getLogger(__name__)


def _dashboard_url(booking):
    base = getattr(settings, 'BASE_URL', '').rstrip('/')
    return f"{base}/dashboard/bookings/{booking.id}/"


class EmailService:
    @staticmethod
    def send_owner_notification(booking, payment_status: str = "UNPAID"):
        ref = getattr(booking, 'reference', None) or str(booking.id)
        ride_label = {
            'chauffeur': 'Chauffeur Drive',
            'long_distance': 'Long Distance',
            'city': 'EasyTransit Ride',
        }.get(getattr(booking, 'ride_type', 'city'), 'EasyTransit Ride')
        subject = f"New Booking {ref} - {ride_label}"

        context = {
            "booking": booking,
            "payment_status": payment_status,
            "taxi_owner_phone": settings.TAXI_OWNER_PHONE,
            "dashboard_url": _dashboard_url(booking),
        }

        text = render_to_string("rides/email_owner.txt", context)
        html = render_to_string("rides/email_owner.html", context)

        if settings.DEBUG:
            logger.info('Sending owner email to %s: %s', settings.TAXI_OWNER_EMAIL, subject)

        try:
            send_mail(
                subject,
                text,
                settings.DEFAULT_FROM_EMAIL,
                [settings.TAXI_OWNER_EMAIL],
                html_message=html,
            )
            logger.info('Owner notification sent for booking %s', booking.id)
        except Exception as e:
            logger.error('Failed to send owner notification for booking %s: %s', booking.id, str(e))

    @staticmethod
    def send_customer_notification(booking, payment_status: str = "UNPAID"):
        if not getattr(booking, 'email', None):
            logger.warning('No customer email for booking %s, skipping notification', booking.id)
            return

        ref = getattr(booking, 'reference', None) or str(booking.id)
        subject = f"Booking Confirmed: {ref} - Easy Transit"

        context = {
            "booking": booking,
            "payment_status": payment_status,
            "taxi_owner_phone": settings.TAXI_OWNER_PHONE,
        }

        text = render_to_string("rides/email_customer.txt", context)
        html = render_to_string("rides/email_customer.html", context)

        if settings.DEBUG:
            logger.info('Sending customer email to %s: %s', booking.email, subject)

        try:
            send_mail(
                subject,
                text,
                settings.DEFAULT_FROM_EMAIL,
                [booking.email],
                html_message=html,
            )
            logger.info('Customer notification sent for booking %s', booking.id)
        except Exception as e:
            logger.error('Failed to send customer notification for booking %s: %s', booking.id, str(e))

    @staticmethod
    def send_payment_confirmation(booking):
        if not getattr(booking, 'email', None):
            logger.warning('No customer email for booking %s, skipping payment confirmation', booking.id)
            return

        ref = getattr(booking, 'reference', None) or str(booking.id)
        subject = f"Payment Confirmed: {ref} - Easy Transit"

        context = {"booking": booking}
        text = render_to_string("rides/email_payment_confirm.txt", context)
        html = render_to_string("rides/email_payment_confirm.html", context)

        if settings.DEBUG:
            logger.info('Sending payment confirmation to %s: %s', booking.email, subject)

        try:
            send_mail(
                subject,
                text,
                settings.DEFAULT_FROM_EMAIL,
                [booking.email],
                html_message=html,
            )
            logger.info('Payment confirmation sent for booking %s', booking.id)
        except Exception as e:
            logger.error('Failed to send payment confirmation for booking %s: %s', booking.id, str(e))
