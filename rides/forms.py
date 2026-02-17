from django import forms
from django.core.exceptions import ValidationError
from .models import RideBooking
from .services.distance import DistanceService


class BookingForm(forms.Form):
    pickup_address = forms.CharField(max_length=512)
    pickup_lat = forms.FloatField(required=False)
    pickup_lng = forms.FloatField(required=False)
    dropoff_address = forms.CharField(max_length=512)
    dropoff_lat = forms.FloatField(required=False)
    dropoff_lng = forms.FloatField(required=False)

    distance_km = forms.FloatField(required=False)

    num_adults = forms.IntegerField(min_value=1, initial=1)
    num_kids_seated = forms.IntegerField(min_value=0, initial=0)
    num_kids_carried = forms.IntegerField(min_value=0, initial=0)
    luggage_count = forms.IntegerField(min_value=0, initial=0)

    phone = forms.CharField(max_length=32)
    email = forms.EmailField()

    payment_option = forms.ChoiceField(choices=[(RideBooking.PAYMENT_ON_ARRIVAL, 'Pay on Arrival'), (RideBooking.PAYMENT_PAYNOW, 'Pay Online')])

    def clean(self):
        cleaned = super().clean()
        distance = cleaned.get('distance_km')
        if distance is None:
            # require coordinates
            coords = ('pickup_lat', 'pickup_lng', 'dropoff_lat', 'dropoff_lng')
            missing = [c for c in coords if cleaned.get(c) is None]
            if missing:
                raise ValidationError(f"Either provide distance_km or coordinates for pickup and dropoff. Missing: {', '.join(missing)}")
            # compute distance via DistanceService
            try:
                distance = DistanceService.get_distance_km((cleaned.get('pickup_lat'), cleaned.get('pickup_lng')),
                                                          (cleaned.get('dropoff_lat'), cleaned.get('dropoff_lng')))
            except Exception as exc:
                raise ValidationError(f"Unable to compute distance: {exc}")

            cleaned['distance_km'] = distance

        if cleaned.get('num_adults') < 1:
            raise ValidationError('At least one adult is required')

        return cleaned


# Step-based wizard forms (for new booking_wizard.html)

class BookingStep1Form(forms.Form):
    """Step 1: Pickup & Dropoff Locations"""
    pickup_address = forms.CharField(
        max_length=512,
        required=True,
        error_messages={'required': 'Pickup address is required'}
    )
    pickup_lat = forms.FloatField(
        required=True,
        error_messages={'required': 'Pickup coordinates are required'}
    )
    pickup_lng = forms.FloatField(
        required=True,
        error_messages={'required': 'Pickup coordinates are required'}
    )
    dropoff_address = forms.CharField(
        max_length=512,
        required=True,
        error_messages={'required': 'Dropoff address is required'}
    )
    dropoff_lat = forms.FloatField(
        required=True,
        error_messages={'required': 'Dropoff coordinates are required'}
    )
    dropoff_lng = forms.FloatField(
        required=True,
        error_messages={'required': 'Dropoff coordinates are required'}
    )
    distance_km = forms.FloatField(required=False)

    def clean(self):
        cleaned = super().clean()

        # Validate distance or compute it
        distance = cleaned.get('distance_km')
        if distance is None:
            try:
                distance = DistanceService.get_distance_km(
                    (cleaned.get('pickup_lat'), cleaned.get('pickup_lng')),
                    (cleaned.get('dropoff_lat'), cleaned.get('dropoff_lng'))
                )
                cleaned['distance_km'] = distance
            except Exception as exc:
                raise ValidationError(f"Unable to compute distance: {exc}")

        # Validate minimum distance (0.5 km)
        if distance < 0.5:
            raise ValidationError("Pickup and dropoff are too close (minimum 0.5 km)")

        return cleaned


class BookingStep2Form(forms.Form):
    """Step 2: Passengers & Luggage"""
    num_adults = forms.IntegerField(
        min_value=1,
        required=True,
        error_messages={'required': 'Number of adults is required', 'min_value': 'At least one adult is required'}
    )
    num_kids_seated = forms.IntegerField(
        min_value=0,
        required=True,
        initial=0
    )
    num_kids_carried = forms.IntegerField(
        min_value=0,
        required=True,
        initial=0
    )
    luggage_count = forms.IntegerField(
        min_value=0,
        required=True,
        initial=0
    )
    # Optional: passenger details as JSON (names, ages) if user toggles "Add passenger names/details?"
    passenger_details_json = forms.CharField(
        required=False,
        widget=forms.HiddenInput()
    )


class BookingStep3Form(forms.Form):
    """Step 3: Contact & Special Instructions"""
    phone = forms.CharField(
        max_length=32,
        min_length=5,
        required=True,
        error_messages={'required': 'Phone number is required', 'min_length': 'Phone number must be at least 5 characters'}
    )
    email = forms.EmailField(
        required=True,
        error_messages={'required': 'Email is required', 'invalid': 'Enter a valid email address'}
    )
    special_instructions = forms.CharField(
        max_length=300,
        required=False,
        widget=forms.Textarea(attrs={'rows': 3}),
        help_text='Optional: E.g., "Please wait at back gate" or "I have a pet" (max 300 characters)'
    )


class BookingStep4Form(forms.Form):
    """Step 4: Payment Method Selection"""
    payment_option = forms.ChoiceField(
        choices=[
            (RideBooking.PAYMENT_ON_ARRIVAL, 'Pay on Arrival (Cash)'),
            (RideBooking.PAYMENT_PAYNOW, 'Pay Online (Paynow)')
        ],
        required=True,
        error_messages={'required': 'Please select a payment method'}
    )


class BookingStep5Form(forms.Form):
    """Step 5: Confirmation (no validation, just a placeholder for consistency)"""
    # No fields to validate on confirmation step
    pass
