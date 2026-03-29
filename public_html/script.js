     // Initialize EmailJS (replace with your actual public key)
        emailjs.init("YOUR_EMAILJS_PUBLIC_KEY");
        
        // Global variables
        let map;
        let directionsService;
        let directionsRenderer;
        let pickupAutocomplete;
        let dropoffAutocomplete;
        let currentDistance = 0;
        
        // Initialize the map and autocomplete
        function initMap() {
            // Set default location to Harare, Zimbabwe
            const harare = { lat: -17.8252, lng: 31.0335 };
            
            // Initialize the map
            map = new google.maps.Map(document.getElementById("map"), {
                zoom: 12,
                center: harare,
                styles: [
                    {
                        "featureType": "all",
                        "elementType": "geometry",
                        "stylers": [{ "color": "#f5f5f5" }]
                    },
                    {
                        "featureType": "water",
                        "elementType": "geometry",
                        "stylers": [{ "color": "#c9c9c9" }]
                    }
                ]
            });
            
            // Initialize directions service and renderer
            directionsService = new google.maps.DirectionsService();
            directionsRenderer = new google.maps.DirectionsRenderer({
                map: map,
                polylineOptions: {
                    strokeColor: "#2c5aa0",
                    strokeWeight: 5
                },
                suppressMarkers: false
            });
            
            // Initialize autocomplete for pickup and dropoff
            pickupAutocomplete = new google.maps.places.Autocomplete(
                document.getElementById("pickup"),
                {
                    types: ["geocode"],
                    componentRestrictions: { country: "zw" }
                }
            );
            
            dropoffAutocomplete = new google.maps.places.Autocomplete(
                document.getElementById("dropoff"),
                {
                    types: ["geocode"],
                    componentRestrictions: { country: "zw" }
                }
            );
            
            // Add event listeners to update route when places change
            pickupAutocomplete.addListener("place_changed", updateRoute);
            dropoffAutocomplete.addListener("place_changed", updateRoute);
            
            // Set default route
            setDefaultRoute();
        }
        
        // Set a default route for demonstration
        function setDefaultRoute() {
            const defaultPickup = "Harare International Airport, Zimbabwe";
            const defaultDropoff = "Harare City Centre, Zimbabwe";
            
            document.getElementById("pickup").value = defaultPickup;
            document.getElementById("dropoff").value = defaultDropoff;
            
            calculateAndDisplayRoute(defaultPickup, defaultDropoff);
        }
        
        // Update the route when input changes
        function updateRoute() {
            const pickup = document.getElementById("pickup").value;
            const dropoff = document.getElementById("dropoff").value;
            
            if (pickup && dropoff) {
                calculateAndDisplayRoute(pickup, dropoff);
            }
        }
        
        // Calculate and display the route on the map
        function calculateAndDisplayRoute(pickup, dropoff) {
            directionsService.route(
                {
                    origin: pickup,
                    destination: dropoff,
                    travelMode: google.maps.TravelMode.DRIVING,
                },
                (response, status) => {
                    if (status === "OK") {
                        directionsRenderer.setDirections(response);
                        
                        // Extract distance and duration
                        const route = response.routes[0];
                        const leg = route.legs[0];
                        
                        currentDistance = leg.distance.value / 1000; // Convert to km
                        const duration = leg.duration.text;
                        
                        // Update UI with distance and duration
                        document.getElementById("distanceValue").textContent = currentDistance.toFixed(1) + " km";
                        document.getElementById("durationValue").textContent = duration;
                        
                        // Update fare calculation
                        calculateFare();
                    } else {
                        console.error("Directions request failed: " + status);
                    }
                }
            );
        }
        
        // Calculate fare based on distance and passengers
        function calculateFare() {
            const distance = currentDistance;
            const adults = parseInt(document.getElementById("adults").value);
            const children = parseInt(document.getElementById("children").value);
            
            // Base fare calculation based on distance
            let baseFare = 0;
            let distanceSurcharge = 0;
            
            if (distance <= 12) {
                baseFare = 20;
            } else if (distance <= 15) {
                baseFare = 25;
            } else if (distance <= 20) {
                baseFare = 30;
            } else if (distance <= 25) {
                baseFare = 35;
            } else if (distance <= 35) {
                baseFare = 40;
            } else {
                baseFare = 40;
                distanceSurcharge = (distance - 35) * 2; // $2 per km beyond 35km
            }
            
            // Additional adults charge
            let extraAdultsCharge = 0;
            if (adults > 3) {
                extraAdultsCharge = (adults - 3) * 10;
            }
            
            // Update fare display
            document.getElementById("baseFare").textContent = "$" + baseFare.toFixed(2);
            document.getElementById("extraAdults").textContent = "$" + extraAdultsCharge.toFixed(2);
            document.getElementById("distanceSurcharge").textContent = "$" + distanceSurcharge.toFixed(2);
            
            const totalFare = baseFare + extraAdultsCharge + distanceSurcharge;
            document.getElementById("totalFare").textContent = "$" + totalFare.toFixed(2);
        }
        
        // Send booking email using EmailJS
        function sendBookingEmail(bookingData, isPayment = false) {
            const templateParams = {
                to_email: "bookings@easytransit.co.zw",
                from_name: bookingData.name,
                from_email: bookingData.email,
                phone: bookingData.phone,
                pickup: bookingData.pickup,
                dropoff: bookingData.dropoff,
                adults: bookingData.adults,
                children: bookingData.children,
                fare: bookingData.fare,
                payment_method: isPayment ? "Online Payment" : "Pay Later"
            };
            
            emailjs.send("YOUR_EMAILJS_SERVICE_ID", "YOUR_EMAILJS_TEMPLATE_ID", templateParams)
                .then(function(response) {
                    console.log("Email sent successfully:", response);
                    showSuccessMessage();
                }, function(error) {
                    console.error("Email sending failed:", error);
                    showErrorMessage();
                });
        }
        
        // Show success message
        function showSuccessMessage() {
            document.getElementById("loadingIndicator").style.display = "none";
            document.getElementById("successMessage").style.display = "block";
            
            // Reset form after 3 seconds
            setTimeout(() => {
                document.getElementById("successMessage").style.display = "none";
                document.getElementById("bookingForm").reset();
                setDefaultRoute();
            }, 3000);
        }
        
        // Show error message
        function showErrorMessage() {
            document.getElementById("loadingIndicator").style.display = "none";
            document.getElementById("errorMessage").style.display = "block";
            
            // Hide error message after 5 seconds
            setTimeout(() => {
                document.getElementById("errorMessage").style.display = "none";
            }, 5000);
        }
        
        // Event listeners when DOM is loaded
        document.addEventListener("DOMContentLoaded", function() {
            // Update fare when number of adults or children changes
            document.getElementById("adults").addEventListener("change", calculateFare);
            document.getElementById("children").addEventListener("change", calculateFare);
            
            // Handle form submission
            document.getElementById("bookingForm").addEventListener("submit", function(e) {
                e.preventDefault();
                
                // Show loading indicator
                document.getElementById("loadingIndicator").style.display = "block";
                
                // Collect form data
                const bookingData = {
                    name: document.getElementById("name").value,
                    email: document.getElementById("email").value,
                    phone: document.getElementById("phone").value,
                    pickup: document.getElementById("pickup").value,
                    dropoff: document.getElementById("dropoff").value,
                    adults: document.getElementById("adults").value,
                    children: document.getElementById("children").value,
                    fare: document.getElementById("totalFare").textContent
                };
                
                // Send booking email (without payment)
                sendBookingEmail(bookingData, false);
            });
            
            // Handle pay now button
            document.getElementById("payNowBtn").addEventListener("click", function() {
                // Show loading indicator
                document.getElementById("loadingIndicator").style.display = "block";
                
                // Collect form data
                const bookingData = {
                    name: document.getElementById("name").value,
                    email: document.getElementById("email").value,
                    phone: document.getElementById("phone").value,
                    pickup: document.getElementById("pickup").value,
                    dropoff: document.getElementById("dropoff").value,
                    adults: document.getElementById("adults").value,
                    children: document.getElementById("children").value,
                    fare: document.getElementById("totalFare").textContent
                };
                
                // In a real implementation, you would integrate with a payment gateway here
                // For this demo, we'll just send the booking email with payment flag
                setTimeout(() => {
                    sendBookingEmail(bookingData, true);
                }, 1500);
            });
        });