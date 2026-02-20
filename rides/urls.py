from django.urls import path
from .views import (
    CreateBookingView, PaynowResultView, PaynowReturnView, PaynowPollView,
    BookingFormView, BookingSuccessView, PriceEstimateView,
    MultiStepBookingWizardView, PlacesAutocompleteView, DistanceFareCalcView
)

app_name = 'rides'

urlpatterns = [
    # Template-based booking form
    path('', BookingFormView.as_view(), name='home'),
    path('bookings/success/<str:pk>/', BookingSuccessView.as_view(), name='booking_success'),

    # Step-based wizard booking (multi-step)
    path('booking/step/<int:step>/', MultiStepBookingWizardView.as_view(), name='booking_wizard'),
    path('booking/', MultiStepBookingWizardView.as_view(), {'step': 1}, name='booking_wizard_start'),

    # AJAX endpoints for wizard
    path('api/places-autocomplete/', PlacesAutocompleteView.as_view(), name='places_autocomplete'),
    path('api/distance-fare/', DistanceFareCalcView.as_view(), name='distance_fare_calc'),

    # API endpoints
    path('api/bookings/', CreateBookingView.as_view(), name='create_booking'),
    path('api/price/', PriceEstimateView.as_view(), name='price_estimate'),
    # Removed old DistanceCalculateView and WizardStateView (replaced by AJAX endpoints)
    path('paynow/result/', PaynowResultView.as_view(), name='paynow_result'),
    path('paynow/return/', PaynowReturnView.as_view(), name='paynow_return'),
    path('paynow/poll/<uuid:pk>/', PaynowPollView.as_view(), name='paynow_poll'),
]
