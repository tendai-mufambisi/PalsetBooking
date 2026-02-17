/**
 * api.js - HTTP client for wizard API calls
 * Handles CSRF tokens, requests, and error handling
 */

// Get CSRF token from cookies
function getCsrfToken() {
    const name = 'csrftoken';
    let cookieValue = null;
    if (document.cookie && document.cookie !== '') {
        const cookies = document.cookie.split(';');
        for (let i = 0; i < cookies.length; i++) {
            const cookie = cookies[i].trim();
            if (cookie.substring(0, name.length + 1) === (name + '=')) {
                cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
                break;
            }
        }
    }
    return cookieValue;
}

// Generic API call function
async function apiCall(endpoint, method = 'POST', data = {}) {
    const csrfToken = getCsrfToken();
    const headers = {
        'Content-Type': 'application/json',
        'X-CSRFToken': csrfToken
    };

    try {
        const response = await fetch(endpoint, {
            method: method,
            headers: headers,
            body: method !== 'GET' ? JSON.stringify(data) : undefined,
            credentials: 'same-origin'
        });

        if (!response.ok) {
            throw new Error(`HTTP ${response.status}: ${response.statusText}`);
        }

        return await response.json();
    } catch (error) {
        console.error(`API call failed: ${error.message}`);
        throw error;
    }
}

// Calculate distance
async function fetchDistance(pickupLat, pickupLng, dropoffLat, dropoffLng) {
    return apiCall('/distance/', 'POST', {
        pickup_lat: pickupLat,
        pickup_lng: pickupLng,
        dropoff_lat: dropoffLat,
        dropoff_lng: dropoffLng
    });
}

// Fetch price estimate
async function fetchPrice(distanceKm, numAdults, numKidsSeated, numKidsCarried, luggageCount) {
    return apiCall('/rides/api/price/', 'POST', {
        distance_km: distanceKm,
        num_adults: numAdults,
        num_kids_seated: numKidsSeated,
        num_kids_carried: numKidsCarried,
        luggage_count: luggageCount
    });
}

// Save wizard state to session
async function saveWizardState(state) {
    return apiCall('/wizard-state/', 'POST', { state: state });
}

// Get wizard state from session
async function getWizardState() {
    return apiCall('/wizard-state/', 'GET');
}

// Create booking (final step)
async function createBooking(wizardState) {
    const bookingData = {
        pickup_address: wizardState.data.pickup_address,
        pickup_lat: wizardState.data.pickup_lat,
        pickup_lng: wizardState.data.pickup_lng,
        dropoff_address: wizardState.data.dropoff_address,
        dropoff_lat: wizardState.data.dropoff_lat,
        dropoff_lng: wizardState.data.dropoff_lng,
        distance_km: wizardState.data.distance_km,
        num_adults: wizardState.data.num_adults,
        num_kids_seated: wizardState.data.num_kids_seated,
        num_kids_carried: wizardState.data.num_kids_carried,
        luggage_count: wizardState.data.luggage_count,
        phone: wizardState.data.phone,
        email: wizardState.data.email,
        special_instructions: wizardState.data.special_instructions,
        payment_option: wizardState.data.payment_option
    };

    return apiCall('/rides/api/bookings/', 'POST', bookingData);
}
