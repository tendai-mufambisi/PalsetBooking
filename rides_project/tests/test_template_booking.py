"""End-to-end coverage of the multi-step booking wizard.

These replace two older tests that pointed at `rides:home`, the single-page
booking form that was removed when the wizard took over.
"""

from datetime import timedelta

import pytest
from django.urls import reverse
from django.utils import timezone

from rides.models import RideBooking, Payment


def _future(days=2):
    return timezone.localtime() + timedelta(days=days)


@pytest.mark.django_db
def test_get_service_selector(client):
    resp = client.get(reverse('rides:service_selector'))
    assert resp.status_code == 200
    assert b'Book a Ride' in resp.content or b'Book a ride' in resp.content


@pytest.mark.django_db
def test_get_wizard_step_one(client):
    resp = client.get(reverse('rides:booking_wizard', kwargs={'step': 1}))
    assert resp.status_code == 200
    assert b'pickup_address' in resp.content


@pytest.mark.django_db
def test_wizard_creates_pay_on_arrival_booking(monkeypatch, client):
    monkeypatch.setattr(
        'rides.services.distance.DistanceService.get_distance_km',
        lambda o, d, use_cache=True: 14.0,
    )
    monkeypatch.setattr(
        'rides.services.email_service.EmailService.send_owner_notification',
        lambda b, payment_status='': None,
    )
    monkeypatch.setattr(
        'rides.services.email_service.EmailService.send_customer_notification',
        lambda b, payment_status='': None,
    )

    pickup = _future()

    resp = client.post(reverse('rides:booking_wizard', kwargs={'step': 1}), {
        'pickup_address': 'Start',
        'dropoff_address': 'End',
        'pickup_latitude': -17.8,
        'pickup_longitude': 31.0,
        'dropoff_latitude': -17.9,
        'dropoff_longitude': 31.1,
        'distance_km': 14.0,
        'pickup_date': pickup.date().isoformat(),
        'pickup_time': '10:00',
    })
    assert resp.status_code == 302

    # Passengers and contact are collected together on step 2
    resp = client.post(reverse('rides:booking_wizard', kwargs={'step': 2}), {
        'num_adults': 1,
        'baby_car_seater': 0,
        'num_kids_carried': 0,
        'luggage_count': 0,
        'hand_luggage_count': 0,
        'passenger_full_name': 'Test Passenger',
        'salutation': 'Mr',
        'phone': '+263789000000',
        'email': 'test@example.com',
    })
    assert resp.status_code == 302

    # Step 3 only reviews; the payment choice is posted from step 4
    resp = client.get(reverse('rides:booking_wizard', kwargs={'step': 3}))
    assert resp.status_code == 200

    resp = client.post(
        reverse('rides:booking_wizard', kwargs={'step': 4}),
        {'payment_method': RideBooking.PAYMENT_ON_ARRIVAL},
        follow=True,
    )
    assert resp.status_code == 200
    assert b'Booking Confirmed' in resp.content

    assert RideBooking.objects.count() == 1
    booking = RideBooking.objects.first()
    assert booking.status == RideBooking.STATUS_CONFIRMED
    assert booking.total_amount > 0
    assert booking.passenger_full_name == 'Test Passenger'

    payments = list(booking.payments.all())
    assert len(payments) == 1
    assert payments[0].method == RideBooking.PAYMENT_ON_ARRIVAL
    assert payments[0].status == Payment.STATUS_PENDING


@pytest.mark.django_db
def test_wizard_rejects_lapsed_pickup(client):
    past = timezone.localtime() - timedelta(days=1)

    resp = client.post(reverse('rides:booking_wizard', kwargs={'step': 1}), {
        'pickup_address': 'Start',
        'dropoff_address': 'End',
        'pickup_latitude': -17.8,
        'pickup_longitude': 31.0,
        'dropoff_latitude': -17.9,
        'dropoff_longitude': 31.1,
        'distance_km': 14.0,
        'pickup_date': past.date().isoformat(),
        'pickup_time': '10:00',
    })

    # Re-renders step 1 with the error rather than moving on
    assert resp.status_code == 200
    assert b'already passed' in resp.content
    assert RideBooking.objects.count() == 0


@pytest.mark.django_db
def test_edit_modal_saves_changes_and_reprices(monkeypatch, client):
    """The review page's Edit modal writes through the same validation."""
    monkeypatch.setattr(
        'rides.services.distance.DistanceService.get_distance_km',
        lambda o, d, use_cache=True: 14.0,
    )

    pickup = _future()
    trip = {
        'pickup_address': 'Start',
        'dropoff_address': 'End',
        'pickup_latitude': -17.8,
        'pickup_longitude': 31.0,
        'dropoff_latitude': -17.9,
        'dropoff_longitude': 31.1,
        'distance_km': 14.0,
        'pickup_date': pickup.date().isoformat(),
        'pickup_time': '10:00',
    }
    client.post(reverse('rides:booking_wizard', kwargs={'step': 1}), trip)
    client.post(reverse('rides:booking_wizard', kwargs={'step': 2}), {
        'num_adults': 1,
        'baby_car_seater': 0,
        'num_kids_carried': 0,
        'luggage_count': 0,
        'hand_luggage_count': 0,
        'passenger_full_name': 'Test Passenger',
        'salutation': 'Mr',
        'phone': '+263789000000',
        'email': 'test@example.com',
    })

    before = client.get(reverse('rides:booking_wizard', kwargs={'step': 3}))
    assert before.status_code == 200
    original_total = before.context['fare_breakdown']['total']

    # The modal posts every field at once, not just the edited section.
    resp = client.post(reverse('rides:booking_wizard_edit'), dict(trip, **{
        'num_adults': 4,
        'baby_car_seater': 0,
        'num_kids_carried': 0,
        'luggage_count': 0,
        'hand_luggage_count': 0,
        'passenger_full_name': 'Test Passenger',
        'salutation': 'Mr',
        'phone': '+263789111111',
        'email': 'changed@example.com',
    }))
    assert resp.status_code == 200
    assert resp.json() == {'ok': True}

    after = client.get(reverse('rides:booking_wizard', kwargs={'step': 3}))
    assert after.context['step3_data']['email'] == 'changed@example.com'
    assert after.context['step2_data']['num_adults'] == 4
    # Three extra adults are chargeable, so the fare must have moved.
    assert after.context['fare_breakdown']['total'] > original_total


@pytest.mark.django_db
def test_edit_modal_rejects_invalid_contact(monkeypatch, client):
    monkeypatch.setattr(
        'rides.services.distance.DistanceService.get_distance_km',
        lambda o, d, use_cache=True: 14.0,
    )

    pickup = _future()
    trip = {
        'pickup_address': 'Start',
        'dropoff_address': 'End',
        'pickup_latitude': -17.8,
        'pickup_longitude': 31.0,
        'dropoff_latitude': -17.9,
        'dropoff_longitude': 31.1,
        'distance_km': 14.0,
        'pickup_date': pickup.date().isoformat(),
        'pickup_time': '10:00',
    }
    client.post(reverse('rides:booking_wizard', kwargs={'step': 1}), trip)
    client.post(reverse('rides:booking_wizard', kwargs={'step': 2}), {
        'num_adults': 1,
        'baby_car_seater': 0,
        'num_kids_carried': 0,
        'luggage_count': 0,
        'hand_luggage_count': 0,
        'passenger_full_name': 'Test Passenger',
        'salutation': 'Mr',
        'phone': '+263789000000',
        'email': 'test@example.com',
    })

    resp = client.post(reverse('rides:booking_wizard_edit'), dict(trip, **{
        'num_adults': 1,
        'baby_car_seater': 0,
        'num_kids_carried': 0,
        'luggage_count': 0,
        'hand_luggage_count': 0,
        'passenger_full_name': 'Test Passenger',
        'salutation': 'Mr',
        'phone': '+263789000000',
        'email': '',
    }))
    assert resp.status_code == 400
    assert resp.json()['ok'] is False
    assert 'email' in resp.json()['errors']

    # Nothing was written through
    after = client.get(reverse('rides:booking_wizard', kwargs={'step': 3}))
    assert after.context['step3_data']['email'] == 'test@example.com'


@pytest.mark.django_db
def test_no_template_comment_leaks(monkeypatch, client):
    """Nothing that is meant to be a comment may reach the customer."""
    monkeypatch.setattr('rides.services.distance.DistanceService.get_distance_km',
                        lambda o, d, use_cache=True: 14.0)
    pickup = _future()

    pages = [client.get(reverse('rides:booking_wizard', kwargs={'step': 1}))]

    client.post(reverse('rides:booking_wizard', kwargs={'step': 1}), dict(
        pickup_address='Start', dropoff_address='End',
        pickup_latitude=-17.8, pickup_longitude=31.0,
        dropoff_latitude=-17.9, dropoff_longitude=31.1,
        distance_km=14.0, pickup_date=pickup.date().isoformat(), pickup_time='10:00'))
    pages.append(client.get(reverse('rides:booking_wizard', kwargs={'step': 2})))

    client.post(reverse('rides:booking_wizard', kwargs={'step': 2}), {
        'num_adults': 1, 'baby_car_seater': 0, 'num_kids_carried': 0,
        'luggage_count': 0, 'hand_luggage_count': 0,
        'passenger_full_name': 'Ada L', 'salutation': 'Ms',
        'phone': '+263789000000', 'email': 'a@b.com'})
    pages.append(client.get(reverse('rides:booking_wizard', kwargs={'step': 3})))
    pages.append(client.get(reverse('rides:booking_wizard', kwargs={'step': 4})))

    for i, resp in enumerate(pages, start=1):
        body = resp.content.decode()
        for marker in ('{#', '#}', '{% comment', '{% endcomment', '{%', '{{'):
            assert marker not in body, 'step %d leaks %r' % (i, marker)
    print('NO LEAKS on steps 1-3')


def _setup(client):
    pickup = _future()
    client.post(reverse('rides:booking_wizard', kwargs={'step': 1}), dict(
        pickup_address='Start', dropoff_address='End',
        pickup_latitude=-17.8, pickup_longitude=31.0,
        dropoff_latitude=-17.9, dropoff_longitude=31.1,
        distance_km=14.0, pickup_date=pickup.date().isoformat(), pickup_time='10:00'))
    client.post(reverse('rides:booking_wizard', kwargs={'step': 2}), {
        'num_adults': 2, 'baby_car_seater': 0, 'num_kids_carried': 0,
        'luggage_count': 0, 'hand_luggage_count': 0,
        'passenger_full_name': 'Ada L', 'salutation': 'Ms',
        'phone': '+263789000000', 'email': 'a@b.com'})

@pytest.mark.django_db
def test_four_steps_and_payment_page(monkeypatch, client):
    monkeypatch.setattr('rides.services.distance.DistanceService.get_distance_km',
                        lambda o, d, use_cache=True: 14.0)
    _setup(client)

    b1 = client.get(reverse('rides:booking_wizard', kwargs={'step': 1})).content.decode()
    assert 'Step 1 of 4' in b1
    assert 'Book a Ride' in b1 and 'Fast, safe, and affordable' in b1   # banner on step 1
    assert 'app-bar' in b1 and 'position: sticky' in b1

    b2 = client.get(reverse('rides:booking_wizard', kwargs={'step': 2})).content.decode()
    assert 'Step 2 of 4' in b2
    assert 'Fast, safe, and affordable' not in b2, 'banner should be step 1 only'

    b3 = client.get(reverse('rides:booking_wizard', kwargs={'step': 3})).content.decode()
    assert 'Step 3 of 4' in b3
    assert 'payment_method' not in b3, 'payment moved off the review step'
    assert 'Fare details' in b3 and 'Check your booking' in b3
    assert 'Continue to payment' in b3

    r4 = client.get(reverse('rides:booking_wizard', kwargs={'step': 4}))
    b4 = r4.content.decode()
    assert 'Step 4 of 4' in b4
    total = r4.context['fare_breakdown']['total']
    assert ('$%.2f' % total) in b4, 'headline total missing'
    # One merged arrival card, with cash/card asked underneath
    import re
    values = re.findall(r'<input[^>]*name="payment_method"[^>]*value="([^"]+)"', b4)
    expected = ['POA', 'pos_card', 'money_transfer', 'paylink']
    if r4.context['paynow_allowed']:
        expected.append('PAYNOW')
    else:
        assert 'pay-card is-disabled' in b4, 'Paynow should show as unavailable, not vanish'
    assert sorted(values) == sorted(expected), values
    # Cash/card is asked in a dialog, not a panel at the foot of the page
    assert 'pay_arrival' in b4 and 'id="arrival_modal"' in b4
    assert 'wz-modal' in b4
    assert 'How will you pay the driver?' in b4
    # Green page background is gone
    assert 'linear-gradient(135deg, #10b981 0%, #047857 100%)' not in b4

@pytest.mark.django_db
def test_cash_and_card_both_reach_the_booking(monkeypatch, client):
    monkeypatch.setattr('rides.services.distance.DistanceService.get_distance_km',
                        lambda o, d, use_cache=True: 14.0)
    for sent, expected in ((RideBooking.PAYMENT_ON_ARRIVAL, RideBooking.PAYMENT_ON_ARRIVAL),
                           (RideBooking.PAYMENT_CARD_ON_ARRIVAL, RideBooking.PAYMENT_CARD_ON_ARRIVAL)):
        RideBooking.objects.all().delete()
        c = client.__class__()
        monkeypatch.setattr('rides.services.email_service.EmailService.send_owner_notification',
                            lambda b, payment_status='': None)
        monkeypatch.setattr('rides.services.email_service.EmailService.send_customer_notification',
                            lambda b, payment_status='': None)
        _setup(c)
        resp = c.post(reverse('rides:booking_wizard', kwargs={'step': 4}),
                      {'payment_method': sent}, follow=True)
        assert resp.status_code == 200
        assert b'Booking Confirmed' in resp.content
        booking = RideBooking.objects.first()
        assert booking.payment_option == expected, (sent, booking.payment_option)
    print('CASH + CARD OK')
