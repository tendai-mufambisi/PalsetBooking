from django import forms
from django.core.exceptions import ValidationError
from .models import RideBooking
from .services.distance import DistanceService


# ============================================================================
# Step-Based Forms for the Multi-Step Booking Wizard
# ============================================================================

class Step1PickupDropoffForm(forms.Form):
    """Step 1: Pickup & Dropoff Locations with auto-geolocation."""
    
    pickup_address = forms.CharField(
        max_length=512,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Enter pickup location',
            'id': 'pickup_address',
        })
    )
    pickup_latitude = forms.FloatField(
        widget=forms.HiddenInput(attrs={'id': 'pickup_latitude'}),
        required=False
    )
    pickup_longitude = forms.FloatField(
        widget=forms.HiddenInput(attrs={'id': 'pickup_longitude'}),
        required=False
    )
    
    dropoff_address = forms.CharField(
        max_length=512,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Enter dropoff location',
            'id': 'dropoff_address',
        })
    )
    dropoff_latitude = forms.FloatField(
        widget=forms.HiddenInput(attrs={'id': 'dropoff_latitude'}),
        required=False
    )
    dropoff_longitude = forms.FloatField(
        widget=forms.HiddenInput(attrs={'id': 'dropoff_longitude'}),
        required=False
    )
    # Scheduling and airport-specific fields
    pickup_date = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={'class': 'form-control', 'type': 'date', 'id': 'pickup_date'})
    )
    pickup_time = forms.TimeField(
        required=False,
        widget=forms.TimeInput(attrs={'class': 'form-control', 'type': 'time', 'id': 'pickup_time'})
    )
    pickup_is_airport = forms.BooleanField(
        required=False,
        widget=forms.CheckboxInput(attrs={'id': 'pickup_is_airport', 'class': 'form-check-input'})
    )
    arrival_airline = forms.CharField(
        max_length=64,
        required=False,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. Airlink', 'id': 'id_arrival_airline'})
    )
    arrival_flight_number = forms.CharField(
        max_length=32,
        required=False,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. 40Z10', 'id': 'id_arrival_flight_number'})
    )
    arrival_date = forms.DateField(required=False, widget=forms.DateInput(attrs={'class': 'form-control', 'type': 'date', 'id': 'id_arrival_date'}))
    arrival_time = forms.TimeField(required=False, widget=forms.TimeInput(attrs={'class': 'form-control', 'type': 'time', 'id': 'id_arrival_time'}))

    def clean(self):
        cleaned = super().clean()
        pickup_lat = cleaned.get('pickup_latitude')
        pickup_lng = cleaned.get('pickup_longitude')
        dropoff_lat = cleaned.get('dropoff_latitude')
        dropoff_lng = cleaned.get('dropoff_longitude')
        
        # Validate that coordinates are present after Places Autocomplete
        if not all([pickup_lat, pickup_lng, dropoff_lat, dropoff_lng]):
            raise ValidationError('Please select valid pickup and dropoff locations from the suggestions.')

        # If user indicated airport pickup, require flight details
        if cleaned.get('pickup_is_airport'):
            if not cleaned.get('arrival_airline') or not cleaned.get('arrival_flight_number'):
                raise ValidationError('For airport pickups please provide arrival airline and flight number.')
        
        return cleaned


class Step2PassengersLuggageForm(forms.Form):
    """Step 2: Number of adults, kids (seated/carried), and luggage."""
    
    num_adults = forms.IntegerField(
        min_value=1,
        initial=1,
        widget=forms.HiddenInput()  # Controlled via JS increment/decrement
    )
    num_kids_seated = forms.IntegerField(
        min_value=0,
        initial=0,
        widget=forms.HiddenInput()
    )
    baby_car_seater = forms.IntegerField(
        min_value=0,
        initial=0,
        widget=forms.HiddenInput()
    )
    num_kids_carried = forms.IntegerField(
        min_value=0,
        initial=0,
        widget=forms.HiddenInput()
    )
    luggage_count = forms.IntegerField(
        min_value=0,
        initial=0,
        widget=forms.HiddenInput()
    )

    def clean(self):
        cleaned = super().clean()
        if cleaned.get('num_adults', 0) < 1:
            raise ValidationError('At least one adult is required.')
        return cleaned


class Step3ContactExtraForm(forms.Form):
    """Step 3: Contact information and extra instructions."""
    
    phone = forms.CharField(
        max_length=32,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': '+263 77 000 0000',
            'id': 'phone',
            'type': 'tel',
        })
    )
    email = forms.EmailField(
        required=False,
        widget=forms.EmailInput(attrs={
            'class': 'form-control',
            'placeholder': 'your@email.com',
            'id': 'email',
        })
    )
    extra_instructions = forms.CharField(
        max_length=500,
        required=False,
        widget=forms.Textarea(attrs={
            'class': 'form-control',
            'placeholder': "E.g., 'Please wait at back gate' or 'I have a pet'",
            'rows': 3,
            'id': 'extra_instructions',
        })
    )
    # Passenger details
    salutation = forms.CharField(
        max_length=32,
        required=False,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Mr / Mrs / Dr', 'id': 'id_salutation'})
    )
    passenger_full_name = forms.CharField(
        max_length=256,
        required=False,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Full name (e.g. John Doe)', 'id': 'id_passenger_full_name'})
    )

    def clean(self):
        cleaned = super().clean()
        phone = cleaned.get('phone', '').strip()
        
        if not phone:
            raise ValidationError('Phone number is required.')
        
        # Simple phone validation: must have at least 5 digits
        if len([c for c in phone if c.isdigit()]) < 5:
            raise ValidationError('Phone number must contain at least 5 digits.')
        
        return cleaned


class Step4FarePaymentForm(forms.Form):
    """Step 4: Fare preview & payment method selection."""
    
    # Distance and fare are displayed but not edited here; they're calculated on backend
    distance_km = forms.FloatField(
        widget=forms.HiddenInput(),
        required=False
    )
    estimated_fare = forms.DecimalField(
        max_digits=10,
        decimal_places=2,
        widget=forms.HiddenInput(),
        required=False
    )
    fare_breakdown = forms.CharField(
        widget=forms.HiddenInput(),  # JSON string
        required=False
    )
    
    payment_method = forms.ChoiceField(
        choices=[
            (RideBooking.PAYMENT_ON_ARRIVAL, 'Pay on Arrival (Cash)'),
            (RideBooking.PAYMENT_CARD_ON_ARRIVAL, 'Pay on Arrival (POS/CARD payment)'),
            (RideBooking.PAYMENT_MONEY_TRANSFER, 'Pay Via Money Transfer Agency'),
            (RideBooking.PAYMENT_PAYLINK, 'Paylink'),
            (RideBooking.PAYMENT_PAYNOW, 'Pay Online (Paynow)'),
        ],
        widget=forms.RadioSelect(attrs={
            'class': 'form-check-input',
        })
    )

    def clean(self):
        cleaned = super().clean()
        if not cleaned.get('payment_method'):
            raise ValidationError('Please select a payment method.')
        return cleaned


class Step5ConfirmationForm(forms.Form):
    """Step 5: Final confirmation (display-only, no changes)."""
    # This is a summary page; form mainly used for template rendering context
    confirm = forms.BooleanField(
        required=True,
        widget=forms.CheckboxInput(attrs={
            'class': 'form-check-input',
        })
    )


# ============================================================================
# Legacy Full Booking Form (kept for backward compatibility)
# ============================================================================

class BookingForm(forms.Form):
    """Legacy full booking form (all fields at once)."""
    
    pickup_address = forms.CharField(max_length=512)
    pickup_lat = forms.FloatField(required=False)
    pickup_lng = forms.FloatField(required=False)
    pickup_date = forms.DateField(required=False)
    pickup_time = forms.TimeField(required=False)
    pickup_is_airport = forms.BooleanField(required=False)
    arrival_airline = forms.CharField(max_length=64, required=False, widget=forms.TextInput(attrs={'placeholder': 'e.g. Airlink'}))
    arrival_flight_number = forms.CharField(max_length=32, required=False, widget=forms.TextInput(attrs={'placeholder': 'e.g. 40Z10'}))
    arrival_date = forms.DateField(required=False, widget=forms.DateInput(attrs={'type': 'date'}))
    arrival_time = forms.TimeField(required=False, widget=forms.TimeInput(attrs={'type': 'time'}))
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
    salutation = forms.CharField(max_length=32, required=False)
    salutation = forms.CharField(max_length=32, required=False, widget=forms.TextInput(attrs={'placeholder': 'Mr / Mrs / Dr'}))
    passenger_full_name = forms.CharField(max_length=256, widget=forms.TextInput(attrs={'placeholder': 'Full name (e.g. John Doe)'}))

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
