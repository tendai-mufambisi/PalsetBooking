import pytest
from django.urls import reverse
from rest_framework.test import APIClient

from rides.models import RideBooking, Payment


@pytest.mark.django_db
def test_get_booking_form(client):
    resp = client.get(reverse('rides:home'))
    assert resp.status_code == 200
    assert b'Book a Ride' in resp.content or b'Book a ride' in resp.content


@pytest.mark.django_db
def test_post_booking_form_poa(monkeypatch, client):
    # Mock distance service
    monkeypatch.setattr('rides.services.distance.DistanceService.get_distance_km', lambda o, d, use_cache=True: 14.0)
    # Prevent emails
    monkeypatch.setattr('rides.services.email_service.EmailService.send_owner_notification', lambda b, payment_status='': None)
    monkeypatch.setattr('rides.services.email_service.EmailService.send_customer_notification', lambda b, payment_status='': None)

    payload = {
        'pickup_address': 'Start',
        'pickup_lat': '-17.8',
        'pickup_lng': '31.0',
        'dropoff_address': 'End',
        'dropoff_lat': '-17.9',
        'dropoff_lng': '31.1',
        'num_adults': '1',
        'num_kids_carried': '0',
        'luggage_count': '0',
        'phone': '+263789000000',
        'email': 'test@example.com',
        'payment_option': 'POA',
    }

    resp = client.post(reverse('rides:home'), data=payload, follow=True)
    # Should redirect to success
    assert resp.status_code == 200
    assert b'Booking Confirmed' in resp.content

    # Verify booking exists
    assert RideBooking.objects.count() == 1
    booking = RideBooking.objects.first()
    assert booking.status == RideBooking.STATUS_CONFIRMED
    assert booking.total_amount > 0

    payments = list(booking.payments.all())
    assert len(payments) == 1
    assert payments[0].method == RideBooking.PAYMENT_ON_ARRIVAL
    assert payments[0].status == Payment.STATUS_PENDING
