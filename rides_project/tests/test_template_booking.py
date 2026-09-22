"""End-to-end coverage of the multi-step booking wizard.

These replace two older tests that pointed at `rides:home`, the single-page
booking form that was removed when the wizard took over.
"""

import re
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

    # Step 2 is passengers and luggage only
    resp = client.post(reverse('rides:booking_wizard', kwargs={'step': 2}), {
        'num_adults': 1,
        'baby_car_seater': 0,
        'num_kids_carried': 0,
        'luggage_count': 0,
        'hand_luggage_count': 0,
    })
    assert resp.status_code == 302

    # Step 3 is the contact details, including the name for the placard
    resp = client.post(reverse('rides:booking_wizard', kwargs={'step': 3}), {
        'passenger_full_name': 'Test Passenger',
        'salutation': 'Mr',
        'phone': '+263789000000',
        'email': 'test@example.com',
    })
    assert resp.status_code == 302

    # Step 4 only reviews; the payment choice is posted from step 5
    resp = client.get(reverse('rides:booking_wizard', kwargs={'step': 4}))
    assert resp.status_code == 200

    resp = client.post(
        reverse('rides:booking_wizard', kwargs={'step': 5}),
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
    })
    client.post(reverse('rides:booking_wizard', kwargs={'step': 3}), {
        'passenger_full_name': 'Test Passenger',
        'salutation': 'Mr',
        'phone': '+263789000000',
        'email': 'test@example.com',
    })

    before = client.get(reverse('rides:booking_wizard', kwargs={'step': 4}))
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

    after = client.get(reverse('rides:booking_wizard', kwargs={'step': 4}))
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
    })
    client.post(reverse('rides:booking_wizard', kwargs={'step': 3}), {
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
    after = client.get(reverse('rides:booking_wizard', kwargs={'step': 4}))
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
        'luggage_count': 0, 'hand_luggage_count': 0})
    pages.append(client.get(reverse('rides:booking_wizard', kwargs={'step': 3})))

    client.post(reverse('rides:booking_wizard', kwargs={'step': 3}), {
        'passenger_full_name': 'Ada L', 'salutation': 'Ms',
        'phone': '+263789000000', 'email': 'a@b.com'})
    pages.append(client.get(reverse('rides:booking_wizard', kwargs={'step': 4})))
    pages.append(client.get(reverse('rides:booking_wizard', kwargs={'step': 5})))

    for i, resp in enumerate(pages, start=1):
        body = resp.content.decode()
        for marker in ('{#', '#}', '{% comment', '{% endcomment', '{%', '{{'):
            assert marker not in body, 'step %d leaks %r' % (i, marker)
    print('NO LEAKS on steps 1-5')


def _setup(client):
    pickup = _future()
    client.post(reverse('rides:booking_wizard', kwargs={'step': 1}), dict(
        pickup_address='Start', dropoff_address='End',
        pickup_latitude=-17.8, pickup_longitude=31.0,
        dropoff_latitude=-17.9, dropoff_longitude=31.1,
        distance_km=14.0, pickup_date=pickup.date().isoformat(), pickup_time='10:00'))
    client.post(reverse('rides:booking_wizard', kwargs={'step': 2}), {
        'num_adults': 2, 'baby_car_seater': 0, 'num_kids_carried': 0,
        'luggage_count': 0, 'hand_luggage_count': 0})
    client.post(reverse('rides:booking_wizard', kwargs={'step': 3}), {
        'passenger_full_name': 'Ada L', 'salutation': 'Ms',
        'phone': '+263789000000', 'email': 'a@b.com'})

@pytest.mark.django_db
def test_five_steps_each_with_one_subject(monkeypatch, client):
    monkeypatch.setattr('rides.services.distance.DistanceService.get_distance_km',
                        lambda o, d, use_cache=True: 14.0)
    _setup(client)

    b1 = client.get(reverse('rides:booking_wizard', kwargs={'step': 1})).content.decode()
    assert 'Step 1 of 5' in b1
    assert 'Book a Ride' in b1 and 'Fast, safe, and affordable' in b1   # banner on step 1
    assert 'app-bar' in b1 and 'position: sticky' in b1
    # The route owns its stops, and its exact points sit with the addresses
    assert 'Stops along the way' in b1 and 'add_stop_btn' in b1
    assert 'Exact pickup point' in b1 and 'points_toggle' not in b1
    # Airport pickup is the first card offered
    assert b1.index('trip_type_airport') < b1.index('trip_type_regular')
    assert 'My flight details' in b1
    assert 'Add more flight details' not in b1
    for gone in ('Departures / Drop-off', 'Private &amp; Charter Terminal'):
        assert gone not in b1, gone

    b2 = client.get(reverse('rides:booking_wizard', kwargs={'step': 2})).content.decode()
    assert 'Step 2 of 5' in b2
    assert 'Fast, safe, and affordable' not in b2, 'banner should be step 1 only'
    # Step 2 is passengers and luggage, nothing else
    for stray in ('id="phone"', 'id="email"', 'placard', 'Stops along the way'):
        assert stray not in b2, stray
    assert 'Long distance trip' not in b2, 'the long distance notice is step 1 + payment only'

    b3 = client.get(reverse('rides:booking_wizard', kwargs={'step': 3})).content.decode()
    assert 'Step 3 of 5' in b3
    assert 'placard' in b3
    assert 'id="phone"' in b3 and 'id="email"' in b3

    b4 = client.get(reverse('rides:booking_wizard', kwargs={'step': 4})).content.decode()
    assert 'Step 4 of 5' in b4
    assert 'payment_method' not in b4, 'payment moved off the review step'
    assert 'Fare details' in b4 and 'Check your booking' in b4
    assert 'Continue to payment' in b4

    r5 = client.get(reverse('rides:booking_wizard', kwargs={'step': 5}))
    b5 = r5.content.decode()
    assert 'Step 5 of 5' in b5
    total = r5.context['fare_breakdown']['total']
    assert ('$%.2f' % total) in b5, 'headline total missing'
    # One merged arrival card, with cash/card asked underneath
    import re
    values = re.findall(r'<input[^>]*name="payment_method"[^>]*value="([^"]+)"', b5)
    expected = ['POA', 'pos_card', 'money_transfer', 'paylink']
    if r5.context['paynow_allowed']:
        expected.append('PAYNOW')
    else:
        assert 'pay-card is-disabled' in b5, 'Paynow should show as unavailable, not vanish'
    assert sorted(values) == sorted(expected), values
    # Cash/card is asked in a dialog, not a panel at the foot of the page
    assert 'pay_arrival' in b5 and 'id="arrival_modal"' in b5
    assert 'wz-modal' in b5
    assert 'How will you pay the driver?' in b5
    # Paylink asks who the link is for; money transfer says who to send to
    assert 'id="paylink_modal"' in b5 and 'paylink_card_name' in b5
    assert 'Leonard Zambwi' in b5 and '263772491982' in b5
    # Green page background is gone
    assert 'linear-gradient(135deg, #10b981 0%, #047857 100%)' not in b5


@pytest.mark.django_db
def test_stops_set_on_step_one_are_priced(monkeypatch, client):
    """Stops moved to step 1 with the rest of the route, and still cost money."""
    monkeypatch.setattr('rides.services.distance.DistanceService.get_distance_km',
                        lambda o, d, use_cache=True: 14.0)
    pickup = _future()
    client.post(reverse('rides:booking_wizard', kwargs={'step': 1}), dict(
        pickup_address='Start', dropoff_address='End',
        pickup_latitude=-17.8, pickup_longitude=31.0,
        dropoff_latitude=-17.9, dropoff_longitude=31.1,
        distance_km=14.0, pickup_date=pickup.date().isoformat(), pickup_time='10:00',
        stops_json='[{"description": "Collect a parcel", "minutes": 30}]'))
    client.post(reverse('rides:booking_wizard', kwargs={'step': 2}), {
        'num_adults': 1, 'baby_car_seater': 0, 'num_kids_carried': 0,
        'luggage_count': 0, 'hand_luggage_count': 0})
    client.post(reverse('rides:booking_wizard', kwargs={'step': 3}), {
        'passenger_full_name': 'Ada L', 'salutation': 'Ms',
        'phone': '+263789000000', 'email': 'a@b.com'})

    review = client.get(reverse('rides:booking_wizard', kwargs={'step': 4}))
    stops = review.context['fare_breakdown']['stops']
    assert len(stops) == 1 and stops[0]['description'] == 'Collect a parcel'
    assert 'Collect a parcel' in review.content.decode()


@pytest.mark.django_db
def test_paylink_needs_a_card_holder_and_an_email(monkeypatch, client):
    monkeypatch.setattr('rides.services.distance.DistanceService.get_distance_km',
                        lambda o, d, use_cache=True: 14.0)
    _setup(client)

    resp = client.post(reverse('rides:booking_wizard', kwargs={'step': 5}),
                       {'payment_method': RideBooking.PAYMENT_PAYLINK})
    assert resp.status_code == 200
    assert b'card holder name' in resp.content
    assert RideBooking.objects.count() == 0


@pytest.mark.django_db
def test_paylink_details_are_stored_and_sent_to_the_owner(monkeypatch, client):
    monkeypatch.setattr('rides.services.distance.DistanceService.get_distance_km',
                        lambda o, d, use_cache=True: 14.0)
    sent = {}
    monkeypatch.setattr('rides.services.email_service.EmailService.send_owner_notification',
                        lambda b, payment_status='': sent.update(owner=b))
    monkeypatch.setattr('rides.services.email_service.EmailService.send_customer_notification',
                        lambda b, payment_status='': None)
    _setup(client)

    resp = client.post(reverse('rides:booking_wizard', kwargs={'step': 5}), {
        'payment_method': RideBooking.PAYMENT_PAYLINK,
        'paylink_card_name': 'Ada Lovelace',
        'paylink_email': 'card@example.com',
    }, follow=True)
    assert resp.status_code == 200

    booking = RideBooking.objects.get()
    assert booking.payment_option == RideBooking.PAYMENT_PAYLINK
    assert booking.paylink_card_name == 'Ada Lovelace'
    assert booking.paylink_email == 'card@example.com'
    # The owner is told, and the customer is told a link is coming
    assert sent['owner'].paylink_email == 'card@example.com'
    assert b'card@example.com' in resp.content


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
        resp = c.post(reverse('rides:booking_wizard', kwargs={'step': 5}),
                      {'payment_method': sent}, follow=True)
        assert resp.status_code == 200
        assert b'Booking Confirmed' in resp.content
        booking = RideBooking.objects.first()
        assert booking.payment_option == expected, (sent, booking.payment_option)
    print('CASH + CARD OK')


def _chosen(body):
    """What the page tells the browser about a preselected trip type."""
    return re.search(r'let typeChosen = (\w+);', body).group(1)

@pytest.mark.django_db
def test_nothing_preselected(monkeypatch, client):
    monkeypatch.setattr('rides.services.distance.DistanceService.get_distance_km',
                        lambda o, d, use_cache=True: 14.0)

    # 1. Brand new visitor
    b = client.get(reverse('rides:booking_wizard_start')).content.decode()
    assert _chosen(b) == 'false', 'fresh form must not preselect a card'
    assert 'Choose one to continue' in b

    # 2. Complete step 1, so the session now holds a trip
    pickup = _future()
    client.post(reverse('rides:booking_wizard', kwargs={'step': 1}), dict(
        pickup_address='Start', dropoff_address='End',
        pickup_latitude=-17.8, pickup_longitude=31.0,
        dropoff_latitude=-17.9, dropoff_longitude=31.1,
        distance_km=14.0, pickup_date=pickup.date().isoformat(), pickup_time='10:00'))

    # Going back to step 1 in-flow keeps the answer
    b = client.get(reverse('rides:booking_wizard', kwargs={'step': 1})).content.decode()
    assert _chosen(b) == 'true', 'Back from step 2 should keep the chosen card'
    assert 'value="Start"' in b

    # 3. Re-entering at /booking/ starts clean - this was the reported bug
    b = client.get(reverse('rides:booking_wizard_start')).content.decode()
    assert _chosen(b) == 'false', '/booking/ must start a fresh booking'
    assert 'value="Start"' not in b, 'stale address should be cleared too'

@pytest.mark.django_db
def test_rejected_step1_keeps_the_card(client):
    """A past pickup is rejected; the customer should not lose their choice."""
    past = timezone.localtime() - timedelta(days=1)
    resp = client.post(reverse('rides:booking_wizard', kwargs={'step': 1}), dict(
        pickup_address='Start', dropoff_address='End',
        pickup_latitude=-17.8, pickup_longitude=31.0,
        dropoff_latitude=-17.9, dropoff_longitude=31.1,
        distance_km=14.0, pickup_date=past.date().isoformat(), pickup_time='10:00'))
    assert resp.status_code == 200
    assert _chosen(resp.content.decode()) == 'true'


def _people_payload():
    return {
        'num_adults': 1,
        'baby_car_seater': 0,
        'num_kids_carried': 0,
        'luggage_count': 0,
        'hand_luggage_count': 0,
    }


def _contact_payload():
    return {
        'passenger_full_name': 'Test Passenger',
        'salutation': 'Mr',
        'phone': '+263789000000',
        'email': 'test@example.com',
    }


@pytest.mark.django_db
def test_airport_pickup_uses_flight_arrival_as_the_pickup_time(monkeypatch, client):
    """The airport card replaces the schedule fields, so arrival IS the pickup."""
    monkeypatch.setattr(
        'rides.services.distance.DistanceService.get_distance_km',
        lambda o, d, use_cache=True: 14.0,
    )

    arrival = _future()

    resp = client.post(reverse('rides:booking_wizard', kwargs={'step': 1}), {
        'pickup_address': 'Robert Gabriel Mugabe International Airport',
        'dropoff_address': 'End',
        'pickup_latitude': -17.93,
        'pickup_longitude': 31.09,
        'dropoff_latitude': -17.8,
        'dropoff_longitude': 31.0,
        'distance_km': 14.0,
        'pickup_is_airport': 'on',
        'pickup_airport_terminal': 'International Arrivals',
        'arrival_airline': 'Airlink',
        'arrival_flight_number': '4Z110',
        'arrival_date': arrival.date().isoformat(),
        'arrival_time': '14:30',
    })
    assert resp.status_code == 302

    client.post(reverse('rides:booking_wizard', kwargs={'step': 2}), _people_payload())
    client.post(reverse('rides:booking_wizard', kwargs={'step': 3}), _contact_payload())

    review = client.get(reverse('rides:booking_wizard', kwargs={'step': 4}))
    assert review.status_code == 200
    step1_data = review.context['step1_data']
    assert step1_data['pickup_date'] == arrival.date()
    assert step1_data['pickup_time'].strftime('%H:%M') == '14:30'
    assert step1_data['pickup_airport_terminal'] == 'International Arrivals'


@pytest.mark.django_db
def test_airport_pickup_requires_a_terminal(client):
    """An airport name alone is ambiguous, so step 1 must not advance."""
    arrival = _future()

    resp = client.post(reverse('rides:booking_wizard', kwargs={'step': 1}), {
        'pickup_address': 'Robert Gabriel Mugabe International Airport',
        'dropoff_address': 'End',
        'pickup_latitude': -17.93,
        'pickup_longitude': 31.09,
        'dropoff_latitude': -17.8,
        'dropoff_longitude': 31.0,
        'distance_km': 14.0,
        'pickup_is_airport': 'on',
        'arrival_airline': 'Airlink',
        'arrival_flight_number': '4Z110',
        'arrival_date': arrival.date().isoformat(),
        'arrival_time': '14:30',
    })

    assert resp.status_code == 200
    assert b'which part of the airport' in resp.content


@pytest.mark.django_db
def test_return_leg_with_its_own_route_is_measured_and_priced_separately(monkeypatch, client):
    """A return that starts somewhere else is re-measured, not mirrored."""
    outbound_km, return_km = 14.0, 55.0

    def fake_distance(origin, dest, use_cache=True):
        # The return leg is the only one that starts at the coordinates below.
        return return_km if round(origin[0], 2) == -17.70 else outbound_km

    monkeypatch.setattr(
        'rides.services.distance.DistanceService.get_distance_km', fake_distance
    )

    pickup = _future()
    back = _future(days=4)

    resp = client.post(reverse('rides:booking_wizard', kwargs={'step': 1}), {
        'pickup_address': 'Start',
        'dropoff_address': 'End',
        'pickup_latitude': -17.8,
        'pickup_longitude': 31.0,
        'dropoff_latitude': -17.9,
        'dropoff_longitude': 31.1,
        'distance_km': outbound_km,
        'pickup_date': pickup.date().isoformat(),
        'pickup_time': '10:00',
        'is_return_trip': 'on',
        'return_date': back.date().isoformat(),
        'return_time': '16:00',
        'return_use_different_points': 'on',
        'return_pickup_address': 'Somewhere else',
        'return_pickup_latitude': -17.70,
        'return_pickup_longitude': 31.20,
        'return_dropoff_address': 'Home',
        'return_dropoff_latitude': -17.8,
        'return_dropoff_longitude': 31.0,
    })
    assert resp.status_code == 302

    client.post(reverse('rides:booking_wizard', kwargs={'step': 2}), _people_payload())
    client.post(reverse('rides:booking_wizard', kwargs={'step': 3}), _contact_payload())

    review = client.get(reverse('rides:booking_wizard', kwargs={'step': 4}))
    breakdown = review.context['fare_breakdown']
    assert breakdown['is_return_trip'] is True
    assert breakdown['return_uses_own_route'] is True
    assert breakdown['return_distance_km'] == return_km
    assert breakdown['return_leg_fee'] > 0


@pytest.mark.django_db
def test_return_trip_must_be_after_the_outbound_pickup(client):
    pickup = _future(days=4)
    back = _future(days=2)

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
        'is_return_trip': 'on',
        'return_date': back.date().isoformat(),
        'return_time': '16:00',
    })

    assert resp.status_code == 200
    assert b'must be after the pickup' in resp.content


@pytest.mark.django_db
def test_payment_step_renders_with_the_fare(monkeypatch, client):
    """Step 5 leads with the number, so it must render before any POST."""
    monkeypatch.setattr(
        'rides.services.distance.DistanceService.get_distance_km',
        lambda o, d, use_cache=True: 14.0,
    )

    pickup = _future()
    client.post(reverse('rides:booking_wizard', kwargs={'step': 1}), {
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
    client.post(reverse('rides:booking_wizard', kwargs={'step': 2}), _people_payload())
    client.post(reverse('rides:booking_wizard', kwargs={'step': 3}), _contact_payload())

    resp = client.get(reverse('rides:booking_wizard', kwargs={'step': 5}))
    assert resp.status_code == 200
    assert resp.context['fare_breakdown']['total'] > 0
    assert b'Step 5 of 5' in resp.content
