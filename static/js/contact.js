/**
 * contact.js - Contact information validation
 */

function initContactControls() {
    const emailInput = document.getElementById('emailInput');
    const phoneInput = document.getElementById('phoneInput');
    const instructionsInput = document.getElementById('instructionsInput');
    const charCount = document.getElementById('charCount');

    // Email validation on blur
    if (emailInput) {
        emailInput.addEventListener('blur', validateEmailInput);
    }

    // Phone validation on blur
    if (phoneInput) {
        phoneInput.addEventListener('blur', validatePhoneInput);
    }

    // Character counter for special instructions
    if (instructionsInput && charCount) {
        instructionsInput.addEventListener('input', function() {
            charCount.textContent = this.value.length;
        });
    }
}

function validateEmailInput() {
    const emailInput = document.getElementById('emailInput');
    if (!emailInput) return false;

    const email = emailInput.value.trim();

    if (!email) {
        emailInput.classList.remove('is-valid');
        emailInput.classList.add('is-invalid');
        return false;
    }

    if (!isValidEmail(email)) {
        emailInput.classList.remove('is-valid');
        emailInput.classList.add('is-invalid');
        return false;
    }

    emailInput.classList.remove('is-invalid');
    emailInput.classList.add('is-valid');
    return true;
}

function validatePhoneInput() {
    const phoneInput = document.getElementById('phoneInput');
    if (!phoneInput) return false;

    const phone = phoneInput.value.trim();

    if (!phone) {
        phoneInput.classList.remove('is-valid');
        phoneInput.classList.add('is-invalid');
        return false;
    }

    if (!isValidPhone(phone)) {
        phoneInput.classList.remove('is-valid');
        phoneInput.classList.add('is-invalid');
        return false;
    }

    phoneInput.classList.remove('is-invalid');
    phoneInput.classList.add('is-valid');
    return true;
}

function validateStep3() {
    const emailInput = document.getElementById('emailInput');
    const phoneInput = document.getElementById('phoneInput');
    const instructionsInput = document.getElementById('instructionsInput');

    if (!emailInput || !phoneInput || !instructionsInput) {
        showError('Form elements not found. Please refresh the page.');
        return false;
    }

    const email = emailInput.value.trim();
    const phone = phoneInput.value.trim();
    const instructions = instructionsInput.value.trim();

    // Validate email
    if (!email) {
        showError('Email is required');
        return false;
    }

    if (!isValidEmail(email)) {
        showError('Please enter a valid email address');
        return false;
    }

    // Validate phone
    if (!phone) {
        showError('Phone number is required');
        return false;
    }

    if (!isValidPhone(phone)) {
        showError('Phone number must be at least 5 characters');
        return false;
    }

    // Validate special instructions length
    if (instructions.length > 300) {
        showError('Special instructions must not exceed 300 characters');
        return false;
    }

    return true;
}

// Initialize on document ready
document.addEventListener('DOMContentLoaded', () => {
    initContactControls();
});
