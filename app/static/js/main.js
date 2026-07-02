// Quick Care Connect - Main JavaScript

document.addEventListener('DOMContentLoaded', function () {
    // Initialize tooltips
    var tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'));
    var tooltipList = tooltipTriggerList.map(function (tooltipTriggerEl) {
        return new bootstrap.Tooltip(tooltipTriggerEl);
    });

    // Initialize popovers
    var popoverTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="popover"]'));
    var popoverList = popoverTriggerList.map(function (popoverTriggerEl) {
        return new bootstrap.Popover(popoverTriggerEl);
    });

    // Smooth scrolling for anchor links
    document.querySelectorAll('a[href^="#"]').forEach(anchor => {
        anchor.addEventListener('click', function (e) {
            e.preventDefault();
            const target = document.querySelector(this.getAttribute('href'));
            if (target) {
                target.scrollIntoView({
                    behavior: 'smooth',
                    block: 'start'
                });
            }
        });
    });

    // Auto-hide alerts after 5 seconds
    setTimeout(function () {
        var alerts = document.querySelectorAll('.alert');
        alerts.forEach(function (alert) {
            var bsAlert = new bootstrap.Alert(alert);
            bsAlert.close();
        });
    }, 5000);

    // Form validation enhancement
    const forms = document.querySelectorAll('.needs-validation');
    Array.from(forms).forEach(form => {
        form.addEventListener('submit', event => {
            if (!form.checkValidity()) {
                event.preventDefault();
                event.stopPropagation();
            }
            form.classList.add('was-validated');
        });
    });

    // Loading states for buttons
    document.querySelectorAll('form').forEach(form => {
        form.addEventListener('submit', function () {
            if (this.dataset.ajaxSubmit === 'true') {
                return;
            }

            const submitBtn = this.querySelector('button[type="submit"]');
            if (submitBtn) {
                submitBtn.innerHTML = '<span class="spinner"></span> Processing...';
                submitBtn.disabled = true;
            }
        });
    });

    // Search functionality
    const searchInput = document.querySelector('input[name="q"]');
    if (searchInput) {
        let searchTimeout;
        searchInput.addEventListener('input', function () {
            clearTimeout(searchTimeout);
            searchTimeout = setTimeout(() => {
                // Implement live search if needed
                console.log('Searching for:', this.value);
            }, 300);
        });
    }

    // Appointment type selection
    const appointmentTypeRadios = document.querySelectorAll('input[name="appointment_type"]');
    appointmentTypeRadios.forEach(radio => {
        radio.addEventListener('change', function () {
            // Update charges display
            updateChargesDisplay();
        });
    });

    // Date picker restrictions
    const dateInputs = document.querySelectorAll('input[type="date"]');
    dateInputs.forEach(input => {
        const today = new Date().toISOString().split('T')[0];
        input.setAttribute('min', today);
    });

    // Character counter for textareas
    const textareas = document.querySelectorAll('textarea[maxlength]');
    textareas.forEach(textarea => {
        const maxLength = textarea.getAttribute('maxlength');
        const counter = document.createElement('small');
        counter.className = 'text-muted character-counter';
        counter.textContent = `0/${maxLength} characters`;

        textarea.parentNode.appendChild(counter);

        textarea.addEventListener('input', function () {
            const remaining = maxLength - this.value.length;
            counter.textContent = `${this.value.length}/${maxLength} characters`;
            counter.className = remaining < 10 ? 'text-danger character-counter' : 'text-muted character-counter';
        });
    });

    // Image preview for file inputs
    const fileInputs = document.querySelectorAll('input[type="file"][accept*="image"]');
    fileInputs.forEach(input => {
        input.addEventListener('change', function () {
            const file = this.files[0];
            if (file) {
                const reader = new FileReader();
                reader.onload = function (e) {
                    let preview = input.parentNode.querySelector('.image-preview');
                    if (!preview) {
                        preview = document.createElement('div');
                        preview.className = 'image-preview mt-2';
                        input.parentNode.appendChild(preview);
                    }
                    preview.innerHTML = `<img src="${e.target.result}" class="img-thumbnail" style="max-width: 200px;">`;
                };
                reader.readAsDataURL(file);
            }
        });
    });

    // Mobile menu enhancement
    const navbarToggler = document.querySelector('.navbar-toggler');
    const navbarCollapse = document.querySelector('.navbar-collapse');

    if (navbarToggler && navbarCollapse) {
        // Close mobile menu when clicking on a link
        navbarCollapse.querySelectorAll('.nav-link').forEach(link => {
            link.addEventListener('click', () => {
                if (window.innerWidth < 992) {
                    navbarCollapse.classList.remove('show');
                }
            });
        });
    }

    // Lazy loading for images
    if ('IntersectionObserver' in window) {
        const imageObserver = new IntersectionObserver((entries, observer) => {
            entries.forEach(entry => {
                if (entry.isIntersecting) {
                    const img = entry.target;
                    img.src = img.dataset.src;
                    img.classList.remove('lazy');
                    imageObserver.unobserve(img);
                }
            });
        });

        document.querySelectorAll('img[data-src]').forEach(img => {
            imageObserver.observe(img);
        });
    }

    // Animation on scroll
    const animateOnScroll = new IntersectionObserver((entries) => {
        entries.forEach(entry => {
            if (entry.isIntersecting) {
                entry.target.classList.add('fade-in');
            }
        });
    }, {
        threshold: 0.1,
        rootMargin: '0px 0px -50px 0px'
    });

    document.querySelectorAll('.card, .stat-card, .feature-card').forEach(el => {
        animateOnScroll.observe(el);
    });
});

// Utility functions
function updateChargesDisplay() {
    const selectedType = document.querySelector('input[name="appointment_type"]:checked');
    const chargesDisplay = document.querySelector('.charges-display');

    if (selectedType && chargesDisplay) {
        const charges = selectedType.dataset.charges;
        chargesDisplay.textContent = `PKR ${charges}`;
    }
}

function formatPhoneNumber(input) {
    // Format phone number as user types
    let value = input.value.replace(/\D/g, '');
    if (value.length >= 10) {
        value = value.substring(0, 10);
    }
    if (value.length >= 6) {
        value = value.substring(0, 4) + '-' + value.substring(4, 10);
    } else if (value.length >= 4) {
        value = value.substring(0, 4) + '-' + value.substring(4);
    }
    input.value = value;
}

function validateEmail(email) {
    const re = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
    return re.test(email);
}

function showNotification(message, type = 'info') {
    const notification = document.createElement('div');
    notification.className = `alert alert-${type} alert-dismissible fade show position-fixed`;
    notification.style.cssText = 'top: 20px; right: 20px; z-index: 9999; min-width: 300px;';
    notification.innerHTML = `
        ${message}
        <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
    `;

    document.body.appendChild(notification);

    setTimeout(() => {
        notification.remove();
    }, 5000);
}

// Socket.IO integration is handled per-page (in chat.html etc.)
// Do NOT create a global io() connection here — it conflicts with page-specific socket connections
// and causes session appointment_id to be assigned to the wrong socket on the server.


// Tab close detection - Clear session when tab is closed
let isLoggedIn = false;
let sessionCleared = false;
let isNavigating = false;

// Check if user is logged in (check for logout link or user menu)
if (document.querySelector('a[href*="/logout"]') || document.querySelector('.user-menu') || document.querySelector('[data-user-id]')) {
    isLoggedIn = true;
}

// Mark navigation events (clicking links, form submits)
document.addEventListener('click', function (e) {
    const link = e.target.closest('a');
    if (link && link.href && !link.href.startsWith('javascript:') && !link.href.startsWith('#')) {
        isNavigating = true;
    }
});

document.addEventListener('submit', function () {
    isNavigating = true;
});

// ============================================
// SESSION PERSISTENCE - Auto logout on browser close DISABLED
// ============================================
// Session clearing on browser close has been disabled per user request.
// Users will remain logged in even after closing the browser/tab.
// Sessions persist for 1 year or until manual logout.

// Note: The following code is commented out to prevent session clearing on browser close
// Users will stay logged in across browser sessions

/*
// Function to clear session on server
function clearSessionOnClose() {
    if (isLoggedIn && !sessionCleared && !isNavigating) {
        sessionCleared = true;
        
        // Use navigator.sendBeacon for reliable delivery even if page is closing
        const logoutUrl = '/auth/logout-session';
        
        if (navigator.sendBeacon) {
            // Modern browsers - sendBeacon is more reliable for page unload
            navigator.sendBeacon(logoutUrl, '');
        } else {
            // Fallback for older browsers
            fetch(logoutUrl, {
                method: 'POST',
                keepalive: true,
                headers: {
                    'Content-Type': 'application/x-www-form-urlencoded'
                }
            }).catch(() => {
                // Ignore errors during page unload
            });
        }
    }
}

// Detect tab/window close (primary method)
window.addEventListener('beforeunload', function(e) {
    if (!isNavigating) {
        clearSessionOnClose();
    }
});

// Detect page unload (when tab is actually closed)
window.addEventListener('pagehide', function(e) {
    if (!isNavigating) {
        clearSessionOnClose();
    }
    // Reset navigation flag after a delay
    setTimeout(() => {
        isNavigating = false;
    }, 100);
});
*/

// ============================================
// AUTO LOGOUT DISABLED - Users logout manually only
// ============================================
// Auto logout functionality has been disabled per user request.
// Users will only be logged out when they explicitly click the logout button.
// Session lifetime is managed by backend (8-24 hours) as a security measure.

// Note: The following code is commented out to disable auto-logout
// Users can still logout manually via the logout button

/*
let inactivityTimer = null;
const INACTIVITY_TIMEOUT = 5 * 60 * 1000; // 5 minutes in milliseconds

// Function to reset inactivity timer
function resetInactivityTimer() {
    // Clear existing timer
    if (inactivityTimer) {
        clearTimeout(inactivityTimer);
    }
    
    // Only set timer if user is logged in
    if (isLoggedIn) {
        // Set logout timer (5 minutes)
        inactivityTimer = setTimeout(() => {
            performAutoLogout();
        }, INACTIVITY_TIMEOUT);
    }
}

// Function to perform automatic logout
function performAutoLogout() {
    if (!isLoggedIn) return;
    
    // Clear session on server
    fetch('/auth/logout-session', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/x-www-form-urlencoded'
        }
    }).then(() => {
        // Redirect to login page
        window.location.href = '/auth/login';
    }).catch(() => {
        // Even if request fails, redirect to login
        window.location.href = '/auth/login';
    });
}

// Track user activity events
const activityEvents = [
    'mousedown',
    'mousemove',
    'keypress',
    'scroll',
    'touchstart',
    'click'
];

// Reset timer on any activity
activityEvents.forEach(event => {
    document.addEventListener(event, function() {
        if (isLoggedIn) {
            resetInactivityTimer();
        }
    }, { passive: true });
});

// Also track visibility change (when user switches tabs)
document.addEventListener('visibilitychange', function() {
    if (document.visibilityState === 'visible' && isLoggedIn) {
        // User came back to tab, reset timer
        resetInactivityTimer();
    }
});

// Initialize inactivity timer when page loads (if logged in)
if (isLoggedIn) {
    resetInactivityTimer();
}

// Make resetInactivityTimer available globally
window.resetInactivityTimer = resetInactivityTimer;
*/

// Export functions for global use
window.QuickCare = {
    showNotification,
    validateEmail,
    formatPhoneNumber
};
