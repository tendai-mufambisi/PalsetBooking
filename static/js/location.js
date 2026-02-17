/**
 * location.js - Google Maps and Places Autocomplete integration
 */

let map;
let directionsService;
let directionsRenderer;
let pickupAutocomplete;
let dropoffAutocomplete;

// Initialize Google Maps
function initializeMap() {
    const mapElement = document.getElementById('map');
    const defaultLocation = { lat: -17.8252, lng: 31.0335 }; // Harare central

    map = new google.maps.Map(mapElement, {
        zoom: 12,
        center: defaultLocation,
        mapTypeControl: false,
        fullscreenControl: false
    });

    directionsService = new google.maps.DirectionsService();
    directionsRenderer = new google.maps.DirectionsRenderer({
        map: map,
        suppressMarkers: false,
        polylineOptions: {
            strokeColor: '#0d6efd',
            strokeWeight: 4
        }
    });
}

// Initialize Places Autocomplete
function initializePlacesAutocomplete() {
    const pickupInput = document.getElementById('pickupInput');
    const dropoffInput = document.getElementById('dropoffInput');

    // Restrict to Zimbabwe
    const restrictOptions = {
        componentRestrictions: { country: 'zw' }
    };

    // Pickup autocomplete
    pickupAutocomplete = new google.maps.places.Autocomplete(pickupInput, restrictOptions);
    pickupAutocomplete.addListener('place_changed', onPickupAddressChanged);

    // Dropoff autocomplete
    dropoffAutocomplete = new google.maps.places.Autocomplete(dropoffInput, restrictOptions);
    dropoffAutocomplete.addListener('place_changed', onDropoffAddressChanged);
}

// Handle pickup address selection
function onPickupAddressChanged() {
    const place = pickupAutocomplete.getPlace();
    if (!place.geometry || !place.geometry.location) {
        console.warn('Autocomplete: Place not fully loaded');
        return;
    }

    document.getElementById('pickupLat').value = place.geometry.location.lat();
    document.getElementById('pickupLng').value = place.geometry.location.lng();
    document.getElementById('pickupInput').value = place.formatted_address;

    updateRoutePreview();
}

// Handle dropoff address selection
function onDropoffAddressChanged() {
    const place = dropoffAutocomplete.getPlace();
    if (!place.geometry || !place.geometry.location) {
        console.warn('Autocomplete: Place not fully loaded');
        return;
    }

    document.getElementById('dropoffLat').value = place.geometry.location.lat();
    document.getElementById('dropoffLng').value = place.geometry.location.lng();
    document.getElementById('dropoffInput').value = place.formatted_address;

    updateRoutePreview();
}

// Update route preview on map
function updateRoutePreview() {
    const pickupLat = document.getElementById('pickupLat').value;
    const pickupLng = document.getElementById('pickupLng').value;
    const dropoffLat = document.getElementById('dropoffLat').value;
    const dropoffLng = document.getElementById('dropoffLng').value;

    if (!pickupLat || !pickupLng || !dropoffLat || !dropoffLng) {
        return;
    }

    const origin = new google.maps.LatLng(parseFloat(pickupLat), parseFloat(pickupLng));
    const destination = new google.maps.LatLng(parseFloat(dropoffLat), parseFloat(dropoffLng));

    directionsService.route(
        {
            origin: origin,
            destination: destination,
            travelMode: google.maps.TravelMode.DRIVING,
            avoidHighways: false,
            avoidTolls: false
        },
        (result, status) => {
            if (status === google.maps.DirectionsStatus.OK) {
                directionsRenderer.setDirections(result);
                // Fit map bounds to route
                const bounds = new google.maps.LatLngBounds();
                result.routes[0].legs.forEach(leg => {
                    bounds.extend(leg.start_location);
                    bounds.extend(leg.end_location);
                });
                map.fitBounds(bounds);

                // Calculate and display distance
                calculateAndDisplayDistance();
            } else if (status !== google.maps.DirectionsStatus.ZERO_RESULTS) {
                console.error(`Directions request failed due to ${status}`);
            }
        }
    );
}

// Calculate distance using backend API
async function calculateAndDisplayDistance() {
    const pickupLat = document.getElementById('pickupLat').value;
    const pickupLng = document.getElementById('pickupLng').value;
    const dropoffLat = document.getElementById('dropoffLat').value;
    const dropoffLng = document.getElementById('dropoffLng').value;
    const distanceInput = document.getElementById('distance_km');

    if (!pickupLat || !pickupLng || !dropoffLat || !dropoffLng) {
        return;
    }

    if (!distanceInput) {
        console.error('distance_km input element not found');
        return;
    }

    try {
        const result = await fetchDistance(pickupLat, pickupLng, dropoffLat, dropoffLng);
        distanceInput.value = result.distance_km;

        // Display distance
        document.getElementById('distanceValue').textContent = result.distance_km.toFixed(1);
        document.getElementById('distanceAlert').style.display = 'block';

        // Update fare preview
        await updateFarePreview();
    } catch (error) {
        showError('Failed to calculate distance. Please try again.');
        console.error('Distance calculation error:', error);
    }
}

// Update fare preview (debounced)
const debouncedUpdateFare = debounce(updateFarePreview, 600);

async function updateFarePreview() {
    const distanceKmInput = document.getElementById('distance_km');
    if (!distanceKmInput) {
        console.warn('distance_km input not found');
        return;
    }

    const distanceKm = distanceKmInput.value;
    const numAdults = parseInt(document.getElementById('num_adults')?.value) || 1;
    const numKidsSeated = parseInt(document.getElementById('num_kids_seated')?.value) || 0;
    const numKidsCarried = parseInt(document.getElementById('num_kids_carried')?.value) || 0;
    const luggageCount = parseInt(document.getElementById('luggage_count')?.value) || 0;

    if (!distanceKm) {
        return;
    }

    try {
        const result = await fetchPrice(distanceKm, numAdults, numKidsSeated, numKidsCarried, luggageCount);

        // Display fare
        document.getElementById('fareValue').textContent = formatCurrency(result.total);
        document.getElementById('fareAlert').style.display = 'block';

        // Store breakdown in form (for Step 4 summary)
        distanceKmInput.dataset.priceBreakdown = JSON.stringify(result);
    } catch (error) {
        console.error('Fare calculation error:', error);
    }
}

// Request user's current location (Geolocation API)
function requestUserLocation() {
    const btn = document.getElementById('useMyLocationBtn');

    if (!navigator.geolocation) {
        showError('Geolocation is not supported by your browser');
        return;
    }

    showLoading(btn);

    navigator.geolocation.getCurrentPosition(
        (position) => {
            const lat = position.coords.latitude;
            const lng = position.coords.longitude;

            // Reverse geocode to get address
            reverseGeocodeLocation(lat, lng);

            hideLoading(btn);
        },
        (error) => {
            hideLoading(btn);
            switch (error.code) {
                case error.PERMISSION_DENIED:
                    showError('You denied location permission. Please enable it in your browser settings.');
                    break;
                case error.POSITION_UNAVAILABLE:
                    showError('Your location is currently unavailable.');
                    break;
                case error.TIMEOUT:
                    showError('Location request timed out.');
                    break;
                default:
                    showError('An error occurred while retrieving your location.');
            }
        },
        {
            enableHighAccuracy: false,
            timeout: 10000,
            maximumAge: 300000
        }
    );
}

// Reverse geocode coordinates to address
function reverseGeocodeLocation(lat, lng) {
    const geocoder = new google.maps.Geocoder();
    const latlng = { lat: lat, lng: lng };

    geocoder.geocode({ location: latlng }, (results, status) => {
        if (status === 'OK' && results[0]) {
            document.getElementById('pickupInput').value = results[0].formatted_address;
            document.getElementById('pickupLat').value = lat;
            document.getElementById('pickupLng').value = lng;

            updateRoutePreview();
            showSuccess('Your location has been set as pickup point');
        } else {
            // Even if reverse geocoding fails, use coordinates
            document.getElementById('pickupLat').value = lat;
            document.getElementById('pickupLng').value = lng;
            document.getElementById('pickupInput').value = `${lat.toFixed(4)}, ${lng.toFixed(4)}`;

            updateRoutePreview();
            showSuccess('Your coordinates have been set');
        }
    });
}

// Validate Step 1
async function validateStep1() {
    const pickupInput = document.getElementById('pickupInput').value.trim();
    const pickupLat = document.getElementById('pickupLat').value;
    const pickupLng = document.getElementById('pickupLng').value;
    const dropoffInput = document.getElementById('dropoffInput').value.trim();
    const dropoffLat = document.getElementById('dropoffLat').value;
    const dropoffLng = document.getElementById('dropoffLng').value;

    if (!pickupInput || !pickupLat || !pickupLng) {
        showError('Please select a pickup address with valid coordinates');
        return false;
    }

    if (!dropoffInput || !dropoffLat || !dropoffLng) {
        showError('Please select a dropoff address with valid coordinates');
        return false;
    }

    return true;
}

// Initialize on document ready
document.addEventListener('DOMContentLoaded', () => {
    initializeMap();
    initializePlacesAutocomplete();

    // Setup event listeners
    document.getElementById('useMyLocationBtn').addEventListener('click', requestUserLocation);
    document.getElementById('pickupInput').addEventListener('change', () => {
        debouncedUpdateFare();
    });
    document.getElementById('dropoffInput').addEventListener('change', () => {
        debouncedUpdateFare();
    });
});
