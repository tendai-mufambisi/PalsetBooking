from django.urls import path
from django.views.generic import TemplateView
from .views import (
    CreateBookingView, PaynowResultView, PaynowReturnView, PaynowPollView,
    BookingFormView, BookingSuccessView, PriceEstimateView,
    MultiStepBookingWizardView, PlacesAutocompleteView, DistanceFareCalcView,
    ChauffeurBookingWizardView, ServiceSelectorView,
)

app_name = 'rides'

urlpatterns = [
    # Service selector (landing page)
    path('', ServiceSelectorView.as_view(), name='service_selector'),

    # Regular / Long Distance booking wizard
    path('booking/step/<int:step>/', MultiStepBookingWizardView.as_view(), name='booking_wizard'),
    path('booking/', MultiStepBookingWizardView.as_view(), {'step': 1}, name='booking_wizard_start'),

    # Chauffeur Drive wizard
    path('chauffeur/step/<int:step>/', ChauffeurBookingWizardView.as_view(), name='chauffeur_wizard'),
    path('chauffeur/', ChauffeurBookingWizardView.as_view(), {'step': 1}, name='chauffeur_wizard_start'),

    path('bookings/success/<str:pk>/', BookingSuccessView.as_view(), name='booking_success'),

    # AJAX endpoints for wizard
    path('api/places-autocomplete/', PlacesAutocompleteView.as_view(), name='places_autocomplete'),
    path('api/distance-fare/', DistanceFareCalcView.as_view(), name='distance_fare_calc'),

    # API endpoints
    path('api/bookings/', CreateBookingView.as_view(), name='create_booking'),
    path('api/price/', PriceEstimateView.as_view(), name='price_estimate'),

    # Payment
    path('paynow/result/', PaynowResultView.as_view(), name='paynow_result'),
    path('paynow/return/', PaynowReturnView.as_view(), name='paynow_return'),
    path('paynow/poll/<uuid:pk>/', PaynowPollView.as_view(), name='paynow_poll'),
]
