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

from .models import RideBooking, Payment
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
                data[key] = self.request.session[session_key]
        return data

    def clear_wizard_session(self):
        """Clear all wizard session data."""
        for key in list(self.request.session.keys()):
            if key.startswith(self.SESSION_KEY_PREFIX):
                del self.request.session[key]
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

        if step == 1:
            form = Step1PickupDropoffForm(
                initial=wizard_data.get('step1', {})
            )
            context['form'] = form
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

            try:
                distance_km = float(step1.get('distance_km', 0))
                if distance_km == 0:
                    # Calculate distance from coordinates
                    distance_km = DistanceService.get_distance_km(
                        (step1.get('pickup_latitude'), step1.get('pickup_longitude')),
                        (step1.get('dropoff_latitude'), step1.get('dropoff_longitude')),
                    )
                    step1['distance_km'] = distance_km
                    self.request.session[self.get_session_key('step1')] = step1
                    self.request.session.modified = True

                fare_breakdown = PricingService.calculate(
                    distance_km=distance_km,
                    num_adults=step2.get('num_adults', 1),
                    num_kids_seated=step2.get('num_kids_seated', 0),
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
                try:
                    booking = RideBooking.objects.get(pk=booking_id)
                except RideBooking.DoesNotExist:
                    pass

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
                    
                    msg = f"""Booking ID: {booking.id}

Pickup: {booking.pickup_address}
Dropoff: {booking.dropoff_address}
Distance: {booking.distance_km} km"""
                    
                    if eta_minutes:
                        msg += f"\nEstimated Time: {eta_minutes} minutes"
                    
                    msg += f"""

Total: ${booking.total_amount}
Payment: {payment_status}

Passengers: {booking.num_adults} adult(s)"""
                    
                    if booking.num_kids_seated > 0 or booking.num_kids_carried > 0:
                        msg += f", {booking.num_kids_seated} kid(s) seated, {booking.num_kids_carried} carried"
                    
                    if booking.luggage_count > 0:
                        msg += f"\nLuggage: {booking.luggage_count} bag(s)"
                    
                    # Remove + from phone number for WhatsApp API
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
                self.request.session[self.get_session_key('step1')] = {
                    'pickup_address': form.cleaned_data['pickup_address'],
                    'pickup_latitude': form.cleaned_data['pickup_latitude'],
                    'pickup_longitude': form.cleaned_data['pickup_longitude'],
                    'dropoff_address': form.cleaned_data['dropoff_address'],
                    'dropoff_latitude': form.cleaned_data['dropoff_latitude'],
                    'dropoff_longitude': form.cleaned_data['dropoff_longitude'],
                    'distance_km': 0,  # Will be calculated in Step 4
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
                self.request.session[self.get_session_key('step2')] = {
                    'num_adults': form.cleaned_data['num_adults'],
                    'num_kids_seated': form.cleaned_data['num_kids_seated'],
                    'num_kids_carried': form.cleaned_data['num_kids_carried'],
                    'luggage_count': form.cleaned_data['luggage_count'],
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
                        num_adults=step2.get('num_adults', 1),
                        num_kids_seated=step2.get('num_kids_seated', 0),
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
                            num_adults=step2.get('num_adults', 1),
                            num_kids_seated=step2.get('num_kids_seated', 0),
                            num_kids_carried=step2.get('num_kids_carried', 0),
                            luggage_count=step2.get('luggage_count', 0),
                            phone=step3['phone'],
                            email=step3['email'],
                            extra_instructions=step3.get('extra_instructions', ''),
                            payment_option=payment_method,
                            price_breakdown=fare_breakdown,
                            total_amount=Decimal(str(fare_breakdown['total'])),
                            status=RideBooking.STATUS_PENDING,
                        )

                        # Store booking ID in session
                        self.request.session[f'{self.SESSION_KEY_PREFIX}_booking_id'] = str(booking.id)
                        self.request.session.modified = True

                        if payment_method == RideBooking.PAYMENT_ON_ARRIVAL:
                            # Confirm booking immediately for cash payment
                            booking.status = RideBooking.STATUS_CONFIRMED
                            booking.save()

                            Payment.objects.create(
                                booking=booking,
                                method=RideBooking.PAYMENT_ON_ARRIVAL,
                                amount=booking.total_amount,
                                status=Payment.STATUS_PENDING,
                            )

                            # Send notifications
                            EmailService.send_owner_notification(booking, payment_status='PAY ON ARRIVAL')
                            EmailService.send_customer_notification(booking, payment_status='PAY ON ARRIVAL')

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

                            # Store payment and booking IDs in session for return flow
                            self.request.session['last_payment_id'] = str(payment.id)
                            self.request.session['last_booking_id'] = str(booking.id)
                            self.request.session.modified = True
                            logger.info('Stored in session: last_payment_id=%s, last_booking_id=%s', payment.id, booking.id)

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
                            return render(request, 'rides/paynow_redirect.html', {
                                'redirect_url': redirect_url,
                                'payment_id': str(payment.id),
                                'booking_id': str(booking.id),
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
                context = {
                    'form': form,
                    'step': step,
                    'total_steps': 4,
                    'step1_data': wizard_data.get('step1', {}),
                    'step2_data': wizard_data.get('step2', {}),
                    'step3_data': wizard_data.get('step3', {}),
                    'GOOGLE_MAPS_CLIENT_KEY': settings.GOOGLE_MAPS_CLIENT_KEY,
                    'TAXI_OWNER_PHONE': settings.TAXI_OWNER_PHONE,
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
        "num_kids_seated": 0,
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

            num_adults = int(data.get('num_adults', 1))
            num_kids_seated = int(data.get('num_kids_seated', 0))
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
                num_kids_seated=num_kids_seated,
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
            
            msg = f"""Booking ID: {booking.id}

Pickup: {booking.pickup_address}
Dropoff: {booking.dropoff_address}
Distance: {booking.distance_km} km"""
            
            if eta_minutes:
                msg += f"\nEstimated Time: {eta_minutes} minutes"
            
            msg += f"""

Total: ${booking.total_amount}
Payment: {payment_status}

Passengers: {booking.num_adults} adult(s)"""
            
            if booking.num_kids_seated > 0 or booking.num_kids_carried > 0:
                msg += f", {booking.num_kids_seated} kid(s) seated, {booking.num_kids_carried} carried"
            
            if booking.luggage_count > 0:
                msg += f"\nLuggage: {booking.luggage_count} bag(s)"
            
            # Remove + from phone number for WhatsApp API
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
                num_adults=data.get('num_adults', 1),
                num_kids_seated=data.get('num_kids_seated', 0),
                num_kids_carried=data.get('num_kids_carried', 0),
                luggage_count=data.get('luggage_count', 0),
            )

            booking = RideBooking.objects.create(
                pickup_address=data['pickup_address'],
                pickup_lat=data.get('pickup_lat'),
                pickup_lng=data.get('pickup_lng'),
                dropoff_address=data['dropoff_address'],
                dropoff_lat=data.get('dropoff_lat'),
                dropoff_lng=data.get('dropoff_lng'),
                distance_km=distance,
                num_adults=data.get('num_adults', 1),
                num_kids_seated=data.get('num_kids_seated', 0),
                num_kids_carried=data.get('num_kids_carried', 0),
                luggage_count=data.get('luggage_count', 0),
                phone=data['phone'],
                email=data['email'],
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
                num_adults=data.get('num_adults', 1),
                num_kids_seated=data.get('num_kids_seated', 0),
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
                            payment_status = "PAID" if payment.status == Payment.STATUS_PAID else "PENDING"
                            msg = f"""Booking ID: {booking.id}

Pickup: {booking.pickup_address}
Dropoff: {booking.dropoff_address}
Distance: {booking.distance_km} km"""
                            
                            if eta_minutes:
                                msg += f"\nEstimated Time: {eta_minutes} minutes"
                            
                            msg += f"""

Total: ${booking.total_amount}
Payment Status: {payment_status}

Passengers: {booking.num_adults} adult(s)"""
                            
                            if booking.num_kids_seated > 0 or booking.num_kids_carried > 0:
                                msg += f", {booking.num_kids_seated} kid(s) seated, {booking.num_kids_carried} carried"
                            
                            if booking.luggage_count > 0:
                                msg += f"\nLuggage: {booking.luggage_count} bag(s)"
                            
                            # Remove + from phone number for WhatsApp API
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
