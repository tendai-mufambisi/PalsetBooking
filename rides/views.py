"""
============================================================================
Easy Transit Multi-Step Booking Wizard - Redesigned
============================================================================

Multi-step ride booking platform with:
- Step 1: Pickup & Dropoff (with Google Places Autocomplete)
- Step 2: Passengers & Luggage (increment/decrement)
- Step 3: Contact & Extra Instructions
- Step 4: Fare Preview & Payment Method
- Step 5: Confirmation
- AJAX endpoints for real-time distance/fare calculations
"""

import logging
import uuid
import json
from decimal import Decimal
from typing import Dict, Any

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status

from django.shortcuts import render, redirect, get_object_or_404
from django.views.generic import View, TemplateView
from django.http import JsonResponse
from django.middleware.csrf import get_token
from django.conf import settings
from django.db import transaction
from django.urls import reverse
from django.core.exceptions import ValidationError

from .models import RideBooking, Payment
import datetime
from .forms import (
    Step1PickupDropoffForm,
    Step2PassengersLuggageForm,
    Step3ContactExtraForm,
    Step4FarePaymentForm,
    Step5ConfirmationForm,
    BookingForm,
)
from .serializers import (
    CreateBookingSerializer,
    RideBookingSerializer,
    PaymentSerializer,
    PriceEstimateSerializer,
)
from .services.distance import DistanceService
from .services.pricing import PricingService
from .services.paynow import PaynowService
from .services.email_service import EmailService

logger = logging.getLogger(__name__)


def merged_adult_count(num_adults, num_kids_seated=0) -> int:
    """Merge seated kids into adult count for backward-compatible payload handling."""
    try:
        adults = int(num_adults or 0)
    except (TypeError, ValueError):
        adults = 0
    try:
        seated = int(num_kids_seated or 0)
    except (TypeError, ValueError):
        seated = 0

    return max(1, adults + max(0, seated))

def build_booking_message(booking, eta_minutes=None, payment_label_override: str | None = None):
    """Return a multi-line plain-text summary of the booking suitable for WhatsApp sharing."""
    try:
        parts = []
        parts.append("Hello Easy Transit, I have just booked a ride on your platform 🚗")
        parts.append("")
        parts.append("*Booking Details:*")
        parts.append("")
        bid = getattr(booking, 'reference', None) or str(booking.id)
        parts.append(f"*Booking ID:* {bid}")

        # Pickup with optional date/time
        pickup_line = f"*Pickup:* {booking.pickup_address}"
        if getattr(booking, 'pickup_date', None):
            try:
                pickup_line += f" on {booking.pickup_date.isoformat()}"
            except Exception:
                pickup_line += f" on {booking.pickup_date}"
        if getattr(booking, 'pickup_time', None):
            try:
                pickup_line += f" at {booking.pickup_time.strftime('%H:%M') }"
            except Exception:
                pickup_line += f" at {booking.pickup_time}"
        parts.append(pickup_line)

        # Airport / arrival info
        if getattr(booking, 'pickup_is_airport', False):
            ar = getattr(booking, 'arrival_airline', None)
            af = getattr(booking, 'arrival_flight_number', None)
            ad = getattr(booking, 'arrival_date', None)
            at = getattr(booking, 'arrival_time', None)
            if ar or af or ad or at:
                arr_parts = []
                if ar:
                    arr_parts.append(f"Airline: {ar}")
                if af:
                    arr_parts.append(f"Flight: {af}")
                if ad:
                    try:
                        arr_parts.append(f"Arrival date: {ad.isoformat()}")
                    except Exception:
                        arr_parts.append(f"Arrival date: {ad}")
                if at:
                    try:
                        arr_parts.append(f"Arrival time: {at.strftime('%H:%M')}")
                    except Exception:
                        arr_parts.append(f"Arrival time: {at}")
                parts.append("*Arrival:* " + ", ".join(arr_parts))

        parts.append(f"*Dropoff:* {booking.dropoff_address}")
        parts.append(f"*Distance:* {booking.distance_km} km")
        if eta_minutes:
            parts.append(f"*Estimated Time:* {eta_minutes} minutes")

        parts.append("")
        parts.append(f"*Total Fare:* ${booking.total_amount}")
        if payment_label_override:
            parts.append(f"*Payment:* {payment_label_override}")
        else:
            po = getattr(booking, 'payment_option', '')
            if po == RideBooking.PAYMENT_ON_ARRIVAL:
                parts.append("*Payment:* Pay on Arrival (Cash)")
            elif po == RideBooking.PAYMENT_CARD_ON_ARRIVAL:
                parts.append("*Payment:* Pay on Arrival (POS/CARD)")
            elif po == RideBooking.PAYMENT_MONEY_TRANSFER:
                parts.append("*Payment:* Money Transfer Agency")
            elif po == RideBooking.PAYMENT_PAYLINK:
                parts.append("*Payment:* Paylink")
            elif po == RideBooking.PAYMENT_PAYNOW:
                parts.append("*Payment:* Pay Online (Paynow)")
            else:
                parts.append(f"*Payment:* {po}")

        # Passenger summary
        pfull = getattr(booking, 'passenger_full_name', None)
        psal = getattr(booking, 'salutation', None)
        if pfull:
            parts.append("")
            parts.append(f"*Passenger:* {psal + ' ' if psal else ''}{pfull}")
        else:
            parts.append("")
            parts.append(f"*Passengers:* {booking.num_adults} adult(s)")
            if booking.num_kids_carried:
                parts[-1] += f", {booking.num_kids_carried} carried"

        if booking.luggage_count:
            parts.append(f"*Luggage:* {booking.luggage_count} bag(s)")

        # Extra instructions and contact
        if getattr(booking, 'extra_instructions', None):
            parts.append("")
            parts.append(f"*Notes:* {booking.extra_instructions}")

        parts.append("")
        parts.append(f"Contact phone: {booking.phone}")
        if getattr(booking, 'email', None):
            parts.append(f"Contact email: {booking.email}")

        parts.append("")
        parts.append("Thank you! Ready for my ride.")

        return "\n".join(parts)
    except Exception as exc:
        logger.exception('Error building booking message: %s', exc)
        bid = getattr(booking, 'reference', None) or str(booking.id)
        return f"Booking {bid} - Pickup: {booking.pickup_address} -> {booking.dropoff_address}"


# ============================================================================
# Multi-Step Booking Wizard (Session-Based)
# ============================================================================

class MultiStepBookingWizardView(View):
    """
    Multi-step booking wizard that uses Django sessions to preserve state.
    
    Flow:
    - Step 1 (GET): Show pickup/dropoff form
    - Step 1 (POST): Validate locations, save to session, redirect to Step 2
    - Step 2 (GET): Show passengers/luggage form
    - Step 2 (POST): Validate and save, redirect to Step 3
    - Step 3 (GET): Show contact form
    - Step 3 (POST): Validate and save, redirect to Step 4
    - Step 4 (GET): Show fare preview & payment method selection
    - Step 4 (POST): Create booking + payment, redirect to Step 5 or payment gateway
    - Step 5 (GET): Show confirmation (display-only)
    """

    VALID_STEPS = [1, 2, 3, 4, 5]
    SESSION_KEY_PREFIX = 'booking_wizard'

    def get_session_key(self, key: str) -> str:
        """Generate a session key for wizard state."""
        return f"{self.SESSION_KEY_PREFIX}_{key}"

    def get_wizard_data(self) -> Dict[str, Any]:
        """Get all wizard data from session."""
        data = {}
        for key in ['step1', 'step2', 'step3', 'step4']:
            session_key = self.get_session_key(key)
            if session_key in self.request.session:
                # Clone session data and convert ISO date/time strings back to objects
                item = dict(self.request.session[session_key])
                if key == 'step1':
                    # parse dates/times if stored as ISO strings
                    pd = item.get('pickup_date')
                    pt = item.get('pickup_time')
                    ad = item.get('arrival_date')
                    at = item.get('arrival_time')
                    try:
                        if isinstance(pd, str) and pd:
                            item['pickup_date'] = datetime.date.fromisoformat(pd)
                    except Exception:
                        pass
                    try:
                        if isinstance(pt, str) and pt:
                            item['pickup_time'] = datetime.time.fromisoformat(pt)
                    except Exception:
                        pass
                    try:
                        if isinstance(ad, str) and ad:
                            item['arrival_date'] = datetime.date.fromisoformat(ad)
                    except Exception:
                        pass
                    try:
                        if isinstance(at, str) and at:
                            item['arrival_time'] = datetime.time.fromisoformat(at)
                    except Exception:
                        pass
                data[key] = item
        return data

    def clear_wizard_session(self):
        """Clear all wizard session data."""
        for key in list(self.request.session.keys()):
            if key.startswith(self.SESSION_KEY_PREFIX):
                del self.request.session[key]
        self.request.session.modified = True

    def clear_wizard_steps(self):
        """Clear only the saved step data (step1..step4) but keep other wizard-related keys like booking id."""
        for step_key in ['step1', 'step2', 'step3', 'step4']:
            session_key = self.get_session_key(step_key)
            if session_key in self.request.session:
                del self.request.session[session_key]
        self.request.session.modified = True

    def get(self, request, step=1):
        """Render the form for the current step."""
        step = int(step)

        if step not in self.VALID_STEPS:
            return redirect('rides:booking_wizard_start')

        # Build context with CSRF token and Google Maps API key
        context = {
            'step': step,
            'total_steps': 4,  # Steps 1-4 have forms; Step 5 is confirmation
            'GOOGLE_MAPS_CLIENT_KEY': settings.GOOGLE_MAPS_CLIENT_KEY,
            'TAXI_OWNER_PHONE': settings.TAXI_OWNER_PHONE,
            'csrf_token': get_token(request),
        }

        # Restore previous step data from session if user navigates back
        wizard_data = self.get_wizard_data()

        # Allow callers to force-start a new booking by passing ?reset=1 (or true/yes)
        if step == 1:
            reset_param = (request.GET.get('reset') or '').lower()
            if reset_param in ('1', 'true', 'yes'):
                # Clear wizard state so the form shows empty values
                self.clear_wizard_session()
                wizard_data = {}
            else:
                # If a booking was just completed (booking_id present) and user
                # navigates back to the start, clear only the saved step data
                # so a fresh form is shown while preserving booking reference.
                booking_key = self.get_session_key('booking_id')
                if booking_key in request.session:
                    self.clear_wizard_steps()
                    wizard_data = {}

        if step == 1:
            form = Step1PickupDropoffForm(
                initial=wizard_data.get('step1', {})
            )
            context['form'] = form
            # Pass step1 saved values so template can populate hidden coords
            context['step1_data'] = wizard_data.get('step1', {})
            return render(request, 'rides/booking_wizard/step1.html', context)

        elif step == 2:
            # Check that Step 1 is complete
            if 'step1' not in wizard_data:
                return redirect('rides:booking_wizard', step=1)

            form = Step2PassengersLuggageForm(
                initial=wizard_data.get('step2', {})
            )
            context['form'] = form
            context['step1_data'] = wizard_data['step1']
            return render(request, 'rides/booking_wizard/step2.html', context)

        elif step == 3:
            if 'step2' not in wizard_data:
                return redirect('rides:booking_wizard', step=2)

            form = Step3ContactExtraForm(
                initial=wizard_data.get('step3', {})
            )
            context['form'] = form
            context['step1_data'] = wizard_data.get('step1', {})
            context['step2_data'] = wizard_data.get('step2', {})
            return render(request, 'rides/booking_wizard/step3.html', context)

        elif step == 4:
            if 'step3' not in wizard_data:
                return redirect('rides:booking_wizard', step=3)

            # Calculate fare based on Step 1 & 2 data
            step1 = wizard_data.get('step1', {})
            step2 = wizard_data.get('step2', {})

            # Ensure coordinates are present and valid; if not, send user back to step 1
            def _coords_valid(val):
                try:
                    return val is not None and str(val) != '' and float(val) == float(val)
                except Exception:
                    return False

            p_lat = step1.get('pickup_latitude')
            p_lng = step1.get('pickup_longitude')
            d_lat = step1.get('dropoff_latitude')
            d_lng = step1.get('dropoff_longitude')

            if not (_coords_valid(p_lat) and _coords_valid(p_lng) and _coords_valid(d_lat) and _coords_valid(d_lng)):
                from django.urls import reverse
                return redirect(reverse('rides:booking_wizard', kwargs={'step': 1}) + '?missing_coords=1')

            try:
                distance_km = float(step1.get('distance_km', 0))
                if distance_km == 0:
                    # Calculate distance from coordinates
                    distance_km = DistanceService.get_distance_km(
                        (step1.get('pickup_latitude'), step1.get('pickup_longitude')),
                        (step1.get('dropoff_latitude'), step1.get('dropoff_longitude')),
                    )
                    step1['distance_km'] = distance_km
                    # Ensure session-stored step1 is JSON-serializable (convert dates/times)
                    def _iso_date(d):
                        return d.isoformat() if d is not None and hasattr(d, 'isoformat') else d
                    session_step1 = dict(step1)
                    session_step1['pickup_date'] = _iso_date(session_step1.get('pickup_date'))
                    session_step1['pickup_time'] = _iso_date(session_step1.get('pickup_time'))
                    session_step1['arrival_date'] = _iso_date(session_step1.get('arrival_date'))
                    session_step1['arrival_time'] = _iso_date(session_step1.get('arrival_time'))
                    self.request.session[self.get_session_key('step1')] = session_step1
                    self.request.session.modified = True

                fare_breakdown = PricingService.calculate(
                    distance_km=distance_km,
                    num_adults=merged_adult_count(step2.get('num_adults', 1), step2.get('num_kids_seated', 0)),
                    num_kids_seated=0,
                    baby_car_seater=step2.get('baby_car_seater', 0),
                    num_kids_carried=step2.get('num_kids_carried', 0),
                    luggage_count=step2.get('luggage_count', 0),
                )
                context['fare_breakdown'] = fare_breakdown
                context['estimated_fare'] = fare_breakdown['total']
            except Exception as e:
                logger.exception('Fare calculation failed')
                context['fare_error'] = str(e)
                context['estimated_fare'] = 'Unable to calculate'

            form = Step4FarePaymentForm()
            context['form'] = form
            context['step1_data'] = step1
            context['step2_data'] = step2
            context['step3_data'] = wizard_data.get('step3', {})
            return render(request, 'rides/booking_wizard/step4.html', context)

        elif step == 5:
            # Confirmation page (read-only summary)
            if not all(k in wizard_data for k in ['step1', 'step2', 'step3']):
                return redirect('rides:booking_wizard', step=1)

            # Get booked booking if it exists
            booking_id = request.session.get(f'{self.SESSION_KEY_PREFIX}_booking_id')
            booking = None
            if booking_id:
                # booking_id may be a UUID (primary key) or a human-friendly reference like ET101
                try:
                    booking = RideBooking.objects.get(pk=booking_id)
                except Exception:
                    try:
                        booking = RideBooking.objects.get(reference=booking_id)
                    except RideBooking.DoesNotExist:
                        booking = None

            # Calculate estimated travelling time
            eta_minutes = None
            if booking and booking.distance_km:
                try:
                    avg_speed = float(getattr(settings, 'AVERAGE_SPEED_KMH', 40.0))
                    eta_minutes = int(round((float(booking.distance_km) / avg_speed) * 60))
                except Exception:
                    pass

            # Generate WhatsApp message
            whatsapp_message = None
            if booking:
                try:
                    from urllib.parse import quote
                    payment_status = "Pending"
                    if booking.payment_option == "POA":
                        payment_status = "Pay on Arrival (Cash)"
                    elif booking.payment_option == "PAYNOW":
                        payment_status = "Pay Online (Paynow)"
                    
                    # Build detailed message and URL-encode it
                    msg = build_booking_message(booking, eta_minutes=eta_minutes, payment_label_override=payment_status)
                    from urllib.parse import quote
                    phone = settings.TAXI_OWNER_PHONE.lstrip('+')
                    whatsapp_message = f"https://wa.me/{phone}?text={quote(msg)}"
                except Exception as e:
                    logger.exception('Error generating WhatsApp message: %s', e)

            context['step1_data'] = wizard_data.get('step1', {})
            context['step2_data'] = wizard_data.get('step2', {})
            context['step3_data'] = wizard_data.get('step3', {})
            context['booking'] = booking
            context['eta_minutes'] = eta_minutes
            context['whatsapp_message'] = whatsapp_message
            return render(request, 'rides/booking_wizard/step5.html', context)

        return redirect('rides:booking_wizard_start')

    def post(self, request, step=1):
        """Handle form submission for current step."""
        step = int(step)

        if step not in self.VALID_STEPS:
            return redirect('rides:booking_wizard_start')

        wizard_data = self.get_wizard_data()

        if step == 1:
            form = Step1PickupDropoffForm(request.POST)
            if form.is_valid():
                # Save to session and progress
                # Store date/time as ISO strings to keep session JSON-serializable
                def _iso_date(d):
                    return d.isoformat() if d is not None and hasattr(d, 'isoformat') else d
                self.request.session[self.get_session_key('step1')] = {
                    'pickup_address': form.cleaned_data['pickup_address'],
                    'pickup_latitude': form.cleaned_data['pickup_latitude'],
                    'pickup_longitude': form.cleaned_data['pickup_longitude'],
                    'dropoff_address': form.cleaned_data['dropoff_address'],
                    'dropoff_latitude': form.cleaned_data['dropoff_latitude'],
                    'dropoff_longitude': form.cleaned_data['dropoff_longitude'],
                    'distance_km': 0,  # Will be calculated in Step 4
                    'pickup_date': _iso_date(form.cleaned_data.get('pickup_date')),
                    'pickup_time': _iso_date(form.cleaned_data.get('pickup_time')),
                    'pickup_is_airport': bool(form.cleaned_data.get('pickup_is_airport')),
                    'arrival_airline': form.cleaned_data.get('arrival_airline'),
                    'arrival_flight_number': form.cleaned_data.get('arrival_flight_number'),
                    'arrival_date': _iso_date(form.cleaned_data.get('arrival_date')),
                    'arrival_time': _iso_date(form.cleaned_data.get('arrival_time')),
                }
                self.request.session.modified = True
                return redirect('rides:booking_wizard', step=2)
            else:
                context = {
                    'form': form,
                    'step': step,
                    'total_steps': 4,
                    'GOOGLE_MAPS_CLIENT_KEY': settings.GOOGLE_MAPS_CLIENT_KEY,
                    'TAXI_OWNER_PHONE': settings.TAXI_OWNER_PHONE,
                }
                return render(request, 'rides/booking_wizard/step1.html', context)

        elif step == 2:
            if 'step1' not in wizard_data:
                return redirect('rides:booking_wizard', step=1)

            form = Step2PassengersLuggageForm(request.POST)
            if form.is_valid():
                # persist passenger counts and optional passengers JSON from client
                passengers_json = request.POST.get('passengers_json') or request.POST.get('passengersJson') or '[]'
                # update step2 counts
                self.request.session[self.get_session_key('step2')] = {
                    'num_adults': merged_adult_count(form.cleaned_data['num_adults'], request.POST.get('num_kids_seated', 0)),
                    'num_kids_seated': 0,
                    'baby_car_seater': form.cleaned_data['baby_car_seater'],
                    'num_kids_carried': form.cleaned_data['num_kids_carried'],
                    'luggage_count': form.cleaned_data['luggage_count'],
                    'passengers_json': passengers_json,
                }
                self.request.session.modified = True
                return redirect('rides:booking_wizard', step=3)
            else:
                context = {
                    'form': form,
                    'step': step,
                    'total_steps': 4,
                    'step1_data': wizard_data.get('step1', {}),
                    'GOOGLE_MAPS_CLIENT_KEY': settings.GOOGLE_MAPS_CLIENT_KEY,
                    'TAXI_OWNER_PHONE': settings.TAXI_OWNER_PHONE,
                }
                return render(request, 'rides/booking_wizard/step2.html', context)

        elif step == 3:
            if 'step2' not in wizard_data:
                return redirect('rides:booking_wizard', step=2)

            form = Step3ContactExtraForm(request.POST)
            if form.is_valid():
                self.request.session[self.get_session_key('step3')] = {
                    'phone': form.cleaned_data['phone'],
                    'email': form.cleaned_data['email'],
                    'extra_instructions': form.cleaned_data['extra_instructions'],
                    'salutation': form.cleaned_data.get('salutation'),
                    'passenger_full_name': form.cleaned_data.get('passenger_full_name'),
                }
                self.request.session.modified = True
                return redirect('rides:booking_wizard', step=4)
            else:
                context = {
                    'form': form,
                    'step': step,
                    'total_steps': 4,
                    'step1_data': wizard_data.get('step1', {}),
                    'step2_data': wizard_data.get('step2', {}),
                    'GOOGLE_MAPS_CLIENT_KEY': settings.GOOGLE_MAPS_CLIENT_KEY,
                    'TAXI_OWNER_PHONE': settings.TAXI_OWNER_PHONE,
                }
                return render(request, 'rides/booking_wizard/step3.html', context)

        elif step == 4:
            if 'step3' not in wizard_data:
                return redirect('rides:booking_wizard', step=3)

            form = Step4FarePaymentForm(request.POST)
            if form.is_valid():
                # Create the booking in the database
                step1 = wizard_data['step1']
                step2 = wizard_data['step2']
                step3 = wizard_data['step3']
                payment_method = form.cleaned_data['payment_method']

                try:
                    distance_km = float(step1.get('distance_km', 0))
                    if distance_km == 0:
                        distance_km = DistanceService.get_distance_km(
                            (step1['pickup_latitude'], step1['pickup_longitude']),
                            (step1['dropoff_latitude'], step1['dropoff_longitude']),
                        )

                    fare_breakdown = PricingService.calculate(
                        distance_km=distance_km,
                        num_adults=merged_adult_count(step2.get('num_adults', 1), step2.get('num_kids_seated', 0)),
                        num_kids_seated=0,
                        baby_car_seater=step2.get('baby_car_seater', 0),
                        num_kids_carried=step2.get('num_kids_carried', 0),
                        luggage_count=step2.get('luggage_count', 0),
                    )

                    with transaction.atomic():
                        booking = RideBooking.objects.create(
                            pickup_address=step1['pickup_address'],
                            pickup_lat=Decimal(str(step1['pickup_latitude'])),
                            pickup_lng=Decimal(str(step1['pickup_longitude'])),
                            dropoff_address=step1['dropoff_address'],
                            dropoff_lat=Decimal(str(step1['dropoff_latitude'])),
                            dropoff_lng=Decimal(str(step1['dropoff_longitude'])),
                            distance_km=Decimal(str(distance_km)),
                            num_adults=merged_adult_count(step2.get('num_adults', 1), step2.get('num_kids_seated', 0)),
                            num_kids_seated=0,
                            baby_car_seater=step2.get('baby_car_seater', 0),
                            num_kids_carried=step2.get('num_kids_carried', 0),
                            luggage_count=step2.get('luggage_count', 0),
                            phone=step3['phone'],
                            email=step3['email'],
                            extra_instructions=step3.get('extra_instructions', ''),
                            pickup_date=step1.get('pickup_date'),
                            pickup_time=step1.get('pickup_time'),
                            pickup_is_airport=step1.get('pickup_is_airport', False),
                            arrival_airline=step1.get('arrival_airline'),
                            arrival_flight_number=step1.get('arrival_flight_number'),
                            arrival_date=step1.get('arrival_date'),
                            arrival_time=step1.get('arrival_time'),
                            salutation=step3.get('salutation'),
                            passenger_full_name=step3.get('passenger_full_name'),
                            payment_option=payment_method,
                            price_breakdown=fare_breakdown,
                            total_amount=Decimal(str(fare_breakdown['total'])),
                            status=RideBooking.STATUS_PENDING,
                        )

                        # Store booking reference (fallback to UUID) in session
                        bref = getattr(booking, 'reference', None) or str(booking.id)
                        self.request.session[f'{self.SESSION_KEY_PREFIX}_booking_id'] = str(bref)
                        self.request.session.modified = True

                        # Handle payment methods that confirm immediately (non-online gateways)
                        immediate_confirmation_methods = [
                            RideBooking.PAYMENT_ON_ARRIVAL,
                            RideBooking.PAYMENT_CARD_ON_ARRIVAL,
                            RideBooking.PAYMENT_MONEY_TRANSFER,
                            RideBooking.PAYMENT_PAYLINK,
                        ]

                        if payment_method in immediate_confirmation_methods:
                            # Confirm booking immediately for non-online payment methods
                            booking.status = RideBooking.STATUS_CONFIRMED
                            booking.save()

                            Payment.objects.create(
                                booking=booking,
                                method=payment_method,
                                amount=booking.total_amount,
                                status=Payment.STATUS_PENDING,
                            )

                            # Determine payment label for notifications
                            payment_label = {
                                RideBooking.PAYMENT_ON_ARRIVAL: 'Pay on Arrival (Cash)',
                                RideBooking.PAYMENT_CARD_ON_ARRIVAL: 'Pay on Arrival (POS/CARD)',
                                RideBooking.PAYMENT_MONEY_TRANSFER: 'Money Transfer Agency',
                                RideBooking.PAYMENT_PAYLINK: 'Paylink',
                            }.get(payment_method, payment_method)

                            # Send notifications
                            EmailService.send_owner_notification(booking, payment_status=payment_label)
                            EmailService.send_customer_notification(booking, payment_status=payment_label)

                            # Go to confirmation
                            return redirect('rides:booking_wizard', step=5)

                        else:
                            # Paynow flow
                            payment = Payment.objects.create(
                                booking=booking,
                                method='PAYNOW',
                                amount=booking.total_amount,
                                status=Payment.STATUS_PENDING,
                            )

                            logger.info('=== WIZARD: Creating Paynow transaction ===')
                            logger.info('Payment ID: %s, Amount: %s', payment.id, payment.amount)
                            paynow = PaynowService()
                            paynow_response = paynow.create_transaction(
                                amount=float(payment.amount),
                                reference=str(payment.id),
                                email=booking.email,
                                phone=booking.phone,
                            )

                            logger.info('=== WIZARD: Paynow response received ===')
                            logger.info('Response keys: %s', paynow_response.keys() if isinstance(paynow_response, dict) else type(paynow_response))
                            logger.info('Response: %s', paynow_response)

                            # Store payment and booking refs/ids in session for return flow
                            bref = getattr(booking, 'reference', None) or str(booking.id)
                            self.request.session['last_payment_id'] = str(payment.id)
                            self.request.session['last_booking_id'] = str(bref)
                            self.request.session.modified = True
                            logger.info('Stored in session: last_payment_id=%s, last_booking_id=%s', payment.id, bref)

                            payment.paynow_response = paynow_response
                            # Extract Paynow reference
                            candidates = [
                                paynow_response.get('paynowreference'),
                                paynow_response.get('paynow_reference'),
                                paynow_response.get('reference'),
                                paynow_response.get('transaction_id'),
                                (paynow_response.get('response') or {}).get('data', {}).get('paynowreference'),
                            ]
                            for c in candidates:
                                if c:
                                    payment.paynow_reference = str(c)
                                    break
                            payment.save()

                            redirect_url = paynow_response.get('redirectUrl') or paynow_response.get('redirect_url')
                            logger.info('Redirect URL extracted: %s', redirect_url)
                            logger.info('All keys in paynow_response: %s', list(paynow_response.keys()) if isinstance(paynow_response, dict) else 'not a dict')
                            if redirect_url:
                                logger.info('Redirecting to PayNow: %s', redirect_url)
                                return redirect(redirect_url)

                            # Fallback: show paynow redirect template
                            logger.warning('No redirect_url found in paynow_response, showing fallback template')
                            bref = getattr(booking, 'reference', None) or str(booking.id)
                            return render(request, 'rides/paynow_redirect.html', {
                                'redirect_url': redirect_url,
                                'payment_id': str(payment.id),
                                'booking_id': str(bref),
                            })

                except Exception as e:
                    logger.exception('Booking creation failed')
                    context = {
                        'step': step,
                        'error': f'Failed to create booking: {e}',
                        'GOOGLE_MAPS_CLIENT_KEY': settings.GOOGLE_MAPS_CLIENT_KEY,
                        'TAXI_OWNER_PHONE': settings.TAXI_OWNER_PHONE,
                    }
                    return render(request, 'rides/booking_wizard/step4.html', context)

            else:
                # Form invalid - but still calculate fare for display
                step1 = wizard_data.get('step1', {})
                step2 = wizard_data.get('step2', {})
                try:
                    distance_km = float(step1.get('distance_km', 0))
                    if distance_km == 0:
                        distance_km = DistanceService.get_distance_km(
                            (step1.get('pickup_latitude'), step1.get('pickup_longitude')),
                            (step1.get('dropoff_latitude'), step1.get('dropoff_longitude')),
                        )
                    fare_breakdown = PricingService.calculate(
                        distance_km=distance_km,
                        num_adults=merged_adult_count(step2.get('num_adults', 1), step2.get('num_kids_seated', 0)),
                        num_kids_seated=0,
                        baby_car_seater=step2.get('baby_car_seater', 0),
                        num_kids_carried=step2.get('num_kids_carried', 0),
                        luggage_count=step2.get('luggage_count', 0),
                    )
                    context_extra = {'fare_breakdown': fare_breakdown}
                except Exception as e:
                    logger.exception('Fare calculation failed on re-render')
                    context_extra = {'fare_error': str(e), 'estimated_fare': 'Unable to calculate'}
                
                context = {
                    'form': form,
                    'step': step,
                    'total_steps': 4,
                    'step1_data': step1,
                    'step2_data': step2,
                    'step3_data': wizard_data.get('step3', {}),
                    'GOOGLE_MAPS_CLIENT_KEY': settings.GOOGLE_MAPS_CLIENT_KEY,
                    'TAXI_OWNER_PHONE': settings.TAXI_OWNER_PHONE,
                    **context_extra,
                }
                return render(request, 'rides/booking_wizard/step4.html', context)

        return redirect('rides:booking_wizard_start')


# ============================================================================
# AJAX Endpoints for Real-Time Calculations & Autocomplete
# ============================================================================

class PlacesAutocompleteView(APIView):
    """
    AJAX endpoint for Google Places Autocomplete.
    
    GET /api/places-autocomplete/?input=pickup+location
    Returns: JSON with suggestions from Google Places API.
    
    Note: This is a sample integration. In production, you'd typically pass
    the request directly to Google's client-side library instead.
    """

    def get(self, request):
        """
        Client-side autocomplete should use Google Places JS API directly.
        This endpoint is here for reference or as a proxy if needed.
        """
        input_text = request.GET.get('input', '').strip()

        if not input_text or len(input_text) < 3:
            return JsonResponse({'suggestions': []})

        # In production, integrate with Google Places API if needed
        # For now, return empty as client-side JS handles autocomplete
        return JsonResponse({'suggestions': []})


class DistanceFareCalcView(APIView):
    """
    AJAX endpoint to calculate distance and estimated fare.
    
    POST /api/distance-fare/
    Payload:
    {
        "pickup_latitude": 17.8252,
        "pickup_longitude": 31.0335,
        "dropoff_latitude": 17.8300,
        "dropoff_longitude": 31.0400,
        "num_adults": 1,
        "num_kids_carried": 0,
        "luggage_count": 0
    }
    
    Returns:
    {
        "distance_km": 12.5,
        "fare_breakdown": { ... },
        "estimated_fare": 50.00
    }
    """

    def post(self, request):
        try:
            data = request.data or request.POST.dict()

            pickup_lat = float(data.get('pickup_latitude'))
            pickup_lng = float(data.get('pickup_longitude'))
            dropoff_lat = float(data.get('dropoff_latitude'))
            dropoff_lng = float(data.get('dropoff_longitude'))

            num_adults = merged_adult_count(data.get('num_adults', 1), data.get('num_kids_seated', 0))
            num_kids_carried = int(data.get('num_kids_carried', 0))
            luggage_count = int(data.get('luggage_count', 0))

            # Calculate distance
            distance_km = DistanceService.get_distance_km(
                (pickup_lat, pickup_lng),
                (dropoff_lat, dropoff_lng),
            )

            # Calculate fare
            fare_breakdown = PricingService.calculate(
                distance_km=distance_km,
                num_adults=num_adults,
                num_kids_seated=0,
                baby_car_seater=request.POST.get('baby_car_seater', 0),
                num_kids_carried=num_kids_carried,
                luggage_count=luggage_count,
            )

            return JsonResponse({
                'distance_km': distance_km,
                'fare_breakdown': fare_breakdown,
                'estimated_fare': fare_breakdown['total'],
            })

        except ValueError as e:
            return JsonResponse(
                {'error': f'Invalid input: {e}'},
                status=400
            )
        except Exception as e:
            logger.exception('Distance/fare calculation failed')
            return JsonResponse(
                {'error': f'Calculation failed: {e}'},
                status=500
            )


# ============================================================================
# Legacy Views (Backward Compatibility)
# ============================================================================

class BookingFormView(TemplateView):
    """Legacy single-page booking form (kept for backward compatibility)."""
    template_name = 'rides/booking_form.html'
    form_class = BookingForm

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['GOOGLE_MAPS_CLIENT_KEY'] = settings.GOOGLE_MAPS_CLIENT_KEY
        ctx['TAXI_OWNER_PHONE'] = settings.TAXI_OWNER_PHONE
        return ctx


class BookingSuccessView(TemplateView):
    """Booking success page."""
    template_name = 'rides/booking_success.html'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        booking = None
        pk_val = self.kwargs.get('pk')
        if pk_val:
            try:
                booking = RideBooking.objects.get(pk=pk_val)
            except Exception:
                try:
                    booking = RideBooking.objects.get(reference=pk_val)
                except RideBooking.DoesNotExist:
                    booking = None
        if not booking:
            # Let original 404 behavior happen
            booking = get_object_or_404(RideBooking, pk=self.kwargs.get('pk'))
        ctx['booking'] = booking
        ctx['TAXI_OWNER_PHONE'] = settings.TAXI_OWNER_PHONE
        
        # Calculate estimated travelling time
        eta_minutes = None
        if booking.distance_km:
            try:
                avg_speed = float(getattr(settings, 'AVERAGE_SPEED_KMH', 40.0))
                eta_minutes = int(round((float(booking.distance_km) / avg_speed) * 60))
            except Exception:
                pass
        ctx['eta_minutes'] = eta_minutes
        
        # Generate WhatsApp message
        whatsapp_message = None
        try:
            from urllib.parse import quote
            payment_status = "Pending"
            if booking.payment_option == "POA":
                payment_status = "Pay on Arrival (Cash)"
            elif booking.payment_option == "PAYNOW":
                payment_status = "Pay Online (Paynow)"
            
                msg = build_booking_message(booking, eta_minutes=eta_minutes, payment_label_override=payment_status)
                phone = settings.TAXI_OWNER_PHONE.lstrip('+')
                whatsapp_message = f"https://wa.me/{phone}?text={quote(msg)}"
        except Exception as e:
            logger.exception('Error generating WhatsApp message: %s', e)
        
        ctx['whatsapp_message'] = whatsapp_message
        return ctx


class CreateBookingView(APIView):
    """API endpoint for creating bookings (REST API alternative to wizard)."""

    def post(self, request):
        serializer = CreateBookingSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        try:
            distance = data.get('distance_km')
            if distance is None:
                distance = DistanceService.get_distance_km(
                    (data.get('pickup_lat'), data.get('pickup_lng')),
                    (data.get('dropoff_lat'), data.get('dropoff_lng')),
                )

            breakdown = PricingService.calculate(
                distance_km=distance,
                num_adults=merged_adult_count(data.get('num_adults', 1), data.get('num_kids_seated', 0)),
                num_kids_seated=0,
                baby_car_seater=data.get('baby_car_seater', 0),
                num_kids_carried=data.get('num_kids_carried', 0),
                luggage_count=data.get('luggage_count', 0),
            )

            # normalize passengers_json which may come as a JSON string or already as a list/dict
            raw_passengers = data.get('passengers_json') or data.get('passengers')
            passengers_json = None
            if raw_passengers:
                if isinstance(raw_passengers, str):
                    try:
                        passengers_json = json.loads(raw_passengers)
                    except Exception:
                        passengers_json = raw_passengers
                else:
                    passengers_json = raw_passengers

            booking = RideBooking.objects.create(
                pickup_address=data['pickup_address'],
                pickup_lat=data.get('pickup_lat'),
                pickup_lng=data.get('pickup_lng'),
                dropoff_address=data['dropoff_address'],
                dropoff_lat=data.get('dropoff_lat'),
                dropoff_lng=data.get('dropoff_lng'),
                distance_km=distance,
                num_adults=merged_adult_count(data.get('num_adults', 1), data.get('num_kids_seated', 0)),
                num_kids_seated=0,
                num_kids_carried=data.get('num_kids_carried', 0),
                luggage_count=data.get('luggage_count', 0),
                phone=data['phone'],
                email=data['email'],
                pickup_date=data.get('pickup_date'),
                pickup_time=data.get('pickup_time'),
                pickup_is_airport=data.get('pickup_is_airport', False),
                arrival_airline=data.get('arrival_airline'),
                arrival_flight_number=data.get('arrival_flight_number'),
                arrival_date=data.get('arrival_date'),
                arrival_time=data.get('arrival_time'),
                salutation=data.get('salutation'),
                passenger_full_name=data.get('passenger_full_name'),
                passengers_json=passengers_json,
                payment_option=data['payment_option'],
                price_breakdown=breakdown,
                total_amount=breakdown['total'],
            )

            if data['payment_option'] == RideBooking.PAYMENT_ON_ARRIVAL:
                booking.status = RideBooking.STATUS_CONFIRMED
                booking.save()
                Payment.objects.create(
                    booking=booking,
                    method=RideBooking.PAYMENT_ON_ARRIVAL,
                    amount=booking.total_amount,
                    status=Payment.STATUS_PENDING,
                )
                EmailService.send_owner_notification(booking, payment_status='PAY ON ARRIVAL')
                EmailService.send_customer_notification(booking, payment_status='PAY ON ARRIVAL')
                return Response(RideBookingSerializer(booking).data, status=status.HTTP_201_CREATED)

            # Paynow flow
            paynow = PaynowService()
            payment = Payment.objects.create(
                booking=booking,
                method='PAYNOW',
                amount=booking.total_amount,
                status=Payment.STATUS_PENDING,
            )

            try:
                paynow_response = paynow.create_transaction(
                    amount=float(payment.amount),
                    reference=str(payment.id),
                    email=booking.email,
                    phone=booking.phone,
                )
                payment.paynow_response = paynow_response
                candidates = [
                    paynow_response.get('paynowreference'),
                    paynow_response.get('paynow_reference'),
                    paynow_response.get('reference'),
                    paynow_response.get('transaction_id'),
                    (paynow_response.get('response') or {}).get('data', {}).get('paynowreference'),
                ]
                for c in candidates:
                    if c:
                        payment.paynow_reference = str(c)
                        break
                payment.save()
                return Response(
                    {
                        'payment': PaymentSerializer(payment).data,
                        'redirect_url': paynow_response.get('redirectUrl') or paynow_response.get('redirect_url'),
                        'poll_url': paynow_response.get('pollUrl') or paynow_response.get('poll_url'),
                    },
                    status=status.HTTP_201_CREATED,
                )
            except Exception as exc:
                logger.exception('Paynow creation failed')
                payment.status = Payment.STATUS_FAILED
                payment.paynow_response = {'error': str(exc)}
                payment.save()
                return Response(
                    {'detail': 'Payment initiation failed'},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR,
                )

        except Exception as exc:
            logger.exception('Booking creation failed')
            return Response(
                {'detail': str(exc)},
                status=status.HTTP_400_BAD_REQUEST,
            )


class PriceEstimateView(APIView):
    """API endpoint for pricing estimates."""

    def post(self, request):
        serializer = PriceEstimateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        try:
            distance = data.get('distance_km')
            if distance is None:
                distance = DistanceService.get_distance_km(
                    (data.get('pickup_lat'), data.get('pickup_lng')),
                    (data.get('dropoff_lat'), data.get('dropoff_lng')),
                )

            breakdown = PricingService.calculate(
                distance_km=distance,
                num_adults=merged_adult_count(data.get('num_adults', 1), data.get('num_kids_seated', 0)),
                num_kids_seated=0,
                baby_car_seater=data.get('baby_car_seater', 0),
                num_kids_carried=data.get('num_kids_carried', 0),
                luggage_count=data.get('luggage_count', 0),
            )

            return Response(breakdown)
        except Exception as exc:
            logger.exception('Price estimate failed')
            return Response(
                {'detail': str(exc)},
                status=status.HTTP_400_BAD_REQUEST,
            )


# ============================================================================
# Paynow Integration Views (Payment Handling)
# ============================================================================

class PaynowResultView(APIView):
    """Server-to-server Paynow webhook for payment notifications."""

    def post(self, request):
        from .services.paynow import PaynowService

        paynow = PaynowService()
        logger.debug(
            'Incoming Paynow webhook: headers=%s body=%s',
            {k: v for k, v in request.META.items() if k.startswith('HTTP_')},
            request.body[:2000],
        )

        if not paynow.verify_notification(request):
            logger.warning('Paynow webhook failed signature verification')
            return Response({'detail': 'Invalid signature'}, status=status.HTTP_403_FORBIDDEN)

        data = request.POST.dict()
        status_text = (data.get('status') or '').strip()
        logger.info('Paynow webhook data: %s', data)

        reference_candidates = [
            data.get('reference'),
            data.get('transaction_id'),
            data.get('paynowreference'),
            data.get('paynow_reference'),
        ]

        payment = None
        for ref in reference_candidates:
            if not ref:
                continue
            payment = Payment.objects.filter(paynow_reference=ref).first()
            if payment:
                logger.debug('Matched payment by paynow_reference: %s', payment.id)
                break
            try:
                payment = Payment.objects.get(pk=ref)
                logger.debug('Matched payment by local id: %s', payment.id)
                break
            except Exception:
                pass

        if not payment:
            payref = data.get('paynowreference') or data.get('paynow_reference') or data.get('paynowReference')
            if payref:
                payment = Payment.objects.filter(paynow_response__icontains=str(payref)).first()
                if payment:
                    logger.debug('Matched payment by searching paynow_response: %s', payment.id)

        if not payment:
            logger.warning('Paynow webhook for unknown reference: %s', reference_candidates)
            return Response({'ok': True})

        payref = data.get('paynowreference') or data.get('paynow_reference') or data.get('paynowReference')
        if payref and not payment.paynow_reference:
            payment.paynow_reference = payref
            payment.save()
            logger.debug('Updated payment %s paynow_reference=%s from webhook', payment.id, payref)

        FAILURE_STATUSES = {'failed', 'cancelled', 'expired'}

        with transaction.atomic():
            p = Payment.objects.select_for_update().get(pk=payment.pk)

            if p.status == Payment.STATUS_PAID:
                logger.info('Webhook for already-PAID payment %s received; ignoring', p.id)
                return Response({'ok': True})

            if status_text and status_text.lower() == 'paid':
                incoming_amount = data.get('amount')
                if incoming_amount:
                    try:
                        inc_amt = Decimal(incoming_amount)
                        if inc_amt != p.amount:
                            logger.error('Webhook amount mismatch for payment %s: expected=%s got=%s', p.id, p.amount, inc_amt)
                            p.paynow_response = p.paynow_response or {}
                            p.paynow_response['last_webhook'] = data
                            p.status = Payment.STATUS_FAILED
                            p.save()
                            return Response({'ok': True})
                    except Exception:
                        logger.warning('Unable to parse amount from webhook: %s', incoming_amount)

                p.status = Payment.STATUS_PAID
                p.save()

                booking = p.booking
                booking.status = RideBooking.STATUS_CONFIRMED
                booking.save()

                EmailService.send_payment_confirmation(booking)
                EmailService.send_owner_notification(booking, payment_status='PAID')

                logger.info('Payment %s marked PAID via webhook', p.id)
                return Response({'ok': True})

            if status_text and status_text.lower() in FAILURE_STATUSES:
                p.status = Payment.STATUS_FAILED
                p.paynow_response = p.paynow_response or {}
                p.paynow_response['last_webhook'] = data
                p.save()
                logger.info('Payment %s marked FAILED via webhook (status=%s)', p.id, status_text)
                return Response({'ok': True})

            p.paynow_response = p.paynow_response or {}
            p.paynow_response['last_webhook'] = data
            p.save()
            logger.info('Payment %s received intermediate webhook status=%s; left as PENDING', p.id, status_text)
            return Response({'ok': True})


class PaynowReturnView(APIView):
    """User redirected back from Paynow."""

    def get(self, request):
        logger.info('=== PAYNOW_RETURN_VIEW HIT ===')
        logger.info('GET parameters: %s', dict(request.GET))
        logger.info('Session keys: %s', list(request.session.keys()))
        logger.info('Session data: %s', {k: v for k, v in request.session.items() if 'booking' in k.lower() or 'payment' in k.lower()})

        reference = request.GET.get('reference')
        logger.info('Reference from GET: %s', reference)
        if not reference:
            last_pid = request.session.get('last_payment_id')
            logger.info('No reference in GET params, checking session. last_payment_id: %s', last_pid)
            if last_pid:
                try:
                    uuid.UUID(last_pid)
                    payment = Payment.objects.filter(pk=last_pid).first()
                    if payment:
                        logger.info('Found payment from session: %s, status=%s', payment.id, payment.status)
                        try:
                            del request.session['last_payment_id']
                            del request.session['last_booking_id']
                            request.session.modified = True
                        except Exception:
                            pass

                        booking = payment.booking
                        try:
                            avg_speed = float(getattr(settings, 'AVERAGE_SPEED_KMH', 40.0))
                        except Exception:
                            avg_speed = 40.0

                        eta_minutes = None
                        if booking.distance_km:
                            try:
                                eta_minutes = int(round((float(booking.distance_km) / avg_speed) * 60))
                            except Exception:
                                pass

                        maps_url = None
                        if booking.pickup_lat and booking.pickup_lng and booking.dropoff_lat and booking.dropoff_lng:
                            maps_url = f"https://www.google.com/maps/dir/?api=1&origin={booking.pickup_lat},{booking.pickup_lng}&destination={booking.dropoff_lat},{booking.dropoff_lng}&travelmode=driving"
                        else:
                            from urllib.parse import urlencode, quote
                            params = {
                                'api': 1,
                                'origin': booking.pickup_address,
                                'destination': booking.dropoff_address,
                                'travelmode': 'driving',
                            }
                            maps_url = "https://www.google.com/maps/dir/?" + urlencode(params)

                        # Generate WhatsApp message
                        whatsapp_message = None
                        try:
                            payment_status = "PAID ✅" if payment.status == Payment.STATUS_PAID else "PENDING ⏳"
                            msg = build_booking_message(booking, eta_minutes=eta_minutes, payment_label_override=payment_status)
                            phone = settings.TAXI_OWNER_PHONE.lstrip('+')
                            whatsapp_message = f"https://wa.me/{phone}?text={quote(msg)}"
                        except Exception as e:
                            logger.exception('Error generating WhatsApp message for paynow_return: %s', e)

                        poll_url = reverse('rides:paynow_poll', args=[payment.pk])
                        logger.info('Rendering return page with payment. poll_url: %s', poll_url)
                        return render(request, 'rides/paynow_return.html', {
                            'payment': payment,
                            'booking': booking,
                            'eta_minutes': eta_minutes,
                            'maps_url': maps_url,
                            'whatsapp_message': whatsapp_message,
                            'poll_url': poll_url,
                            'TAXI_OWNER_PHONE': settings.TAXI_OWNER_PHONE,
                        })
                except Exception:
                    logger.exception('Error while attempting to use session last_payment_id')

            logger.warning('No payment found via session, showing generic message')

            return render(request, 'rides/paynow_return.html', {
                'message': 'Check your email for payment confirmation.',
                'TAXI_OWNER_PHONE': settings.TAXI_OWNER_PHONE,
            })

        payment = None
        try:
            uuid.UUID(reference)
            payment = Payment.objects.filter(pk=reference).first()
            if payment:
                logger.info('Found payment by UUID reference: %s', payment.id)
        except Exception:
            pass

        if not payment:
            logger.info('Reference not a UUID, searching by paynow_reference: %s', reference)
            candidates = Payment.objects.filter(paynow_reference=reference).order_by('-created_at')
            if candidates.exists():
                payment = candidates.filter(status=Payment.STATUS_PENDING).first() or candidates.first()
                logger.info('Found payment by paynow_reference: %s', payment.id if payment else None)

        if not payment:
            logger.warning('Paynow return for unknown reference: %s', reference)
            return render(request, 'rides/error.html', {
                'message': 'Payment not found.',
                'TAXI_OWNER_PHONE': settings.TAXI_OWNER_PHONE,
            })

        logger.info('Processing payment %s with status %s', payment.id, payment.status)
        booking = payment.booking
        try:
            avg_speed = float(getattr(settings, 'AVERAGE_SPEED_KMH', 40.0))
        except Exception:
            avg_speed = 40.0

        eta_minutes = None
        if booking.distance_km:
            try:
                eta_minutes = int(round((float(booking.distance_km) / avg_speed) * 60))
            except Exception:
                pass

        maps_url = None
        if booking.pickup_lat and booking.pickup_lng and booking.dropoff_lat and booking.dropoff_lng:
            maps_url = f"https://www.google.com/maps/dir/?api=1&origin={booking.pickup_lat},{booking.pickup_lng}&destination={booking.dropoff_lat},{booking.dropoff_lng}&travelmode=driving"
        else:
            from urllib.parse import urlencode
            params = {
                'api': 1,
                'origin': booking.pickup_address,
                'destination': booking.dropoff_address,
                'travelmode': 'driving',
            }
            maps_url = "https://www.google.com/maps/dir/?" + urlencode(params)

        poll_url = reverse('rides:paynow_poll', args=[payment.pk])
        logger.info('Rendering return page for referenced payment. poll_url: %s', poll_url)

        return render(request, 'rides/paynow_return.html', {
            'payment': payment,
            'booking': booking,
            'TAXI_OWNER_PHONE': settings.TAXI_OWNER_PHONE,
            'eta_minutes': eta_minutes,
            'maps_url': maps_url,
            'poll_url': poll_url,
        })


class PaynowPollView(APIView):
    """AJAX endpoint to poll payment status."""

    def get(self, request, pk):
        paynow = PaynowService()
        payment = get_object_or_404(Payment, pk=pk)

        logger.info(f'=== PAYNOW_POLL START: payment_id={payment.pk}, current_status={payment.status} ===')

        if payment.status == Payment.STATUS_PAID:
            logger.info(f'Payment already PAID')
            return Response({'paid': True, 'status': 'PAID', 'message': 'Already confirmed'})

        pr = payment.paynow_response or {}
        poll_url = (
            pr.get('pollUrl')
            or pr.get('poll_url')
            or (pr.get('response') or {}).get('poll_url')
            or (pr.get('response') or {}).get('pollUrl')
            or (pr.get('response') or {}).get('data', {}).get('poll_url')
        )

        if not poll_url and payment.paynow_reference:
            poll_url = f"https://www.paynow.co.zw/Interface/CheckPayment/?guid={payment.paynow_reference}"

        logger.info(f'Poll URL: {poll_url}')

        if not poll_url:
            logger.warning('No poll URL available for payment %s', payment.id)
            return Response(
                {'error': 'no_poll_url', 'message': 'No poll URL available. Check payment status manually with booking ID.', 'paid': False},
                status=status.HTTP_200_OK,
            )

        try:
            status_obj = paynow.verify_payment(poll_url)
        except Exception as e:
            logger.exception('Error checking Paynow status for %s: %s', payment.id, e)
            return Response(
                {'error': 'verify_failed', 'message': f'Could not verify payment: {str(e)}', 'paid': False, 'status': 'Error checking status'},
                status=status.HTTP_200_OK,
            )

        logger.debug('Paynow poll result for %s: %s', poll_url, status_obj)
        logger.info('=== PAYNOOW_POLL_VIEW: verify_payment returned ===')
        logger.info(f'status_obj: {status_obj}')
        logger.info(f'status_obj.get("paid"): {status_obj.get("paid")}')
        logger.info(f'status_obj.get("status"): {status_obj.get("status")}')

        if status_obj.get('paid'):
            logger.info('Poll result: PAYMENT IS PAID! Updating database...')
            with transaction.atomic():
                p = Payment.objects.select_for_update().get(pk=payment.pk)
                if p.status == Payment.STATUS_PAID:
                    logger.info('Poll: payment %s already PAID', p.id)
                    return Response({'paid': True, 'status': status_obj.get('status')})

                p.status = Payment.STATUS_PAID
                p.save()

                booking = p.booking
                booking.status = RideBooking.STATUS_CONFIRMED
                booking.save()

            EmailService.send_payment_confirmation(booking)
            EmailService.send_owner_notification(booking, payment_status='PAID')

            return Response({'paid': True, 'status': status_obj.get('status')})

        logger.info('Poll result: Payment still pending or failed')
        return Response({'paid': False, 'status': status_obj.get('status'), 'message': 'Payment not yet confirmed'})
