// Agora Video Call Implementation
let agoraClient = null;
let localAudioTrack = null;
let localVideoTrack = null;
let remoteUsers = {};
let isAudioMuted = false;
let isVideoOff = false;
let currentAppointmentId = null; // Store current appointment ID for Leave Lobby button
/** Last subscribed remote audio (1:1 calls); used for the "their voice" slider */
let primaryRemoteAudioTrack = null;
let primaryRemoteAudioUid = null;

function buildMicAudioConstraints() {
    const cfg = {
        echoCancellation: true,
        noiseSuppression: true,
        autoGainControl: true,
    };
    try {
        const c = navigator.mediaDevices && navigator.mediaDevices.getSupportedConstraints
            ? navigator.mediaDevices.getSupportedConstraints()
            : null;
        if (c && c.channelCount) {
            cfg.channelCount = 1;
        }
    } catch (e) {
        /* ignore */
    }
    return cfg;
}

function getRemoteVoiceVolumeFromUI() {
    const el = document.getElementById('remote-voice-volume');
    if (!el) return 100;
    const v = parseInt(el.value, 10);
    return Number.isFinite(v) ? Math.max(0, Math.min(100, v)) : 100;
}

function applyRemoteAudioPlaybackVolume(track) {
    if (!track || typeof track.setVolume !== 'function') return;
    track.setVolume(getRemoteVoiceVolumeFromUI());
}

const AGORA_SDK_PATH = '/static/vendor/agora/AgoraRTC_N-4.19.0.js';

function ensureAgoraSdkReady(timeoutMs) {
    return new Promise((resolve, reject) => {
        if (typeof AgoraRTC !== 'undefined') {
            resolve();
            return;
        }
        const deadline = Date.now() + timeoutMs;
        const poll = () => {
            if (typeof AgoraRTC !== 'undefined') {
                resolve();
                return;
            }
            if (Date.now() >= deadline) {
                reject(new Error('AgoraRTC load timeout'));
                return;
            }
            setTimeout(poll, 100);
        };
        poll();
    });
}

function getAgoraSdkUrl() {
    return AGORA_SDK_PATH;
}

function injectAgoraSdk() {
    return new Promise((resolve, reject) => {
        if (typeof AgoraRTC !== 'undefined') {
            resolve();
            return;
        }
        let tag = document.querySelector('script[data-agora-sdk]');
        if (tag && tag.src && tag.src.indexOf('/static/vendor/agora/') === -1) {
            tag.remove();
            tag = null;
        }
        if (!tag) {
            tag = document.createElement('script');
            tag.src = getAgoraSdkUrl();
            tag.dataset.agoraSdk = '1';
            document.head.appendChild(tag);
        }
        tag.addEventListener('load', () => {
            if (typeof AgoraRTC !== 'undefined') resolve();
            else reject(new Error('AgoraRTC missing after script load'));
        }, { once: true });
        tag.addEventListener('error', () => reject(new Error('Failed to load Agora SDK')), { once: true });
    });
}

async function waitForAgoraSdk() {
    try {
        await ensureAgoraSdkReady(8000);
    } catch (firstWaitErr) {
        console.warn('Agora SDK not ready yet, injecting:', firstWaitErr.message);
        await injectAgoraSdk();
        await ensureAgoraSdkReady(30000);
    }
}

// Initialize video call
async function initVideoCall(appointmentId) {
    try {
        // Store appointment ID globally for Leave Lobby button
        currentAppointmentId = appointmentId;

        cloudRecordingRequested = false;
        isVideoOff = false;
        primaryRemoteAudioTrack = null;
        primaryRemoteAudioUid = null;
        const micBtnReset = document.getElementById('toggle-mic');
        if (micBtnReset) {
            micBtnReset.classList.remove('muted');
            micBtnReset.innerHTML = '<i class="fas fa-microphone"></i>';
        }
        const camBtnReset = document.getElementById('toggle-camera');
        if (camBtnReset) {
            camBtnReset.classList.remove('off');
            camBtnReset.innerHTML = '<i class="fas fa-video"></i>';
        }
        const remoteVolReset = document.getElementById('remote-voice-volume');
        if (remoteVolReset) remoteVolReset.value = '100';

        // Wait for Agora SDK (patient may click before external/slow script finishes)
        try {
            await waitForAgoraSdk();
        } catch (sdkErr) {
            alert('Video call library (AgoraRTC) failed to load. Please refresh the page and try again.');
            console.error('AgoraRTC load failed:', sdkErr);
            return;
        }

        // Show modal
        const modal = document.getElementById('video-call-modal');
        modal.classList.add('active');

        // Update status
        updateConnectionStatus('connecting');

        // Get Agora token from backend
        const response = await fetch(`/video/token/${appointmentId}`);
        const contentType = response.headers.get('content-type') || '';
        let data = null;

        if (contentType.includes('application/json')) {
            data = await response.json();
        }

        if (!response.ok) {
            if (data && data.error === 'Too early to join') {
                const minutes = data.minutes_remaining;
                const canJoinAt = data.can_join_at;
                alert(`⏰ Too Early!\n\nThe Virtual Waiting Room opens at ${canJoinAt}\n\nPlease wait ${minutes} minute${minutes !== 1 ? 's' : ''} before joining.`);
                updateConnectionStatus('failed');
                const modal = document.getElementById('video-call-modal');
                if (modal) modal.classList.remove('active');
                return;
            }

            if (data && (data.error === 'Link expired' || response.status === 410)) {
                const expiredAt = data.expired_at || 'the scheduled time';
                alert(`🚫 Link Expired\n\nThis video call link expired at ${expiredAt}.\n\nThe appointment window has closed. Please contact support if you need assistance.`);
                updateConnectionStatus('failed');
                const modal = document.getElementById('video-call-modal');
                if (modal) modal.classList.remove('active');
                return;
            }

            const errMsg = (data && data.error) ? data.error : `Server returned error (${response.status})`;
            throw new Error(errMsg);
        }

        if (!data) {
            throw new Error('Invalid server response');
        }

        const { token, channel, uid, appId, waiting_room } = data;

        console.log('✅ Token received:', { channel, uid, appId: appId.substring(0, 8) + '...' });

        // Create Agora client with optimized settings for low latency
        console.log('4. Creating Agora client...');
        agoraClient = AgoraRTC.createClient({
            mode: "rtc",  // Real-time communication mode
            codec: "vp8"  // VP8 handles low bandwidth better than H.264 (less blocking)
        });

        console.log('✅ Agora client created');


        // Set up event listeners
        agoraClient.on("user-published", handleUserPublished);
        agoraClient.on("user-unpublished", handleUserUnpublished);
        agoraClient.on("user-left", handleUserLeft);

        console.log('Event listeners set up');

        // Join channel
        console.log('Attempting to join channel:', channel);
        await agoraClient.join(appId, channel, token, uid);

        console.log('✅ Successfully joined channel as UID:', uid);

        console.log('Creating microphone and camera tracks...');
        [localAudioTrack, localVideoTrack] = await AgoraRTC.createMicrophoneAndCameraTracks(
            buildMicAudioConstraints(),
            // Video: Priority on MOTION (smoothness) over clarity
            {
                encoderConfig: {
                    width: 640,             // VGA is standard for mobile calls
                    height: 480,
                    frameRate: 15,          // 15fps is plenty for talking
                    bitrateMin: 200,        // Very low floor to prevent freezing
                    bitrateMax: 600         // Cap bitrate to prevent congestion
                },
                optimizationMode: "motion"  // Prioritize smoothness (no freezing)
            }
        );


        console.log('✅ Local tracks created');
        // Do not call localAudioTrack.setVolume(0): in many browsers/SDK builds it
        // attenuates or silences the published mic so the other party cannot hear you.
        // Echo is handled via echoCancellation + headset when possible.

        // Play local video
        localVideoTrack.play("local-player");

        console.log('✅ Local video playing');

        // Check if we're in Waiting Room or Live Call
        if (waiting_room && waiting_room.is_waiting) {
            // WAITING ROOM MODE: Show beautiful waiting UI
            updateConnectionStatus('waiting');
            showWaitingRoomUI(waiting_room);
            console.log(`⏳ Entered Virtual Waiting Room. Appointment starts at ${waiting_room.appointment_time}`);
            console.log('⏳ Patient will remain in waiting room until doctor starts the call');

            // DO NOT PUBLISH yet. Wait for doctor to start call.
        } else {
            // LIVE CALL MODE: Normal video call (doctor already started)
            await publishLocalTracks();
        }

        // Notify backend (optional) - ONLY DOCTORS SHOULD FIRE THIS
        if (!waiting_room || !waiting_room.is_waiting) {
            fetch(`/video/start/${appointmentId}`, { method: 'POST' })
                .catch(err => console.error("Could not notify backend of call start:", err));
        }

        // --- NO-SHOW LOGIC ---
        // If this is the doctor, start polling for no-show status
        if (!waiting_room || !waiting_room.is_waiting) {
            startNoShowPolling(appointmentId);
        }

    } catch (error) {
        console.error('❌ Video call error:', error);
        console.error('Error name:', error.name);
        console.error('Error code:', error.code);
        console.error('Error message:', error.message);
        updateConnectionStatus('failed');
        showErrorModal(error.message, 'Technical details: ' + (error.stack || 'Check browser console (F12)'));
        const modal = document.getElementById('video-call-modal');
        if (modal) modal.classList.remove('active');
        const startBtn = document.getElementById('start-consultation-btn');
        if (startBtn) {
            startBtn.disabled = false;
            startBtn.innerHTML = '<i class="fas fa-play-circle"></i> <span>Start Consultation</span>';
        }
    }
}

// Handle remote user publishing
async function handleUserPublished(user, mediaType) {
    console.log(`📥 Remote user ${user.uid} published ${mediaType}`);

    remoteUsers[user.uid] = user;
    await agoraClient.subscribe(user, mediaType);
    console.log(`✅ Subscribed to ${mediaType}`);

    // Stop no-show polling since someone joined
    stopNoShowPolling();

    // FOOLPROOF FALLBACK: If we receive the doctor's stream but are still stuck in the waiting room, force the transition immediately!
    const waitingOverlay = document.getElementById('waiting-room-overlay');
    if (waitingOverlay && waitingOverlay.style.display !== 'none') {
        console.log("🚀 Receiving doctor's live stream! Forcing transition out of waiting room...");
        if (typeof window.onDoctorStartedCall === 'function') {
            window.onDoctorStartedCall();
        } else {
            hideWaitingRoomUI();
            updateConnectionStatus('connected');
            if (localAudioTrack && localVideoTrack) {
                agoraClient.publish([localAudioTrack, localVideoTrack])
                    .then(() => maybeStartCloudRecording())
                    .catch(e => console.error(e));
            }
        }
    }

    if (mediaType === "video") {
        const remotePlayer = document.getElementById("remote-player");
        if (remotePlayer) {
            remotePlayer.style.display = 'block';
            remotePlayer.style.opacity = '1';
            remotePlayer.style.width = '100%';
            remotePlayer.style.height = '100%';
            remotePlayer.innerHTML = '';

            try {
                user.videoTrack.play(remotePlayer);
                console.log(`✅ Remote video playing for user ${user.uid}`);
                maybeStartCloudRecording();
            } catch (err) {
                console.error(`❌ Failed to play remote video: ${err.message}`);
                setTimeout(() => {
                    try {
                        user.videoTrack.play(remotePlayer);
                        console.log(`✅ Retry: Remote video playing for user ${user.uid}`);
                        maybeStartCloudRecording();
                    } catch (retryErr) {
                        console.error(`❌ Retry failed: ${retryErr.message}`);
                    }
                }, 1000);
            }
        } else {
            console.error('❌ Remote player container not found!');
        }
    }

    if (mediaType === "audio") {
        primaryRemoteAudioTrack = user.audioTrack;
        primaryRemoteAudioUid = user.uid;
        applyRemoteAudioPlaybackVolume(user.audioTrack);
        user.audioTrack.play();
    }
}

// Handle remote user unpublishing
function handleUserUnpublished(user, mediaType) {
    if (mediaType === "video") {
        const remotePlayer = document.getElementById("remote-player");
        if (remotePlayer) remotePlayer.innerHTML = '';
    }
    if (mediaType === "audio" && user.audioTrack) {
        try {
            user.audioTrack.stop();
        } catch (e) {
            console.warn('Remote audio stop:', e);
        }
        if (primaryRemoteAudioUid === user.uid) {
            primaryRemoteAudioTrack = null;
            primaryRemoteAudioUid = null;
        }
    }
}

// Handle remote user leaving
function handleUserLeft(user) {
    delete remoteUsers[user.uid];
    if (primaryRemoteAudioUid === user.uid) {
        primaryRemoteAudioTrack = null;
        primaryRemoteAudioUid = null;
    }
}

// Toggle microphone
function toggleMic() {
    if (!localAudioTrack) return;

    isAudioMuted = !isAudioMuted;
    localAudioTrack.setEnabled(!isAudioMuted);

    const btn = document.getElementById('toggle-mic');
    if (isAudioMuted) {
        btn.classList.add('muted');
        btn.innerHTML = '<i class="fas fa-microphone-slash"></i>';
    } else {
        btn.classList.remove('muted');
        btn.innerHTML = '<i class="fas fa-microphone"></i>';
    }
}

// Toggle camera
function toggleCamera() {
    if (!localVideoTrack) return;

    isVideoOff = !isVideoOff;
    localVideoTrack.setEnabled(!isVideoOff);

    const btn = document.getElementById('toggle-camera');
    if (isVideoOff) {
        btn.classList.add('off');
        btn.innerHTML = '<i class="fas fa-video-slash"></i>';
    } else {
        btn.classList.remove('off');
        btn.innerHTML = '<i class="fas fa-video"></i>';
    }
}

// Leave and cleanup
async function leaveCall() {
    try {
        console.log('Leaving video call...');

        // Stop no-show polling if active
        stopNoShowPolling();

        const apptId = currentAppointmentId;
        if (apptId) {
            try {
                await fetch(`/video/end/${apptId}`, {
                    method: 'POST',
                    credentials: 'same-origin',
                    headers: { Accept: 'application/json' },
                });
            } catch (e) {
                console.warn('Could not notify server that video ended:', e);
            }
        }

        // Stop and close local tracks
        primaryRemoteAudioTrack = null;
        primaryRemoteAudioUid = null;

        if (localAudioTrack) {
            localAudioTrack.stop();
            localAudioTrack.close();
            localAudioTrack = null;
            console.log('Local audio track closed');
        }
        if (localVideoTrack) {
            localVideoTrack.stop();
            localVideoTrack.close();
            localVideoTrack = null;
            console.log('Local video track closed');
        }

        // Leave channel only if we're actually connected or connecting
        if (agoraClient) {
            try {
                // Check connection state before leaving
                const connectionState = agoraClient.connectionState;
                console.log('Current connection state:', connectionState);

                if (connectionState === 'CONNECTED' || connectionState === 'CONNECTING') {
                    await agoraClient.leave();
                    console.log('✅ Successfully left channel');
                } else {
                    console.log('Skipping leave - not in CONNECTED/CONNECTING state');
                }
            } catch (leaveError) {
                // Ignore leave errors - we're cleaning up anyway
                console.warn('Error during leave (ignored):', leaveError.message);
            }
            agoraClient = null;
        }

        // Close modal
        const modal = document.getElementById('video-call-modal');
        if (modal) {
            modal.classList.remove('active');
        }

        console.log('✅ Video call ended and cleaned up');

        // Reset UI State (Re-enable Start Button if on Doctor Queue)
        const startBtn = document.getElementById('start-consultation-btn');
        if (startBtn) {
            startBtn.disabled = false;
            startBtn.innerHTML = '<i class="fas fa-play-circle"></i> <span>Start Consultation</span>';
        }

        // Redirect based on role
        if (window.location.pathname.includes('/queue')) {
            // If doctor in lobby, redirect to appointment details
            window.location.href = '/appointments/' + currentAppointmentId;
        } else {
            // If patient (or other), reload to refresh state
            window.location.reload();
        }

    } catch (error) {
        console.error('Error in leaveCall:', error);
        // Force cleanup even if there's an error
        localAudioTrack = null;
        localVideoTrack = null;
        agoraClient = null;
        const modal = document.getElementById('video-call-modal');
        if (modal) modal.classList.remove('active');
        window.location.reload();
    }
}

// Update connection status UI
// Show custom error modal
function showErrorModal(message, details = null) {
    // Check if modal already exists
    let errorModal = document.getElementById('video-error-modal');

    if (!errorModal) {
        errorModal = document.createElement('div');
        errorModal.id = 'video-error-modal';
        errorModal.className = 'video-error-modal';
        errorModal.innerHTML = `
            <div class="video-error-content">
                <div class="video-error-icon">
                    <i class="fas fa-exclamation-circle"></i>
                </div>
                <h3 class="video-error-title">Connection Issue</h3>
                <p class="video-error-message" id="video-error-text"></p>
                <div class="video-error-details" id="video-error-details" style="display: none;"></div>
                <button class="video-error-btn" onclick="document.getElementById('video-error-modal').style.display='none'">
                    Got it
                </button>
            </div>
        `;
        document.body.appendChild(errorModal);
    }

    // Parse technical errors into user-friendly messages
    let userMessage = message;
    let technicalDetails = details;

    // Check for JSON error string (like the one in user screenshot)
    if (typeof message === 'string' && message.includes('{') && message.includes('}')) {
        try {
            // Extract JSON part if mixed with text
            const jsonMatch = message.match(/\{.*\}/s);
            if (jsonMatch) {
                const errorObj = JSON.parse(jsonMatch[0]);
                if (errorObj.error) {
                    userMessage = errorObj.error;

                    // Specific handling for "Too early" error
                    if (userMessage.includes('Too early')) {
                        userMessage = `You can join the call at ${errorObj.can_join_at || 'the scheduled time'}.`;
                    }
                }
            }
        } catch (e) {
            // If parsing fails, stick to original message but clean it up
            userMessage = message.replace(/Server returned error \(\d+\):/, '').trim();
        }
    }

    // Set text
    document.getElementById('video-error-text').textContent = userMessage;

    // Set details only if relevant and not already covered
    const detailsEl = document.getElementById('video-error-details');
    if (technicalDetails && technicalDetails !== userMessage) {
        detailsEl.textContent = technicalDetails;
        detailsEl.style.display = 'block';
    } else {
        detailsEl.style.display = 'none';
    }

    // Show modal with animation
    errorModal.style.display = 'flex';
}

function updateConnectionStatus(status) {
    const statusEl = document.getElementById('connection-status');
    statusEl.className = 'connection-status ' + status;

    const messages = {
        'connecting': 'Connecting...',
        'waiting': 'Virtual Waiting Room',
        'connected': 'Connected',
        'failed': 'Connection Failed'
    };

    statusEl.textContent = messages[status] || status;
}

// Show Waiting Room UI
function showWaitingRoomUI(waitingInfo) {
    // Create waiting room overlay
    const modal = document.getElementById('video-call-modal');

    // Add waiting room elements
    let waitingOverlay = document.getElementById('waiting-room-overlay');
    if (!waitingOverlay) {
        waitingOverlay = document.createElement('div');
        waitingOverlay.id = 'waiting-room-overlay';
        waitingOverlay.className = 'waiting-room-overlay';
        waitingOverlay.innerHTML = `
            <div class="waiting-room-content">
                <div class="waiting-pulse"></div>
                <div class="waiting-icon">
                    <i class="fas fa-user-md"></i>
                </div>
                <h2 class="waiting-title">Virtual Waiting Room</h2>
                <p class="waiting-message">Waiting for <strong>${waitingInfo.doctor_name}</strong> to join...</p>
                <p class="waiting-time">Appointment starts at <strong>${waitingInfo.appointment_time}</strong></p>
                
                <div class="waiting-timer" id="waiting-timer">
                    --:--
                </div>
                
                <div id="waiting-room-video-container"></div>
                
                <div class="waiting-tips">
                    <p><i class="fas fa-check-circle"></i> Your camera and microphone are ready</p>
                    <p><i class="fas fa-info-circle"></i> Check your camera view above</p>
                </div>
                
                <button id="leave-lobby-btn" class="leave-lobby-btn">
                    <i class="fas fa-sign-out-alt"></i> Leave Lobby
                </button>
            </div>
        `;
        modal.appendChild(waitingOverlay);

        // Add event listener for Leave Lobby button
        const leaveLobbyBtn = document.getElementById('leave-lobby-btn');
        if (leaveLobbyBtn) {
            leaveLobbyBtn.addEventListener('click', function () {
                if (confirm('Are you sure you want to leave the waiting room?')) {
                    // Clean up media tracks before leaving
                    if (localVideoTrack) {
                        localVideoTrack.stop();
                        localVideoTrack.close();
                    }
                    if (localAudioTrack) {
                        localAudioTrack.stop();
                        localAudioTrack.close();
                    }
                    // Redirect to appointment details
                    window.location.href = `/appointments/${currentAppointmentId}`;
                }
            });
        }
    }

    waitingOverlay.style.display = 'flex';

    // Play local video in the waiting room container
    if (localVideoTrack) {
        localVideoTrack.play('waiting-room-video-container');
    }

    // Update timer every second (MM:SS format)
    let totalSeconds = waitingInfo.minutes_remaining * 60;

    function updateTimerDisplay() {
        const minutes = Math.floor(totalSeconds / 60);
        const seconds = totalSeconds % 60;
        const timerEl = document.getElementById('waiting-timer');
        if (timerEl) {
            timerEl.textContent = `${minutes.toString().padStart(2, '0')}:${seconds.toString().padStart(2, '0')}`;
        }
    }

    updateTimerDisplay(); // Initial call

    const timerInterval = setInterval(() => {
        totalSeconds--;
        if (totalSeconds >= 0) {
            updateTimerDisplay();
        } else {
            clearInterval(timerInterval);
            document.getElementById('waiting-timer').textContent = "Starting...";
        }
    }, 1000); // Update every second

    // Hide remote player during waiting
    const remotePlayer = document.getElementById('remote-player');
    if (remotePlayer) {
        remotePlayer.style.opacity = '0';
    }
}

let cloudRecordingRequested = false;

async function maybeStartCloudRecording() {
    const id = currentAppointmentId;
    if (!id || cloudRecordingRequested) return;
    cloudRecordingRequested = true;
    try {
        const response = await fetch(`/video/recording-start/${id}`, {
            method: 'POST',
            credentials: 'same-origin',
            headers: { Accept: 'application/json' },
        });
        const data = await response.json().catch(() => ({}));
        console.log('Cloud recording start:', response.status, data);
        if (!response.ok && !data.success) {
            cloudRecordingRequested = false;
        }
    } catch (err) {
        console.warn('Cloud recording start failed:', err);
        cloudRecordingRequested = false;
    }
}

// Publish local tracks to join the live call
async function publishLocalTracks() {
    try {
        console.log('Publishing local tracks...');
        if (localAudioTrack && localVideoTrack) {
            await agoraClient.publish([localAudioTrack, localVideoTrack]);
            console.log('✅ Local tracks published successfully');
            maybeStartCloudRecording();
        } else {
            console.warn('⚠️ Local tracks not ready yet, skipping publish');
        }
        updateConnectionStatus('connected');
    } catch (err) {
        console.error('Failed to publish local tracks:', err);
    }
}

// Hide Waiting Room UI
function hideWaitingRoomUI() {
    const waitingOverlay = document.getElementById('waiting-room-overlay');
    if (waitingOverlay) {
        // Fade out animation
        waitingOverlay.style.opacity = '0';
        setTimeout(() => {
            waitingOverlay.style.display = 'none';
            waitingOverlay.remove();

            // Switch local video back to main container
            if (localVideoTrack) {
                localVideoTrack.play('local-player');
            }
        }, 500);
    }

    // Show remote player
    const remotePlayer = document.getElementById('remote-player');
    if (remotePlayer) {
        remotePlayer.style.opacity = '1';
    }
}

// GLOBAL: Called by Socket.IO when doctor starts the call
// This transitions the patient from waiting room to live call
// GLOBAL: Called by Socket.IO when doctor starts the call
// This transitions the patient from waiting room to live call
window.onDoctorStartedCall = async function () {
    console.log('🎬 Doctor started the call! Transitioning from waiting room...');

    try {
        // Publish local tracks now that the call is live
        if (localAudioTrack && localVideoTrack) {
            console.log('Publishing local tracks...');
            await agoraClient.publish([localAudioTrack, localVideoTrack]);
            console.log('✅ Local tracks published successfully');
            maybeStartCloudRecording();
        }
    } catch (e) {
        console.error('Error publishing tracks on transition:', e);
    }

    updateConnectionStatus('connected');
    hideWaitingRoomUI();
};

// Get appointment ID from URL
function getAppointmentIdFromURL() {
    const pathParts = window.location.pathname.split('/');
    return pathParts[pathParts.length - 1];
}

// Initialize button listeners
document.addEventListener('DOMContentLoaded', function () {
    const joinBtn = document.getElementById('join-video-call-btn');
    if (joinBtn) {
        const originalHtml = joinBtn.innerHTML;
        joinBtn.disabled = true;
        joinBtn.innerHTML = '<i class="fas fa-spinner fa-spin me-2"></i>Loading video...';
        waitForAgoraSdk()
            .then(() => {
                joinBtn.disabled = false;
                joinBtn.innerHTML = originalHtml;
            })
            .catch(() => {
                joinBtn.disabled = false;
                joinBtn.innerHTML = originalHtml;
            });

        joinBtn.addEventListener('click', function () {
            const appointmentId = this.dataset.appointmentId;
            initVideoCall(appointmentId);
        });

        // Auto-start video call if URL parameter is set
        const urlParams = new URLSearchParams(window.location.search);
        if (urlParams.get('autostart') === 'true') {
            // Small delay to ensure page is fully loaded
            setTimeout(() => {
                console.log('Auto-starting video call from doctor queue...');
                joinBtn.click();
                // Clean up URL (remove autostart parameter)
                const cleanUrl = window.location.pathname;
                window.history.replaceState({}, document.title, cleanUrl);
            }, 500);
        }
    }

    const toggleMicBtn = document.getElementById('toggle-mic');
    if (toggleMicBtn) {
        toggleMicBtn.addEventListener('click', toggleMic);
    }

    const remoteVoiceVol = document.getElementById('remote-voice-volume');
    if (remoteVoiceVol) {
        remoteVoiceVol.addEventListener('input', function () {
            applyRemoteAudioPlaybackVolume(primaryRemoteAudioTrack);
        });
    }

    const toggleCameraBtn = document.getElementById('toggle-camera');
    if (toggleCameraBtn) {
        toggleCameraBtn.addEventListener('click', toggleCamera);
    }

    const endCallBtn = document.getElementById('end-call-btn');
    if (endCallBtn) {
        endCallBtn.addEventListener('click', leaveCall);
    }

    window.addEventListener('beforeunload', () => {
        const id = currentAppointmentId;
        if (!id) return;
        try {
            fetch(`/video/end/${id}`, { method: 'POST', credentials: 'same-origin', keepalive: true });
        } catch (e) {
            /* ignore */
        }
    });

    // In-Call No-Show button listener
    const noShowBtn = document.getElementById('in-call-no-show-btn');
    if (noShowBtn) {
        noShowBtn.addEventListener('click', handleInCallNoShow);
    }
});

// --- In-Call No-Show Logic ---
let noShowPollingInterval = null;

function startNoShowPolling(appointmentId) {
    const noShowContainer = document.getElementById('in-call-no-show-container');
    const noShowBtn = document.getElementById('in-call-no-show-btn');
    const noShowHint = document.getElementById('in-call-no-show-hint');

    if (!noShowContainer || !noShowBtn) return;

    // Clear any existing polling
    stopNoShowPolling();

    // Poll every 5 seconds
    noShowPollingInterval = setInterval(async () => {
        // Stop polling if a remote user has joined
        if (Object.keys(remoteUsers).length > 0) {
            noShowContainer.style.display = 'none';
            stopNoShowPolling();
            return;
        }

        try {
            const response = await fetch(`/video/queue-status/${appointmentId}`);
            if (!response.ok) return;

            const data = await response.json();

            if (data.status && data.status.hasOwnProperty('can_mark_no_show')) {
                if (data.status.no_show_reason.includes('Grace period active')) {
                    noShowContainer.style.display = 'none';
                } else {
                    noShowContainer.style.display = 'block';
                    if (data.status.can_mark_no_show) {
                        noShowBtn.disabled = false;
                        noShowBtn.style.opacity = '1';
                        noShowBtn.style.cursor = 'pointer';
                        noShowHint.textContent = "2m grace elapsed. You may mark no-show.";
                        noShowHint.style.color = '#10b981'; // Green
                    } else {
                        noShowBtn.disabled = true;
                        noShowBtn.style.opacity = '0.5';
                        noShowBtn.style.cursor = 'not-allowed';
                        noShowHint.textContent = data.status.no_show_reason;
                        noShowHint.style.color = '#ef4444'; // Red
                    }
                }
            }
        } catch (err) {
            console.error('Error polling no-show status:', err);
        }
    }, 5000);
}

function stopNoShowPolling() {
    if (noShowPollingInterval) {
        clearInterval(noShowPollingInterval);
        noShowPollingInterval = null;
    }
    const noShowContainer = document.getElementById('in-call-no-show-container');
    if (noShowContainer) {
        noShowContainer.style.display = 'none';
    }
}

async function handleInCallNoShow() {
    if (!confirm('Are you sure you want to mark this appointment as a Patient No-Show? A penalty fee will be applied and the call will end.')) {
        return;
    }

    const btn = document.getElementById('in-call-no-show-btn');
    const originalContent = btn.innerHTML;
    btn.disabled = true;
    btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> <span>Processing...</span>';

    try {
        const response = await fetch(`/video/mark-no-show/${currentAppointmentId}`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            }
        });

        const data = await response.json();
        if (response.ok) {
            alert(data.message || 'Appointment marked as No-Show.');
            // End the call and redirect
            leaveCall();
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
