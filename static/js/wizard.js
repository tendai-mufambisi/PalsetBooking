/**
 * wizard.js - Main orchestration for the booking wizard
 * Initializes all modules and manages the workflow
 */

class BookingWizard {
    constructor() {
        this.currentStep = 1;
        this.state = {};
    }

    async init() {
        console.log('Initializing Booking Wizard...');

        // All modules are initialized via DOMContentLoaded events in their respective files
        // (location.js, passengers.js, contact.js, navigation.js)
        // This is a central initialization point

        // Set initial state
        this.currentStep = 1;
    }
}

// Initialize wizard on document ready
document.addEventListener('DOMContentLoaded', () => {
    const wizard = new BookingWizard();
    window.bookingWizard = wizard; // Make globally available for debugging
    wizard.init();

    console.log('Booking Wizard initialized successfully');
});
