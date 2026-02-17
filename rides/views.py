import logging
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.shortcuts import get_object_or_404, redirect, render
from django.http import HttpResponse
from django.conf import settings
from django.views.generic import FormView, TemplateView

from .serializers import CreateBookingSerializer, RideBookingSerializer, PaymentSerializer, PriceEstimateSerializer
from .models import RideBooking, Payment
from .services.pricing import PricingService
from .services.paynow import PaynowService
from .services.email_service import EmailService
from .forms import BookingForm, BookingStep1Form, BookingStep2Form, BookingStep3Form, BookingStep4Form, BookingStep5Form

logger = logging.getLogger(__name__)


class BookingFormView(FormView):
    template_name = 'rides/booking_form.html'
    form_class = BookingForm

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        # Provide the client-side Maps key to the template
        ctx['GOOGLE_MAPS_CLIENT_KEY'] = settings.GOOGLE_MAPS_CLIENT_KEY
        ctx['TAXI_OWNER_PHONE'] = settings.TAXI_OWNER_PHONE
        return ctx

    def form_valid(self, form):
        data = form.cleaned_data

        # Compute pricing
        breakdown = PricingService.calculate(
            distance_km=data['distance_km'],
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
            distance_km=data['distance_km'],
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
            Payment.objects.create(booking=booking, method=RideBooking.PAYMENT_ON_ARRIVAL, amount=booking.total_amount, status=Payment.STATUS_PENDING)

            # Send notifications
            EmailService.send_owner_notification(booking, payment_status='PAY ON ARRIVAL')
            EmailService.send_customer_notification(booking, payment_status='PAY ON ARRIVAL')

            return redirect('rides:booking_success', pk=booking.id)

        # Paynow flow
        payment = Payment.objects.create(booking=booking, method='PAYNOW', amount=booking.total_amount, status=Payment.STATUS_PENDING)
        paynow = PaynowService()
        try:
            paynow_response = paynow.create_transaction(amount=float(payment.amount), reference=str(payment.id), email=booking.email, phone=booking.phone)
            # Persist the raw response and try to extract any Paynow reference that can be used
            # by webhooks to find this Payment later.
            payment.paynow_response = paynow_response
            # Candidate locations for Paynow's reference
            candidates = [
                paynow_response.get('paynowreference'),
                paynow_response.get('paynow_reference'),
                paynow_response.get('reference'),
                paynow_response.get('transaction_id'),
                (paynow_response.get('response') or {}).get('data', {}).get('paynowreference'),
                (paynow_response.get('response') or {}).get('data', {}).get('paynow_reference'),
                (paynow_response.get('response') or {}).get('data', {}).get('paynowReference'),
            ]
            for c in candidates:
                if c:
                    payment.paynow_reference = str(c)
                    break
            payment.save()

            redirect_url = paynow_response.get('redirectUrl') or paynow_response.get('redirect_url')
            # poll url can be returned as 'pollUrl', 'poll_url' or inside response.data
            poll_url = paynow_response.get('pollUrl') or paynow_response.get('poll_url') or (paynow_response.get('response') or {}).get('poll_url') or (paynow_response.get('response') or {}).get('pollUrl') or (paynow_response.get('response') or {}).get('data', {}).get('poll_url')

            def _is_valid_url(u):
                try:
                    return isinstance(u, str) and (u.startswith('http://') or u.startswith('https://'))
                except Exception:
                    return False

            # If the response provided a poll_url or redirect_url, treat this as initiated/pending
            # and show the appropriate UI instead of failing immediately.
            try:
                ctx = {
                    'redirect_url': redirect_url,
                    'redirect_is_valid': _is_valid_url(redirect_url),
                    'poll_url': poll_url,
                    'message': 'Payment initiated. Please follow the instructions or check the payment status via the poll URL.',
                    'payment_id': str(payment.id),
                    'booking_id': str(booking.id),
                }
                # Save last payment/booking into the session so we can show a friendly summary when user returns without a reference
                try:
                    self.request.session['last_payment_id'] = str(payment.id)
                    self.request.session['last_booking_id'] = str(booking.id)
                    self.request.session.modified = True
                except Exception:
                    logger.exception('Failed to set session last_payment_id (non-fatal)')

                if redirect_url and _is_valid_url(redirect_url):
                    return render(self.request, 'rides/paynow_redirect.html', ctx)
                elif poll_url:
                    return render(self.request, 'rides/paynow_poll.html', ctx)
                else:
                    logger.warning('Paynow returned invalid or missing redirect/poll URLs. redirect=%r poll=%r', redirect_url, poll_url)
                    raw = paynow_response.get('raw_response') or paynow_response.get('response') or paynow_response.get('data')
                    if settings.DEBUG and raw:
                        base_tag = '<base href="https://www.paynow.co.zw/">'
                        ctx.update({'raw_html': raw, 'base_tag': base_tag})
                        return render(self.request, 'rides/paynow_debug.html', ctx)

                    ctx['redirect_url'] = None
                    return render(self.request, 'rides/paynow_redirect.html', ctx)
            except Exception as exc:
                logger.exception('Error rendering Paynow UI templates: %s', exc)
                print("here is the error ...............",exc)
                return render(self.request, 'rides/error.html', { 'message': 'Payment initiated but an internal error occurred. Please contact support.' })
        except Exception as exc:
            logger.exception('Paynow creation failed: %s', exc)
            payment.status = Payment.STATUS_FAILED
            payment.paynow_response = { 'error': str(exc) }
            payment.save()
            return render(self.request, 'rides/error.html', { 'message': 'Payment initiation failed' })


class BookingSuccessView(TemplateView):
    template_name = 'rides/booking_success.html'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        booking = get_object_or_404(RideBooking, pk=self.kwargs.get('pk'))
        ctx['booking'] = booking
        ctx['TAXI_OWNER_PHONE'] = settings.TAXI_OWNER_PHONE
        return ctx


class CreateBookingView(APIView):
    def post(self, request):
        serializer = CreateBookingSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        # Determine distance: either provided by client or calculated using DistanceService
        distance = data.get('distance_km')
        if distance is None:
            try:
                from .services.distance import DistanceService

                distance = DistanceService.get_distance_km(
                    (data.get('pickup_lat'), data.get('pickup_lng')),
                    (data.get('dropoff_lat'), data.get('dropoff_lng')),
                )
            except Exception as exc:
                logger.exception("Distance computation failed")
                return Response({"detail": f"Unable to compute distance: {exc}"}, status=status.HTTP_400_BAD_REQUEST)

        # Calculate price based on the distance and passenger details
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
            # Mark as confirmed (business: booking can be confirmed after selecting Pay on Arrival)
            booking.status = RideBooking.STATUS_CONFIRMED
            booking.save()

            # Create a placeholder payment record (unpaid)
            Payment.objects.create(booking=booking, method=RideBooking.PAYMENT_ON_ARRIVAL, amount=booking.total_amount, status=Payment.STATUS_PENDING)

            # Send emails
            EmailService.send_owner_notification(booking, payment_status='PAY ON ARRIVAL')
            EmailService.send_customer_notification(booking, payment_status='PAY ON ARRIVAL')

            return Response(RideBookingSerializer(booking).data, status=status.HTTP_201_CREATED)

        # Else Paynow flow
        paynow = PaynowService()
        payment = Payment.objects.create(booking=booking, method='PAYNOW', amount=booking.total_amount, status=Payment.STATUS_PENDING)

        try:
            paynow_response = paynow.create_transaction(amount=float(payment.amount), reference=str(payment.id), email=booking.email, phone=booking.phone)
            payment.paynow_response = paynow_response
            # Persist any Paynow-assigned reference
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
            # Return redirect url to client
            return Response({"payment": PaymentSerializer(payment).data, "redirect_url": paynow_response.get('redirectUrl') or paynow_response.get('redirect_url'), "poll_url": paynow_response.get('pollUrl') or paynow_response.get('poll_url') or (paynow_response.get('response') or {}).get('poll_url')}, status=status.HTTP_201_CREATED)
        except Exception as exc:
            logger.exception("Paynow creation failed")
            payment.status = Payment.STATUS_FAILED
            payment.paynow_response = {"error": str(exc)}
            payment.save()
            return Response({"detail": "Payment initiation failed"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class PaynowResultView(APIView):
    """Endpoint for Paynow server-to-server notifications (result_url)"""

    def post(self, request):
        from .services.paynow import PaynowService

        paynow = PaynowService()
        # Log incoming webhook (debug): raw body and headers (useful to trace test-mode notifications)
        logger.debug('Incoming Paynow webhook: headers=%s body=%s', {k:v for k,v in request.META.items() if k.startswith('HTTP_')}, request.body[:2000])
        # Verify signature
        if not paynow.verify_notification(request):
            logger.warning('Paynow webhook failed signature verification')
            return Response({'detail': 'Invalid signature'}, status=status.HTTP_403_FORBIDDEN)

        from decimal import Decimal
        from django.db import transaction

        data = request.POST.dict()
        status_text = (data.get('status') or '').strip()
        logger.info('Paynow webhook data: %s', data)

        # Paynow can send the local reference as 'reference' or 'transaction_id',
        # but often sends its own 'paynowreference' field — try a few candidates.
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
            # Try to match the Paynow reference stored on the Payment
            payment = Payment.objects.filter(paynow_reference=ref).first()
            if payment:
                logger.debug('Matched payment by paynow_reference: %s', payment.id)
                break
            # If the reference looks like our local payment id, try that too
            try:
                payment = Payment.objects.get(pk=ref)
                logger.debug('Matched payment by local id: %s', payment.id)
                break
            except Exception:
                pass

        if not payment:
            # As a last resort, search payments whose saved paynow_response contains the paynow reference
            payref = data.get('paynowreference') or data.get('paynow_reference') or data.get('paynowReference')
            if payref:
                payment = Payment.objects.filter(paynow_response__icontains=str(payref)).first()
                if payment:
                    logger.debug('Matched payment by searching paynow_response for paynowreference: %s', payment.id)

        if not payment:
            # Don't fail the webhook outright (Paynow may retry). Log and ACK to avoid retries.
            logger.warning('Paynow webhook for unknown reference: %s', reference_candidates)
            return Response({'ok': True})

        # Ensure payment.paynow_reference is recorded if provided in the webhook
        payref = data.get('paynowreference') or data.get('paynow_reference') or data.get('paynowReference')
        if payref and not payment.paynow_reference:
            payment.paynow_reference = payref
            payment.save()
            logger.debug('Updated payment %s paynow_reference=%s from webhook', payment.id, payref)

        # Only treat explicit 'Paid' as a success. Other statuses may be intermediate and should
        # not immediately move a PENDING->FAILED state (Paynow may send 'Awaiting Delivery' etc.).
        FAILURE_STATUSES = { 'failed', 'cancelled', 'expired' }

        with transaction.atomic():
            # Lock the payment row to avoid races between concurrent webhooks/pollers
            p = Payment.objects.select_for_update().get(pk=payment.pk)

            # If we've already recorded PAID, ack and do nothing else (idempotent)
            if p.status == Payment.STATUS_PAID:
                logger.info('Webhook for already-PAID payment %s received; ignoring', p.id)
                return Response({'ok': True})

            # If Paynow reports paid, validate amount (if provided) before confirming
            if status_text and status_text.lower() == 'paid':
                incoming_amount = data.get('amount')
                if incoming_amount:
                    try:
                        inc_amt = Decimal(incoming_amount)
                    except Exception:
                        logger.warning('Unable to parse amount from webhook: %s', incoming_amount)
                        inc_amt = None

                    # If amount doesn't match expected, mark for manual review rather than auto-confirm
                    if inc_amt is not None and inc_amt != p.amount:
                        logger.error('Webhook amount mismatch for payment %s: expected=%s got=%s', p.id, p.amount, inc_amt)
                        # Record raw webhook in paynow_response for manual inspection and mark FAILED
                        p.paynow_response = p.paynow_response or {}
                        p.paynow_response['last_webhook'] = data
                        p.status = Payment.STATUS_FAILED
                        p.save()
                        return Response({'ok': True})

                # Transition to PAID
                p.status = Payment.STATUS_PAID
                p.save()

                booking = p.booking
                booking.status = RideBooking.STATUS_CONFIRMED
                booking.save()

                # Send confirmation emails (guard must be outside the DB transaction)
                EmailService.send_payment_confirmation(booking)
                EmailService.send_owner_notification(booking, payment_status='PAID')

                logger.info('Payment %s marked PAID via webhook', p.id)
                return Response({'ok': True})

            # For explicit failure statuses, mark FAILED
            if status_text and status_text.lower() in FAILURE_STATUSES:
                p.status = Payment.STATUS_FAILED
                p.paynow_response = p.paynow_response or {}
                p.paynow_response['last_webhook'] = data
                p.save()
                logger.info('Payment %s marked FAILED via webhook (status=%s)', p.id, status_text)
                return Response({'ok': True})

            # Otherwise, treat as intermediate: record the webhook but keep PENDING
            p.paynow_response = p.paynow_response or {}
            p.paynow_response['last_webhook'] = data
            p.save()
            logger.info('Payment %s received intermediate webhook status=%s; left as PENDING', p.id, status_text)
            return Response({'ok': True})


class PaynowReturnView(APIView):
    """User redirected back from Paynow after payment

    NOTE: this return URL is UX-only and MUST NOT be used as authoritative confirmation.
    The view should be resilient to missing or ambiguous `reference` values and must not
    raise 500 (e.g., MultipleObjectsReturned) when Paynow omits the parameter or when
    duplicate records exist. The canonical verification is done by server-to-server
    webhooks (result_url) and via polling (poll_url).
    """

    def get(self, request):
        reference = request.GET.get('reference')
        if not reference:
            logger.info('Paynow return hit without reference parameter (UX-only).')
            # Try to use the last payment stored in the user's session (set during Paynow initiation)
            last_pid = request.session.get('last_payment_id')
            if last_pid:
                try:
                    import uuid
                    uuid.UUID(last_pid)
                    payment = Payment.objects.filter(pk=last_pid).first()
                    if payment:
                        logger.info('Displaying payment summary using session last_payment_id=%s', last_pid)
                        # Clear the session key after use
                        try:
                            del request.session['last_payment_id']
                            del request.session['last_booking_id']
                            request.session.modified = True
                        except Exception:
                            pass
                        booking = payment.booking
                        # compute the same ETA/maps/poll_url context as when a payment is found
                        try:
                            avg_speed = float(getattr(settings, 'AVERAGE_SPEED_KMH', 40.0))
                        except Exception:
                            avg_speed = 40.0
                        eta_minutes = None
                        if booking.distance_km:
                            try:
                                eta_minutes = int(round((float(booking.distance_km) / avg_speed) * 60))
                            except Exception:
                                eta_minutes = None
                        maps_url = None
                        try:
                            if booking.pickup_lat and booking.pickup_lng and booking.dropoff_lat and booking.dropoff_lng:
                                maps_url = f"https://www.google.com/maps/dir/?api=1&origin={booking.pickup_lat},{booking.pickup_lng}&destination={booking.dropoff_lat},{booking.dropoff_lng}&travelmode=driving"
                            else:
                                from urllib.parse import urlencode
                                params = {'api': 1, 'origin': booking.pickup_address, 'destination': booking.dropoff_address, 'travelmode': 'driving'}
                                maps_url = "https://www.google.com/maps/dir/?" + urlencode(params)
                        except Exception:
                            maps_url = None
                        from django.urls import reverse
                        poll_url = reverse('rides:paynow_poll', args=[payment.pk])
                        return render(request, 'rides/paynow_return.html', {
                            'payment': payment,
                            'booking': booking,
                            'eta_minutes': eta_minutes,
                            'maps_url': maps_url,
                            'poll_url': poll_url,
                            'TAXI_OWNER_PHONE': settings.TAXI_OWNER_PHONE,
                        })
                except Exception:
                    logger.exception('Error while attempting to use session last_payment_id')

            # Fallback: show a friendly, non-alarming page with a lookup form so users can check their payment
            # by pasting a Booking ID, Payment ID or Paynow reference.
            return render(request, 'rides/paynow_return.html', {
                'message': 'We did not receive a payment reference from Paynow. If you completed payment, we will confirm it by email shortly. You can also enter your Booking ID, Payment ID or Paynow reference below to check status.',
                'TAXI_OWNER_PHONE': settings.TAXI_OWNER_PHONE,
            })

        # First try to match a local payment id (we pass payment.id as the 'reference' when initiating)
        payment = None
        try:
            import uuid
            # Only attempt PK lookup if the reference is a valid UUID (avoid ValidationError on non-UUIDs)
            uuid.UUID(reference)
            payment = Payment.objects.filter(pk=reference).first()
        except Exception:
            payment = None

        # If not found by local id, try to match Paynow's reference. If multiple matches,
        # prefer the most-recent pending payment, then latest by created_at.
        if not payment:
            candidates = Payment.objects.filter(paynow_reference=reference).order_by('-created_at')
            if candidates.exists():
                payment = candidates.filter(status=Payment.STATUS_PENDING).first() or candidates.first()

        if not payment:
            logger.warning('Paynow return for unknown reference: %s', reference)
            return render(request, 'rides/error.html', {
                'message': 'Payment not found. If you have completed payment, check your email or contact support.',
                'TAXI_OWNER_PHONE': settings.TAXI_OWNER_PHONE,
            })

        booking = payment.booking
        # Compute a simple ETA estimate using distance and a configurable average speed
        try:
            avg_speed = float(getattr(settings, 'AVERAGE_SPEED_KMH', 40.0))
        except Exception:
            avg_speed = 40.0
        eta_minutes = None
        if booking.distance_km:
            try:
                eta_minutes = int(round((float(booking.distance_km) / avg_speed) * 60))
            except Exception:
                eta_minutes = None

        # Build Google Maps directions URL (prefer coordinates when available)
        maps_url = None
        try:
            if booking.pickup_lat and booking.pickup_lng and booking.dropoff_lat and booking.dropoff_lng:
                maps_url = f"https://www.google.com/maps/dir/?api=1&origin={booking.pickup_lat},{booking.pickup_lng}&destination={booking.dropoff_lat},{booking.dropoff_lng}&travelmode=driving"
            else:
                from urllib.parse import urlencode
                params = {'api': 1, 'origin': booking.pickup_address, 'destination': booking.dropoff_address, 'travelmode': 'driving'}
                maps_url = "https://www.google.com/maps/dir/?" + urlencode(params)
        except Exception:
            maps_url = None

        # Poll URL for client-side JS to check payment status
        from django.urls import reverse
        poll_url = reverse('rides:paynow_poll', args=[payment.pk])

        context = {
            'payment': payment,
            'booking': booking,
            'TAXI_OWNER_PHONE': settings.TAXI_OWNER_PHONE,
            'eta_minutes': eta_minutes,
            'maps_url': maps_url,
            'poll_url': poll_url,
        }
        return render(request, 'rides/paynow_return.html', context)


class PaynowPollView(APIView):
    """AJAX endpoint to poll Paynow for a payment status.

    GET /rides/paynow/poll/<payment_id>/ => { paid: bool, status: str }
    """

    def get(self, request, pk):
        # import locally to keep top-level imports minimal
        import requests as _requests
        paynow = PaynowService()

        payment = get_object_or_404(Payment, pk=pk)

        # If already paid, short-circuit
        if payment.status == Payment.STATUS_PAID:
            return Response({'paid': True, 'status': 'PAID', 'message': 'Already confirmed'})

        # Try to find poll url where Paynow exposes the check endpoint
        pr = payment.paynow_response or {}
        poll_url = pr.get('pollUrl') or pr.get('poll_url') or (pr.get('response') or {}).get('poll_url') or (pr.get('response') or {}).get('pollUrl') or (pr.get('response') or {}).get('data', {}).get('poll_url')

        # As a last resort attempt to compose a Paynow check URL using the paynow_reference
        if not poll_url and payment.paynow_reference:
            poll_url = f"https://www.paynow.co.zw/Interface/CheckPayment/?guid={payment.paynow_reference}"

        if not poll_url:
            return Response({'error': 'no_poll_url', 'message': 'No poll URL available for this payment.'}, status=status.HTTP_400_BAD_REQUEST)

        # Use PaynowService.verify_payment (SDK) if available, otherwise fall back to a simple HTTP probe
        try:
            status_obj = paynow.verify_payment(poll_url)
        except Exception as e:
            logger.exception('Error checking Paynow status: %s', e)
            return Response({'error': 'verify_failed', 'message': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        # Log poll result for diagnostics (include first chunk of any scraped response when present)
        try:
            logger.debug('Paynow poll result for %s: %s', poll_url, status_obj)
        except Exception:
            pass

        if status_obj.get('paid'):
            from django.db import transaction
            with transaction.atomic():
                p = Payment.objects.select_for_update().get(pk=payment.pk)
                if p.status == Payment.STATUS_PAID:
                    logger.info('Poll: payment %s already PAID', p.id)
                    return Response({'paid': True, 'status': status_obj.get('status')})

                # Optionally verify amount via status_obj if included (SDK may return amount)
                # Transition to PAID
                p.status = Payment.STATUS_PAID
                p.save()

                booking = p.booking
                booking.status = RideBooking.STATUS_CONFIRMED
                booking.save()

            # Send notifications outside DB transaction
            EmailService.send_payment_confirmation(booking)
            EmailService.send_owner_notification(booking, payment_status='PAID')

            return Response({'paid': True, 'status': status_obj.get('status')})

        return Response({'paid': False, 'status': status_obj.get('status')})


class PriceEstimateView(APIView):
    """Estimate price without creating a booking. Accepts distance_km or coordinates plus passenger info."""
    def post(self, request):
        serializer = PriceEstimateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        distance = data.get('distance_km')
        if distance is None:
            try:
                from .services.distance import DistanceService
                distance = DistanceService.get_distance_km(
                    (data.get('pickup_lat'), data.get('pickup_lng')),
                    (data.get('dropoff_lat'), data.get('dropoff_lng')),
                )
            except Exception as exc:
                logger.exception("Distance computation failed in price estimate")
                return Response({"detail": f"Unable to compute distance: {exc}"}, status=status.HTTP_400_BAD_REQUEST)

        breakdown = PricingService.calculate(
            distance_km=distance,
            num_adults=data.get('num_adults', 1),
            num_kids_seated=data.get('num_kids_seated', 0),
            num_kids_carried=data.get('num_kids_carried', 0),
            luggage_count=data.get('luggage_count', 0),
        )

        return Response(breakdown)


# Wizard-based booking views (for new step-by-step booking_wizard.html)

class BookingWizardView(TemplateView):
    """Multi-step wizard view handling all 5 steps of the booking flow"""
    template_name = 'rides/booking_wizard.html'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        # Load current wizard state from session
        wizard_state = self.request.session.get('booking_wizard_state', {})
        ctx['GOOGLE_MAPS_CLIENT_KEY'] = settings.GOOGLE_MAPS_CLIENT_KEY
        ctx['TAXI_OWNER_PHONE'] = settings.TAXI_OWNER_PHONE
        ctx['wizard_state'] = wizard_state
        ctx['current_step'] = wizard_state.get('step', 1)
        return ctx

    def get(self, request, *args, **kwargs):
        """Render the wizard template"""
        # Initialize session state if not exists
        if 'booking_wizard_state' not in request.session:
            request.session['booking_wizard_state'] = {
                'step': 1,
                'data': {
                    'pickup_address': '',
                    'pickup_lat': None,
                    'pickup_lng': None,
                    'dropoff_address': '',
                    'dropoff_lat': None,
                    'dropoff_lng': None,
                    'distance_km': None,
                    'num_adults': 1,
                    'num_kids_seated': 0,
                    'num_kids_carried': 0,
                    'luggage_count': 0,
                    'phone': '',
                    'email': '',
                    'special_instructions': '',
                    'payment_option': None,
                    'price_breakdown': None,
                    'total_amount': None,
                },
                'visited_steps': [1],
            }
            request.session.modified = True

        return super().get(request, *args, **kwargs)

    def post(self, request, *args, **kwargs):
        """Handle form submission at each step"""
        import json
        from .forms import (
            BookingStep1Form, BookingStep2Form, BookingStep3Form,
            BookingStep4Form, BookingStep5Form
        )

        # Get current step from POST data
        current_step = int(request.POST.get('step', 1))

        # Map step number to form class
        step_forms = {
            1: BookingStep1Form,
            2: BookingStep2Form,
            3: BookingStep3Form,
            4: BookingStep4Form,
            5: BookingStep5Form,
        }

        form_class = step_forms.get(current_step, BookingStep1Form)
        form = form_class(request.POST)

        if form.is_valid():
            # Update session with validated data
            wizard_state = request.session.get('booking_wizard_state', {})
            wizard_state['data'].update(form.cleaned_data)
            wizard_state['step'] = min(current_step + 1, 5)
            visited = wizard_state.get('visited_steps', [])
            if current_step not in visited:
                visited.append(current_step)
            wizard_state['visited_steps'] = visited

            request.session['booking_wizard_state'] = wizard_state
            request.session.modified = True

            return Response({
                'success': True,
                'next_step': wizard_state['step'],
                'data': wizard_state['data']
            })
        else:
            return Response({
                'success': False,
                'errors': form.errors
            }, status=status.HTTP_400_BAD_REQUEST)


class DistanceCalculateView(APIView):
    """Calculate distance between pickup and dropoff coordinates"""

    def post(self, request):
        """
        POST /api/booking/distance/
        Request body: { pickup_lat, pickup_lng, dropoff_lat, dropoff_lng }
        Response: { distance_km: <float> }
        """
        from .services.distance import DistanceService

        pickup_lat = request.data.get('pickup_lat')
        pickup_lng = request.data.get('pickup_lng')
        dropoff_lat = request.data.get('dropoff_lat')
        dropoff_lng = request.data.get('dropoff_lng')

        if not all([pickup_lat, pickup_lng, dropoff_lat, dropoff_lng]):
            return Response(
                {'detail': 'Missing coordinates'},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            distance = DistanceService.get_distance_km(
                (float(pickup_lat), float(pickup_lng)),
                (float(dropoff_lat), float(dropoff_lng))
            )
            return Response({'distance_km': distance})
        except Exception as exc:
            logger.exception('Distance calculation failed')
            return Response(
                {'detail': f'Unable to calculate distance: {exc}'},
                status=status.HTTP_400_BAD_REQUEST
            )


class WizardStateView(APIView):
    """Get or update the current wizard session state"""

    def get(self, request):
        """GET /api/booking/wizard-state/"""
        wizard_state = request.session.get('booking_wizard_state', {})
        return Response(wizard_state)

    def post(self, request):
        """POST /api/booking/wizard-state/ - Save state to session"""
        wizard_state = request.data.get('state', {})
        request.session['booking_wizard_state'] = wizard_state
        request.session.modified = True
        return Response({'success': True})
