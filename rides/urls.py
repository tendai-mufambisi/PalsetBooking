from django.urls import path
from django.views.generic import TemplateView
from .views import (
    CreateBookingView, PaynowResultView, PaynowReturnView, PaynowPollView,
    BookingFormView, BookingSuccessView, PriceEstimateView,
    MultiStepBookingWizardView, BookingWizardEditView, DevFillWizardView,
    PlacesAutocompleteView, DistanceFareCalcView,
    ChauffeurBookingWizardView, ServiceSelectorView, ManageBookingView,
)

app_name = 'rides'

urlpatterns = [
    # Service selector (landing page)
    path('', ServiceSelectorView.as_view(), name='service_selector'),

    # Regular / Long Distance booking wizard
    path('booking/step/<int:step>/', MultiStepBookingWizardView.as_view(), name='booking_wizard'),
    path('booking/', MultiStepBookingWizardView.as_view(), {'step': 1}, name='booking_wizard_start'),
    # Development only: seed the wizard session and jump to a step (404 when DEBUG is off)
    path('booking/dev-fill/', DevFillWizardView.as_view(), name='booking_wizard_dev_fill'),
    # Saves edits made from the single Edit modal on the review step
    path('booking/edit/', BookingWizardEditView.as_view(), name='booking_wizard_edit'),

    # Chauffeur Drive wizard
    path('chauffeur/step/<int:step>/', ChauffeurBookingWizardView.as_view(), name='chauffeur_wizard'),
    path('chauffeur/', ChauffeurBookingWizardView.as_view(), {'step': 1}, name='chauffeur_wizard_start'),

    path('bookings/success/<str:pk>/', BookingSuccessView.as_view(), name='booking_success'),

    # Customer self-service via emailed magic link (no account needed)
    path('booking/manage/<str:token>/', ManageBookingView.as_view(), name='manage_booking'),

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
