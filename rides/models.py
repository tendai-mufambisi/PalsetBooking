import uuid
import re
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
    PAYMENT_PAYNOW = 'PAYNOW'

    STATUS_PENDING = 'PENDING'
    STATUS_CONFIRMED = 'CONFIRMED'
    STATUS_CANCELLED = 'CANCELLED'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    pickup_address = models.CharField(max_length=512)
    pickup_lat = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    pickup_lng = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    dropoff_address = models.CharField(max_length=512)
    dropoff_lat = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    dropoff_lng = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)

    distance_km = models.DecimalField(max_digits=8, decimal_places=2, validators=[MinValueValidator(0)])

    num_adults = models.PositiveSmallIntegerField(default=1)
    num_kids_seated = models.PositiveSmallIntegerField(default=0)
    num_kids_carried = models.PositiveSmallIntegerField(default=0)
    luggage_count = models.PositiveSmallIntegerField(default=0)

    phone = models.CharField(max_length=32)
    email = models.EmailField()
    extra_instructions = models.TextField(max_length=500, blank=True, null=True, default="")

    # Pickup scheduling and passenger details
    pickup_date = models.DateField(null=True, blank=True)
    pickup_time = models.TimeField(null=True, blank=True)

    # Airport / flight details (optional; required only for airport pickups)
    pickup_is_airport = models.BooleanField(default=False)
    arrival_airline = models.CharField(max_length=64, null=True, blank=True)
    arrival_flight_number = models.CharField(max_length=32, null=True, blank=True)
    arrival_date = models.DateField(null=True, blank=True)
    arrival_time = models.TimeField(null=True, blank=True)

    # Passenger identity / salutation
    salutation = models.CharField(max_length=32, null=True, blank=True)
    passenger_full_name = models.CharField(max_length=256, null=True, blank=True)

    # Human-friendly booking reference (e.g. ET101)
    reference = models.CharField(max_length=16, unique=True, null=True, blank=True)

    payment_option = models.CharField(max_length=16, choices=[(PAYMENT_ON_ARRIVAL, 'Pay on Arrival'), (PAYMENT_PAYNOW, 'Pay Online (Paynow)')])

    status = models.CharField(max_length=16, choices=[(STATUS_PENDING, 'Pending'), (STATUS_CONFIRMED, 'Confirmed'), (STATUS_CANCELLED, 'Cancelled')], default=STATUS_PENDING)

    price_breakdown = JSONField(null=True, blank=True)
    total_amount = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    passengers_json = JSONField(null=True, blank=True)

    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

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
