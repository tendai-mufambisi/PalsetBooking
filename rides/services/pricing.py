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
}

DEFAULT_LONG_DISTANCE = {
    "THRESHOLD_KM": 80.0,
    "PER_KM": 1.40,
    "BASE_PASSENGERS": 3,
    "EXTRA_PAX_FEE": 40.0,
    "FREE_LUGGAGE_ITEMS": 5,
    "LUGGAGE_FEE": 5.0,
}

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
    def calculate(cls, distance_km: float, num_adults: int = 1, num_kids_seated: int = 0, baby_car_seater: int = 0, num_kids_carried: int = 0, luggage_count: int = 0) -> dict:
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
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Invalid passenger/luggage counts: {exc}") from exc

        if num_adults < 1:
            raise ValueError("At least one adult is required")
        if num_kids_seated < 0 or baby_car_seater < 0 or num_kids_carried < 0 or luggage_count < 0:
            raise ValueError("Counts cannot be negative")

        # Legacy compatibility: fold seated kids into adults for all fare logic.
        num_adults = num_adults + num_kids_seated
        num_kids_seated = 0

        pricing_cfg = _get_pricing_cfg() or {}

        # Determine base distance price
        base_price = None
        # Enforce minimum distance bracket
        min_km = Decimal(str(pricing_cfg.get("MIN_DISTANCE_KM", DEFAULT_PRICING["MIN_DISTANCE_KM"])))
        effective_distance = max(distance, min_km)

        # Use configured brackets or defaults
        brackets = pricing_cfg.get("BRACKETS") or DEFAULT_PRICING["BRACKETS"]
        for bracket in brackets:
            try:
                if Decimal(str(bracket.get("min"))) <= effective_distance <= Decimal(str(bracket.get("max"))):
                    base_price = Decimal(str(bracket.get("price")))
                    break
            except Exception:
                # Skip malformed bracket entries
                logger.exception('Malformed pricing bracket: %s', bracket)

        if base_price is None:
            # If above 35, use special rule
            if effective_distance > Decimal("35"):
                last_bracket_price = (brackets or DEFAULT_PRICING["BRACKETS"])[-1]["price"]
                base_35 = Decimal(str(last_bracket_price))
                per_km = Decimal(str(pricing_cfg.get("ABOVE_35_PER_KM", DEFAULT_PRICING["ABOVE_35_PER_KM"])))
                extra_km = effective_distance - Decimal("35")
                base_price = base_35 + (per_km * extra_km)
            else:
                # Fallback: use first bracket price from config or defaults
                try:
                    first_price = brackets[0].get("price")
                    base_price = Decimal(str(first_price))
                except Exception:
                    base_price = Decimal(str(DEFAULT_PRICING["BRACKETS"][0]["price"]))

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

        # Sum up
        subtotal = base_price + extra_adults_fee + baby_car_seater_fee + luggage_fee
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
            "subtotal": float(cls._round(subtotal)),
            "total": float(total),
        }

        return breakdown

    @classmethod
    def _get_ld_threshold(cls) -> float:
        cfg = _get_long_distance_cfg() or DEFAULT_LONG_DISTANCE
        return float(cfg.get("THRESHOLD_KM", DEFAULT_LONG_DISTANCE["THRESHOLD_KM"]))

    @classmethod
    def is_long_distance(cls, distance_km: float) -> bool:
        return float(distance_km) >= cls._get_ld_threshold()

    @classmethod
    def calculate_long_distance(cls, distance_km: float, num_adults: int = 1, luggage_count: int = 0) -> dict:
        try:
            distance = Decimal(str(float(distance_km)))
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Invalid distance_km: {exc}") from exc

        try:
            num_adults = int(num_adults)
            luggage_count = int(luggage_count)
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

        total = cls._round(base_price + extra_pax_fee + luggage_fee)

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
