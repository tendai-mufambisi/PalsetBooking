from django.contrib import admin
from .models import RideBooking, Payment, SiteSettings


@admin.register(RideBooking)
class RideBookingAdmin(admin.ModelAdmin):
    list_display = (
        "reference", "ride_type", "pickup_address", "dropoff_address",
        "distance_km", "total_amount", "status", "passengers_over_limit", "created_at",
    )
    list_filter = ("ride_type", "status", "payment_option", "passengers_over_limit")
    readonly_fields = ("created_at", "updated_at", "reference")
    search_fields = ("pickup_address", "dropoff_address", "phone", "email", "reference")
    fieldsets = (
        ("Booking Reference", {
            "fields": ("reference", "ride_type", "status"),
        }),
        ("Route", {
            "fields": (
                "pickup_address", "pickup_lat", "pickup_lng",
                "dropoff_address", "dropoff_lat", "dropoff_lng",
                "distance_km",
            ),
        }),
        ("Chauffeur Drive", {
            "fields": ("chauffeur_hours", "chauffeur_package_label"),
            "classes": ("collapse",),
        }),
        ("Passengers & Luggage", {
            "fields": (
                "num_adults", "num_kids_seated", "baby_car_seater",
                "num_kids_carried", "luggage_count", "passengers_over_limit",
            ),
        }),
        ("Schedule", {
            "fields": ("pickup_date", "pickup_time"),
        }),
        ("Airport Details", {
            "fields": (
                "pickup_is_airport", "arrival_airline", "arrival_flight_number",
                "arrival_date", "arrival_time",
            ),
            "classes": ("collapse",),
        }),
        ("Passenger Identity", {
            "fields": ("salutation", "passenger_full_name"),
        }),
        ("Contact", {
            "fields": ("phone", "email", "extra_instructions"),
        }),
        ("Payment", {
            "fields": ("payment_option", "total_amount", "price_breakdown"),
        }),
        ("Timestamps", {
            "fields": ("created_at", "updated_at"),
            "classes": ("collapse",),
        }),
    )


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ("id", "booking", "amount", "status", "paynow_reference", "created_at")
    readonly_fields = ("created_at", "updated_at")
    search_fields = ("paynow_reference",)


@admin.register(SiteSettings)
class SiteSettingsAdmin(admin.ModelAdmin):
    fieldsets = (
        ("Contact", {
            "fields": ("taxi_owner_email", "taxi_owner_phone"),
        }),
        ("EasyTransit Ride Pricing", {
            "description": (
                "Prices for regular city rides. Distance brackets define flat fares; "
                "above the last bracket a per-km rate applies."
            ),
            "fields": (
                "pricing_min_km",
                "pricing_brackets",
                "pricing_above_35_per_km",
                "pricing_base_passengers",
                "pricing_extra_adult_fee",
                "pricing_free_luggage",
                "pricing_luggage_fee",
            ),
        }),
        ("Long Distance Pricing", {
            "description": (
                "Applied automatically when trip distance reaches the threshold. "
                "Rate is per km from the start, not per km above the threshold."
            ),
            "fields": (
                "long_distance_threshold_km",
                "long_distance_per_km",
                "long_distance_base_passengers",
                "long_distance_extra_pax_fee",
                "long_distance_free_luggage",
                "long_distance_luggage_fee",
            ),
        }),
        ("Chauffeur Drive Packages", {
            "description": (
                'JSON list of packages. Each entry: '
                '{"hours": 4, "price": 100, "km_limit": 100, '
                '"window_start": "07:30", "window_end": "17:00", "max_passengers": 4}'
            ),
            "fields": ("chauffeur_packages",),
        }),
    )

    def has_add_permission(self, request):
        return not SiteSettings.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False
