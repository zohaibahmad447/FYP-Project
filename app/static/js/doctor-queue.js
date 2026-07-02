// Doctor Queue Dashboard - Live Status & Actions
// ================================================

let appointmentId = null;
let pollingInterval = null;

// Initialize on page load
document.addEventListener('DOMContentLoaded', function () {
    // Get appointment ID from hidden input
    const appointmentIdInput = document.getElementById('appointment-id');
    if (appointmentIdInput) {
        appointmentId = appointmentIdInput.value;

        // Initial load
        fetchQueueStatus();

        // Poll every 5 seconds
        pollingInterval = setInterval(fetchQueueStatus, 5000);
    }

    // Start consultation button
    const startBtn = document.getElementById('start-consultation-btn');
    if (startBtn) {
        startBtn.addEventListener('click', startConsultation);

        // Initial check for time restriction
        checkTimeRestriction();

        // Update countdown every second
        setInterval(checkTimeRestriction, 1000);
    }

    // Mark No-Show button
    const markNoShowBtn = document.getElementById('mark-no-show-btn');
    if (markNoShowBtn) {
        markNoShowBtn.addEventListener('click', handleNoShow);
    }
});

// Check if we are within the 30-minute window
function checkTimeRestriction() {
    const startBtn = document.getElementById('start-consultation-btn');
    const noticeEl = document.getElementById('early-access-notice');
    const countdownEl = document.getElementById('countdown-display');
    const hintEl = document.getElementById('action-hint');
    const appointmentTimeInput = document.getElementById('appointment-datetime');

    if (!startBtn || !appointmentTimeInput) return;

    // Parse appointment time
    const appointmentTime = new Date(appointmentTimeInput.value);
    const now = new Date();

    // Calculate difference in minutes
    const diffMs = appointmentTime - now;
    const diffMins = Math.floor(diffMs / 60000);

    // 30 minute window (in milliseconds)
    const windowMs = 30 * 60 * 1000;

    // If more than 30 mins remaining
    if (diffMs > windowMs) {
        // DISABLE BUTTON
        startBtn.disabled = true;
        startBtn.style.opacity = '0.6';
        startBtn.style.cursor = 'not-allowed';
        startBtn.title = "Consultation opens 30 minutes before appointment";

        // Show notice
        if (noticeEl) noticeEl.style.display = 'block';
        if (hintEl) hintEl.style.display = 'none';

        // Update countdown
        const timeToOpen = diffMs - windowMs;
        const hours = Math.floor(timeToOpen / (1000 * 60 * 60));
        const minutes = Math.floor((timeToOpen % (1000 * 60 * 60)) / (1000 * 60));
        const seconds = Math.floor((timeToOpen % (1000 * 60)) / 1000);

        if (countdownEl) {
            countdownEl.textContent = `${hours.toString().padStart(2, '0')}:${minutes.toString().padStart(2, '0')}:${seconds.toString().padStart(2, '0')}`;
        }
    } else {
        // ENABLE BUTTON (We are within 30 mins or past time)
        // Only enable if not already processing (loading state)
        if (!startBtn.innerHTML.includes('fa-spinner')) {
            startBtn.disabled = false;
            startBtn.style.opacity = '1';
            startBtn.style.cursor = 'pointer';
            startBtn.title = "";
        }

        // Hide notice
        if (noticeEl) noticeEl.style.display = 'none';
        if (hintEl) hintEl.style.display = 'block';
    }
}

// Fetch queue status from API
async function fetchQueueStatus() {
    try {
        const response = await fetch(`/video/queue-status/${appointmentId}`);

        if (!response.ok) {
            console.error('Failed to fetch queue status:', response.status);
            return;
        }

        const data = await response.json();
        updateUI(data);

    } catch (error) {
        console.error('Error fetching queue status:', error);
    }
}

// Update UI with queue data
function updateUI(data) {
    // Patient Info
    document.getElementById('patient-name').textContent = data.patient.name;
    document.getElementById('patient-email').textContent = data.patient.email;

    // Appointment Details
    document.getElementById('appointment-time').textContent = data.timing.appointment_time;
    document.getElementById('appointment-type').textContent =
        data.appointment.type === 'video' ? 'Video Consultation' : 'Physical';

    // Time Until Appointment
    const minutesUntil = data.timing.minutes_until_appointment;
    const timeUntilEl = document.getElementById('time-until');

    if (minutesUntil > 0) {
        timeUntilEl.textContent = `${minutesUntil} mins`;
        timeUntilEl.style.color = '#059669';
    } else if (minutesUntil === 0) {
        timeUntilEl.textContent = 'Now';
        timeUntilEl.style.color = '#047857';
    } else {
        timeUntilEl.textContent = `${Math.abs(minutesUntil)} mins ago`;
        timeUntilEl.style.color = '#d97706';
    }

    // Status Badge
    const statusBadge = document.getElementById('status-badge');
    const statusText = document.getElementById('status-text');

    if (data.status.patient_waiting) {
        statusText.textContent = 'Patient can join waiting room';
        statusBadge.style.borderColor = 'rgba(16, 185, 129, 0.45)';
        statusBadge.style.background = '#ecfdf5';
        statusText.style.color = '#047857';
    } else {
        statusText.textContent = 'Waiting room not yet open';
        statusBadge.style.borderColor = '#fcd34d';
        statusBadge.style.background = '#fffbeb';
        statusText.style.color = '#b45309';
    }

    // Medical Notes
    document.getElementById('disease-category').textContent =
        data.appointment.disease_category || 'Not specified';
    document.getElementById('symptoms').textContent =
        data.appointment.symptoms || 'Not specified';

    // Additional Notes (if present)
    if (data.appointment.notes) {
        document.getElementById('notes').textContent = data.appointment.notes;
        document.getElementById('notes-container').style.display = 'flex';
    }
}

// Initialize Socket.IO
const socket = io();

// Start consultation - Open video call directly (no redirect)
function startConsultation() {
    // Stop polling
    if (pollingInterval) {
        clearInterval(pollingInterval);
    }

    // Add loading state to button
    const btn = document.getElementById('start-consultation-btn');
    btn.disabled = true;
    btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> <span>Starting Call...</span>';

    // Emit start_call event to signal patient
    console.log(`Starting call for appointment ${appointmentId}...`);
    socket.emit('start_call', { appointment_id: appointmentId });

    // Wait for socket event to be sent, then start video call directly
    setTimeout(() => {
        // Check if initVideoCall function exists (from video-call.js)
        if (typeof initVideoCall === 'function') {
            initVideoCall(appointmentId);
        } else {
            console.error('initVideoCall function not found! Make sure video-call.js is loaded.');
            // Fallback: redirect if video-call.js is not loaded
            window.location.href = `/appointments/${appointmentId}?autostart=true`;
        }
    }, 500);
}

// Cleanup on page unload
window.addEventListener('beforeunload', function () {
    if (pollingInterval) {
        clearInterval(pollingInterval);
    }
});

// Handle Mark No-Show action
async function handleNoShow() {
    if (!confirm('Are you sure you want to mark this appointment as a Patient No-Show? A penalty fee will be applied.')) {
        return;
    }

    const btn = document.getElementById('mark-no-show-btn');
    const originalContent = btn.innerHTML;
    btn.disabled = true;
    btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> <span>Processing...</span>';

    try {
        const response = await fetch(`/video/mark-no-show/${appointmentId}`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            }
        });

        const data = await response.json();
        if (response.ok) {
            alert(data.message || 'Appointment marked as No-Show.');
            window.location.href = '/doctor/appointments'; // Redirect to doctor appointments list
        } else {
            alert(data.error || 'Failed to mark as No-Show.');
            btn.disabled = false;
            btn.innerHTML = originalContent;
        }
    } catch (err) {
        console.error('Error marking no-show:', err);
        alert('An error occurred. Please try again.');
        btn.disabled = false;
        btn.innerHTML = originalContent;
    }
}
