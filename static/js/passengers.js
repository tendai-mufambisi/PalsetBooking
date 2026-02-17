/**
 * passengers.js - Passenger count increment/decrement and fare preview
 */

function initPassengerControls() {
    // Attach event listeners to increment/decrement buttons
    document.querySelectorAll('.increment-btn').forEach(btn => {
        btn.addEventListener('click', incrementField);
    });

    document.querySelectorAll('.decrement-btn').forEach(btn => {
        btn.addEventListener('click', decrementField);
    });

    // Passenger details toggle
    const addDetailsCheckbox = document.getElementById('addPassengerDetails');
    const detailsPanel = document.getElementById('passengerDetailsPanel');

    addDetailsCheckbox.addEventListener('change', function() {
        detailsPanel.style.display = this.checked ? 'block' : 'none';
    });
}

function incrementField(event) {
    event.preventDefault();
    const field = event.target.getAttribute('data-field');
    const input = document.getElementById(field);
    if (!input) return;

    const currentValue = parseInt(input.value) || 0;

    // Set reasonable limits
    const maxValue = field === 'num_adults' ? 20 : 10;
    if (currentValue < maxValue) {
        input.value = currentValue + 1;
        onPassengerChange();
    }
}

function decrementField(event) {
    event.preventDefault();
    const field = event.target.getAttribute('data-field');
    const input = document.getElementById(field);
    if (!input) return;

    const currentValue = parseInt(input.value) || 0;

    // Minimum values
    const minValue = field === 'num_adults' ? 1 : 0;
    if (currentValue > minValue) {
        input.value = currentValue - 1;
        onPassengerChange();
    }
}

function onPassengerChange() {
    // Validate at least 1 adult
    const numAdultsInput = document.getElementById('num_adults');
    if (numAdultsInput) {
        const numAdults = parseInt(numAdultsInput.value) || 1;
        if (numAdults < 1) {
            numAdultsInput.value = 1;
        }
    }

    // Update fare preview (debounced)
    debouncedUpdateFare();
}

function displayFareBreakdown(breakdown) {
    const tableBody = document.getElementById('fareBreakdownTable');
    if (!tableBody) return;

    const rows = [
        ['Base Fare (Distance)', breakdown.base_distance_price],
        ['Extra Adults', breakdown.extra_adults_fee || 0],
        ['Kids (Seated)', breakdown.kids_seated_fee || 0],
        ['Luggage', breakdown.luggage_fee || 0]
    ];

    let html = '';
    rows.forEach(([label, amount]) => {
        html += `<tr><td>${label}</td><td class="text-end">${formatCurrency(amount)}</td></tr>`;
    });

    html += `<tr class="table-active fw-bold"><td>Total Fare</td><td class="text-end">${formatCurrency(breakdown.total)}</td></tr>`;

    tableBody.innerHTML = html;
    document.getElementById('totalFareDisplay').textContent = formatCurrency(breakdown.total);
}

function validateStep2() {
    const numAdults = parseInt(document.getElementById('num_adults').value);

    if (numAdults < 1) {
        showError('At least one adult is required');
        return false;
    }

    return true;
}

// Initialize on document ready
document.addEventListener('DOMContentLoaded', () => {
    initPassengerControls();
});
