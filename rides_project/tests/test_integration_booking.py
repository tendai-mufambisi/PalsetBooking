import pytest
from rest_framework.test import APIClient
from django.urls import reverse

from rides.models import RideBooking, Payment
from rides.services.pricing import PricingService


@pytest.mark.django_db
def test_booking_pay_on_arrival_uses_distance_service(monkeypatch):
    client = APIClient()

    # Mock DistanceService to return 14 km
    monkeypatch.setattr('rides.services.distance.DistanceService.get_distance_km', lambda origin, destination, use_cache=True: 14.0)

    # Prevent emails from sending
    monkeypatch.setattr('rides.services.email_service.EmailService.send_owner_notification', lambda booking, payment_status='UNPAID': None)
    monkeypatch.setattr('rides.services.email_service.EmailService.send_customer_notification', lambda booking, payment_status='UNPAID': None)

    payload = {
        'pickup_address': 'Start',
        'pickup_lat': -17.8,
        'pickup_lng': 31.0,
        'dropoff_address': 'End',
        'dropoff_lat': -17.9,
        'dropoff_lng': 31.1,
        'num_adults': 1,
        'num_kids_carried': 0,
        'luggage_count': 0,
        'phone': '+263789000000',
        'email': 'test@example.com',
        'payment_option': RideBooking.PAYMENT_ON_ARRIVAL,
    }

    resp = client.post(reverse('rides:create_booking'), payload, format='json')
    assert resp.status_code == 201

    booking = RideBooking.objects.get(pk=resp.data['id'])
    assert booking.status == RideBooking.STATUS_CONFIRMED

    expected_total = PricingService.calculate(distance_km=14.0)['total']
    assert float(booking.total_amount) == float(expected_total)

    # Ensure a Payment record was created and is pending
    payments = list(booking.payments.all())
    assert len(payments) == 1
    assert payments[0].method == RideBooking.PAYMENT_ON_ARRIVAL
    assert payments[0].status == Payment.STATUS_PENDING


@pytest.mark.django_db
def test_booking_paynow_initiates_transaction(monkeypatch):
    client = APIClient()

    # Mock DistanceService to return 40 km
    monkeypatch.setattr('rides.services.distance.DistanceService.get_distance_km', lambda origin, destination, use_cache=True: 40.0)

    # Mock PaynowService.create_transaction to return reference and redirect URL
    def fake_create(self, amount, reference, email, phone, return_url=None):
        return {'reference': 'fake-ref-123', 'redirectUrl': 'https://paynow.example/redirect'}

    monkeypatch.setattr('rides.services.paynow.PaynowService.create_transaction', fake_create)

    # Prevent emails from sending
    monkeypatch.setattr('rides.services.email_service.EmailService.send_owner_notification', lambda booking, payment_status='UNPAID': None)
    monkeypatch.setattr('rides.services.email_service.EmailService.send_customer_notification', lambda booking, payment_status='UNPAID': None)

    payload = {
        'pickup_address': 'Start',
        'pickup_lat': -17.8,
        'pickup_lng': 31.0,
        'dropoff_address': 'End',
        'dropoff_lat': -17.9,
        'dropoff_lng': 31.1,
        'num_adults': 1,
        'num_kids_carried': 0,
        'luggage_count': 0,
        'phone': '+263789000000',
        'email': 'test@example.com',
        'payment_option': RideBooking.PAYMENT_PAYNOW,
    }

    resp = client.post(reverse('rides:create_booking'), payload, format='json')
    assert resp.status_code == 201

    # Ensure redirect_url returned and payment created with reference
    assert 'redirect_url' in resp.data
    payment_data = resp.data['payment']
    assert payment_data['status'] == Payment.STATUS_PENDING
    assert payment_data['paynow_reference'] == 'fake-ref-123'

    # Verify DB payment record
    payment = Payment.objects.get(id=payment_data['id'])
    assert payment.paynow_reference == 'fake-ref-123'
    assert payment.status == Payment.STATUS_PENDING
