/**
 * Easy Transit - Booking Platform JavaScript
 * Handles AJAX interactions, distance calculations, real-time updates
 */

class BookingPlatform {
    /**
     * Initialize the booking platform
     */
    static init() {
        console.log('Booking platform initialized');
    }

    /**
     * Calculate distance and fare in real-time via AJAX
     *
     * @param {number} pickupLat
     * @param {number} pickupLng
     * @param {number} dropoffLat
     * @param {number} dropoffLng
     * @param {number} numAdults
     * @param {number} numKidsCarried
     * @param {number} luggageCount
     * @returns {Promise}
     */
    static async calculateDistanceFare(
        pickupLat,
        pickupLng,
        dropoffLat,
        dropoffLng,
        numAdults = 1,
        numKidsCarried = 0,
        luggageCount = 0
    ) {
        try {
            const response = await fetch('/api/distance-fare/', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': document.querySelector('[name=csrfmiddlewaretoken]')?.value || '',
                },
                body: JSON.stringify({
                    pickup_latitude: pickupLat,
                    pickup_longitude: pickupLng,
                    dropoff_latitude: dropoffLat,
                    dropoff_longitude: dropoffLng,
                    num_adults: numAdults,
                    num_kids_carried: numKidsCarried,
                    luggage_count: luggageCount,
                }),
            });

            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }

            const data = await response.json();
            return data;
        } catch (error) {
            console.error('Distance/Fare calculation error:', error);
            return null;
        }
    }

    /**
     * Validate phone number
     *
     * @param {string} phone
     * @returns {boolean}
     */
    static validatePhone(phone) {
        const digitCount = (phone.match(/\d/g) || []).length;
        return digitCount >= 5;
    }

    /**
     * Validate email
     *
     * @param {string} email
     * @returns {boolean}
     */
    static validateEmail(email) {
        if (!email) return true; // Email is optional
        const re = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
        return re.test(email);
    }

    /**
     * Get CSRF token from DOM
     *
     * @returns {string}
     */
    static getCSRFToken() {
        return (
            document.querySelector('[name=csrfmiddlewaretoken]')?.value ||
            localStorage.getItem('csrfToken') ||
            ''
        );
    }

    /**
     * Format currency value
     *
     * @param {number} amount
     * @param {string} currency
     * @returns {string}
     */
    static formatCurrency(amount, currency = 'USD') {
        return new Intl.NumberFormat('en-US', {
            style: 'currency',
            currency: currency,
        }).format(amount);
    }

    /**
     * Format distance
     *
     * @param {number} km
     * @returns {string}
     */
    static formatDistance(km) {
        if (km < 1) {
            return `${Math.round(km * 1000)} m`;
        }
        return `${km.toFixed(1)} km`;
    }

    /**
     * Calculate ETA in minutes
     *
     * @param {number} distanceKm
     * @param {number} averageSpeedKmh
     * @returns {number}
     */
    static calculateETA(distanceKm, averageSpeedKmh = 40) {
        return Math.round((distanceKm / averageSpeedKmh) * 60);
    }

    /**
     * Show loading spinner on element
     *
     * @param {Element} element
     * @param {string} message
     */
    static showLoading(element, message = 'Loading...') {
        element.innerHTML = `
            <div style="display: flex; align-items: center; gap: 8px; justify-content: center;">
                <span class="spinner"></span>
                <span>${message}</span>
            </div>
        `;
        element.classList.add('loading');
    }

    /**
     * Hide loading state
     *
     * @param {Element} element
     */
    static hideLoading(element) {
        element.classList.remove('loading');
    }

    /**
     * Show notification
     *
     * @param {string} message
     * @param {string} type
     * @param {number} duration
     */
    static showNotification(message, type = 'info', duration = 3000) {
        const notification = document.createElement('div');
        notification.className = `alert alert-${type}`;
        notification.style.cssText = `
            position: fixed;
            top: 20px;
            right: 20px;
            max-width: 400px;
            z-index: 9999;
            animation: slideIn 0.3s ease;
        `;
        notification.innerHTML = message;

        document.body.appendChild(notification);

        if (duration > 0) {
            setTimeout(() => {
                notification.style.animation = 'slideOut 0.3s ease';
                setTimeout(() => notification.remove(), 300);
            }, duration);
        }

        return notification;
    }

    /**
     * Debounce function
     *
     * @param {Function} func
     * @param {number} delay
     * @returns {Function}
     */
    static debounce(func, delay = 300) {
        let timeoutId;
        return function (...args) {
            clearTimeout(timeoutId);
            timeoutId = setTimeout(() => func.apply(this, args), delay);
        };
    }

    /**
     * Throttle function
     *
     * @param {Function} func
     * @param {number} limit
     * @returns {Function}
     */
    static throttle(func, limit = 300) {
        let inThrottle;
        return function (...args) {
            if (!inThrottle) {
                func.apply(this, args);
                inThrottle = true;
                setTimeout(() => (inThrottle = false), limit);
            }
        };
    }
}

// Add CSS animations
const style = document.createElement('style');
style.textContent = `
    @keyframes slideIn {
        from {
            transform: translateX(400px);
            opacity: 0;
        }
        to {
            transform: translateX(0);
            opacity: 1;
        }
    }

    @keyframes slideOut {
        from {
            transform: translateX(0);
            opacity: 1;
        }
        to {
            transform: translateX(400px);
            opacity: 0;
        }
    }

    .spinner {
        display: inline-block;
        width: 16px;
        height: 16px;
        border: 2px solid #f3f3f3;
        border-top: 2px solid #667eea;
        border-radius: 50%;
        animation: spin 1s linear infinite;
    }

    @keyframes spin {
        0% { transform: rotate(0deg); }
        100% { transform: rotate(360deg); }
    }
`;
document.head.appendChild(style);

// Initialize on page load
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', BookingPlatform.init);
} else {
    BookingPlatform.init();
}

// Export for use in modules/other scripts
if (typeof module !== 'undefined' && module.exports) {
    module.exports = BookingPlatform;
}
