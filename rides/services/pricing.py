from datetime import time as dt_time
from decimal import Decimal, ROUND_HALF_UP
import logging

logger = logging.getLogger(__name__)

DEFAULT_PRICING = {
    "MIN_DISTANCE_KM": 13.0,
    "BRACKETS": [
        {"min": 13, "max": 15, "price": 25.0},
        {"min": 16, "max": 20, "price": 30.0},
        {"min": 21, "max": 25, "price": 35.0},
        {"min": 26, "max": 35, "price": 40.0},
    ],
    "ABOVE_35_PER_KM": 1.0,
    "BASE_PASSENGERS": 3,
    "EXTRA_ADULT_FEE": 10.0,
    "FREE_LUGGAGE_ITEMS": 5,
    "LUGGAGE_FEE": 5.0,
    "HAND_LUGGAGE_FREE_ITEMS": 5,
    "HAND_LUGGAGE_FEE": 1.50,
}

DEFAULT_LONG_DISTANCE = {
    "THRESHOLD_KM": 80.0,
    "PER_KM": 1.40,
    "BASE_PASSENGERS": 3,
    "EXTRA_PAX_FEE": 40.0,
    "FREE_LUGGAGE_ITEMS": 5,
    "LUGGAGE_FEE": 5.0,
    "HAND_LUGGAGE_FREE_ITEMS": 5,
    "HAND_LUGGAGE_FEE": 1.50,
}

DEFAULT_NIGHT = {
    "ENABLED": True,
    "AMOUNT": 10.0,
    "START": dt_time(22, 0),
    "END": dt_time(4, 0),
}

DEFAULT_STOP_TIERS = [
    {"max_minutes": 10, "price": 0},
    {"max_minutes": 20, "price": 5},
    {"max_minutes": 30, "price": 15},
    {"max_minutes": 60, "price": 30},
]

DEFAULT_CHAUFFEUR_PACKAGES = [
    {"hours": 4,  "price": 100, "km_limit": 100, "window_start": "07:30", "window_end": "17:00", "max_passengers": 4},
    {"hours": 6,  "price": 125, "km_limit": 130, "window_start": "07:30", "window_end": "20:00", "max_passengers": 4},
    {"hours": 8,  "price": 170, "km_limit": 200, "window_start": "07:30", "window_end": "18:00", "max_passengers": 4},
    {"hours": 12, "price": 200, "km_limit": 220, "window_start": "07:30", "window_end": "21:00", "max_passengers": 4},
]


def _get_pricing_cfg():
    try:
        from rides.models import SiteSettings
        return SiteSettings.get_settings().get_pricing_cfg()
    except Exception:
        return {}


def _get_long_distance_cfg():
    try:
        from rides.models import SiteSettings
        return SiteSettings.get_settings().get_long_distance_cfg()
    except Exception:
        return {}


def _get_night_cfg():
    try:
        from rides.models import SiteSettings
        return SiteSettings.get_settings().get_night_cfg()
    except Exception:
        return dict(DEFAULT_NIGHT)


def _get_return_discount():
    try:
        from rides.models import SiteSettings
        return SiteSettings.get_settings().get_return_discount()
    except Exception:
        return 0.0


def _get_self_service_cfg():
    try:
        from rides.models import SiteSettings
        return SiteSettings.get_settings().get_self_service_cfg()
    except Exception:
        return {
            "ALLOW_RESCHEDULE": True,
            "ALLOW_CANCELLATION": True,
            "ALLOW_FLIGHT_UPDATE": True,
            "CUTOFF_HOURS": 12,
        }


def _get_stop_tiers():
    try:
        from rides.models import SiteSettings
        return SiteSettings.get_settings().get_stop_tiers()
    except Exception:
        return list(DEFAULT_STOP_TIERS)


def _parse_time(value):
    """Accept a time, a "HH:MM" string, or None."""
    if value is None or isinstance(value, dt_time):
        return value
    text = str(value).strip()
    if not text:
        return None
    for fmt in ('%H:%M:%S', '%H:%M'):
        try:
            from datetime import datetime
            return datetime.strptime(text, fmt).time()
        except ValueError:
            continue
    return None


def _get_chauffeur_packages():
    try:
        from rides.models import SiteSettings
        return SiteSettings.get_settings().get_chauffeur_packages()
    except Exception:
        return DEFAULT_CHAUFFEUR_PACKAGES


class PricingService:
    """PricingService calculates fare breakdown according to business rules.

    Rules summary (implemented):
    - Distances below 13km are charged at the 13-15km bracket ($25) as a minimum.
    - Distance brackets: 13-15 ($25), 16-20 ($30), 21-25 ($35), 26-35 ($40)
    - For distance >35km: price = $40 + 1.0 * (distance - 35)
    - Base fare covers up to 3 passengers. Extra passengers (>3) pay $10 each
    - Kids seated are counted as adults
    - Kids carried are free
    - First 5 luggage items are free, then $5 per additional item
    """

    @staticmethod
    def _round(value: Decimal) -> Decimal:
        return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    @classmethod
    def is_night_pickup(cls, pickup_time) -> bool:
        """True when `pickup_time` falls inside the configured night window.

        The window normally crosses midnight (e.g. 22:00-04:00), so the two cases
        are handled separately.
        """
        pickup_time = _parse_time(pickup_time)
        if pickup_time is None:
            return False

        cfg = _get_night_cfg() or DEFAULT_NIGHT
        if not cfg.get("ENABLED", True):
            return False

        start = _parse_time(cfg.get("START")) or DEFAULT_NIGHT["START"]
        end = _parse_time(cfg.get("END")) or DEFAULT_NIGHT["END"]
        if start == end:
            return False
        if start < end:
            return start <= pickup_time < end
        # Window crosses midnight
        return pickup_time >= start or pickup_time < end

    @classmethod
    def night_surcharge_for(cls, pickup_time) -> Decimal:
        """Flat night surcharge owed for a pickup at `pickup_time` (may be zero)."""
        if not cls.is_night_pickup(pickup_time):
            return Decimal("0.00")
        cfg = _get_night_cfg() or DEFAULT_NIGHT
        try:
            return cls._round(Decimal(str(cfg.get("AMOUNT", DEFAULT_NIGHT["AMOUNT"]))))
        except Exception:
            return Decimal("0.00")

    @classmethod
    def city_base_price(cls, distance_km) -> Decimal:
        """Distance component of a city fare, from the configured brackets."""
        try:
            distance = Decimal(str(float(distance_km)))
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Invalid distance_km: {exc}") from exc

        pricing_cfg = _get_pricing_cfg() or {}
        brackets = pricing_cfg.get("BRACKETS") or DEFAULT_PRICING["BRACKETS"]
        try:
            sorted_brackets = sorted(brackets, key=lambda b: float(b.get('min', 0)))
        except Exception:
            sorted_brackets = list(brackets)

        # Enforce minimum chargeable distance
        min_km = Decimal(str(pricing_cfg.get("MIN_DISTANCE_KM", DEFAULT_PRICING["MIN_DISTANCE_KM"])))
        effective_distance = max(distance, min_km)

        base_price = None

        # 1. Try exact bracket match (min <= distance <= max)
        for bracket in sorted_brackets:
            try:
                if Decimal(str(bracket.get("min"))) <= effective_distance <= Decimal(str(bracket.get("max"))):
                    base_price = Decimal(str(bracket.get("price")))
                    break
            except Exception:
                logger.exception('Malformed pricing bracket: %s', bracket)

        if base_price is None and sorted_brackets:
            last_bracket = sorted_brackets[-1]
            last_max = Decimal(str(last_bracket.get('max', 0)))
            last_price = Decimal(str(last_bracket.get('price', 0)))

            if effective_distance > last_max:
                # 2. Above all brackets — per-km rate above the last bracket's max
                per_km = Decimal(str(pricing_cfg.get("ABOVE_35_PER_KM", DEFAULT_PRICING["ABOVE_35_PER_KM"])))
                extra_km = effective_distance - last_max
                base_price = last_price + (per_km * extra_km)
            else:
                # 3. Distance is in a gap between brackets (e.g. 20.6 km between a 17–20 and 21–25
                #    bracket) or below the first bracket's min.
                #    Use the highest bracket whose max < effective_distance (the lower tier).
                best = None
                for b in sorted_brackets:
                    try:
                        if Decimal(str(b.get('max', 0))) < effective_distance:
                            best = b
                    except Exception:
                        pass
                if best:
                    base_price = Decimal(str(best.get('price', 0)))
                else:
                    # Below all brackets — use first bracket price as the floor
                    base_price = Decimal(str(sorted_brackets[0].get('price', 0)))

        if base_price is None:
            base_price = Decimal(str(DEFAULT_PRICING["BRACKETS"][0]["price"]))

        return base_price, effective_distance

    @classmethod
    def return_leg_fee(cls, one_way_core: Decimal) -> Decimal:
        """Cost of the return leg, given the one-way fare for the same people and bags.

        The journey back carries the same passengers and luggage, so it is charged
        like the outbound leg, less any configured round-trip discount. When the
        return runs a different route (collected from somewhere other than where we
        dropped them), the caller passes a core built from the return distance
        instead. Stops and night surcharges are handled separately by the caller —
        stops are one-off and priced once, and each leg is checked against the night
        window on its own departure time.
        """
        try:
            discount = Decimal(str(_get_return_discount()))
        except Exception:
            discount = Decimal("0")
        return cls._round(one_way_core * (Decimal("1") - discount))

    @classmethod
    def get_return_discount_percent(cls) -> float:
        return round(_get_return_discount() * 100, 2)

    @classmethod
    def get_night_cfg(cls) -> dict:
        return _get_night_cfg() or dict(DEFAULT_NIGHT)

    @classmethod
    def get_stop_tiers(cls) -> list:
        """Stop charge bands, sorted by duration ascending."""
        tiers = _get_stop_tiers() or DEFAULT_STOP_TIERS
        try:
            return sorted(tiers, key=lambda t: float(t.get("max_minutes", 0)))
        except Exception:
            return list(tiers)

    @classmethod
    def fee_for_stop(cls, minutes) -> Decimal:
        """Charge for a single stop lasting `minutes`.

        The first band whose max_minutes covers the stop is charged. A stop longer
        than every band falls back to the longest band's price.
        """
        try:
            minutes = int(minutes or 0)
        except (TypeError, ValueError):
            return Decimal("0.00")
        if minutes <= 0:
            return Decimal("0.00")

        tiers = cls.get_stop_tiers()
        for tier in tiers:
            try:
                if minutes <= float(tier.get("max_minutes", 0)):
                    return cls._round(Decimal(str(tier.get("price", 0))))
            except Exception:
                logger.exception('Malformed stop tier: %s', tier)
        if tiers:
            try:
                return cls._round(Decimal(str(tiers[-1].get("price", 0))))
            except Exception:
                return Decimal("0.00")
        return Decimal("0.00")

    @classmethod
    def price_stops(cls, stops) -> tuple:
        """Price a list of stops. Returns (priced_stops, total_fee).

        Each stop is charged separately — two 15-minute stops cost twice one
        15-minute stop.
        """
        priced = []
        total = Decimal("0.00")
        for stop in (stops or []):
            if not isinstance(stop, dict):
                continue
            try:
                minutes = int(stop.get("minutes") or 0)
            except (TypeError, ValueError):
                minutes = 0
            fee = cls.fee_for_stop(minutes)
            total += fee
            priced.append({
                "description": (stop.get("description") or "").strip(),
                "minutes": minutes,
                "fee": float(fee),
            })
        return priced, cls._round(total)

    @classmethod
    def calculate(cls, distance_km: float, num_adults: int = 1, num_kids_seated: int = 0, baby_car_seater: int = 0, num_kids_carried: int = 0, luggage_count: int = 0, hand_luggage_count: int = 0, pickup_time=None, stops=None, is_return_trip: bool = False, return_time=None, return_distance_km=None) -> dict:
        # Coerce and validate inputs to avoid type errors caused by session/JSON strings
        try:
            if distance_km is None:
                raise ValueError("distance_km is required")
            distance = Decimal(str(float(distance_km)))
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Invalid distance_km: {exc}") from exc

        try:
            num_adults = int(num_adults)
            num_kids_seated = int(num_kids_seated)
            baby_car_seater = int(baby_car_seater)
            num_kids_carried = int(num_kids_carried)
            luggage_count = int(luggage_count)
            hand_luggage_count = int(hand_luggage_count or 0)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Invalid passenger/luggage counts: {exc}") from exc

        if num_adults < 1:
            raise ValueError("At least one adult is required")
        if num_kids_seated < 0 or baby_car_seater < 0 or num_kids_carried < 0 or luggage_count < 0 or hand_luggage_count < 0:
            raise ValueError("Counts cannot be negative")

        # Legacy compatibility: fold seated kids into adults for all fare logic.
        num_adults = num_adults + num_kids_seated
        num_kids_seated = 0

        pricing_cfg = _get_pricing_cfg() or {}

        base_price, effective_distance = cls.city_base_price(distance)

        # Extra adults
        base_passengers = int(pricing_cfg.get("BASE_PASSENGERS", DEFAULT_PRICING["BASE_PASSENGERS"]))
        extra_adults = max(0, num_adults - base_passengers)
        extra_adults_fee = Decimal(str(pricing_cfg.get("EXTRA_ADULT_FEE", DEFAULT_PRICING["EXTRA_ADULT_FEE"]))) * extra_adults

        # Baby car seater: flat $10 fee
        baby_car_seater_fee = Decimal("10.00") * Decimal(baby_car_seater)

        # Luggage: First N items are free
        free_luggage = int(pricing_cfg.get("FREE_LUGGAGE_ITEMS", DEFAULT_PRICING["FREE_LUGGAGE_ITEMS"]))
        chargeable_luggage = max(0, luggage_count - free_luggage)
        luggage_fee = Decimal(str(pricing_cfg.get("LUGGAGE_FEE", DEFAULT_PRICING["LUGGAGE_FEE"]))) * Decimal(chargeable_luggage)

        # Hand luggage: first N items free, then a per-item fee (fee of 0 means always free)
        free_hand_luggage = int(pricing_cfg.get("HAND_LUGGAGE_FREE_ITEMS", DEFAULT_PRICING["HAND_LUGGAGE_FREE_ITEMS"]))
        chargeable_hand_luggage = max(0, hand_luggage_count - free_hand_luggage)
        hand_luggage_fee = Decimal(str(pricing_cfg.get("HAND_LUGGAGE_FEE", DEFAULT_PRICING["HAND_LUGGAGE_FEE"]))) * Decimal(chargeable_hand_luggage)

        # Fare for a single leg, before per-leg surcharges and one-off stops
        one_way_core = base_price + extra_adults_fee + baby_car_seater_fee + luggage_fee + hand_luggage_fee

        # Night pickup surcharge (configured in the dashboard), checked per leg
        night_surcharge = cls.night_surcharge_for(pickup_time)
        is_night = night_surcharge > 0

        # Stops along the way — charged per stop, once (not doubled on a return trip)
        priced_stops, stops_fee = cls.price_stops(stops)

        # Return leg, if the customer booked a round trip. A return that runs its own
        # route (different pickup or dropoff) is measured and charged on that route;
        # otherwise it mirrors the outbound leg.
        return_core = one_way_core
        return_base_price = base_price
        return_distance = None
        if is_return_trip:
            try:
                if return_distance_km is not None and float(return_distance_km) > 0:
                    return_distance = Decimal(str(float(return_distance_km)))
            except (TypeError, ValueError):
                return_distance = None
            if return_distance is not None:
                return_base_price, _ = cls.city_base_price(return_distance)
                return_core = (
                    return_base_price + extra_adults_fee + baby_car_seater_fee
                    + luggage_fee + hand_luggage_fee
                )

        return_leg = cls.return_leg_fee(return_core) if is_return_trip else Decimal("0.00")
        return_night_surcharge = cls.night_surcharge_for(return_time) if is_return_trip else Decimal("0.00")

        # Sum up
        subtotal = (
            one_way_core + night_surcharge + stops_fee
            + return_leg + return_night_surcharge
        )
        total = cls._round(subtotal)

        breakdown = {
            "ride_type": "city",
            "distance_km": float(distance),
            "effective_distance_km": float(effective_distance),
            "base_distance_price": float(cls._round(base_price)),
            "extra_adults": int(extra_adults),
            "extra_adults_fee": float(cls._round(extra_adults_fee)),
            "baby_car_seater": int(baby_car_seater),
            "baby_car_seater_fee": float(cls._round(baby_car_seater_fee)),
            "kids_carried": int(num_kids_carried),
            "luggage_count": int(luggage_count),
            "luggage_free": int(min(luggage_count, free_luggage)),
            "luggage_chargeable": int(chargeable_luggage),
            "luggage_fee": float(cls._round(luggage_fee)),
            "hand_luggage_count": int(hand_luggage_count),
            "hand_luggage_free": int(min(hand_luggage_count, free_hand_luggage)),
            "hand_luggage_chargeable": int(chargeable_hand_luggage),
            "hand_luggage_fee": float(cls._round(hand_luggage_fee)),
            "is_night_pickup": bool(is_night),
            "night_surcharge": float(cls._round(night_surcharge)),
            "stops": priced_stops,
            "stops_count": len(priced_stops),
            "stops_fee": float(stops_fee),
            "one_way_total": float(cls._round(one_way_core + night_surcharge + stops_fee)),
            "is_return_trip": bool(is_return_trip),
            "return_leg_fee": float(cls._round(return_leg)),
            "return_distance_km": float(return_distance) if return_distance is not None else None,
            "return_base_distance_price": float(cls._round(return_base_price)) if is_return_trip else 0,
            "return_uses_own_route": bool(return_distance is not None),
            "return_discount_percent": cls.get_return_discount_percent() if is_return_trip else 0,
            "is_night_return": bool(return_night_surcharge > 0),
            "return_night_surcharge": float(cls._round(return_night_surcharge)),
            "subtotal": float(cls._round(subtotal)),
            "total": float(total),
        }

        return breakdown

    @classmethod
    def _get_ld_threshold(cls) -> float:
        cfg = _get_long_distance_cfg() or DEFAULT_LONG_DISTANCE
        return float(cfg.get("THRESHOLD_KM", DEFAULT_LONG_DISTANCE["THRESHOLD_KM"]))

    @classmethod
    def get_long_distance_cfg(cls) -> dict:
        """Long distance rates and allowances, for quoting them in the wizard."""
        return _get_long_distance_cfg() or DEFAULT_LONG_DISTANCE

    @classmethod
    def is_long_distance(cls, distance_km: float) -> bool:
        return float(distance_km) >= cls._get_ld_threshold()

    @classmethod
    def calculate_long_distance(cls, distance_km: float, num_adults: int = 1, luggage_count: int = 0, hand_luggage_count: int = 0, pickup_time=None, stops=None, is_return_trip: bool = False, return_time=None, return_distance_km=None) -> dict:
        try:
            distance = Decimal(str(float(distance_km)))
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Invalid distance_km: {exc}") from exc

        try:
            num_adults = int(num_adults)
            luggage_count = int(luggage_count)
            hand_luggage_count = int(hand_luggage_count or 0)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Invalid passenger/luggage counts: {exc}") from exc

        if num_adults < 1:
            raise ValueError("At least one adult is required")

        cfg = _get_long_distance_cfg() or DEFAULT_LONG_DISTANCE

        per_km = Decimal(str(cfg.get("PER_KM", DEFAULT_LONG_DISTANCE["PER_KM"])))
        base_passengers = int(cfg.get("BASE_PASSENGERS", DEFAULT_LONG_DISTANCE["BASE_PASSENGERS"]))
        extra_pax_fee_rate = Decimal(str(cfg.get("EXTRA_PAX_FEE", DEFAULT_LONG_DISTANCE["EXTRA_PAX_FEE"])))
        free_luggage = int(cfg.get("FREE_LUGGAGE_ITEMS", DEFAULT_LONG_DISTANCE["FREE_LUGGAGE_ITEMS"]))
        luggage_fee_rate = Decimal(str(cfg.get("LUGGAGE_FEE", DEFAULT_LONG_DISTANCE["LUGGAGE_FEE"])))

        base_price = cls._round(per_km * distance)

        extra_pax = max(0, num_adults - base_passengers)
        extra_pax_fee = cls._round(extra_pax_fee_rate * extra_pax)

        chargeable_luggage = max(0, luggage_count - free_luggage)
        luggage_fee = cls._round(luggage_fee_rate * chargeable_luggage)

        free_hand_luggage = int(cfg.get("HAND_LUGGAGE_FREE_ITEMS", DEFAULT_LONG_DISTANCE["HAND_LUGGAGE_FREE_ITEMS"]))
        chargeable_hand_luggage = max(0, hand_luggage_count - free_hand_luggage)
        hand_luggage_fee = cls._round(
            Decimal(str(cfg.get("HAND_LUGGAGE_FEE", DEFAULT_LONG_DISTANCE["HAND_LUGGAGE_FEE"]))) * chargeable_hand_luggage
        )

        one_way_core = base_price + extra_pax_fee + luggage_fee + hand_luggage_fee

        night_surcharge = cls.night_surcharge_for(pickup_time)
        priced_stops, stops_fee = cls.price_stops(stops)

        # A return leg on its own route is measured at the same per-km rate.
        return_core = one_way_core
        return_base_price = base_price
        return_distance = None
        if is_return_trip:
            try:
                if return_distance_km is not None and float(return_distance_km) > 0:
                    return_distance = Decimal(str(float(return_distance_km)))
            except (TypeError, ValueError):
                return_distance = None
            if return_distance is not None:
                return_base_price = cls._round(per_km * return_distance)
                return_core = return_base_price + extra_pax_fee + luggage_fee + hand_luggage_fee

        return_leg = cls.return_leg_fee(return_core) if is_return_trip else Decimal("0.00")
        return_night_surcharge = cls.night_surcharge_for(return_time) if is_return_trip else Decimal("0.00")

        total = cls._round(
            one_way_core + night_surcharge + stops_fee + return_leg + return_night_surcharge
        )

        return {
            "ride_type": "long_distance",
            "distance_km": float(distance),
            "per_km_rate": float(per_km),
            "base_distance_price": float(base_price),
            "base_passengers": base_passengers,
            "num_adults": num_adults,
            "extra_passengers": extra_pax,
            "extra_passenger_fee": float(extra_pax_fee),
            "luggage_count": luggage_count,
            "luggage_free": min(luggage_count, free_luggage),
            "luggage_chargeable": chargeable_luggage,
            "luggage_fee": float(luggage_fee),
            "hand_luggage_count": hand_luggage_count,
            "hand_luggage_free": min(hand_luggage_count, free_hand_luggage),
            "hand_luggage_chargeable": chargeable_hand_luggage,
            "hand_luggage_fee": float(hand_luggage_fee),
            "is_night_pickup": bool(night_surcharge > 0),
            "night_surcharge": float(night_surcharge),
            "stops": priced_stops,
            "stops_count": len(priced_stops),
            "stops_fee": float(stops_fee),
            "one_way_total": float(cls._round(one_way_core + night_surcharge + stops_fee)),
            "is_return_trip": bool(is_return_trip),
            "return_leg_fee": float(return_leg),
            "return_distance_km": float(return_distance) if return_distance is not None else None,
            "return_base_distance_price": float(return_base_price) if is_return_trip else 0,
            "return_uses_own_route": bool(return_distance is not None),
            "return_discount_percent": cls.get_return_discount_percent() if is_return_trip else 0,
            "is_night_return": bool(return_night_surcharge > 0),
            "return_night_surcharge": float(return_night_surcharge),
            "subtotal": float(total),
            "total": float(total),
        }

    @classmethod
    def calculate_chauffeur(cls, hours: int) -> dict:
        try:
            hours = int(hours)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Invalid hours value: {exc}") from exc

        packages = _get_chauffeur_packages()
        package = next((p for p in packages if int(p.get("hours", 0)) == hours), None)

        if package is None:
            available = [p.get("hours") for p in packages]
            raise ValueError(f"No chauffeur package found for {hours} hours. Available: {available}")

        price = Decimal(str(package["price"]))

        return {
            "ride_type": "chauffeur",
            "hours": hours,
            "label": f"{hours} Hour Chauffeur Drive",
            "price": float(price),
            "km_limit": package.get("km_limit"),
            "window_start": package.get("window_start"),
            "window_end": package.get("window_end"),
            "max_passengers": package.get("max_passengers"),
            "subtotal": float(price),
            "total": float(price),
        }

    @classmethod
    def get_chauffeur_packages(cls) -> list:
        return _get_chauffeur_packages()

    @classmethod
    def get_booking_limits(cls) -> dict:
        """Counter limits for the booking wizard. A value of 0 means no limit."""
        try:
            from rides.models import SiteSettings
            return SiteSettings.get_settings().get_limits_cfg()
        except Exception:
            return {"MAX_PASSENGERS": 0, "MAX_LUGGAGE": 0, "MAX_HAND_LUGGAGE": 0}

    @classmethod
    def get_airport_terminals(cls) -> list:
        """Pickup points offered for an airport pickup (international side, etc.)."""
        try:
            from rides.models import SiteSettings
            return SiteSettings.get_settings().get_airport_terminals()
        except Exception:
            return [
                'International Arrivals',
                'Domestic Arrivals',
            ]

    @classmethod
    def get_money_transfer_recipient(cls) -> dict:
        """Who a money transfer should be sent to."""
        default = {"NAME": 'Leonard Zambwi', "PHONE": '+263772491982'}
        try:
            from rides.models import SiteSettings
            cfg = SiteSettings.get_settings()
            return {
                "NAME": (cfg.money_transfer_recipient_name or default["NAME"]).strip(),
                "PHONE": (cfg.money_transfer_recipient_phone or default["PHONE"]).strip(),
            }
        except Exception:
            return default

    @classmethod
    def get_hand_luggage_cfg(cls) -> dict:
        """Free hand luggage allowance and the per-item charge beyond it."""
        try:
            from rides.models import SiteSettings
            return SiteSettings.get_settings().get_hand_luggage_cfg()
        except Exception:
            return {"FREE_ITEMS": 5, "FEE": 1.50}

    @classmethod
    def get_paynow_rule(cls) -> dict:
        """Minimum fare at which Paynow may be offered, plus the note shown below it."""
        default_note = (
            'Paynow is only available for bookings of $201 and above. '
            'For $200 and below, please pay via Paylink or a money transfer agency '
            '(Western Union, Mukuru, WorldRemit, etc.).'
        )
        try:
            from rides.models import SiteSettings
            cfg = SiteSettings.get_settings()
            return {
                "MIN_AMOUNT": float(cfg.paynow_min_amount or 0),
                "NOTE": (cfg.paynow_min_note or default_note).strip(),
            }
        except Exception:
            return {"MIN_AMOUNT": 201.0, "NOTE": default_note}

    @classmethod
    def paynow_allowed(cls, total) -> bool:
        """True when a fare of `total` is large enough for Paynow to be offered."""
        try:
            minimum = Decimal(str(cls.get_paynow_rule()["MIN_AMOUNT"]))
        except Exception:
            return True
        if minimum <= 0:
            return True
        try:
            return Decimal(str(total)) >= minimum
        except (TypeError, ValueError):
            return True
