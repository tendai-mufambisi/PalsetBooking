from django.urls import path
from django.views.generic import TemplateView
from .views import (
    CreateBookingView, PaynowResultView, PaynowReturnView, PaynowPollView,
    BookingFormView, BookingSuccessView, PriceEstimateView,
    MultiStepBookingWizardView, PlacesAutocompleteView, DistanceFareCalcView
)

app_name = 'rides'

urlpatterns = [
    # Home/Template-based pages
    path('', TemplateView.as_view(template_name='rides/index.html'), name='index'),
    path('about/', TemplateView.as_view(template_name='rides/about.html'), name='about'),
    path('services/', TemplateView.as_view(template_name='rides/services.html'), name='services'),
    
    # Service Pages
    path('airport-transfers/', TemplateView.as_view(template_name='rides/airport-transfers.html'), name='airport_transfers'),
    path('corporate-transfers/', TemplateView.as_view(template_name='rides/corporate-transfers.html'), name='corporate_transfers'),
    path('chauffeur-drive/', TemplateView.as_view(template_name='rides/chauffeur-drive.html'), name='chauffeur_drive'),
    path('private-tours/', TemplateView.as_view(template_name='rides/private-tours.html'), name='private_tours'),
    path('group-transfers/', TemplateView.as_view(template_name='rides/group-transfers.html'), name='group_transfers'),
    path('point-transfers/', TemplateView.as_view(template_name='rides/point-transfers.html'), name='point_transfers'),
    path('car-rental/', TemplateView.as_view(template_name='rides/car-rental.html'), name='car_rental'),
    path('special-events/', TemplateView.as_view(template_name='rides/special-events.html'), name='special_events'),
    path('long-distance/', TemplateView.as_view(template_name='rides/long-distance.html'), name='long_distance'),
    path('dinner-transfers/', TemplateView.as_view(template_name='rides/dinner-transfers.html'), name='dinner_transfers'),
    
    # Other Pages
    path('fleet/', TemplateView.as_view(template_name='rides/fleet.html'), name='fleet'),
    path('tours/', TemplateView.as_view(template_name='rides/tours.html'), name='tours'),
    path('gallery/', TemplateView.as_view(template_name='rides/gallery.html'), name='gallery'),
    path('blog/', TemplateView.as_view(template_name='rides/blog.html'), name='blog'),
    path('blog/<int:id>/', TemplateView.as_view(template_name='rides/blog-details.html'), name='blog_details'),
    path('testimonials/', TemplateView.as_view(template_name='rides/testimonials.html'), name='testimonials'),
    path('faq/', TemplateView.as_view(template_name='rides/faq.html'), name='faq'),
    path('terms/', TemplateView.as_view(template_name='rides/terms.html'), name='terms'),
    path('privacy/', TemplateView.as_view(template_name='rides/privacy.html'), name='privacy'),
    path('contact/', TemplateView.as_view(template_name='rides/contact.html'), name='contact'),
    
    # Booking Pages and Wizard
    path('booking-page/', TemplateView.as_view(template_name='rides/booking.html'), name='booking_page'),
    path('booking/step/<int:step>/', MultiStepBookingWizardView.as_view(), name='booking_wizard'),
    path('booking/', MultiStepBookingWizardView.as_view(), {'step': 1}, name='booking_wizard_start'),
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
