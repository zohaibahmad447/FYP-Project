from flask import Blueprint, jsonify, current_app, request
from app.utils.auth import login_required, get_current_user
from app.models import Appointment
from app.utils.timezone import appointment_datetime_pkt, pkt_now_naive
from agora_token_builder import RtcTokenBuilder
import time

video_bp = Blueprint('video', __name__)

@video_bp.route('/token/<int:appointment_id>', methods=['GET'])
@login_required
def get_video_token(appointment_id):
    """Generate Agora RTC token for video call"""
    
    # Get appointment
    appointment = Appointment.query.get_or_404(appointment_id)
    
    # Get current user
    current_user = get_current_user()
    if not current_user:
        return jsonify({'error': 'Authentication required'}), 401
    
    # Verify user has access (must be patient or doctor of this appointment)
    if current_user.id != appointment.patient.user_id and current_user.id != appointment.doctor.user_id:
        return jsonify({'error': 'Unauthorized access'}), 403
    
    # Verify appointment is approved and is a video appointment
    if appointment.status != 'approved':
        return jsonify({'error': 'Appointment not approved'}), 400
    
    if appointment.appointment_type != 'video':
        return jsonify({'error': 'Not a video appointment'}), 400
    
    try:
        # TIME-BASED ACCESS CONTROL: Role-based Virtual Waiting Room Window
        from datetime import timedelta

        # Appointments are stored as Pakistan local date/time (naive)
        appointment_datetime = appointment_datetime_pkt(
            appointment.appointment_date, appointment.appointment_time
        )
        current_datetime = pkt_now_naive()
        
        # Determine if current user is the doctor
        is_doctor = (current_user.id == appointment.doctor.user_id)
        
        # Doctors get 30-min early access (industry standard); patients get 15-min early access
        if is_doctor:
            early_access_window = timedelta(minutes=30)
        else:
            early_access_window = timedelta(minutes=15)
        
        expiry_window = timedelta(minutes=30)
        
        start_window = appointment_datetime - early_access_window
        end_window = appointment_datetime + expiry_window
        
        # Calculate time difference
        time_diff = appointment_datetime - current_datetime
        minutes_remaining = int(time_diff.total_seconds() / 60)
        
        # Check 1: Too Early
        if current_datetime < start_window:
            minutes_until_access = int((start_window - current_datetime).total_seconds() / 60)
            
            role_label = "Consultation" if is_doctor else "Virtual Waiting Room"
            return jsonify({
                'error': 'Too early to join',
                'message': f'{role_label} opens at {start_window.strftime("%I:%M %p")}',
                'minutes_remaining': minutes_until_access,
                'appointment_time': appointment_datetime.strftime('%Y-%m-%d %H:%M:%S'),
                'can_join_at': start_window.strftime('%I:%M %p')
            }), 403
        
        # Check 2: Expired (More than 30 minutes after)
        # Exception: If the call is CURRENTLY active (doctor and patient are talking), do not expire the link.
        # This prevents cutting off long consultations or late starts.
        # But if the call is NOT active (doctor left), enforce the expiry.
        if current_datetime > end_window and not appointment.is_call_active:
            return jsonify({
                'error': 'Link expired',
                'message': f'This video call link expired at {end_window.strftime("%I:%M %p")}',
                'appointment_time': appointment_datetime.strftime('%Y-%m-%d %H:%M:%S'),
                'expired_at': end_window.strftime('%I:%M %p')
            }), 410  # 410 Gone - Resource no longer available
        
        # Access granted! Calculate status for frontend
        
        # Get Agora credentials from config
        app_id = current_app.config.get('AGORA_APP_ID')
        app_certificate = current_app.config.get('AGORA_APP_CERTIFICATE')
        
        if not app_id or not app_certificate:
            print("Error: Agora credentials missing")
            return jsonify({'error': 'Video call configuration missing'}), 500
        
        # Channel name is the appointment ID
        channel_name = f"appointment_{appointment_id}"
        
        # User ID - use database user ID
        uid = current_user.id
        
        # Token expiration time (24 hours from now)
        expiration_time_in_seconds = 86400  # 24 hours
        current_timestamp = int(time.time())
        privilege_expired_ts = current_timestamp + expiration_time_in_seconds
        
        # Role: Publisher (can send and receive video/audio)
        role = 1  # 1 = Publisher, 2 = Subscriber
        
        # Generate token
        token = RtcTokenBuilder.buildTokenWithUid(
            app_id, 
            app_certificate, 
            channel_name, 
            uid, 
            role, 
            privilege_expired_ts
        )
        
        # Mark user as joined when they successfully obtain a token
        if current_user.id == appointment.patient.user_id:
            if not appointment.patient_joined_video:  # Only mark once
                appointment.patient_joined_video = True
                appointment.patient_joined_at = pkt_now_naive()
        elif current_user.id == appointment.doctor.user_id:
            if not appointment.doctor_joined_video:  # Only mark once
                appointment.doctor_joined_video = True
                appointment.doctor_joined_at = pkt_now_naive()

        # Prescription timer only — recording starts later (live media), not on token
        if (appointment.doctor_joined_video and appointment.patient_joined_video
                and not appointment.mutual_call_start):
            appointment.mutual_call_start = pkt_now_naive()

        from app import db
        db.session.commit()

        # Refresh session to ensure we have the latest state (CRITICAL for is_call_active)
        db.session.expire_all()
        appointment = Appointment.query.get(appointment_id)
        
        print(f"DEBUG_VIDEO_TOKEN: ApptID={appointment.id}, Role={current_user.role}, UserID={current_user.id}, DocUserID={appointment.doctor.user_id}, IsCallActive={appointment.is_call_active}")

        return jsonify({
            'token': token,
            'channel': channel_name,
            'uid': uid,
            'appId': app_id,
            'role': 'doctor' if current_user.id == appointment.doctor.user_id else 'patient',
            # Waiting Room Status - DOCTOR-INITIATED (not time-based)
            'waiting_room': {
                # Patient waits until doctor explicitly starts (is_call_active = True)
                # Doctors NEVER wait - they start the call
                'is_waiting': (not appointment.is_call_active) and (current_user.id != appointment.doctor.user_id),
                'minutes_remaining': minutes_remaining,
                'appointment_time': appointment_datetime.strftime('%I:%M %p'),
                'doctor_name': appointment.doctor.user.name if hasattr(appointment.doctor, 'user') else 'Doctor'
            }
        })
    except Exception as e:
        import traceback
        print(f"Error generating video token: {str(e)}")
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

@video_bp.route('/queue-status/<int:appointment_id>', methods=['GET'])
@login_required
def get_queue_status(appointment_id):
    """Get queue status for doctor's waiting room dashboard"""
    from datetime import timedelta

    appointment = Appointment.query.get_or_404(appointment_id)
    current_user = get_current_user()
    
    if not current_user:
        return jsonify({'error': 'Authentication required'}), 401
    
    # Only doctors can access queue status
    if current_user.id != appointment.doctor.user_id:
        return jsonify({'error': 'Only doctors can view queue status'}), 403
    
    # Get patient info
    patient = appointment.patient
    patient_user = patient.user if patient else None
    
    # Calculate appointment timing (PKT)
    appointment_datetime = appointment_datetime_pkt(
        appointment.appointment_date, appointment.appointment_time
    )
    current_datetime = pkt_now_naive()
    
    # Access window (patient: 15 min early)
    patient_start_window = appointment_datetime - timedelta(minutes=15)
    time_diff = appointment_datetime - current_datetime
    minutes_until_appointment = int(time_diff.total_seconds() / 60)
    patient_can_join = current_datetime >= patient_start_window
    
    # --- NO-SHOW LOGIC ---
    # Determine if doctor can mark patient as no-show
    doctor_first_join = appointment.doctor_joined_at or appointment.call_started_at
    can_mark_no_show = False
    no_show_reason = ""
    
    # Calculate the effective start time (appointment time OR doctor join time, whichever is later)
    # If doctor hasn't joined, use appointment time
    effective_start = max(appointment_datetime, doctor_first_join) if doctor_first_join else appointment_datetime
    
    # 1. Has 2 minutes passed since the effective start time? (TESTING OVERRIDE)
    grace_period_end = effective_start + timedelta(minutes=2)
    if current_datetime >= grace_period_end:
        # 2. Did the doctor join the call?
        if doctor_first_join:
            # 3. Doctor Punctuality Check: Did they join more than 5 mins late?
            if doctor_first_join > appointment_datetime + timedelta(minutes=5):
                no_show_reason = "You joined >5 mins late. No-Show penalty waived."
            else:
                can_mark_no_show = True
        else:
            no_show_reason = "You must start the consultation to wait."
    else:
        mins_left = int((grace_period_end - current_datetime).total_seconds() / 60)
        # Ensure it doesn't show negative if something is off
        mins_left = max(1, mins_left)
        no_show_reason = f"Grace period active. Wait {mins_left} more min(s)."
    # ---------------------
    
    return jsonify({
        'appointment': {
            'id': appointment.id,
            'type': appointment.appointment_type,
            'date': appointment.appointment_date.strftime('%Y-%m-%d'),
            'time': appointment.appointment_time.strftime('%I:%M %p'),
            'datetime': appointment_datetime.strftime('%Y-%m-%d %H:%M:%S'),
            'symptoms': appointment.symptoms,
            'disease_category': appointment.disease_category,
            'notes': appointment.notes
        },
        'patient': {
            'name': patient_user.name if patient_user else 'Unknown',
            'email': patient_user.email if patient_user else '',
        },
        'timing': {
            'appointment_time': appointment_datetime.strftime('%I:%M %p'),
            'minutes_until_appointment': minutes_until_appointment,
            'is_early': minutes_until_appointment > 0,
            'patient_can_join': patient_can_join
        },
        'status': {
            'ready_to_start': True,  # Doctor can always click "Start"
            'patient_waiting': patient_can_join,  # Patient may be waiting
            'can_mark_no_show': can_mark_no_show,
            'no_show_reason': no_show_reason
        }
    })

@video_bp.route('/start/<int:appointment_id>', methods=['POST'])
@login_required  
def start_video_call(appointment_id):
    """Mark video call as started (optional - for logging)"""
    appointment = Appointment.query.get_or_404(appointment_id)
    
    # Get current user
    current_user = get_current_user()
    if not current_user:
        return jsonify({'error': 'Authentication required'}), 401
    
    # Verify access - Only the doctor can START the call officially
    if current_user.id != appointment.doctor.user_id:
        # Patients can still join (they will just hit the lobby or live call)
        # But they SHOULD NOT actuate the "is_call_active" trigger in the backend
        return jsonify({'error': 'Only doctors can start a video call'}), 403
    
    from app import db

    # Mark the call as active so patients waiting in lobby get pulled in
    if not appointment.is_call_active:
        appointment.is_call_active = True
        appointment.call_started_at = pkt_now_naive()
    
    # Track who joined
    if current_user.id == appointment.doctor.user_id and not appointment.doctor_joined_video:
        appointment.doctor_joined_video = True
        appointment.doctor_joined_at = pkt_now_naive()
    elif current_user.id == appointment.patient.user_id and not appointment.patient_joined_video:
        appointment.patient_joined_video = True
        appointment.patient_joined_at = pkt_now_naive()
        
    # ─── CONSULTATION GATE: Record mutual start when both parties are in the call ───
    started_mutual = False
    if (appointment.doctor_joined_video and appointment.patient_joined_video 
            and not appointment.mutual_call_start):
        appointment.mutual_call_start = pkt_now_naive()
        started_mutual = True
        
    db.session.commit()

    print(f"✅ Video Call #{appointment.id} — {current_user.role} joined")
    
    return jsonify({'success': True, 'message': 'Video call started', 'is_active': True})


@video_bp.route('/recording-start/<int:appointment_id>', methods=['POST'])
@login_required
def recording_start(appointment_id):
    """Start Agora cloud recording once both parties are publishing media in the channel."""
    appointment = Appointment.query.get_or_404(appointment_id)
    current_user = get_current_user()
    if not current_user:
        return jsonify({'error': 'Authentication required'}), 401
    if current_user.id != appointment.patient.user_id and current_user.id != appointment.doctor.user_id:
        return jsonify({'error': 'Unauthorized'}), 403
    if appointment.appointment_type != 'video':
        return jsonify({'error': 'Not a video appointment'}), 400
    if not appointment.is_call_active:
        return jsonify({'error': 'Call not active yet'}), 400
    if not (appointment.doctor_joined_video and appointment.patient_joined_video):
        return jsonify({'error': 'Both parties must join before recording'}), 400

    from app.models import VideoCallRecording
    existing = VideoCallRecording.query.filter_by(
        appointment_id=appointment_id, status='recording'
    ).first()
    if existing:
        return jsonify({'success': True, 'status': 'recording', 'sid': existing.agora_sid})

    try:
        from app.services.recording_service import maybe_start_recording
        started = maybe_start_recording(appointment_id, from_client=True)
    except Exception as exc:
        current_app.logger.warning('recording-start appt %s: %s', appointment_id, exc)
        return jsonify({'error': 'Recording start failed'}), 500

    if started:
        active = VideoCallRecording.query.filter_by(
            appointment_id=appointment_id, status='recording'
        ).first()
        return jsonify({'success': True, 'status': 'recording', 'sid': active.agora_sid if active else None})
    return jsonify({'success': False, 'status': 'not_started'}), 502


@video_bp.route('/check-unlock/<int:appointment_id>', methods=['GET'])
@login_required
def check_unlock(appointment_id):
    """
    Polling endpoint (typically every ~12s from appointment view).
    Returns whether the prescription is now unlocked.
    If both parties have been in the call for 3+ minutes, unlocks immediately.
    """
    from app import db

    appointment = Appointment.query.get_or_404(appointment_id)
    current_user = get_current_user()
    if not current_user:
        return jsonify({'error': 'Authentication required'}), 401

    # Already unlocked — just confirm
    if appointment.prescription_unlocked:
        return jsonify({'unlocked': True, 'reason': 'consultation_complete'})

    from app.utils.prescription_gate import MIN_MUTUAL_VIDEO_SECONDS, try_unlock_prescription_from_mutual_video

    # Server backup: start recording during active call (8s after doctor started)
    if appointment.is_call_active:
        try:
            from app.services.recording_service import maybe_start_recording
            maybe_start_recording(appointment_id, from_client=False)
        except Exception:
            pass

    if try_unlock_prescription_from_mutual_video(appointment):
        db.session.commit()
        elapsed = int((pkt_now_naive() - appointment.mutual_call_start).total_seconds()) if appointment.mutual_call_start else MIN_MUTUAL_VIDEO_SECONDS
        print(f"✅ Prescription unlocked for Appointment #{appointment.id} — {elapsed}s mutual video")
        return jsonify({'unlocked': True, 'reason': 'video_minimum_met', 'elapsed_seconds': elapsed})

    if appointment.mutual_call_start:
        elapsed = (pkt_now_naive() - appointment.mutual_call_start).total_seconds()
        remaining = int(MIN_MUTUAL_VIDEO_SECONDS - elapsed)
        return jsonify(
            {
                'unlocked': False,
                'reason': 'waiting_for_minimum',
                'elapsed_seconds': int(elapsed),
                'remaining_seconds': max(0, remaining),
            }
        )

    return jsonify({'unlocked': False, 'reason': 'no_interaction_yet'})


@video_bp.route('/end/<int:appointment_id>', methods=['POST'])
@login_required
def end_video_call(appointment_id):
    """Mark video call as ended (optional - for logging)"""
    appointment = Appointment.query.get_or_404(appointment_id)
    
    # Get current user
    current_user = get_current_user()
    if not current_user:
        return jsonify({'error': 'Authentication required'}), 401
    
    # Verify access
    if current_user.id != appointment.patient.user_id and current_user.id != appointment.doctor.user_id:
        return jsonify({'error': 'Unauthorized'}), 403
    
    # Stop Agora cloud recording when either party leaves (must run for patient too)
    try:
        from app.services.recording_service import stop_recording
        stop_recording(appointment.id)
    except Exception as e:
        print(f"Recording stop skipped for appt #{appointment.id}: {e}")

    from app import db
    from app.utils.prescription_gate import try_unlock_prescription_from_mutual_video

    # Apply 3-minute rule before doctor clears mutual_call_start (avoids losing unlock if polling missed a beat)
    try_unlock_prescription_from_mutual_video(appointment)

    if current_user.id == appointment.doctor.user_id:
        appointment.is_call_active = False
        if appointment.prescription_unlocked:
            appointment.mutual_call_start = None

    db.session.commit()

    return jsonify({'success': True, 'message': 'Video call ended'})

@video_bp.route('/mark-no-show/<int:appointment_id>', methods=['POST'])
@login_required
def mark_no_show(appointment_id):
    """Mark appointment as patient no-show"""
    from datetime import timedelta
    from app import db
    
    appointment = Appointment.query.get_or_404(appointment_id)
    current_user = get_current_user()
    
    # Verify access
    if not current_user or current_user.id != appointment.doctor.user_id:
        return jsonify({'error': 'Unauthorized'}), 403
        
    appointment_datetime = appointment_datetime_pkt(
        appointment.appointment_date, appointment.appointment_time
    )
    current_datetime = pkt_now_naive()
    doctor_first_join = appointment.doctor_joined_at or appointment.call_started_at
    
    if not doctor_first_join:
        return jsonify({'error': 'You must start the consultation before marking no-show.'}), 400
        
    effective_start = max(appointment_datetime, doctor_first_join)
    grace_period_end = effective_start + timedelta(minutes=2) # TESTING OVERRIDE
    
    if current_datetime < grace_period_end:
        return jsonify({'error': 'Grace period has not expired yet.'}), 400
        
    if not doctor_first_join:
        return jsonify({'error': 'You must start the consultation before marking no-show.'}), 400
        
    if doctor_first_join > appointment_datetime + timedelta(minutes=5):
        return jsonify({'error': 'You joined the consultation late. No-Show penalty cannot be applied.'}), 400
        
    # Mark as no-show
    appointment.status = 'no_show'
    appointment.cancellation_reason = 'Patient No-Show - Fee Applied'
    # ─── CONSULTATION GATE: No-show is a valid end state — unlock so doctor can add notes ───
    appointment.prescription_unlocked = True
    db.session.commit()
    
    return jsonify({
        'success': True,
        'message': 'Appointment marked as No-Show. Penalty applied.'
    })
