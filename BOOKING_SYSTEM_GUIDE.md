# Easy Transit - Multi-Step Ride Booking Platform

## Project Overview

This is a complete redesign of the Easy Transit "Book a Ride" system into a professional, mobile-first, multi-step ride booking platform.

### Key Features

✅ **Multi-Step Wizard Flow**
- Step 1: Pickup & Dropoff locations with Google Maps integration
- Step 2: Number of passengers (adults, kids seated/carried) and luggage
- Step 3: Contact information and extra instructions
- Step 4: Fare preview and payment method selection
- Step 5: Booking confirmation

✅ **Smart Features**
- Real-time Google Places Autocomplete for addresses
- "Use My Current Location" button with geolocation
- Dynamic map showing route between pickup and dropoff
- Real-time distance & fare calculation
- Step-based state management using Django sessions
- Responsive mobile-first UI

✅ **Payment Integration**
- Pay on Arrival (cash)
- Paynow online payment gateway
- Secure payment handling

✅ **Backend Services**
- Google Directions API for distance calculation
- Dynamic pricing based on distance + passengers + luggage
- Database persistence of all bookings
- Email notifications

---

## Directory Structure

```
rides/
├── models.py                 # RideBooking & Payment models
├── views.py                  # Multi-step wizard views + AJAX endpoints
├── forms.py                  # Step-based forms (Step1-5)
├── urls.py                   # Booking flow routes
├── serializers.py            # DRF serializers
├── services/
│   ├── distance.py           # Google Distance Matrix API integration
│   ├── pricing.py            # Dynamic fare calculation
│   ├── paynow.py             # Paynow payment integration
│   └── email_service.py      # Email notifications
├── templates/rides/
│   └── booking_wizard/
│       ├── base_wizard.html  # Master template with progress bar
│       ├── step1.html        # Pickup & Dropoff
│       ├── step2.html        # Passengers & Luggage
│       ├── step3.html        # Contact & Instructions
│       ├── step4.html        # Fare Preview & Payment
│       └── step5.html        # Confirmation
└── migrations/
    └── 0003_add_extra_instructions.py

static/
├── css/wizard.css            # Responsive styling
└── js/booking.js             # Shared booking platform utilities
```

---

## Database Models

### RideBooking Model

Stores complete booking information:

```python
- id: UUID (primary key)
- pickup_address: CharField(512)
- pickup_lat, pickup_lng: DecimalField (coordinates)
- dropoff_address: CharField(512)
- dropoff_lat, dropoff_lng: DecimalField (coordinates)
- distance_km: DecimalField
- num_adults, num_kids_seated, num_kids_carried, luggage_count: SmallIntegerField
- phone, email: CharField / EmailField
- extra_instructions: TextField (optional, max 500 chars)
- payment_option: CharField (POA | PAYNOW)
- status: CharField (PENDING | CONFIRMED | CANCELLED)
- price_breakdown: JSONField (fare details)
- total_amount: DecimalField
- created_at, updated_at: DateTimeField
```

### Payment Model

Tracks payment status:

```python
- id: UUID
- booking: ForeignKey to RideBooking
- method: CharField
- amount: DecimalField
- status: CharField (PENDING | PAID | FAILED)
- paynow_reference: CharField
- paynow_response: JSONField (raw Paynow API response)
- created_at, updated_at: DateTimeField
```

---

## View Flow

### Multi-Step Booking Wizard

**URL:** `/rides/booking/` or `/rides/booking/step/1/`

**Session Management:**
- Step data stored in Django session with key prefix `booking_wizard_`
- User can navigate back and forth; state is preserved
- Session cleared after booking confirmation

**Steps:**

1. **Step 1 (GET):** Show location form with map
   - **POST:** Validate locations, save to session, redirect to Step 2

2. **Step 2 (GET):** Show passengers/luggage form
   - **POST:** Save passenger data, redirect to Step 3

3. **Step 3 (GET):** Show contact form
   - **POST:** Save contact info, redirect to Step 4

4. **Step 4 (GET):** Show fare preview + payment method
   - Calculate distance & fare on the fly
   - **POST:** Create RideBooking + Payment
     - If Pay on Arrival: Confirm and go to Step 5
     - If Paynow: Redirect to payment gateway

5. **Step 5 (GET):** Show confirmation with booking summary

### AJAX Endpoints

#### Distance & Fare Calculation
**POST** `/rides/api/distance-fare/`

Request:
```json
{
  "pickup_latitude": 17.8252,
  "pickup_longitude": 31.0335,
  "dropoff_latitude": 17.8300,
  "dropoff_longitude": 31.0400,
  "num_adults": 1,
  "num_kids_seated": 0,
  "num_kids_carried": 0,
  "luggage_count": 0
}
```

Response:
```json
{
  "distance_km": 5.2,
  "fare_breakdown": {
    "distance_km": 5.2,
    "base_distance_price": 25.0,
    "extra_adults": 0,
    "extra_adults_fee": 0,
    "kids_seated": 0,
    "kids_seated_fee": 0,
    "luggage_count": 0,
    "luggage_fee": 0,
    "subtotal": 25.0,
    "total": 25.0
  },
  "estimated_fare": 25.0
}
```

---

## Frontend Features

### Step 1: Location Selection

- **GooglePlaces Autocomplete** for pickup & dropoff addresses
- **"Use My Current Location"** button:
  - Requests browser geolocation
  - Reverse-geocodes to get address
  - Auto-fills pickup coordinates
- **Real-time Google Maps preview:**
  - Green marker = Pickup
  - Red marker = Dropoff
  - Blue polyline = Route
  - Auto-pans/zooms to fit route
- **Validation:** Both locations required before proceeding

### Step 2: Passengers & Luggage

- **Increment/Decrement Controls** for each passenger type
- **Toggle "Add Children & Luggage"** to show optional fields
- Adults minimum = 1
- Pricing tiers:
  - Base fare for up to 3 adults
  - Extra adults: $10 each
  - Kids seated: 50% of per-adult share
  - Kids carried: Free
  - Luggage: $5 per bag

### Step 3: Contact & Extra Instructions

- **Phone (required):** Must be valid format
- **Email (optional):** Confirmation sent here
- **Extra Instructions (optional):** 500 character max
  - Examples: "Wait at back gate", "I have a pet"
  - Real-time character counter

### Step 4: Fare Preview & Payment

- **Fare Breakdown Table:**
  - Distance
  - Base fare
  - Extra adult fees
  - Kid discounts
  - Luggage fees
  - **Total**
- **Payment Method Selection:**
  - Radio buttons with card-style UI
  - "Pay on Arrival (Cash)"
  - "Pay Online (Paynow)"
- **Terms acceptance checkbox**

### Step 5: Confirmation

- **Booking Summary Card** with all details
- **Booking ID** (UUID)
- **Status badge**
- **Contact number** for support
- **Action Buttons:**
  - "Home"
  - "New Booking"
- **Print option** for booking confirmation

---

## Forms (Step-Based)

### Step1PickupDropoffForm
- `pickup_address` (CharField)
- `pickup_latitude`, `pickup_longitude` (FloatField, hidden)
- `dropoff_address` (CharField)
- `dropoff_latitude`, `dropoff_longitude` (FloatField, hidden)
- **Validation:** Both locations must have valid coordinates

### Step2PassengersLuggageForm
- `num_adults` (IntegerField, min=1)
- `num_kids_seated` (IntegerField, min=0)
- `num_kids_carried` (IntegerField, min=0)
- `luggage_count` (IntegerField, min=0)

### Step3ContactExtraForm
- `phone` (CharField, required)
- `email` (EmailField, optional)
- `extra_instructions` (CharField, max=500, optional)

### Step4FarePaymentForm
- `distance_km` (FloatField, hidden)
- `estimated_fare` (DecimalField, hidden)
- `payment_method` (ChoiceField: POA | PAYNOW)

### Step5ConfirmationForm
- `confirm` (BooleanField)

---

## Pricing Logic

Located in `services/pricing.py` - `PricingService.calculate()`

**Pricing Brackets:**
```
Distance      Price
0-13 km       $25 (minimum)
13-15 km      $25
16-20 km      $30
21-25 km      $35
26-35 km      $40
>35 km        $40 + $1.30 per km
```

**Modifiers:**
- **Extra Adults** (>3): $10 each
- **Kids Seated**: 50% of per-adult share of base fare
- **Kids Carried**: FREE
- **Luggage**: $5 per bag

**Fare = Base Distance Price + Extra Adults Fee + Kids Seated Fee + Luggage Fee**

---

## API Endpoints (REST)

### CreateBookingView
**POST** `/rides/api/bookings/`
- Alternative to multi-step wizard
- Creates booking in single request
- Returns booking or Paynow redirect URL

### PriceEstimateView
**POST** `/rides/api/price/`
- Calculates fare without creating booking
- Useful for pre-checkout estimates

### PaynowResultView
**POST** `/rides/paynow/result/`
- Server-to-server webhook from Paynow
- Verifies payment completion
- Updates booking status

### PaynowReturnView
**GET** `/rides/paynow/return/`
- User redirected back from Paynow
- Shows payment status
- Not authoritative (use webhooks instead)

### PaynowPollView
**GET** `/rides/paynow/poll/<payment_id>/`
- AJAX endpoint to check payment status
- Used by Step 5 for real-time updates

---

## Configuration & Environment Variables

Required `.env` variables:

```env
# Google Maps
GOOGLE_MAPS_CLIENT_KEY=Your_Google_Maps_API_Key
GOOGLE_MAPS_SERVER_KEY=Your_Google_Server_API_Key

# Paynow Integration
PAYNOW_INTEGRATION_ID=Your_Paynow_ID
PAYNOW_INTEGRATION_KEY=Your_Paynow_Key
PAYNOW_RETURN_URL=https://yourdomain.com/rides/paynow/return/
PAYNOW_RESULT_URL=https://yourdomain.com/rides/paynow/result/

# Email
EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
EMAIL_HOST=smtp.gmail.com
EMAIL_PORT=587
EMAIL_USE_TLS=True
EMAIL_HOST_USER=your_email@gmail.com
EMAIL_HOST_PASSWORD=your_app_password
TAXI_OWNER_EMAIL=owner@easytransit.co.zw

# Pricing (in settings.py)
PRICING = {
    "MIN_DISTANCE_KM": 13.0,
    "BRACKETS": [
        {"min": 13, "max": 15, "price": 25.0},
        {"min": 16, "max": 20, "price": 30.0},
        {"min": 21, "max": 25, "price": 35.0},
        {"min": 26, "max": 35, "price": 40.0},
    ],
    "ABOVE_35_PER_KM": 1.30,
    "EXTRA_ADULT_FEE": 10.0,
    "KID_SEATED_FACTOR": 0.5,
    "LUGGAGE_FEE": 5.0,
}
```

---

## JavaScript Integration

### booking.js

Shared utility class `BookingPlatform` with static methods:

```javascript
// Calculate distance & fare via AJAX
BookingPlatform.calculateDistanceFare(
  pickupLat, pickupLng, 
  dropoffLat, dropoffLng,
  numAdults, numKidsSeated, 
  numKidsCarried, luggageCount
)
// Returns: { distance_km, fare_breakdown, estimated_fare }

// Validation helpers
BookingPlatform.validatePhone(phone)
BookingPlatform.validateEmail(email)

// Formatting
BookingPlatform.formatCurrency(amount, currency)
BookingPlatform.formatDistance(km)
BookingPlatform.calculateETA(distanceKm, avgSpeedKmh)

// UI Helpers
BookingPlatform.showLoading(element, message)
BookingPlatform.hideLoading(element)
BookingPlatform.showNotification(message, type, duration)

// Function utilities
BookingPlatform.debounce(func, delay)
BookingPlatform.throttle(func, limit)
```

---

## Testing the System

### 1. Start Django Development Server
```bash
python manage.py runserver
```

### 2. Access Booking Wizard
```
http://localhost:8000/rides/booking/
```

### 3. Test Workflow
1. **Step 1:** Enter pickup & dropoff locations (or click "Use My Current Location")
2. **Step 2:** Adjust passenger/luggage counts
3. **Step 3:** Enter phone, optional email
4. **Step 4:** Review fare, select payment method
5. **Step 5:** Confirm booking

### 4. Check Database
```bash
python manage.py shell
>>> from rides.models import RideBooking, Payment
>>> RideBooking.objects.all()
>>> Payment.objects.all()
```

---

## Mobile-First Responsive Design

- **Base Font:** Bootstrap 5 system stack
- **Colors:** Purple gradient primary (#667eea → #764ba2)
- **Spacing:** 8px base unit
- **Breakpoints:**
  - Small (<576px): Single column, simplified UI
  - Medium (576-768px): Tablet optimize
  - Large (768px+): Desktop view
- **Touch-Friendly:** Buttons min 44x44px
- **Accessibility:** WCAG 2.1 AA compliant

---

## Common Customizations

### Change Pricing Rules
Edit `settings.py` → `PRICING` dictionary

### Add Promo Codes
Extend `PricingService.calculate()` with discount logic

### Change Primary Color
Update CSS variables in `base_wizard.html`:
```css
--primary-color: #667eea;
--primary-dark: #764ba2;
```

### Add Driver Assignment Logic
Extend Step 5 to query available drivers after booking confirmation

### Add Real-Time Tracking
After payment, embed live driver location map on confirmation page

---

## Troubleshooting

### "Google Maps API not loaded"
- Verify `GOOGLE_MAPS_CLIENT_KEY` is set
- Check API key has Maps JS, Places, and Directions enabled
- Verify domain is whitelisted in Google Console

### Payment redirects to error page
- Check `PAYNOW_INTEGRATION_ID` and `PAYNOW_INTEGRATION_KEY`
- Verify `PAYNOW_RETURN_URL` and `PAYNOW_RESULT_URL` match deployment domain

### Geolocation permission denied
- Browser security: HTTPS required for geolocation
- User may have denied permission; allow manual entry

### Session expires mid-wizard
- Session timeout configured in `settings.py` (default: 1209600s = 2 weeks)
- Adjust `SESSION_COOKIE_AGE` as needed

---

## Next Steps & Enhancements

1. **Driver Mobile App:** Accept/reject bookings in real-time
2. **Live Tracking:** WebSocket integration for driver location updates
3. **Rating System:** Post-ride feedback and driver ratings
4. **Saved Addresses:** Quick-book home/work locations
5. **Referral Program:** Discount codes for referrals
6. **Admin Dashboard:** Analytics and booking management
7. **SMS Notifications:** Update customers via text instead of email
8. **Multiple Vehicle Types:** Economy, Premium, XL van options

---

## Support & Documentation

- Django Docs: https://docs.djangoproject.com/
- Google Maps API: https://developers.google.com/maps
- Paynow Zimbabwe: https://www.paynow.co.zw/
- Bootstrap 5: https://getbootstrap.com/docs/5.0/

---

**Version:** 1.0.0  
**Last Updated:** February 17, 2026  
**License:** MIT
