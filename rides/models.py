import uuid
import re
from datetime import time as dt_time
from decimal import Decimal
from django.db import models
from django.core.validators import MinValueValidator
from django.utils import timezone
from django.contrib.postgres.fields import JSONField as PGJSONField


# Use JSONField depending on Django version; try to be compatible
try:
    from django.db.models import JSONField
except Exception:
    JSONField = PGJSONField


class RideBooking(models.Model):
    PAYMENT_ON_ARRIVAL = 'POA'
    PAYMENT_CARD_ON_ARRIVAL = 'pos_card'
    PAYMENT_MONEY_TRANSFER = 'money_transfer'
    PAYMENT_PAYLINK = 'paylink'
    PAYMENT_PAYNOW = 'PAYNOW'

    STATUS_PENDING = 'PENDING'
    STATUS_CONFIRMED = 'CONFIRMED'
    STATUS_CANCELLED = 'CANCELLED'

    RIDE_TYPE_CITY = 'city'
    RIDE_TYPE_LONG_DISTANCE = 'long_distance'
    RIDE_TYPE_CHAUFFEUR = 'chauffeur'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    pickup_address = models.CharField(max_length=512)
    pickup_lat = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    pickup_lng = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    dropoff_address = models.CharField(max_length=512)
    dropoff_lat = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    dropoff_lng = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)

    # Exactly where at that address the driver meets the passenger. A place name
    # like "Harare International Airport" or "Avondale Shops" covers a lot of
    # ground, so the customer pins the meeting point in their own words.
    pickup_point_detail = models.CharField(max_length=256, blank=True, default='')
    dropoff_point_detail = models.CharField(max_length=256, blank=True, default='')

    distance_km = models.DecimalField(max_digits=8, decimal_places=2, validators=[MinValueValidator(0)])

    num_adults = models.PositiveSmallIntegerField(default=1)
    num_kids_seated = models.PositiveSmallIntegerField(default=0)
    baby_car_seater = models.PositiveSmallIntegerField(default=0)
    num_kids_carried = models.PositiveSmallIntegerField(default=0)
    luggage_count = models.PositiveSmallIntegerField(default=0)
    hand_luggage_count = models.PositiveSmallIntegerField(default=0)
    # Anything that is not a countable bag — a wheelchair, a pushchair, golf
    # clubs. Free text, so the driver knows what to make room for.
    other_luggage = models.CharField(max_length=256, blank=True, default='')

    # Stops along the way: list of {"description": str, "minutes": int, "fee": float}
    stops_json = JSONField(null=True, blank=True)

    # Return trip: the same booking covers the journey back
    is_return_trip = models.BooleanField(default=False)
    return_date = models.DateField(null=True, blank=True)
    return_time = models.TimeField(null=True, blank=True)

    # The way back does not have to retrace the way out — we may have dropped the
    # passenger in one place and be collecting them from another. When these are
    # blank the return leg simply reverses the outbound trip.
    return_uses_different_points = models.BooleanField(default=False)
    return_pickup_address = models.CharField(max_length=512, blank=True, default='')
    return_pickup_lat = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    return_pickup_lng = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    return_pickup_point_detail = models.CharField(max_length=256, blank=True, default='')
    return_dropoff_address = models.CharField(max_length=512, blank=True, default='')
    return_dropoff_lat = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    return_dropoff_lng = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    return_dropoff_point_detail = models.CharField(max_length=256, blank=True, default='')
    return_distance_km = models.DecimalField(
        max_digits=8, decimal_places=2, null=True, blank=True,
        validators=[MinValueValidator(0)],
        help_text='Distance of the return leg when it runs a different route from the outbound trip.'
    )

    phone = models.CharField(max_length=32)
    email = models.EmailField()
    extra_instructions = models.TextField(max_length=500, blank=True, null=True, default="")

    # Pickup scheduling and passenger details
    pickup_date = models.DateField(null=True, blank=True)
    pickup_time = models.TimeField(null=True, blank=True)
    approximate_end_time = models.TimeField(null=True, blank=True)

    # Airport / flight details (optional; required only for airport pickups)
    pickup_is_airport = models.BooleanField(default=False)
    # Which side of the airport — international arrivals, domestic arrivals, etc.
    pickup_airport_terminal = models.CharField(max_length=64, blank=True, default='')
    arrival_airline = models.CharField(max_length=64, null=True, blank=True)
    arrival_flight_number = models.CharField(max_length=32, null=True, blank=True)
    arrival_date = models.DateField(null=True, blank=True)
    arrival_time = models.TimeField(null=True, blank=True)

    # Extra flight context. Passengers often rebook mid-journey (e.g. they change
    # flight while connecting through Johannesburg), so these can be filled in at
    # booking time and corrected later from the customer's own booking link.
    flight_departure_airport = models.CharField(max_length=128, blank=True, default='')
    flight_connection_details = models.CharField(max_length=256, blank=True, default='')
    flight_notes = models.TextField(max_length=500, blank=True, default='')
    flight_details_updated_at = models.DateTimeField(null=True, blank=True)

    # Passenger identity / salutation
    salutation = models.CharField(max_length=32, null=True, blank=True)
    passenger_full_name = models.CharField(max_length=256, null=True, blank=True)
    # What goes on the driver's board. Kept apart from the first name above so a
    # customer can be met under a company name, a surname, or a group's name.
    display_name = models.CharField(max_length=256, blank=True, default='')

    # Human-friendly booking reference (e.g. ET101)
    reference = models.CharField(max_length=16, unique=True, null=True, blank=True)

    # Paylink: the customer asks us to send them a payment link, so we need the
    # name on the card and the address the link goes to. Blank for every other
    # payment method.
    paylink_card_name = models.CharField(max_length=256, blank=True, default='')
    paylink_email = models.EmailField(blank=True, default='')

    payment_option = models.CharField(max_length=16, choices=[
        (PAYMENT_ON_ARRIVAL, 'Pay on Arrival (Cash)'),
        (PAYMENT_CARD_ON_ARRIVAL, 'Pay on Arrival (POS/CARD)'),
        (PAYMENT_MONEY_TRANSFER, 'Money Transfer Agency'),
        (PAYMENT_PAYLINK, 'Paylink'),
        (PAYMENT_PAYNOW, 'Pay Online (Paynow)'),
    ])

    status = models.CharField(max_length=16, choices=[(STATUS_PENDING, 'Pending'), (STATUS_CONFIRMED, 'Confirmed'), (STATUS_CANCELLED, 'Cancelled')], default=STATUS_PENDING)

    price_breakdown = JSONField(null=True, blank=True)
    total_amount = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    passengers_json = JSONField(null=True, blank=True)

    ride_type = models.CharField(
        max_length=20,
        choices=[
            (RIDE_TYPE_CITY, 'EasyTransit Ride'),
            (RIDE_TYPE_LONG_DISTANCE, 'Long Distance'),
            (RIDE_TYPE_CHAUFFEUR, 'Chauffeur Drive'),
        ],
        default=RIDE_TYPE_CITY,
    )
    chauffeur_hours = models.PositiveSmallIntegerField(null=True, blank=True)
    chauffeur_package_label = models.CharField(max_length=64, null=True, blank=True)
    passengers_over_limit = models.BooleanField(default=False)

    # Customer self-service (magic-link "manage my booking")
    cancelled_at = models.DateTimeField(null=True, blank=True)
    cancelled_by_customer = models.BooleanField(default=False)
    # Audit trail of customer-made changes: [{"at": iso, "action": str, "detail": str}]
    change_log = JSONField(null=True, blank=True)

    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    @property
    def pickup_display(self):
        """Pickup address with the terminal and meeting point the customer gave."""
        return self._place_display(self.pickup_address, self.pickup_airport_terminal, self.pickup_point_detail)

    @property
    def dropoff_display(self):
        return self._place_display(self.dropoff_address, '', self.dropoff_point_detail)

    @property
    def return_pickup_display(self):
        """Where the return leg starts — the stated point, or the outbound dropoff."""
        if self.return_uses_different_points and self.return_pickup_address:
            return self._place_display(self.return_pickup_address, '', self.return_pickup_point_detail)
        return self.dropoff_display

    @property
    def return_dropoff_display(self):
        """Where the return leg ends — the stated point, or back to the outbound pickup."""
        if self.return_uses_different_points and self.return_dropoff_address:
            return self._place_display(self.return_dropoff_address, '', self.return_dropoff_point_detail)
        return self.pickup_display

    @staticmethod
    def _place_display(address, terminal='', detail=''):
        parts = [p for p in (address, terminal, detail) if p and str(p).strip()]
        return ' — '.join(str(p).strip() for p in parts)

    @property
    def has_flight_details(self):
        return bool(
            self.arrival_airline or self.arrival_flight_number
            or self.flight_departure_airport or self.flight_connection_details
            or self.flight_notes
        )

    def log_change(self, action: str, detail: str = ''):
        """Append an entry to the customer-facing change history."""
        entries = list(self.change_log or [])
        entries.append({
            'at': timezone.now().isoformat(timespec='seconds'),
            'action': action,
            'detail': detail,
        })
        self.change_log = entries

    def __str__(self):
        ref = self.reference if self.reference else str(self.id)
        return f"Ride {ref} from {self.pickup_address} to {self.dropoff_address}"

    @staticmethod
    def _generate_next_reference(prefix: str = "ET") -> str:
        """Generate next human-friendly reference like ET26001 by scanning existing refs.
        If `prefix` is None, use current year two-digit (e.g. ET26).
        """
        if not prefix:
            yy = timezone.now().year % 100
            prefix = f"ET{yy:02d}"
        # Find max numeric suffix for refs starting with the prefix
        qs = RideBooking.objects.filter(reference__startswith=prefix).values_list('reference', flat=True)
        max_num = 0
        for r in qs:
            if not r:
                continue
            m = re.match(rf'^{re.escape(prefix)}(\d+)$', r)
            if m:
                try:
                    n = int(m.group(1))
                    if n > max_num:
                        max_num = n
                except Exception:
                    continue
        # zero-pad numeric part to at least 3 digits for readability
        next_num = max_num + 1
        return f"{prefix}{next_num:03d}"

    def save(self, *args, **kwargs):
        if not self.reference:
            # Try to generate a unique reference using current-year prefix; loop a few times in case of race
            for _ in range(5):
                candidate = self._generate_next_reference(None)
                if not RideBooking.objects.filter(reference=candidate).exists():
                    self.reference = candidate
                    break
        super().save(*args, **kwargs)


class SiteSettings(models.Model):
    taxi_owner_email = models.EmailField(default='enquiries@easytransit.co.zw')
    taxi_owner_phone = models.CharField(max_length=32, default='+263789423154')

    # Who the customer sends a money transfer to. Shown on the payment step and
    # repeated in their confirmation, so it is kept editable rather than hardcoded.
    money_transfer_recipient_name = models.CharField(
        max_length=128, default='Leonard Zambwi',
        help_text='Name the customer sends a money transfer to.'
    )
    money_transfer_recipient_phone = models.CharField(
        max_length=32, default='+263772491982',
        help_text='Number the customer sends a money transfer to.'
    )

    # City Ride Pricing
    pricing_min_km = models.DecimalField(max_digits=6, decimal_places=2, default=13.0)
    pricing_brackets = JSONField(default=list)
    pricing_above_35_per_km = models.DecimalField(max_digits=6, decimal_places=2, default=1.0)
    pricing_base_passengers = models.PositiveSmallIntegerField(default=3)
    pricing_extra_adult_fee = models.DecimalField(max_digits=6, decimal_places=2, default=10.0)
    pricing_free_luggage = models.PositiveSmallIntegerField(default=5)
    pricing_luggage_fee = models.DecimalField(max_digits=6, decimal_places=2, default=3.0)

    # Long Distance Pricing
    long_distance_threshold_km = models.DecimalField(
        max_digits=6, decimal_places=2, default=80.0,
        help_text='Trips at or beyond this distance (km) are treated as Long Distance'
    )
    long_distance_per_km = models.DecimalField(max_digits=6, decimal_places=2, default=1.40)
    long_distance_base_passengers = models.PositiveSmallIntegerField(default=3)
    long_distance_extra_pax_fee = models.DecimalField(max_digits=6, decimal_places=2, default=40.0)
    long_distance_free_luggage = models.PositiveSmallIntegerField(default=5)
    long_distance_luggage_fee = models.DecimalField(max_digits=6, decimal_places=2, default=5.0)

    # Customer self-service on their own booking
    allow_customer_reschedule = models.BooleanField(
        default=True, help_text='Let customers change their pickup date and time from the emailed link.'
    )
    allow_customer_cancellation = models.BooleanField(
        default=True, help_text='Let customers cancel their booking from the emailed link.'
    )
    booking_change_cutoff_hours = models.PositiveSmallIntegerField(
        default=12,
        help_text=(
            'Customers can no longer change or cancel once the pickup is this many '
            'hours away. 0 = allowed right up to the pickup time.'
        )
    )

    # Return trips
    return_trip_discount_percent = models.DecimalField(
        max_digits=5, decimal_places=2, default=0.00,
        help_text=(
            'Percentage taken off the return leg when a customer books a round trip. '
            '0 = the return leg costs the same as the outbound leg.'
        )
    )

    # Night pickup surcharge (applies to city and long distance rides)
    night_surcharge_enabled = models.BooleanField(
        default=True, help_text='Charge extra for pickups during the night window.'
    )
    night_surcharge_amount = models.DecimalField(
        max_digits=6, decimal_places=2, default=10.00,
        help_text='Flat amount added to the fare for pickups inside the night window.'
    )
    night_start = models.TimeField(
        default=dt_time(22, 0), help_text='Start of the night window (e.g. 22:00).'
    )
    night_end = models.TimeField(
        default=dt_time(4, 0), help_text='End of the night window (e.g. 04:00). May cross midnight.'
    )

    # Stops along the way — charged per stop, by how long the stop lasts.
    # Each entry: {"max_minutes": 10, "price": 0}
    stop_tiers = JSONField(
        default=list,
        help_text=(
            'Charge bands for a stop along the way, per stop. Each entry needs '
            'max_minutes (int) and price (decimal); the first band whose max_minutes '
            'covers the stop is charged.'
        )
    )

    # Hand luggage (applies to both city and long distance). Small bags are free
    # up to the allowance; beyond that they take real boot space and are charged.
    hand_luggage_free = models.PositiveSmallIntegerField(
        default=5, help_text='Hand luggage items included free per booking.'
    )
    hand_luggage_fee = models.DecimalField(
        max_digits=6, decimal_places=2, default=1.50,
        help_text='Charge per hand luggage item beyond the free allowance. 0 = hand luggage always free.'
    )

    # Airport pickups: which side of the airport the driver waits at.
    airport_terminals = JSONField(
        default=list,
        help_text=(
            'Pickup points offered when a customer ticks "pickup is from an airport", '
            'as a list of labels, e.g. ["International Arrivals", "Domestic Arrivals"].'
        )
    )

    allow_customer_flight_update = models.BooleanField(
        default=True,
        help_text=(
            'Let customers correct their flight details from the emailed link. '
            'Allowed right up to the pickup, since flights are often changed in transit.'
        )
    )

    # Booking limits (0 = no limit)
    max_passengers = models.PositiveSmallIntegerField(
        default=0, help_text='Maximum passengers a customer may select. 0 = no limit.'
    )
    max_luggage = models.PositiveSmallIntegerField(
        default=0, help_text='Maximum luggage bags a customer may select. 0 = no limit.'
    )
    max_hand_luggage = models.PositiveSmallIntegerField(
        default=0, help_text='Maximum hand luggage items a customer may select. 0 = no limit.'
    )

    # Paynow minimum amount rule
    paynow_min_amount = models.DecimalField(
        max_digits=8, decimal_places=2, default=201.00,
        help_text='Paynow is only offered when the fare is at or above this amount (Paynow fees are high on small amounts). 0 = always offer Paynow.'
    )
    paynow_min_note = models.TextField(
        default=(
            'Paynow is only available for bookings of $201 and above. '
            'For $200 and below, please pay via Paylink or a money transfer agency '
            '(Western Union, Mukuru, WorldRemit, etc.).'
        ),
        help_text='Message shown to customers when their fare is below the Paynow minimum.'
    )

    # Chauffeur Drive Packages (JSON list)
    # Each entry: {"hours": 4, "price": 100, "km_limit": 100,
    #              "window_start": "07:30", "window_end": "17:00", "max_passengers": 4}
    chauffeur_packages = JSONField(
        default=list,
        help_text=(
            'List of chauffeur drive packages. Each entry must have: '
            'hours (int), price (decimal), km_limit (int), '
            'window_start ("HH:MM"), window_end ("HH:MM"), max_passengers (int).'
        )
    )

    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Site Settings'

    @classmethod
    def get_settings(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj

    def get_pricing_cfg(self):
        brackets = self.pricing_brackets or [
            {"min": 13, "max": 15, "price": 25.0},
            {"min": 16, "max": 20, "price": 30.0},
            {"min": 21, "max": 25, "price": 35.0},
            {"min": 26, "max": 35, "price": 40.0},
        ]
        return {
            "MIN_DISTANCE_KM": float(self.pricing_min_km),
            "BRACKETS": brackets,
            "ABOVE_35_PER_KM": float(self.pricing_above_35_per_km),
            "BASE_PASSENGERS": self.pricing_base_passengers,
            "EXTRA_ADULT_FEE": float(self.pricing_extra_adult_fee),
            "FREE_LUGGAGE_ITEMS": self.pricing_free_luggage,
            "LUGGAGE_FEE": float(self.pricing_luggage_fee),
            "HAND_LUGGAGE_FREE_ITEMS": int(self.hand_luggage_free or 0),
            "HAND_LUGGAGE_FEE": float(self.hand_luggage_fee or 0),
        }

    def get_long_distance_cfg(self):
        return {
            "THRESHOLD_KM": float(self.long_distance_threshold_km),
            "PER_KM": float(self.long_distance_per_km),
            "BASE_PASSENGERS": self.long_distance_base_passengers,
            "EXTRA_PAX_FEE": float(self.long_distance_extra_pax_fee),
            "FREE_LUGGAGE_ITEMS": self.long_distance_free_luggage,
            "LUGGAGE_FEE": float(self.long_distance_luggage_fee),
            "HAND_LUGGAGE_FREE_ITEMS": int(self.hand_luggage_free or 0),
            "HAND_LUGGAGE_FEE": float(self.hand_luggage_fee or 0),
        }

    def get_self_service_cfg(self):
        return {
            "ALLOW_RESCHEDULE": bool(self.allow_customer_reschedule),
            "ALLOW_CANCELLATION": bool(self.allow_customer_cancellation),
            "ALLOW_FLIGHT_UPDATE": bool(self.allow_customer_flight_update),
            "CUTOFF_HOURS": int(self.booking_change_cutoff_hours or 0),
        }

    def get_airport_terminals(self):
        # We only collect from the arrivals halls, so departures and the private
        # terminal are deliberately not offered.
        default = [
            'International Arrivals',
            'Domestic Arrivals',
        ]
        terminals = [str(t).strip() for t in (self.airport_terminals or []) if str(t).strip()]
        return terminals or default

    def get_return_discount(self):
        """Return leg discount as a fraction between 0 and 1."""
        try:
            pct = float(self.return_trip_discount_percent or 0)
        except (TypeError, ValueError):
            return 0.0
        return max(0.0, min(pct, 100.0)) / 100.0

    def get_night_cfg(self):
        return {
            "ENABLED": bool(self.night_surcharge_enabled),
            "AMOUNT": float(self.night_surcharge_amount or 0),
            "START": self.night_start or dt_time(22, 0),
            "END": self.night_end or dt_time(4, 0),
        }

    def get_stop_tiers(self):
        default = [
            {"max_minutes": 10, "price": 0},
            {"max_minutes": 20, "price": 5},
            {"max_minutes": 30, "price": 15},
            {"max_minutes": 60, "price": 30},
        ]
        return self.stop_tiers or default

    def get_luggage_cfg(self):
        """Free hold-luggage allowance and the per-bag charge beyond it."""
        return {
            "FREE_ITEMS": int(self.pricing_free_luggage or 0),
            "FEE": float(self.pricing_luggage_fee or 0),
        }

    def get_hand_luggage_cfg(self):
        return {
            "FREE_ITEMS": int(self.hand_luggage_free or 0),
            "FEE": float(self.hand_luggage_fee or 0),
        }

    def get_limits_cfg(self):
        """Counter limits for the booking wizard. 0 means no limit."""
        return {
            "MAX_PASSENGERS": int(self.max_passengers or 0),
            "MAX_LUGGAGE": int(self.max_luggage or 0),
            "MAX_HAND_LUGGAGE": int(self.max_hand_luggage or 0),
        }

    def get_chauffeur_packages(self):
        default = [
            {"hours": 4,  "price": 100, "km_limit": 100, "window_start": "07:30", "window_end": "17:00", "max_passengers": 4},
            {"hours": 6,  "price": 125, "km_limit": 130, "window_start": "07:30", "window_end": "20:00", "max_passengers": 4},
            {"hours": 8,  "price": 170, "km_limit": 200, "window_start": "07:30", "window_end": "18:00", "max_passengers": 4},
            {"hours": 12, "price": 200, "km_limit": 220, "window_start": "07:30", "window_end": "21:00", "max_passengers": 4},
        ]
        return self.chauffeur_packages or default

    def __str__(self):
        return 'Site Settings'


class Payment(models.Model):
    STATUS_PENDING = 'PENDING'
    STATUS_PAID = 'PAID'
    STATUS_FAILED = 'FAILED'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    booking = models.ForeignKey(RideBooking, on_delete=models.CASCADE, related_name='payments')
    method = models.CharField(max_length=32, blank=True)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    status = models.CharField(max_length=16, choices=[(STATUS_PENDING, 'Pending'), (STATUS_PAID, 'Paid'), (STATUS_FAILED, 'Failed')], default=STATUS_PENDING)
    paynow_reference = models.CharField(max_length=128, blank=True, null=True, db_index=True)
    paynow_response = JSONField(null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Payment {self.id} - {self.status} ({self.amount})"
