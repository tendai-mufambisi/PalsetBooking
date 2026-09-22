from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.conf import settings
import logging

logger = logging.getLogger(__name__)


def _dashboard_url(booking):
    base = getattr(settings, 'BASE_URL', '').rstrip('/')
    return f"{base}/dashboard/bookings/{booking.id}/"


def _manage_url(booking):
    """Signed self-service link for the customer, or empty if it cannot be built."""
    try:
        from rides.services.booking_access import manage_url
        return manage_url(booking)
    except Exception:
        logger.exception('Could not build manage link for booking %s', getattr(booking, 'id', '?'))
        return ''


def _money_transfer_recipient():
    """Who a money transfer goes to, as configured in the dashboard."""
    try:
        from rides.services.pricing import PricingService
        return PricingService.get_money_transfer_recipient()
    except Exception:
        logger.exception('Could not read the money transfer recipient')
        return {"NAME": '', "PHONE": ''}


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
            "manage_url": _manage_url(booking),
            # A money transfer is only actionable with someone to send it to.
            "money_transfer_recipient": _money_transfer_recipient(),
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
    def send_booking_cancelled(booking):
        """Tell both the customer and the owner that a booking was cancelled."""
        ref = getattr(booking, 'reference', None) or str(booking.id)
        context = {
            "booking": booking,
            "taxi_owner_phone": settings.TAXI_OWNER_PHONE,
            "dashboard_url": _dashboard_url(booking),
        }
        html = render_to_string("rides/email_cancelled.html", context)
        text = (
            f"Booking {ref} has been cancelled.\n\n"
            f"Pickup was: {booking.pickup_address} on {booking.pickup_date} at {booking.pickup_time}\n"
            f"Dropoff: {booking.dropoff_address}\n"
        )

        recipients = [settings.TAXI_OWNER_EMAIL]
        if getattr(booking, 'email', None):
            recipients.append(booking.email)

        try:
            send_mail(
                f"Booking Cancelled: {ref} - Easy Transit",
                text,
                settings.DEFAULT_FROM_EMAIL,
                recipients,
                html_message=html,
            )
            logger.info('Cancellation notice sent for booking %s', booking.id)
        except Exception as e:
            logger.error('Failed to send cancellation notice for booking %s: %s', booking.id, str(e))

    @staticmethod
    def send_booking_rescheduled(booking, detail: str = ''):
        """Tell both the customer and the owner that a booking moved."""
        ref = getattr(booking, 'reference', None) or str(booking.id)
        context = {
            "booking": booking,
            "change_detail": detail,
            "taxi_owner_phone": settings.TAXI_OWNER_PHONE,
            "dashboard_url": _dashboard_url(booking),
            "manage_url": _manage_url(booking),
        }
        html = render_to_string("rides/email_rescheduled.html", context)
        text = (
            f"Booking {ref} has been changed.\n\n"
            f"{detail}\n\n"
            f"New pickup: {booking.pickup_address} on {booking.pickup_date} at {booking.pickup_time}\n"
            f"Total: ${booking.total_amount}\n"
        )

        recipients = [settings.TAXI_OWNER_EMAIL]
        if getattr(booking, 'email', None):
            recipients.append(booking.email)

        try:
            send_mail(
                f"Booking Updated: {ref} - Easy Transit",
                text,
                settings.DEFAULT_FROM_EMAIL,
                recipients,
                html_message=html,
            )
            logger.info('Reschedule notice sent for booking %s', booking.id)
        except Exception as e:
            logger.error('Failed to send reschedule notice for booking %s: %s', booking.id, str(e))

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
