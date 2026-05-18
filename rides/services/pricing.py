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


def _get_pricing_cfg():
    try:
        from rides.models import SiteSettings
        return SiteSettings.get_settings().get_pricing_cfg()
    except Exception:
        return {}


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
