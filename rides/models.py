import uuid
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
    special_instructions = models.CharField(max_length=300, blank=True, null=True)

    payment_option = models.CharField(max_length=16, choices=[(PAYMENT_ON_ARRIVAL, 'Pay on Arrival'), (PAYMENT_PAYNOW, 'Pay Online (Paynow)')])

    status = models.CharField(max_length=16, choices=[(STATUS_PENDING, 'Pending'), (STATUS_CONFIRMED, 'Confirmed'), (STATUS_CANCELLED, 'Cancelled')], default=STATUS_PENDING)

    price_breakdown = JSONField(null=True, blank=True)
    total_amount = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))

    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Ride {self.id} from {self.pickup_address} to {self.dropoff_address}"


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
