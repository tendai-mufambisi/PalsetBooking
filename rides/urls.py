from django.urls import path
from .views import (
    CreateBookingView, PaynowResultView, PaynowReturnView, PaynowPollView,
    BookingFormView, BookingSuccessView, PriceEstimateView,
    BookingWizardView, DistanceCalculateView, WizardStateView
)

app_name = 'rides'

urlpatterns = [
    # Template-based booking form
    #path('', BookingFormView.as_view(), name='home'),
    path('bookings/success/<uuid:pk>/', BookingSuccessView.as_view(), name='booking_success'),

    # Step-based wizard booking
    path('', BookingWizardView.as_view(), name='booking_wizard'),

    # API endpoints
    path('api/bookings/', CreateBookingView.as_view(), name='create_booking'),
    path('api/price/', PriceEstimateView.as_view(), name='price_estimate'),
    path('api/booking/distance/', DistanceCalculateView.as_view(), name='distance_calculate'),
    path('api/booking/wizard-state/', WizardStateView.as_view(), name='wizard_state'),
    path('paynow/result/', PaynowResultView.as_view(), name='paynow_result'),
    path('paynow/return/', PaynowReturnView.as_view(), name='paynow_return'),
    path('paynow/poll/<uuid:pk>/', PaynowPollView.as_view(), name='paynow_poll'),
]
