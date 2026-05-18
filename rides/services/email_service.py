from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.conf import settings
import logging

logger = logging.getLogger(__name__)


class EmailService:
    @staticmethod
    def send_owner_notification(booking, payment_status: str = "UNPAID"):
        subject = f"New ride booking: {booking.id}"
        context = {"booking": booking, "payment_status": payment_status, "taxi_owner_phone": settings.TAXI_OWNER_PHONE}

        text = render_to_string("rides/email_owner.txt", context)
        html = render_to_string("rides/email_owner.html", context)

        # In debug mode, log the rendered email to the console for visibility
        if settings.DEBUG:
            logger.info('Sending owner email to %s: %s', settings.TAXI_OWNER_EMAIL, subject)
            print('\n--- Owner email (text) ---\n')
            print(text)
            print('\n--- Owner email (html truncated) ---\n')
            print((html or '')[:2000])

        try:
            send_mail(subject, text, settings.DEFAULT_FROM_EMAIL, [settings.TAXI_OWNER_EMAIL], html_message=html)
            logger.info('Owner notification email sent successfully for booking %s', booking.id)
        except Exception as e:
            logger.error('Failed to send owner notification email for booking %s: %s', booking.id, str(e))

    @staticmethod
    def send_customer_notification(booking, payment_status: str = "UNPAID"):
        subject = f"Your booking: {booking.id}"
        context = {"booking": booking, "payment_status": payment_status, "taxi_owner_phone": settings.TAXI_OWNER_PHONE}

        text = render_to_string("rides/email_customer.txt", context)
        html = render_to_string("rides/email_customer.html", context)

        if settings.DEBUG:
            logger.info('Sending customer email to %s: %s', booking.email, subject)
            print('\n--- Customer email (text) ---\n')
            print(text)
            print('\n--- Customer email (html truncated) ---\n')
            print((html or '')[:2000])

        try:
            send_mail(subject, text, settings.DEFAULT_FROM_EMAIL, [booking.email], html_message=html)
            logger.info('Customer notification email sent successfully for booking %s', booking.id)
        except Exception as e:
            logger.error('Failed to send customer notification email for booking %s: %s', booking.id, str(e))

    @staticmethod
    def send_payment_confirmation(booking):
        subject = f"Payment confirmed for booking: {booking.id}"
        context = {"booking": booking}
        text = render_to_string("rides/email_payment_confirm.txt", context)
        html = render_to_string("rides/email_payment_confirm.html", context)
        if settings.DEBUG:
            logger.info('Sending payment confirmation to %s: %s', booking.email, subject)
            print('\n--- Payment confirmation (text) ---\n')
            print(text)
            print('\n--- Payment confirmation (html truncated) ---\n')
            print((html or '')[:2000])

        try:
            send_mail(subject, text, settings.DEFAULT_FROM_EMAIL, [booking.email], html_message=html)
            logger.info('Payment confirmation email sent successfully for booking %s', booking.id)
        except Exception as e:
            logger.error('Failed to send payment confirmation email for booking %s: %s', booking.id, str(e))
