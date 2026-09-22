import pytest
from django.urls import reverse
from django.test import override_settings

URL = '/booking/dev-fill/'

@pytest.mark.django_db
@override_settings(ENABLE_DEV_FILL=True)
def test_seeds_and_jumps(monkeypatch, client):
    monkeypatch.setattr('rides.services.distance.DistanceService.get_distance_km',
                        lambda o, d, use_cache=True: 14.0)
    r = client.get(URL + '?step=5')
    assert r.status_code == 302, r.content[:400]
    assert r['Location'].endswith('/booking/step/5/')

    page = client.get(r['Location'])
    assert page.status_code == 200, 'seeded session must satisfy the payment step'
    assert page.context['fare_breakdown']['total'] > 0
    assert page.context['step3_data']['email'] == 'dev@example.com'

@pytest.mark.django_db
@override_settings(ENABLE_DEV_FILL=True)
def test_variants(monkeypatch, client):
    monkeypatch.setattr('rides.services.distance.DistanceService.get_distance_km',
                        lambda o, d, use_cache=True: 120.0)
    r = client.get(URL + '?step=4&type=airport&return=1&stops=2&km=120')
    assert r.status_code == 302, r.content[:400]
    page = client.get(r['Location'])
    s1 = page.context['step1_data']
    assert s1['pickup_is_airport'] is True
    assert s1['arrival_airline'] == 'Airlink'
    assert s1['is_return_trip'] is True
    assert len(s1['stops']) == 2, 'stops travel with the trip'
    assert page.context['fare_breakdown']['is_return_trip'] is True

@pytest.mark.django_db
@override_settings(ENABLE_DEV_FILL=False)
def test_hidden_in_production(client):
    assert client.get(URL).status_code == 404
