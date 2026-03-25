from rides.services.pricing import PricingService
from decimal import Decimal


def test_pricing_brackets():
    # 14 km -> bracket 13-15 => $25 base
    out = PricingService.calculate(distance_km=14, num_adults=1, luggage_count=0)
    assert out['base_distance_price'] == 25.00
    assert out['total'] == 25.00


def test_pricing_above_35():
    # 40 km => base = 40 + 1.3*(40-35) = 40 + 6.5 = 46.5
    out = PricingService.calculate(distance_km=40, num_adults=1)
    assert round(out['base_distance_price'], 2) == 46.5


def test_extra_adults_and_luggage():
    # 20 km -> base 30
    out = PricingService.calculate(distance_km=20, num_adults=5, luggage_count=1)
    # base 30, extra adults 2*10=20, luggage 0 (first 5 free)
    assert out['base_distance_price'] == 30.00
    assert out['extra_adults_fee'] == 20.00
    assert out['luggage_fee'] == 0.00
    assert out['total'] == 50.00
