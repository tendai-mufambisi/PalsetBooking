/**
 * navigation.js - Step navigation and transitions
 */

function initNavigation() {
    const backBtn = document.getElementById('backBtn');
    const nextBtn = document.getElementById('nextBtn');
    const confirmBtn = document.getElementById('confirmBtn');

    backBtn.addEventListener('click', goToPreviousStep);
    nextBtn.addEventListener('click', goToNextStep);
    confirmBtn.addEventListener('click', submitWizard);
}

async function goToNextStep() {
    const currentStep = parseInt(document.getElementById('currentStep').value);

    // Validate current step
    let isValid = false;
    switch (currentStep) {
        case 1:
            isValid = await validateStep1();
            break;
        case 2:
            isValid = validateStep2();
            break;
        case 3:
            isValid = validateStep3();
            break;
        case 4:
            isValid = validateStep4();
            break;
        case 5:
            isValid = true; // Confirmation has no validation
            break;
    }

    if (!isValid) {
        return;
    }

    // Save form data to inputs
    saveStepData(currentStep);

    // Move to next step
    const nextStep = Math.min(currentStep + 1, 5);
    renderStep(nextStep);
}

function goToPreviousStep() {
    const currentStep = parseInt(document.getElementById('currentStep').value);
    if (currentStep > 1) {
        saveStepData(currentStep);
        renderStep(currentStep - 1);
    }
}

function renderStep(stepNumber) {
    const currentStep = parseInt(document.getElementById('currentStep').value);

    // Hide current step
    hideStep(currentStep);

    // Show new step
    showStep(stepNumber);

    // Update hidden input
    document.getElementById('currentStep').value = stepNumber;

    // Update progress indicator
    updateProgressIndicator(stepNumber);

    // Update buttons
    updateNavigationButtons(stepNumber);

    // Update form state display (for Step 4 & 5)
    if (stepNumber === 4) {
        updateFareDisplay();
    } else if (stepNumber === 5) {
        updateConfirmationSummary();
    }

    // Scroll to top
    window.scrollTo({ top: 0, behavior: 'smooth' });
}

function hideStep(stepNumber) {
    const section = document.querySelector(`section[data-step="${stepNumber}"]`);
    if (section) {
        section.style.display = 'none';
    }
}

function showStep(stepNumber) {
    const section = document.querySelector(`section[data-step="${stepNumber}"]`);
    if (section) {
        section.style.display = 'block';
    }
}

function updateProgressIndicator(stepNumber) {
    document.querySelectorAll('.step-item').forEach(item => {
        const step = parseInt(item.getAttribute('data-step'));
        item.classList.remove('active', 'complete');

        if (step < stepNumber) {
            item.classList.add('complete');
        } else if (step === stepNumber) {
            item.classList.add('active');
        }
    });
}

function updateNavigationButtons(stepNumber) {
    const backBtn = document.getElementById('backBtn');
    const nextBtn = document.getElementById('nextBtn');
    const confirmBtn = document.getElementById('confirmBtn');

    // Show/hide back button
    backBtn.style.display = stepNumber === 1 ? 'none' : 'block';

    if (stepNumber === 5) {
        // Hide next, show confirm
        nextBtn.style.display = 'none';
        confirmBtn.style.display = 'block';
    } else {
        // Show next, hide confirm
        nextBtn.style.display = 'block';
        confirmBtn.style.display = 'none';
    }
}

function saveStepData(stepNumber) {
    // Collect form data from current step
    const formData = new FormData(document.getElementById('wizardForm'));
    const data = Object.fromEntries(formData);

    // Save to session via API
    const wizardState = {
        step: stepNumber,
        data: data,
        visited_steps: Array.from(document.querySelectorAll('.step-item.complete, .step-item.active')).map(item =>
            parseInt(item.getAttribute('data-step'))
        )
    };

    // Optional: Save to session (non-blocking)
    saveWizardState(wizardState).catch(err => console.error('Failed to save state:', err));
}

function updateFareDisplay() {
    // Retrieve stored fare breakdown from Step 1/2
    const distanceKmInput = document.getElementById('distance_km');
    let priceBreakdown = null;

    if (distanceKmInput && distanceKmInput.dataset.priceBreakdown) {
        try {
            priceBreakdown = JSON.parse(distanceKmInput.dataset.priceBreakdown);
        } catch (e) {
            console.error('Failed to parse price breakdown:', e);
        }
    }

    if (!priceBreakdown) {
        // If no breakdown data, hide the summary
        const fareSummary = document.getElementById('fareSummary');
        if (fareSummary) {
            fareSummary.style.display = 'none';
        }
        return;
    }

    // Update fare breakdown table
    const tableBody = document.getElementById('fareBreakdownTable');
    if (tableBody) {
        const rows = [
            ['Base Fare (Distance)', priceBreakdown.base_distance_price || 0],
            ['Extra Adults', priceBreakdown.extra_adults_fee || 0],
            ['Kids (Seated)', priceBreakdown.kids_seated_fee || 0],
            ['Luggage', priceBreakdown.luggage_fee || 0]
        ];

        let html = '';
        rows.forEach(([label, amount]) => {
            html += `<tr><td>${label}</td><td class="text-end">${formatCurrency(amount)}</td></tr>`;
        });

        html += `<tr class="table-active fw-bold"><td>Total Fare</td><td class="text-end">${formatCurrency(priceBreakdown.total)}</td></tr>`;

        tableBody.innerHTML = html;
    }

    // Update total fare display
    const totalDisplay = document.getElementById('totalFareDisplay');
    if (totalDisplay) {
        totalDisplay.textContent = formatCurrency(priceBreakdown.total);
    }

    // Show fare summary
    const fareSummary = document.getElementById('fareSummary');
    if (fareSummary) {
        fareSummary.style.display = 'block';
    }
}

function updateConfirmationSummary() {
    // Pickup & Dropoff
    document.getElementById('confirmPickup').textContent = document.getElementById('pickupInput').value || '--';
    document.getElementById('confirmDropoff').textContent = document.getElementById('dropoffInput').value || '--';

    // Passengers & Luggage
    const adults = document.getElementById('num_adults').value;
    const kidsSeated = document.getElementById('num_kids_seated').value;
    const kidsCarried = document.getElementById('num_kids_carried').value;
    const luggage = document.getElementById('luggage_count').value;

    let passengerSummary = `${kidsSeated} kids (seated), ${kidsCarried} kids (carried), ${luggage} bags`;
    document.getElementById('confirmAdults').textContent = adults;
    document.getElementById('confirmPassengers').textContent = passengerSummary;

    // Contact
    document.getElementById('confirmEmail').textContent = document.getElementById('emailInput').value || '--';
    document.getElementById('confirmPhone').textContent = document.getElementById('phoneInput').value || '--';

    // Payment
    const paymentOption = document.querySelector('input[name="payment_option"]:checked');
    const paymentText = paymentOption ? (paymentOption.value === 'POA' ? 'Pay on Arrival' : 'Pay Online (Paynow)') : '--';
    document.getElementById('confirmPayment').textContent = paymentText;

    // Total - retrieve from stored price breakdown
    let totalText = '--';
    const distanceKmInput = document.getElementById('distance_km');
    if (distanceKmInput && distanceKmInput.dataset.priceBreakdown) {
        try {
            const priceBreakdown = JSON.parse(distanceKmInput.dataset.priceBreakdown);
            totalText = formatCurrency(priceBreakdown.total);
        } catch (e) {
            console.error('Failed to parse price breakdown:', e);
        }
    }
    document.getElementById('confirmTotal').textContent = totalText;

    // Special Instructions (if present)
    const instructions = document.getElementById('instructionsInput').value.trim();
    if (instructions) {
        document.getElementById('confirmInstructionsSection').style.display = 'block';
        document.getElementById('confirmInstructions').textContent = instructions;
    } else {
        document.getElementById('confirmInstructionsSection').style.display = 'none';
    }
}

function validateStep4() {
    const paymentOption = document.querySelector('input[name="payment_option"]:checked');
    const agreeTerms = document.getElementById('agreeTerms').checked;

    if (!paymentOption) {
        showError('Please select a payment method');
        return false;
    }

    if (!agreeTerms) {
        showError('Please agree to the terms and conditions');
        return false;
    }

    return true;
}

async function submitWizard() {
    const confirmBtn = document.getElementById('confirmBtn');
    showLoading(confirmBtn);

    try {
        // Collect all form data
        const formData = new FormData(document.getElementById('wizardForm'));
        const wizardState = {
            step: 5,
            data: Object.fromEntries(formData)
        };

        // Create booking via API
        const response = await createBooking(wizardState);

        hideLoading(confirmBtn);

        if (response && response.id) {
            // Booking created successfully
            showSuccess('Booking confirmed! Redirecting...');
            setTimeout(() => {
                // Redirect based on payment method
                if (response.payment_option === 'PAYNOW') {
                    // Redirect to Paynow flow
                    window.location.href = `/rides/paynow/return/?reference=${response.payment?.id || response.id}`;
                } else {
                    // Redirect to success page
                    window.location.href = `/rides/bookings/success/${response.id}/`;
                }
            }, 1500);
        } else {
            showError('Booking failed. Please try again.');
        }
    } catch (error) {
        hideLoading(confirmBtn);
        showError(`Booking failed: ${error.message}`);
        console.error('Booking submission error:', error);
    }
}

// Initialize on document ready
document.addEventListener('DOMContentLoaded', () => {
    initNavigation();
    renderStep(1); // Start at step 1
});
