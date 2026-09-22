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
from typing import Optional

from django.shortcuts import render, redirect, get_object_or_404
from django.views.generic import View, TemplateView
from django.http import JsonResponse, Http404
from django.middleware.csrf import get_token
from django.conf import settings
from django.utils import timezone
from django.db import transaction
from django.urls import reverse
from django.core.exceptions import ValidationError



from .models import RideBooking, Payment
import datetime
from .forms import (
    Step1PickupDropoffForm,
    Step2PassengersLuggageForm,
    ChauffeurPassengersForm,
    Step3ContactExtraForm,
    Step4FarePaymentForm,
    Step5ConfirmationForm,
    BookingForm,
    ChauffeurStep1Form,
    ChauffeurStep2Form,
    ChauffeurStep4ContactForm,
    RescheduleBookingForm,
    UpdateFlightDetailsForm,
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


def _logo_url():
    """Return the static URL for the Easy Transit logo, or None if not uploaded yet."""
    from django.templatetags.static import static
    from django.contrib.staticfiles.finders import find
    if find('img/logo.png'):
        return static('img/logo.png')
    return None


def _calculate_fare(distance_km, num_adults, num_kids_seated=0, baby_car_seater=0, num_kids_carried=0, luggage_count=0, hand_luggage_count=0, pickup_time=None, stops=None, is_return_trip=False, return_time=None, return_distance_km=None):
    """Pick city vs long-distance pricing automatically based on distance threshold.

    The ride type is set by the outbound distance; a return leg on its own route is
    then priced under the same rules, on its own distance.
    """
    if PricingService.is_long_distance(distance_km):
        return PricingService.calculate_long_distance(
            distance_km=distance_km,
            num_adults=num_adults,
            luggage_count=luggage_count,
            hand_luggage_count=hand_luggage_count,
            pickup_time=pickup_time,
            stops=stops,
            is_return_trip=is_return_trip,
            return_time=return_time,
            return_distance_km=return_distance_km,
        )
    return PricingService.calculate(
        distance_km=distance_km,
        num_adults=num_adults,
        num_kids_seated=num_kids_seated,
        baby_car_seater=baby_car_seater,
        num_kids_carried=num_kids_carried,
        luggage_count=luggage_count,
        hand_luggage_count=hand_luggage_count,
        pickup_time=pickup_time,
        stops=stops,
        is_return_trip=is_return_trip,
        return_time=return_time,
        return_distance_km=return_distance_km,
    )


def _as_decimal(value):
    """Decimal for the database, or None when the value is missing or unusable."""
    if value is None or value == '':
        return None
    try:
        return Decimal(str(value))
    except Exception:
        return None


def _return_leg_distance(step1):
    """Distance of the return leg when it runs its own route, else None.

    Measured from the return coordinates the customer picked; falls back to the
    value the browser already worked out if the lookup fails.
    """
    if not step1.get('is_return_trip') or not step1.get('return_use_different_points'):
        return None

    cached = step1.get('return_distance_km')
    coords = (
        step1.get('return_pickup_latitude'), step1.get('return_pickup_longitude'),
        step1.get('return_dropoff_latitude'), step1.get('return_dropoff_longitude'),
    )
    if not all(coords):
        return float(cached) if cached else None

    try:
        return DistanceService.get_distance_km(
            (coords[0], coords[1]), (coords[2], coords[3]),
        )
    except Exception:
        logger.exception('Could not measure the return leg; falling back to the submitted distance')
        try:
            return float(cached) if cached else None
        except (TypeError, ValueError):
            return None

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

def build_booking_message(booking, eta_minutes=None, payment_label_override: Optional[str] = None):
    """Return a multi-line plain-text summary of the booking suitable for WhatsApp sharing."""
    try:
        parts = []
        ride_type = getattr(booking, 'ride_type', 'city')
        if ride_type == 'chauffeur':
            parts.append("Hello Easy Transit, I have just booked a *Chauffeur Drive* on your platform 🚗")
        elif ride_type == 'long_distance':
            parts.append("Hello Easy Transit, I have just booked a *Long Distance* ride on your platform 🚗")
        else:
            parts.append("Hello Easy Transit, I have just booked a ride on your platform 🚗")
        parts.append("")
        parts.append("*Booking Details:*")
        parts.append("")
        bid = getattr(booking, 'reference', None) or str(booking.id)
        parts.append(f"*Booking ID:* {bid}")

        if ride_type == 'chauffeur':
            pkg_label = getattr(booking, 'chauffeur_package_label', None) or f"{getattr(booking, 'chauffeur_hours', '?')} Hour Chauffeur Drive"
            parts.append(f"*Service:* {pkg_label}")
        elif ride_type == 'long_distance':
            parts.append("*Service:* Long Distance")

        # Pickup with optional date/time
        pickup_line = f"*Pickup:* {getattr(booking, 'pickup_display', None) or booking.pickup_address}"
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

            # Extra flight context the passenger added (or corrected later)
            extra_flight = []
            if getattr(booking, 'flight_departure_airport', ''):
                extra_flight.append(f"Departing from: {booking.flight_departure_airport}")
            if getattr(booking, 'flight_connection_details', ''):
                extra_flight.append(f"Connection: {booking.flight_connection_details}")
            if extra_flight:
                parts.append("*Flight details:* " + ", ".join(extra_flight))
            if getattr(booking, 'flight_notes', ''):
                parts.append(f"*Flight notes:* {booking.flight_notes}")

        if ride_type != 'chauffeur':
            parts.append(f"*Dropoff:* {getattr(booking, 'dropoff_display', None) or booking.dropoff_address}")
            parts.append(f"*Distance:* {booking.distance_km} km")
        else:
            aet = getattr(booking, 'approximate_end_time', None)
            if aet:
                try:
                    parts.append(f"*Approx End Time:* {aet.strftime('%H:%M')}")
                except Exception:
                    parts.append(f"*Approx End Time:* {aet}")
            if getattr(booking, 'extra_instructions', None):
                parts.append(f"*Trip Summary:* {booking.extra_instructions}")
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

        if getattr(booking, 'hand_luggage_count', 0):
            parts.append(f"*Hand luggage:* {booking.hand_luggage_count} item(s)")

        stops = getattr(booking, 'stops_json', None) or []
        if stops:
            parts.append("")
            parts.append("*Stops along the way:*")
            for idx, stop in enumerate(stops, start=1):
                desc = (stop.get('description') or 'Stop').strip()
                mins = stop.get('minutes')
                fee = stop.get('fee') or 0
                fee_text = f"${fee:.2f}" if fee else "Free"
                parts.append(f"  {idx}. {desc} - up to {mins} min ({fee_text})")

        breakdown = getattr(booking, 'price_breakdown', None) or {}
        if breakdown.get('night_surcharge'):
            parts.append(f"*Night pickup surcharge:* ${breakdown['night_surcharge']:.2f}")

        if getattr(booking, 'is_return_trip', False):
            parts.append("")
            return_line = "*Return trip:* Yes"
            rd = getattr(booking, 'return_date', None)
            rt = getattr(booking, 'return_time', None)
            if rd:
                try:
                    return_line += f" - {rd.isoformat()}"
                except Exception:
                    return_line += f" - {rd}"
            if rt:
                try:
                    return_line += f" at {rt.strftime('%H:%M')}"
                except Exception:
                    return_line += f" at {rt}"
            parts.append(return_line)
            if getattr(booking, 'return_uses_different_points', False):
                parts.append(f"*Return pickup:* {booking.return_pickup_display}")
                parts.append(f"*Return dropoff:* {booking.return_dropoff_display}")
                if getattr(booking, 'return_distance_km', None):
                    parts.append(f"*Return distance:* {booking.return_distance_km} km")
            if breakdown.get('return_leg_fee'):
                parts.append(f"*Return leg fare:* ${breakdown['return_leg_fee']:.2f}")
            if breakdown.get('return_night_surcharge'):
                parts.append(f"*Night return surcharge:* ${breakdown['return_night_surcharge']:.2f}")

        if getattr(booking, 'passengers_over_limit', False):
            parts.append("⚠️ *Passengers exceed standard package limit — follow up required*")

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
    - Step 1 (GET): Show the trip: route, schedule, flight and stops
    - Step 1 (POST): Validate locations, save to session, redirect to Step 2
    - Step 2 (GET): Show passenger counts and luggage
    - Step 2 (POST): Validate and save, redirect to Step 3
    - Step 3 (GET): Show contact details and the name for the driver's placard
    - Step 3 (POST): Validate and save, redirect to Step 4
    - Step 4 (GET): Show fare breakdown and the full review, editable via modal
    - Step 5 (GET): Show the total and the payment choices, nothing else
    - Step 5 (POST): Create booking + payment, redirect to Step 6 or payment gateway
    - Step 6 (GET): Show confirmation (display-only)

    Each screen owns one subject, and the session keys follow it: 'step1' is the
    trip, 'step2' the people, 'step3' the contact details.
    """

    VALID_STEPS = [1, 2, 3, 4, 5, 6]
    TOTAL_STEPS = 5  # Steps 1-5 collect input; step 6 is the confirmation page

    # One source of truth for the progress rail: (number, heading, rail label).
    # The short label has to survive five columns on a narrow screen.
    STEP_LABELS = (
        (1, 'My trip details', 'Trip'),
        (2, 'Passengers & luggage', 'Guests'),
        (3, 'Contact details', 'Contact'),
        (4, 'Check your booking', 'Review'),
        (5, 'Payment', 'Pay'),
    )
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

    def base_context(self, request, step):
        """Context every wizard screen needs.

        Built in one place so an error re-render can never ship a thinner
        context than the happy path and quietly drop half a form.
        """
        # A completed step can be reopened; the current and later ones cannot.
        rail = [{
            'number': number,
            'label': label,
            'short': short,
            'state': 'done' if number < step else ('current' if number == step else 'todo'),
        } for number, label, short in self.STEP_LABELS]

        spans = max(self.TOTAL_STEPS - 1, 1)
        heading = next((l for n, l, _ in self.STEP_LABELS if n == step), '')

        return {
            'step': step,
            'total_steps': self.TOTAL_STEPS,
            'show_progress': step <= self.TOTAL_STEPS,
            'wizard_rail': rail,
            'step_heading': heading,
            # Lets the shell play the exit transition before a Back navigation,
            # without every step template having to hand over its own target.
            'prev_step': step - 1 if step > 1 else None,
            # How far along the rail the fill reaches, 0-1, as a scaleX factor
            'progress_ratio': '%.4f' % (max(step - 1, 0) / spans),
            # The form only introduces itself once; after step 1 it is noise.
            'show_banner': step == 1,
            'GOOGLE_MAPS_CLIENT_KEY': settings.GOOGLE_MAPS_CLIENT_KEY,
            'TAXI_OWNER_PHONE': settings.TAXI_OWNER_PHONE,
            'TAXI_OWNER_EMAIL': settings.TAXI_OWNER_EMAIL,
            'csrf_token': get_token(request),
            'logo_url': _logo_url(),
            'ld_threshold_km': PricingService._get_ld_threshold(),
            'ld_cfg': PricingService.get_long_distance_cfg(),
            'booking_limits': PricingService.get_booking_limits(),
            'stop_tiers': PricingService.get_stop_tiers(),
            'night_cfg': PricingService.get_night_cfg(),
            'hand_luggage_cfg': PricingService.get_hand_luggage_cfg(),
            'return_discount_percent': PricingService.get_return_discount_percent(),
            'money_transfer_recipient': PricingService.get_money_transfer_recipient(),
        }

    @staticmethod
    def coords_present(step1):
        """True when both ends of the outbound trip have usable coordinates."""
        def ok(value):
            try:
                return value is not None and str(value) != '' and float(value) == float(value)
            except Exception:
                return False

        return all(ok(step1.get(key)) for key in (
            'pickup_latitude', 'pickup_longitude', 'dropoff_latitude', 'dropoff_longitude',
        ))

    def fare_context(self, wizard_data):
        """Price the booking as it currently stands in the session.

        Shared by the review step, the payment step and the booking-creation
        POST, so all three always quote the same number. Returns context keys
        only - the caller decides what to render.
        """
        step1 = wizard_data.get('step1', {})
        step2 = wizard_data.get('step2', {})

        try:
            distance_km = float(step1.get('distance_km', 0))
            if distance_km == 0:
                distance_km = DistanceService.get_distance_km(
                    (step1.get('pickup_latitude'), step1.get('pickup_longitude')),
                    (step1.get('dropoff_latitude'), step1.get('dropoff_longitude')),
                )
                step1['distance_km'] = distance_km

                # Keep the session copy JSON-serializable
                def iso(value):
                    return value.isoformat() if value is not None and hasattr(value, 'isoformat') else value

                session_step1 = dict(step1)
                for key in ('pickup_date', 'pickup_time', 'arrival_date', 'arrival_time'):
                    session_step1[key] = iso(session_step1.get(key))
                self.request.session[self.get_session_key('step1')] = session_step1
                self.request.session.modified = True

            fare_breakdown = _calculate_fare(
                distance_km=distance_km,
                num_adults=merged_adult_count(step2.get('num_adults', 1), step2.get('num_kids_seated', 0)),
                baby_car_seater=step2.get('baby_car_seater', 0),
                num_kids_carried=step2.get('num_kids_carried', 0),
                luggage_count=step2.get('luggage_count', 0),
                hand_luggage_count=step2.get('hand_luggage_count', 0),
                pickup_time=step1.get('pickup_time'),
                stops=step1.get('stops', []),
                is_return_trip=step1.get('is_return_trip', False),
                return_time=step1.get('return_time'),
                return_distance_km=_return_leg_distance(step1),
            )
            return {
                'fare_breakdown': fare_breakdown,
                'estimated_fare': fare_breakdown['total'],
                'ride_type': fare_breakdown.get('ride_type', 'city'),
                'paynow_rule': PricingService.get_paynow_rule(),
                'paynow_allowed': PricingService.paynow_allowed(fare_breakdown['total']),
            }
        except Exception as exc:
            logger.exception('Fare calculation failed')
            return {
                'fare_error': str(exc),
                'estimated_fare': 'Unable to calculate',
                'paynow_rule': PricingService.get_paynow_rule(),
                'paynow_allowed': False,
            }

    def payment_context(self, request, wizard_data, **overrides):
        """Context for the payment step - the total and how to pay it."""
        step1 = wizard_data.get('step1', {})
        distance_km = float(step1.get('distance_km') or 0)

        context = self.base_context(request, 5)
        context.update({
            'step1_data': step1,
            'step2_data': wizard_data.get('step2', {}),
            'step3_data': wizard_data.get('step3', {}),
            'form': Step4FarePaymentForm(),
            # Repeated here because it changes what the customer is agreeing to
            # pay; it is deliberately not shown on the screens in between.
            'is_long_distance': PricingService.is_long_distance(distance_km) if distance_km > 0 else False,
        })
        context.update(self.fare_context(wizard_data))
        context.update(overrides)
        return context

    def review_context(self, request, wizard_data, **overrides):
        """Context for the review screen, including the edit modal's forms.

        The modal re-renders every wizard field, so it needs each step's form
        bound to the saved answers.
        """
        step1 = wizard_data.get('step1', {})
        step2 = wizard_data.get('step2', {})
        step3 = wizard_data.get('step3', {})

        context = self.base_context(request, 4)
        context.update({
            'step1_data': step1,
            'step2_data': step2,
            'step3_data': step3,
            'trip_form': Step1PickupDropoffForm(initial=step1),
            'trip_type_chosen': True,
            'people_form': Step2PassengersLuggageForm(initial=step2),
            'contact_form': Step3ContactExtraForm(initial=step3),
        })
        context.update(overrides)
        return context

    @staticmethod
    def build_step1_payload(cleaned):
        """Flatten a validated step-1 form into the session's step1 dict.

        Shared by the wizard's own step 1 and the review page's edit modal, so
        the two can never disagree about what a saved trip looks like. Dates and
        times are stored as ISO strings to keep the session JSON-serializable.
        """
        def iso(value):
            return value.isoformat() if value is not None and hasattr(value, 'isoformat') else value

        return {
            'pickup_address': cleaned['pickup_address'],
            'pickup_latitude': cleaned['pickup_latitude'],
            'pickup_longitude': cleaned['pickup_longitude'],
            'dropoff_address': cleaned['dropoff_address'],
            'dropoff_latitude': cleaned['dropoff_latitude'],
            'dropoff_longitude': cleaned['dropoff_longitude'],
            'distance_km': cleaned.get('distance_km') or 0,
            'pickup_date': iso(cleaned.get('pickup_date')),
            'pickup_time': iso(cleaned.get('pickup_time')),
            'pickup_point_detail': cleaned.get('pickup_point_detail') or '',
            'dropoff_point_detail': cleaned.get('dropoff_point_detail') or '',
            'pickup_is_airport': bool(cleaned.get('pickup_is_airport')),
            'pickup_airport_terminal': cleaned.get('pickup_airport_terminal') or '',
            'arrival_airline': cleaned.get('arrival_airline'),
            'arrival_flight_number': cleaned.get('arrival_flight_number'),
            'arrival_date': iso(cleaned.get('arrival_date')),
            'arrival_time': iso(cleaned.get('arrival_time')),
            'flight_departure_airport': cleaned.get('flight_departure_airport') or '',
            'flight_connection_details': cleaned.get('flight_connection_details') or '',
            'flight_notes': cleaned.get('flight_notes') or '',
            'is_return_trip': bool(cleaned.get('is_return_trip')),
            'return_date': iso(cleaned.get('return_date')),
            'return_time': iso(cleaned.get('return_time')),
            'return_use_different_points': bool(cleaned.get('return_use_different_points')),
            'return_pickup_address': cleaned.get('return_pickup_address') or '',
            'return_pickup_latitude': cleaned.get('return_pickup_latitude'),
            'return_pickup_longitude': cleaned.get('return_pickup_longitude'),
            'return_pickup_point_detail': cleaned.get('return_pickup_point_detail') or '',
            'return_dropoff_address': cleaned.get('return_dropoff_address') or '',
            'return_dropoff_latitude': cleaned.get('return_dropoff_latitude'),
            'return_dropoff_longitude': cleaned.get('return_dropoff_longitude'),
            'return_dropoff_point_detail': cleaned.get('return_dropoff_point_detail') or '',
            'return_distance_km': cleaned.get('return_distance_km'),
            # Stops belong to the route, so they travel with the trip data.
            'stops': cleaned.get('stops') or [],
            'stops_json': json.dumps(cleaned.get('stops') or []),
        }

    @staticmethod
    def build_people_payload(cleaned, post_data):
        """Flatten a validated step-2 form into the session's step2 dict."""
        return {
            'num_adults': merged_adult_count(cleaned['num_adults'], post_data.get('num_kids_seated', 0)),
            'num_kids_seated': 0,
            'baby_car_seater': cleaned['baby_car_seater'],
            'num_kids_carried': cleaned['num_kids_carried'],
            'luggage_count': cleaned['luggage_count'],
            'hand_luggage_count': cleaned.get('hand_luggage_count') or 0,
            'passengers_json': post_data.get('passengers_json') or '[]',
        }

    @staticmethod
    def build_contact_payload(cleaned):
        """Flatten a validated contact form into the session's step3 dict."""
        return {
            'phone': cleaned['phone'],
            'email': cleaned['email'],
            'extra_instructions': cleaned['extra_instructions'],
            'salutation': cleaned.get('salutation'),
            'passenger_full_name': cleaned.get('passenger_full_name'),
        }

    def get(self, request, step=1):
        """Render the form for the current step."""
        step = int(step)

        if step not in self.VALID_STEPS:
            return redirect('rides:booking_wizard_start')

        context = self.base_context(request, step)

        # Restore previous step data from session if user navigates back
        wizard_data = self.get_wizard_data()

        # Allow callers to force-start a new booking by passing ?reset=1 (or true/yes)
        if step == 1:
            reset_param = (request.GET.get('reset') or '').lower()
            # /booking/ is the entry point, so it starts a clean booking. Going
            # back to /booking/step/1/ from step 2 still restores the answers.
            entering = bool(request.resolver_match) and                 request.resolver_match.url_name == 'booking_wizard_start'
            if entering or reset_param in ('1', 'true', 'yes'):
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
            context['form'] = Step1PickupDropoffForm(initial=wizard_data.get('step1', {}))
            # Pass step1 saved values so template can populate hidden coords
            context['step1_data'] = wizard_data.get('step1', {})
            # Neither trip-type card is preselected until step 1 has been saved
            context['trip_type_chosen'] = 'step1' in wizard_data
            return render(request, 'rides/booking_wizard/step1.html', context)

        elif step == 2:
            # Check that Step 1 is complete
            if 'step1' not in wizard_data:
                return redirect('rides:booking_wizard', step=1)

            context['people_form'] = Step2PassengersLuggageForm(initial=wizard_data.get('step2', {}))
            context['step1_data'] = wizard_data['step1']
            context['step2_data'] = wizard_data.get('step2', {})
            return render(request, 'rides/booking_wizard/step2.html', context)

        elif step == 3:
            if 'step2' not in wizard_data:
                return redirect('rides:booking_wizard', step=2)

            context['contact_form'] = Step3ContactExtraForm(initial=wizard_data.get('step3', {}))
            context['step1_data'] = wizard_data.get('step1', {})
            return render(request, 'rides/booking_wizard/step3.html', context)

        elif step == 4:
            if 'step3' not in wizard_data:
                return redirect('rides:booking_wizard', step=3)

            # Without coordinates there is nothing to price
            if not self.coords_present(wizard_data.get('step1', {})):
                return redirect(reverse('rides:booking_wizard', kwargs={'step': 1}) + '?missing_coords=1')

            context = self.review_context(request, wizard_data)
            context.update(self.fare_context(wizard_data))
            context['step1_data'] = wizard_data.get('step1', {})
            return render(request, 'rides/booking_wizard/step4.html', context)

        elif step == 5:
            if 'step3' not in wizard_data:
                return redirect('rides:booking_wizard', step=3)

            if not self.coords_present(wizard_data.get('step1', {})):
                return redirect(reverse('rides:booking_wizard', kwargs={'step': 1}) + '?missing_coords=1')

            return render(request, 'rides/booking_wizard/step5.html',
                          self.payment_context(request, wizard_data))

        elif step == 6:
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
            return render(request, 'rides/booking_wizard/step6.html', context)

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
                self.request.session[self.get_session_key('step1')] = self.build_step1_payload(form.cleaned_data)
                self.request.session.modified = True
                return redirect('rides:booking_wizard', step=2)

            context = self.base_context(request, step)
            context['form'] = form
            context['step1_data'] = wizard_data.get('step1', {})
            # They got far enough to submit, so a card was already picked
            context['trip_type_chosen'] = True
            return render(request, 'rides/booking_wizard/step1.html', context)

        elif step == 2:
            if 'step1' not in wizard_data:
                return redirect('rides:booking_wizard', step=1)

            people_form = Step2PassengersLuggageForm(request.POST)
            if people_form.is_valid():
                self.request.session[self.get_session_key('step2')] = self.build_people_payload(
                    people_form.cleaned_data, request.POST
                )
                self.request.session.modified = True
                return redirect('rides:booking_wizard', step=3)

            context = self.base_context(request, step)
            context.update({
                'people_form': people_form,
                'step1_data': wizard_data.get('step1', {}),
                'step2_data': wizard_data.get('step2', {}),
            })
            return render(request, 'rides/booking_wizard/step2.html', context)

        elif step == 3:
            if 'step2' not in wizard_data:
                return redirect('rides:booking_wizard', step=2)

            contact_form = Step3ContactExtraForm(request.POST)
            if contact_form.is_valid():
                self.request.session[self.get_session_key('step3')] = self.build_contact_payload(
                    contact_form.cleaned_data
                )
                self.request.session.modified = True
                return redirect('rides:booking_wizard', step=4)

            context = self.base_context(request, step)
            context.update({
                'contact_form': contact_form,
                'step1_data': wizard_data.get('step1', {}),
            })
            return render(request, 'rides/booking_wizard/step3.html', context)

        elif step == 5:
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

                    return_distance_km = _return_leg_distance(step1)

                    fare_breakdown = _calculate_fare(
                        distance_km=distance_km,
                        num_adults=merged_adult_count(step2.get('num_adults', 1), step2.get('num_kids_seated', 0)),
                        baby_car_seater=step2.get('baby_car_seater', 0),
                        num_kids_carried=step2.get('num_kids_carried', 0),
                        luggage_count=step2.get('luggage_count', 0),
                        hand_luggage_count=step2.get('hand_luggage_count', 0),
                        pickup_time=step1.get('pickup_time'),
                        stops=step1.get('stops', []),
                        is_return_trip=step1.get('is_return_trip', False),
                        return_time=step1.get('return_time'),
                        return_distance_km=return_distance_km,
                    )

                    # Paynow carries high fees on small amounts, so it is only offered
                    # at or above the configured minimum. Re-checked here because the
                    # payment radio can be re-enabled client-side.
                    if payment_method == RideBooking.PAYMENT_PAYNOW and not PricingService.paynow_allowed(fare_breakdown['total']):
                        paynow_rule = PricingService.get_paynow_rule()
                        context = self.payment_context(
                            request, wizard_data,
                            form=form,
                            paynow_rule=paynow_rule,
                            paynow_allowed=False,
                            error_message=paynow_rule['NOTE'],
                        )
                        return render(request, 'rides/booking_wizard/step5.html', context)

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
                            hand_luggage_count=step2.get('hand_luggage_count', 0),
                            stops_json=fare_breakdown.get('stops') or [],
                            is_return_trip=step1.get('is_return_trip', False),
                            return_date=step1.get('return_date'),
                            return_time=step1.get('return_time'),
                            return_uses_different_points=step1.get('return_use_different_points', False),
                            return_pickup_address=step1.get('return_pickup_address') or '',
                            return_pickup_lat=_as_decimal(step1.get('return_pickup_latitude')),
                            return_pickup_lng=_as_decimal(step1.get('return_pickup_longitude')),
                            return_pickup_point_detail=step1.get('return_pickup_point_detail') or '',
                            return_dropoff_address=step1.get('return_dropoff_address') or '',
                            return_dropoff_lat=_as_decimal(step1.get('return_dropoff_latitude')),
                            return_dropoff_lng=_as_decimal(step1.get('return_dropoff_longitude')),
                            return_dropoff_point_detail=step1.get('return_dropoff_point_detail') or '',
                            return_distance_km=_as_decimal(return_distance_km),
                            phone=step3['phone'],
                            email=step3['email'],
                            extra_instructions=step3.get('extra_instructions', ''),
                            pickup_date=step1.get('pickup_date'),
                            pickup_time=step1.get('pickup_time'),
                            pickup_point_detail=step1.get('pickup_point_detail') or '',
                            dropoff_point_detail=step1.get('dropoff_point_detail') or '',
                            pickup_is_airport=step1.get('pickup_is_airport', False),
                            pickup_airport_terminal=step1.get('pickup_airport_terminal') or '',
                            arrival_airline=step1.get('arrival_airline'),
                            arrival_flight_number=step1.get('arrival_flight_number'),
                            arrival_date=step1.get('arrival_date'),
                            arrival_time=step1.get('arrival_time'),
                            flight_departure_airport=step1.get('flight_departure_airport') or '',
                            flight_connection_details=step1.get('flight_connection_details') or '',
                            flight_notes=step1.get('flight_notes') or '',
                            salutation=step3.get('salutation'),
                            passenger_full_name=step3.get('passenger_full_name'),
                            payment_option=payment_method,
                            paylink_card_name=form.cleaned_data.get('paylink_card_name') or '',
                            paylink_email=form.cleaned_data.get('paylink_email') or '',
                            price_breakdown=fare_breakdown,
                            total_amount=Decimal(str(fare_breakdown['total'])),
                            ride_type=fare_breakdown.get('ride_type', RideBooking.RIDE_TYPE_CITY),
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
                            return redirect('rides:booking_wizard', step=6)

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
                    context = self.payment_context(
                        request, wizard_data,
                        form=form,
                        error_message=f'Failed to create booking: {e}',
                    )
                    return render(request, 'rides/booking_wizard/step5.html', context)

            else:
                # No payment method chosen - redraw the page. payment_context
                # re-prices from the session, so the total cannot drift from
                # the one the customer was just looking at.
                context = self.payment_context(request, wizard_data, form=form)
                return render(request, 'rides/booking_wizard/step5.html', context)

        return redirect('rides:booking_wizard_start')


class BookingWizardEditView(MultiStepBookingWizardView):
    """Saves edits made from the review page's single Edit modal.

    The modal submits every wizard field at once, so each step's form can be
    bound and validated in full rather than in fragments. That keeps one set of
    rules — the wizard's own — instead of a second, looser path to the same
    session data. The page reloads afterwards, which re-prices the booking.
    """

    def get(self, request, *args, **kwargs):
        # Nothing to render here; the modal lives on the review page.
        return redirect('rides:booking_wizard', step=4)

    def post(self, request, *args, **kwargs):
        wizard_data = self.get_wizard_data()
        if 'step3' not in wizard_data:
            return JsonResponse({'ok': False, 'errors': {'__all__': ['Your booking session has expired. Please start again.']}}, status=400)

        trip_form = Step1PickupDropoffForm(request.POST)
        people_form = Step2PassengersLuggageForm(request.POST)
        contact_form = Step3ContactExtraForm(request.POST)

        forms = (trip_form, people_form, contact_form)
        if not all(f.is_valid() for f in forms):
            errors = {}
            for form in forms:
                for field, messages in form.errors.items():
                    errors.setdefault(field, []).extend(messages)
            return JsonResponse({'ok': False, 'errors': errors}, status=400)

        self.request.session[self.get_session_key('step1')] = self.build_step1_payload(trip_form.cleaned_data)
        self.request.session[self.get_session_key('step2')] = self.build_people_payload(
            people_form.cleaned_data, request.POST
        )
        self.request.session[self.get_session_key('step3')] = self.build_contact_payload(contact_form.cleaned_data)
        self.request.session.modified = True

        return JsonResponse({'ok': True})


class DevFillWizardView(MultiStepBookingWizardView):
    """Development shortcut: fill the wizard session and jump to a step.

    Reaching the payment step normally means working through the address
    lookups and every field before it, which is a slow way to iterate on a
    later screen. This drops a plausible booking into the session and
    redirects wherever you ask.

    It builds that booking by running the real wizard forms over fixture data
    and calling the same build_*_payload helpers the wizard uses, so it cannot
    drift away from validation: if a new field becomes required and the
    fixture does not supply it, this fails loudly instead of seeding a session
    the wizard would reject.

    Gated on settings.ENABLE_DEV_FILL, which follows DEBUG and can also be
    switched on explicitly (ENABLE_DEV_FILL=True) for a local environment that
    runs with DEBUG off. A 404 everywhere else.

        /booking/dev-fill/                  jump to the review step
        /booking/dev-fill/?step=5           jump to payment
        /booking/dev-fill/?type=airport     seed a flight instead
        /booking/dev-fill/?stops=2&return=1 add stops and a return leg
        /booking/dev-fill/?km=120           force a long-distance fare
    """

    def get(self, request, *args, **kwargs):
        if not getattr(settings, 'ENABLE_DEV_FILL', False):
            raise Http404('Not available')

        step = self._int(request, 'step', default=4, low=1, high=self.TOTAL_STEPS)
        distance_km = self._int(request, 'km', default=14, low=1, high=2000)
        stop_count = self._int(request, 'stops', default=0, low=0, high=5)
        is_airport = request.GET.get('type', 'regular').lower() == 'airport'
        wants_return = request.GET.get('return') in ('1', 'true', 'yes')

        # Far enough ahead that the past-pickup guard never trips
        outbound = timezone.localtime() + datetime.timedelta(days=3)
        back = outbound + datetime.timedelta(days=2)

        trip = {
            'pickup_address': 'Robert Gabriel Mugabe International Airport, Harare'
                              if is_airport else '5 Josiah Chinamano Ave, Harare',
            'dropoff_address': '12 Borrowdale Rd, Harare',
            'pickup_latitude': -17.9318, 'pickup_longitude': 31.0928,
            'dropoff_latitude': -17.7840, 'dropoff_longitude': 31.0810,
            'distance_km': distance_km,
            'pickup_is_airport': 'on' if is_airport else '',
        }
        if is_airport:
            trip.update({
                'arrival_airline': 'Airlink',
                'arrival_flight_number': '4Z110',
                'arrival_date': outbound.date().isoformat(),
                'arrival_time': '14:20',
            })
            terminals = PricingService.get_airport_terminals()
            if terminals:
                trip['pickup_airport_terminal'] = terminals[0]
        else:
            trip.update({
                'pickup_date': outbound.date().isoformat(),
                'pickup_time': '09:30',
            })
        if wants_return:
            trip.update({
                'is_return_trip': 'on',
                'return_date': back.date().isoformat(),
                'return_time': '16:45',
            })

        # Stops belong to the route, so they ride along with the trip form
        trip['stops_json'] = json.dumps(
            [{'description': 'Dev stop %d' % (i + 1), 'minutes': 10} for i in range(stop_count)]
        )

        people = {
            'num_adults': 2, 'baby_car_seater': 0, 'num_kids_carried': 0,
            'luggage_count': 2, 'hand_luggage_count': 1,
        }
        contact = {
            'salutation': 'Ms',
            'passenger_full_name': 'Dev Tester',
            'phone': '+263 77 000 0000',
            'email': 'dev@example.com',
            'extra_instructions': 'Seeded by dev-fill.',
        }

        forms = [
            ('step 1', Step1PickupDropoffForm(trip)),
            ('step 2', Step2PassengersLuggageForm(people)),
            ('step 3', Step3ContactExtraForm(contact)),
        ]
        for label, form in forms:
            if not form.is_valid():
                return JsonResponse(
                    {'ok': False,
                     'where': label,
                     'hint': 'dev-fill fixture no longer satisfies this form',
                     'errors': form.errors},
                    status=500, json_dumps_params={'indent': 2},
                )

        trip_form, people_form, contact_form = (f for _, f in forms)
        self.clear_wizard_session()
        session = self.request.session
        session[self.get_session_key('step1')] = self.build_step1_payload(trip_form.cleaned_data)
        session[self.get_session_key('step2')] = self.build_people_payload(
            people_form.cleaned_data, people
        )
        session[self.get_session_key('step3')] = self.build_contact_payload(contact_form.cleaned_data)
        session.modified = True

        logger.info('dev-fill seeded the wizard session and jumped to step %s', step)
        return redirect('rides:booking_wizard', step=step)

    @staticmethod
    def _int(request, name, default, low, high):
        try:
            return max(low, min(high, int(request.GET.get(name, default))))
        except (TypeError, ValueError):
            return default


# ============================================================================
# Chauffeur Drive Booking Wizard (Session-Based, 6-Step)
# ============================================================================

class ChauffeurBookingWizardView(View):
    """
    Chauffeur Drive booking wizard — 6-step flow.

    Step 1: Package selection (duration only)
    Step 2: Trip details (pickup location, date, start/end time, trip summary)
    Step 3: Passenger details (main passenger name + counts)
    Step 4: Contact details (phone + email, both required)
    Step 5: Payment (full booking summary + payment method)
    Step 6: Confirmation (read-only)
    """

    VALID_STEPS = [1, 2, 3, 4, 5, 6]
    SESSION_KEY_PREFIX = 'chauffeur_wizard'

    def get_session_key(self, key):
        return f"{self.SESSION_KEY_PREFIX}_{key}"

    def get_wizard_data(self):
        data = {}
        for key in ['step1', 'step2', 'step3', 'step4']:
            session_key = self.get_session_key(key)
            if session_key in self.request.session:
                item = dict(self.request.session[session_key])
                if key == 'step2':
                    pd = item.get('pickup_date')
                    pt = item.get('pickup_time')
                    aet = item.get('approximate_end_time')
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
                        if isinstance(aet, str) and aet:
                            item['approximate_end_time'] = datetime.time.fromisoformat(aet)
                    except Exception:
                        pass
                data[key] = item
        return data

    def clear_wizard_session(self):
        for key in list(self.request.session.keys()):
            if key.startswith(self.SESSION_KEY_PREFIX):
                del self.request.session[key]
        self.request.session.modified = True

    def clear_wizard_steps(self):
        for step_key in ['step1', 'step2', 'step3', 'step4']:
            session_key = self.get_session_key(step_key)
            if session_key in self.request.session:
                del self.request.session[session_key]
        self.request.session.modified = True

    def _base_context(self, step):
        return {
            'step': step,
            'total_steps': 5,
            'GOOGLE_MAPS_CLIENT_KEY': settings.GOOGLE_MAPS_CLIENT_KEY,
            'TAXI_OWNER_PHONE': settings.TAXI_OWNER_PHONE,
            'csrf_token': get_token(self.request),
            'logo_url': _logo_url(),
            'booking_limits': PricingService.get_booking_limits(),
        }

    def _label_packages(self, packages):
        """Add display_label and billing_note to each package."""
        result = []
        for i, pkg in enumerate(packages):
            pkg = dict(pkg)
            if i == 0:
                pkg['display_label'] = f"Up to {pkg['hours']} Hours"
                pkg['billing_note'] = f"Ideal for trips up to {pkg['hours']} hours"
            else:
                prev_hours = packages[i - 1]['hours']
                pkg['display_label'] = f"{prev_hours}hrs+ to {pkg['hours']} Hours"
                pkg['billing_note'] = f"Any trip over {prev_hours}hrs is billed at the {pkg['hours']}-hour rate"
            result.append(pkg)
        return result

    def get(self, request, step=1):
        step = int(step)
        if step not in self.VALID_STEPS:
            return redirect('rides:chauffeur_wizard_start')

        context = self._base_context(step)
        wizard_data = self.get_wizard_data()

        if step == 1:
            reset_param = (request.GET.get('reset') or '').lower()
            if reset_param in ('1', 'true', 'yes'):
                self.clear_wizard_session()
                wizard_data = {}
            else:
                booking_key = self.get_session_key('booking_id')
                if booking_key in request.session:
                    self.clear_wizard_steps()
                    wizard_data = {}

            packages = PricingService.get_chauffeur_packages()
            labeled_packages = self._label_packages(packages)
            form = ChauffeurStep1Form(initial=wizard_data.get('step1', {}))
            context.update({
                'form': form,
                'packages': labeled_packages,
                'step1_data': wizard_data.get('step1', {}),
            })
            return render(request, 'rides/chauffeur_wizard/step1.html', context)

        elif step == 2:
            if 'step1' not in wizard_data:
                return redirect('rides:chauffeur_wizard', step=1)

            packages = PricingService.get_chauffeur_packages()
            labeled_packages = self._label_packages(packages)
            selected_hours = wizard_data['step1'].get('chauffeur_hours')
            selected_package = next(
                (p for p in labeled_packages if int(p.get('hours', 0)) == int(selected_hours or 0)),
                None,
            )
            form = ChauffeurStep2Form(initial=wizard_data.get('step2', {}))
            context.update({
                'form': form,
                'step1_data': wizard_data['step1'],
                'step2_data': wizard_data.get('step2', {}),
                'selected_package': selected_package,
            })
            return render(request, 'rides/chauffeur_wizard/step2.html', context)

        elif step == 3:
            if 'step2' not in wizard_data:
                return redirect('rides:chauffeur_wizard', step=2)

            packages = PricingService.get_chauffeur_packages()
            selected_hours = wizard_data['step1'].get('chauffeur_hours')
            selected_package = next(
                (p for p in packages if int(p.get('hours', 0)) == int(selected_hours or 0)),
                None,
            )
            form = ChauffeurPassengersForm(initial=wizard_data.get('step3', {}))
            context.update({
                'form': form,
                'step1_data': wizard_data.get('step1', {}),
                'step2_data': wizard_data.get('step2', {}),
                'step3_data': wizard_data.get('step3', {}),
                'selected_package': selected_package,
            })
            return render(request, 'rides/chauffeur_wizard/step3.html', context)

        elif step == 4:
            if 'step3' not in wizard_data:
                return redirect('rides:chauffeur_wizard', step=3)

            form = ChauffeurStep4ContactForm(initial=wizard_data.get('step4', {}))
            context.update({
                'form': form,
                'step4_data': wizard_data.get('step4', {}),
            })
            return render(request, 'rides/chauffeur_wizard/step4.html', context)

        elif step == 5:
            if 'step4' not in wizard_data:
                return redirect('rides:chauffeur_wizard', step=4)

            step1 = wizard_data['step1']
            hours = step1.get('chauffeur_hours')
            packages = PricingService.get_chauffeur_packages()
            labeled_packages = self._label_packages(packages)
            selected_package = next(
                (p for p in labeled_packages if int(p.get('hours', 0)) == int(hours or 0)),
                None,
            )
            try:
                fare_breakdown = PricingService.calculate_chauffeur(hours)
                context['fare_breakdown'] = fare_breakdown
                context['estimated_fare'] = fare_breakdown['total']
                context['paynow_rule'] = PricingService.get_paynow_rule()
                context['paynow_allowed'] = PricingService.paynow_allowed(fare_breakdown['total'])
            except Exception as e:
                logger.exception('Chauffeur fare calculation failed')
                context['fare_error'] = str(e)
                context['estimated_fare'] = 'Unable to calculate'

            form = Step4FarePaymentForm()
            context.update({
                'form': form,
                'step1_data': step1,
                'step2_data': wizard_data.get('step2', {}),
                'step3_data': wizard_data.get('step3', {}),
                'step4_data': wizard_data.get('step4', {}),
                'selected_package': selected_package,
            })
            return render(request, 'rides/chauffeur_wizard/step5.html', context)

        elif step == 6:
            if not all(k in wizard_data for k in ['step1', 'step2', 'step3', 'step4']):
                return redirect('rides:chauffeur_wizard', step=1)

            booking_id = request.session.get(self.get_session_key('booking_id'))
            booking = None
            if booking_id:
                try:
                    booking = RideBooking.objects.get(pk=booking_id)
                except Exception:
                    try:
                        booking = RideBooking.objects.get(reference=booking_id)
                    except RideBooking.DoesNotExist:
                        booking = None

            whatsapp_message = None
            if booking:
                try:
                    from urllib.parse import quote
                    payment_status = "Pay on Arrival (Cash)"
                    if booking.payment_option == RideBooking.PAYMENT_PAYNOW:
                        payment_status = "Pay Online (Paynow)"
                    elif booking.payment_option == RideBooking.PAYMENT_CARD_ON_ARRIVAL:
                        payment_status = "Pay on Arrival (POS/CARD)"
                    elif booking.payment_option == RideBooking.PAYMENT_MONEY_TRANSFER:
                        payment_status = "Money Transfer"
                    msg = build_booking_message(booking, payment_label_override=payment_status)
                    phone = settings.TAXI_OWNER_PHONE.lstrip('+')
                    whatsapp_message = f"https://wa.me/{phone}?text={quote(msg)}"
                except Exception as e:
                    logger.exception('Error generating WhatsApp message: %s', e)

            context.update({
                'step1_data': wizard_data.get('step1', {}),
                'step2_data': wizard_data.get('step2', {}),
                'step3_data': wizard_data.get('step3', {}),
                'step4_data': wizard_data.get('step4', {}),
                'booking': booking,
                'whatsapp_message': whatsapp_message,
            })
            return render(request, 'rides/chauffeur_wizard/step6.html', context)

        return redirect('rides:chauffeur_wizard_start')

    def post(self, request, step=1):
        step = int(step)
        if step not in self.VALID_STEPS:
            return redirect('rides:chauffeur_wizard_start')

        wizard_data = self.get_wizard_data()
        context = self._base_context(step)

        if step == 1:
            form = ChauffeurStep1Form(request.POST)
            packages = PricingService.get_chauffeur_packages()
            labeled_packages = self._label_packages(packages)
            if form.is_valid():
                self.request.session[self.get_session_key('step1')] = {
                    'chauffeur_hours': form.cleaned_data['chauffeur_hours'],
                }
                self.request.session.modified = True
                return redirect('rides:chauffeur_wizard', step=2)

            context.update({'form': form, 'packages': labeled_packages, 'step1_data': {}})
            return render(request, 'rides/chauffeur_wizard/step1.html', context)

        elif step == 2:
            if 'step1' not in wizard_data:
                return redirect('rides:chauffeur_wizard', step=1)

            form = ChauffeurStep2Form(request.POST)
            packages = PricingService.get_chauffeur_packages()
            labeled_packages = self._label_packages(packages)
            selected_hours = wizard_data['step1'].get('chauffeur_hours')
            selected_package = next(
                (p for p in labeled_packages if int(p.get('hours', 0)) == int(selected_hours or 0)),
                None,
            )
            if form.is_valid():
                def _iso(d):
                    return d.isoformat() if d is not None and hasattr(d, 'isoformat') else d

                self.request.session[self.get_session_key('step2')] = {
                    'pickup_address': form.cleaned_data['pickup_address'],
                    'pickup_latitude': form.cleaned_data.get('pickup_latitude'),
                    'pickup_longitude': form.cleaned_data.get('pickup_longitude'),
                    'pickup_address_detail': form.cleaned_data.get('pickup_address_detail', ''),
                    'pickup_date': _iso(form.cleaned_data.get('pickup_date')),
                    'pickup_time': _iso(form.cleaned_data.get('pickup_time')),
                    'approximate_end_time': _iso(form.cleaned_data.get('approximate_end_time')),
                    'trip_summary': form.cleaned_data.get('trip_summary', ''),
                }
                self.request.session.modified = True
                return redirect('rides:chauffeur_wizard', step=3)

            context.update({
                'form': form,
                'step1_data': wizard_data['step1'],
                'step2_data': {},
                'selected_package': selected_package,
            })
            return render(request, 'rides/chauffeur_wizard/step2.html', context)

        elif step == 3:
            if 'step2' not in wizard_data:
                return redirect('rides:chauffeur_wizard', step=2)

            form = ChauffeurPassengersForm(request.POST)
            packages = PricingService.get_chauffeur_packages()
            selected_hours = wizard_data['step1'].get('chauffeur_hours')
            selected_package = next(
                (p for p in packages if int(p.get('hours', 0)) == int(selected_hours or 0)),
                None,
            )
            if form.is_valid():
                num_adults = merged_adult_count(form.cleaned_data['num_adults'], request.POST.get('num_kids_seated', 0))
                over_limit = bool(selected_package and num_adults > int(selected_package.get('max_passengers', 99)))

                self.request.session[self.get_session_key('step3')] = {
                    'num_adults': num_adults,
                    'num_kids_seated': 0,
                    'baby_car_seater': form.cleaned_data['baby_car_seater'],
                    'num_kids_carried': form.cleaned_data['num_kids_carried'],
                    'luggage_count': form.cleaned_data['luggage_count'],
                    'hand_luggage_count': form.cleaned_data.get('hand_luggage_count') or 0,
                    'salutation': form.cleaned_data.get('salutation'),
                    'passenger_full_name': form.cleaned_data.get('passenger_full_name'),
                    'passengers_over_limit': over_limit,
                }
                self.request.session.modified = True
                return redirect('rides:chauffeur_wizard', step=4)

            context.update({
                'form': form,
                'step1_data': wizard_data.get('step1', {}),
                'step2_data': wizard_data.get('step2', {}),
                'step3_data': {},
                'selected_package': selected_package,
            })
            return render(request, 'rides/chauffeur_wizard/step3.html', context)

        elif step == 4:
            if 'step3' not in wizard_data:
                return redirect('rides:chauffeur_wizard', step=3)

            form = ChauffeurStep4ContactForm(request.POST)
            if form.is_valid():
                self.request.session[self.get_session_key('step4')] = {
                    'phone': form.cleaned_data['phone'],
                    'email': form.cleaned_data['email'],
                }
                self.request.session.modified = True
                return redirect('rides:chauffeur_wizard', step=5)

            context.update({
                'form': form,
                'step4_data': {},
            })
            return render(request, 'rides/chauffeur_wizard/step4.html', context)

        elif step == 5:
            if 'step4' not in wizard_data:
                return redirect('rides:chauffeur_wizard', step=4)

            form = Step4FarePaymentForm(request.POST)
            step1 = wizard_data.get('step1', {})
            step2 = wizard_data.get('step2', {})
            step3 = wizard_data.get('step3', {})
            step4 = wizard_data.get('step4', {})
            hours = step1.get('chauffeur_hours')

            packages = PricingService.get_chauffeur_packages()
            labeled_packages = self._label_packages(packages)
            selected_package = next(
                (p for p in labeled_packages if int(p.get('hours', 0)) == int(hours or 0)),
                None,
            )

            if form.is_valid():
                payment_method = form.cleaned_data['payment_method']

                try:
                    fare_breakdown = PricingService.calculate_chauffeur(hours)

                    # Paynow carries high fees on small amounts, so it is only offered
                    # at or above the configured minimum. Re-checked here because the
                    # payment radio can be re-enabled client-side.
                    if payment_method == RideBooking.PAYMENT_PAYNOW and not PricingService.paynow_allowed(fare_breakdown['total']):
                        paynow_rule = PricingService.get_paynow_rule()
                        context.update({
                            'form': form,
                            'step1_data': step1,
                            'step2_data': step2,
                            'step3_data': step3,
                            'step4_data': step4,
                            'selected_package': selected_package,
                            'fare_breakdown': fare_breakdown,
                            'estimated_fare': fare_breakdown['total'],
                            'paynow_rule': paynow_rule,
                            'paynow_allowed': False,
                            'error_message': paynow_rule['NOTE'],
                        })
                        return render(request, 'rides/chauffeur_wizard/step5.html', context)

                    # Build full pickup address including any additional detail
                    full_pickup = step2.get('pickup_address', '')
                    if step2.get('pickup_address_detail'):
                        full_pickup += f' ({step2["pickup_address_detail"]})'

                    num_adults = step3.get('num_adults', 1)
                    over_limit = bool(
                        selected_package and num_adults > int(selected_package.get('max_passengers', 99))
                    )

                    with transaction.atomic():
                        booking = RideBooking.objects.create(
                            pickup_address=full_pickup,
                            pickup_lat=Decimal(str(step2['pickup_latitude'])) if step2.get('pickup_latitude') else None,
                            pickup_lng=Decimal(str(step2['pickup_longitude'])) if step2.get('pickup_longitude') else None,
                            dropoff_address='Chauffeur Drive - itinerary to be arranged',
                            distance_km=Decimal('0'),
                            num_adults=num_adults,
                            num_kids_seated=0,
                            baby_car_seater=step3.get('baby_car_seater', 0),
                            num_kids_carried=step3.get('num_kids_carried', 0),
                            luggage_count=step3.get('luggage_count', 0),
                            hand_luggage_count=step3.get('hand_luggage_count', 0),
                            phone=step4['phone'],
                            email=step4['email'],
                            extra_instructions=step2.get('trip_summary', ''),
                            pickup_date=step2.get('pickup_date'),
                            pickup_time=step2.get('pickup_time'),
                            approximate_end_time=step2.get('approximate_end_time'),
                            salutation=step3.get('salutation'),
                            passenger_full_name=step3.get('passenger_full_name'),
                            payment_option=payment_method,
                            price_breakdown=fare_breakdown,
                            total_amount=Decimal(str(fare_breakdown['total'])),
                            ride_type=RideBooking.RIDE_TYPE_CHAUFFEUR,
                            chauffeur_hours=hours,
                            chauffeur_package_label=fare_breakdown.get('label', ''),
                            passengers_over_limit=over_limit,
                            status=RideBooking.STATUS_PENDING,
                        )

                        bref = getattr(booking, 'reference', None) or str(booking.id)
                        self.request.session[self.get_session_key('booking_id')] = str(bref)
                        self.request.session.modified = True

                        immediate_methods = [
                            RideBooking.PAYMENT_ON_ARRIVAL,
                            RideBooking.PAYMENT_CARD_ON_ARRIVAL,
                            RideBooking.PAYMENT_MONEY_TRANSFER,
                            RideBooking.PAYMENT_PAYLINK,
                        ]

                        if payment_method in immediate_methods:
                            booking.status = RideBooking.STATUS_CONFIRMED
                            booking.save()

                            Payment.objects.create(
                                booking=booking,
                                method=payment_method,
                                amount=booking.total_amount,
                                status=Payment.STATUS_PENDING,
                            )

                            payment_label = {
                                RideBooking.PAYMENT_ON_ARRIVAL: 'Pay on Arrival (Cash)',
                                RideBooking.PAYMENT_CARD_ON_ARRIVAL: 'Pay on Arrival (POS/CARD)',
                                RideBooking.PAYMENT_MONEY_TRANSFER: 'Money Transfer Agency',
                                RideBooking.PAYMENT_PAYLINK: 'Paylink',
                            }.get(payment_method, payment_method)

                            EmailService.send_owner_notification(booking, payment_status=payment_label)
                            EmailService.send_customer_notification(booking, payment_status=payment_label)

                            return redirect('rides:chauffeur_wizard', step=6)

                        else:
                            payment = Payment.objects.create(
                                booking=booking,
                                method='PAYNOW',
                                amount=booking.total_amount,
                                status=Payment.STATUS_PENDING,
                            )

                            paynow = PaynowService()
                            paynow_response = paynow.create_transaction(
                                amount=float(payment.amount),
                                reference=str(payment.id),
                                email=booking.email,
                                phone=booking.phone,
                            )

                            self.request.session['last_payment_id'] = str(payment.id)
                            self.request.session['last_booking_id'] = str(bref)
                            self.request.session.modified = True

                            payment.paynow_response = paynow_response
                            candidates = [
                                paynow_response.get('paynowreference'),
                                paynow_response.get('paynow_reference'),
                                paynow_response.get('reference'),
                                paynow_response.get('transaction_id'),
                            ]
                            for c in candidates:
                                if c:
                                    payment.paynow_reference = str(c)
                                    break
                            payment.save()

                            redirect_url = paynow_response.get('redirectUrl') or paynow_response.get('redirect_url')
                            if redirect_url:
                                return redirect(redirect_url)

                            return render(request, 'rides/paynow_redirect.html', {
                                'redirect_url': redirect_url,
                                'payment_id': str(payment.id),
                                'booking_id': str(bref),
                            })

                except Exception as e:
                    logger.exception('Chauffeur booking creation failed')
                    context['error'] = f'Failed to create booking: {e}'
                    try:
                        fare_breakdown = PricingService.calculate_chauffeur(hours)
                        context['fare_breakdown'] = fare_breakdown
                    except Exception:
                        context['fare_error'] = 'Unable to calculate fare'
                    context.update({
                        'form': form,
                        'step1_data': step1,
                        'step2_data': step2,
                        'step3_data': step3,
                        'step4_data': step4,
                        'selected_package': selected_package,
                    })
                    return render(request, 'rides/chauffeur_wizard/step5.html', context)

            # Form invalid — re-render with fare
            try:
                fare_breakdown = PricingService.calculate_chauffeur(hours)
                context['fare_breakdown'] = fare_breakdown
            except Exception:
                context['fare_error'] = 'Unable to calculate fare'

            context.update({
                'form': form,
                'step1_data': step1,
                'step2_data': step2,
                'step3_data': step3,
                'step4_data': step4,
                'selected_package': selected_package,
            })
            return render(request, 'rides/chauffeur_wizard/step5.html', context)

        return redirect('rides:chauffeur_wizard_start')


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
            fare_breakdown = _calculate_fare(
                distance_km=distance_km,
                num_adults=num_adults,
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
# Service Selector (Landing / Entry Point)
# ============================================================================

class ServiceSelectorView(TemplateView):
    """Landing page — user picks Regular/Long Distance or Chauffeur Drive."""
    template_name = 'rides/service_selector.html'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['TAXI_OWNER_PHONE'] = settings.TAXI_OWNER_PHONE
        ctx['chauffeur_packages'] = PricingService.get_chauffeur_packages()
        ctx['logo_url'] = _logo_url()
        return ctx


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
        print("............................ ", status_text, "...status text")
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
        from urllib.parse import urlencode, quote
        
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


# ============================================================================
# Customer self-service: manage a booking from an emailed magic link
# ============================================================================

class ManageBookingView(View):
    """Let a customer reschedule or cancel their own booking.

    Access is proved by the signed token in the URL — there are no customer
    accounts. Every state change re-checks the cut-off server-side, because the
    link stays valid after the window closes.
    """

    template_name = 'rides/manage_booking.html'

    def _context(self, request, booking, **extra):
        from rides.services.booking_access import self_service_state
        state = self_service_state(booking)
        context = {
            'booking': booking,
            'logo_url': _logo_url(),
            'TAXI_OWNER_PHONE': settings.TAXI_OWNER_PHONE,
            'csrf_token': get_token(request),
            'flight_form': extra.pop('flight_form', None) or UpdateFlightDetailsForm(
                booking=booking,
                initial={
                    'arrival_airline': booking.arrival_airline,
                    'arrival_flight_number': booking.arrival_flight_number,
                    'arrival_date': booking.arrival_date,
                    'arrival_time': booking.arrival_time,
                    'pickup_airport_terminal': booking.pickup_airport_terminal,
                    'flight_departure_airport': booking.flight_departure_airport,
                    'flight_connection_details': booking.flight_connection_details,
                    'flight_notes': booking.flight_notes,
                },
            ),
        }
        context.update(state)
        context.update(extra)
        return context

    def get(self, request, token):
        from rides.services.booking_access import load_booking
        booking = load_booking(token)
        if booking is None:
            return render(request, self.template_name, {
                'invalid_link': True,
                'logo_url': _logo_url(),
                'TAXI_OWNER_PHONE': settings.TAXI_OWNER_PHONE,
            }, status=404)

        return render(request, self.template_name, self._context(request, booking, token=token))

    def post(self, request, token):
        from rides.services.booking_access import load_booking, self_service_state

        booking = load_booking(token)
        if booking is None:
            return render(request, self.template_name, {
                'invalid_link': True,
                'logo_url': _logo_url(),
                'TAXI_OWNER_PHONE': settings.TAXI_OWNER_PHONE,
            }, status=404)

        action = request.POST.get('action', '')
        state = self_service_state(booking)

        if action == 'cancel':
            return self._handle_cancel(request, booking, token, state)
        if action == 'reschedule':
            return self._handle_reschedule(request, booking, token, state)
        if action == 'update_flight':
            return self._handle_flight_update(request, booking, token, state)

        return redirect('rides:manage_booking', token=token)

    # ------------------------------------------------------------------ cancel
    def _handle_cancel(self, request, booking, token, state):
        if not state['can_cancel']:
            return render(request, self.template_name, self._context(
                request, booking, token=token,
                error_message=state['blocked_reason'] or 'This booking can no longer be cancelled online.',
            ))

        booking.status = RideBooking.STATUS_CANCELLED
        booking.cancelled_at = timezone.now()
        booking.cancelled_by_customer = True
        booking.log_change('cancelled', 'Cancelled by the customer from their booking link.')
        booking.save()

        try:
            EmailService.send_booking_cancelled(booking)
        except Exception:
            logger.exception('Failed to send cancellation emails for booking %s', booking.id)

        return render(request, self.template_name, self._context(
            request, booking, token=token,
            success_message='Your booking has been cancelled. We have let the team know.',
        ))

    # ----------------------------------------------------------- flight details
    def _handle_flight_update(self, request, booking, token, state):
        """Record a corrected flight, and move the pickup with it.

        Airlines move people around at short notice, so this is allowed inside the
        normal change cut-off — a passenger who is rebooked while connecting still
        needs the driver to meet the right flight.
        """
        if not state['can_update_flight']:
            return render(request, self.template_name, self._context(
                request, booking, token=token,
                error_message=state['flight_blocked_reason'] or 'Flight details can no longer be changed online.',
            ))

        form = UpdateFlightDetailsForm(request.POST, booking=booking)
        if not form.is_valid():
            return render(request, self.template_name, self._context(
                request, booking, token=token, flight_form=form,
                error_message='; '.join(form.errors.get('__all__', [])) or 'Please check the flight details below.',
            ))

        old_flight = f"{booking.arrival_airline or '-'} {booking.arrival_flight_number or '-'}"
        old_arrival = f"{booking.arrival_date} {booking.arrival_time}"

        booking.arrival_airline = form.cleaned_data['arrival_airline']
        booking.arrival_flight_number = form.cleaned_data['arrival_flight_number']
        booking.arrival_date = form.cleaned_data['arrival_date']
        booking.arrival_time = form.cleaned_data['arrival_time']
        booking.pickup_airport_terminal = form.cleaned_data.get('pickup_airport_terminal') or ''
        booking.flight_departure_airport = form.cleaned_data.get('flight_departure_airport') or ''
        booking.flight_connection_details = form.cleaned_data.get('flight_connection_details') or ''
        booking.flight_notes = form.cleaned_data.get('flight_notes') or ''
        booking.flight_details_updated_at = timezone.now()

        # The pickup is timed off the arrival for an airport booking, so it follows.
        booking.pickup_is_airport = True
        booking.pickup_date = booking.arrival_date
        booking.pickup_time = booking.arrival_time

        new_flight = f"{booking.arrival_airline} {booking.arrival_flight_number}"
        detail = (
            f"Flight changed from {old_flight} arriving {old_arrival} to {new_flight} "
            f"arriving {booking.arrival_date} {booking.arrival_time}."
        )
        if booking.pickup_airport_terminal:
            detail += f" Pickup point: {booking.pickup_airport_terminal}."

        # The night surcharge depends on the hour, so the fare is re-checked.
        old_total = booking.total_amount
        try:
            breakdown = _calculate_fare(
                distance_km=float(booking.distance_km or 0),
                num_adults=booking.num_adults,
                baby_car_seater=booking.baby_car_seater,
                num_kids_carried=booking.num_kids_carried,
                luggage_count=booking.luggage_count,
                hand_luggage_count=booking.hand_luggage_count,
                pickup_time=booking.pickup_time,
                stops=booking.stops_json or [],
                is_return_trip=booking.is_return_trip,
                return_time=booking.return_time,
                return_distance_km=float(booking.return_distance_km) if booking.return_distance_km else None,
            )
            booking.price_breakdown = breakdown
            booking.total_amount = Decimal(str(breakdown['total']))
            if booking.total_amount != old_total:
                detail += f" Fare updated from ${old_total} to ${booking.total_amount}."
        except Exception:
            logger.exception('Could not re-price booking %s after a flight change', booking.id)

        booking.log_change('flight_updated', detail)
        booking.save()

        try:
            EmailService.send_booking_rescheduled(booking, detail)
        except Exception:
            logger.exception('Failed to send flight update emails for booking %s', booking.id)

        message = 'Thank you — we have your new flight details and the driver will meet that flight.'
        if booking.total_amount != old_total:
            message += f' Your fare is now ${booking.total_amount}.'

        return render(request, self.template_name, self._context(
            request, booking, token=token, success_message=message,
        ))

    # -------------------------------------------------------------- reschedule
    def _handle_reschedule(self, request, booking, token, state):
        if not state['can_reschedule']:
            return render(request, self.template_name, self._context(
                request, booking, token=token,
                error_message=state['blocked_reason'] or 'This booking can no longer be changed online.',
            ))

        form = RescheduleBookingForm(request.POST, booking=booking)
        if not form.is_valid():
            return render(request, self.template_name, self._context(
                request, booking, token=token, form=form,
                error_message='; '.join(form.errors.get('__all__', [])) or 'Please check the dates and times below.',
            ))

        old_pickup = f"{booking.pickup_date} {booking.pickup_time}"
        booking.pickup_date = form.cleaned_data['pickup_date']
        booking.pickup_time = form.cleaned_data['pickup_time']

        detail = f"Pickup moved from {old_pickup} to {booking.pickup_date} {booking.pickup_time}."

        if booking.is_return_trip and form.cleaned_data.get('return_date'):
            old_return = f"{booking.return_date} {booking.return_time}"
            booking.return_date = form.cleaned_data['return_date']
            booking.return_time = form.cleaned_data['return_time']
            detail += f" Return moved from {old_return} to {booking.return_date} {booking.return_time}."

        # The night surcharge depends on the time of day, so the fare is re-priced.
        old_total = booking.total_amount
        try:
            breakdown = _calculate_fare(
                distance_km=float(booking.distance_km or 0),
                num_adults=booking.num_adults,
                baby_car_seater=booking.baby_car_seater,
                num_kids_carried=booking.num_kids_carried,
                luggage_count=booking.luggage_count,
                hand_luggage_count=booking.hand_luggage_count,
                pickup_time=booking.pickup_time,
                stops=booking.stops_json or [],
                is_return_trip=booking.is_return_trip,
                return_time=booking.return_time,
                return_distance_km=float(booking.return_distance_km) if booking.return_distance_km else None,
            )
            booking.price_breakdown = breakdown
            booking.total_amount = Decimal(str(breakdown['total']))
            if booking.total_amount != old_total:
                detail += f" Fare updated from ${old_total} to ${booking.total_amount}."
        except Exception:
            logger.exception('Could not re-price booking %s after reschedule', booking.id)

        booking.log_change('rescheduled', detail)
        booking.save()

        try:
            EmailService.send_booking_rescheduled(booking, detail)
        except Exception:
            logger.exception('Failed to send reschedule emails for booking %s', booking.id)

        message = 'Your booking has been updated. A confirmation is on its way to your inbox.'
        if booking.total_amount != old_total:
            message += f' Your new fare is ${booking.total_amount}.'

        return render(request, self.template_name, self._context(
            request, booking, token=token, success_message=message,
        ))
