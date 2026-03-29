import pytest
from rest_framework.test import APIClient

@pytest.mark.django_db
def test_price_estimate_by_distance():
    client = APIClient()
    payload = {
        "distance_km": 15.0,
        "num_adults": 3,
        "luggage_count": 1
    }
    resp = client.post('/api/price/', payload, format='json')
    assert resp.status_code == 200
    data = resp.json()
    assert 'total' in data
    assert 'distance_km' in data
    assert data['distance_km'] == 15.0

@pytest.mark.django_db
def test_price_estimate_by_coords(monkeypatch):
    client = APIClient()

    # Mock DistanceService.get_distance_km
    class Dummy:
        @staticmethod
        def get_distance_km(a, b):
            return 10.5

    monkeypatch.setattr('rides.services.distance.DistanceService', Dummy)

    payload = {
        "pickup_lat": -17.8,
        "pickup_lng": 31.0,
        "dropoff_lat": -17.9,
        "dropoff_lng": 31.1,
        "num_adults": 1
    }
    resp = client.post('/api/price/', payload, format='json')
    assert resp.status_code == 200
    data = resp.json()
    assert data['distance_km'] == 10.5
    assert 'total' in data

@pytest.mark.django_db
def test_price_estimate_missing_params():
    client = APIClient()
    payload = {"num_adults": 1}
    resp = client.post('/api/price/', payload, format='json')
    assert resp.status_code == 400
