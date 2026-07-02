from flask import Blueprint, render_template, request, flash, redirect, url_for, session, jsonify
from app.models import Appointment, Doctor, Patient, User
from app.database import db
from app.utils.auth import login_required, get_current_user, patient_required, doctor_required
from app.utils.timezone import get_pakistan_now, get_pakistan_today, get_pakistan_time, pkt_now_naive
from datetime import datetime, date, time, timedelta
import json
from app.services.email_service import send_appointment_request_email, send_appointment_approved_email
from app.utils.slots import APPOINTMENT_SLOT_INTERVAL_MINUTES, find_reserved_appointment
from app.utils.appointment_workflow import set_booking_payment_deadline, on_payment_marked_approved, appointment_awaiting_doctor
from app.routes.payments import mark_appointment_paid

appointments_bp = Blueprint('appointments', __name__)

def check_doctor_approval():
    """Check if doctor is approved, redirect to pending dashboard if not"""
    user = get_current_user()
    doctor = user.doctor_profile
    
    if not doctor.is_approved:
        flash('Your account is pending admin approval. Appointment management is restricted.', 'warning')
        return render_template('doctors/pending_dashboard.html', doctor=doctor)
    return None

@appointments_bp.route('/')
@login_required
def index():
    """Appointments overview"""
    user = get_current_user()
    
    if user.role == 'doctor':
        return redirect(url_for('doctors.appointments'))
    elif user.role == 'patient':
        return redirect(url_for('patients.appointments'))
    else:
        return redirect(url_for('home.index'))

@appointments_bp.route('/book', methods=['GET', 'POST'])
@patient_required
def book_appointment():
    """Book a new appointment"""
    user = get_current_user()
    patient = user.patient_profile
    
    if request.method == 'POST':
        # Get form data
        doctor_id = request.form.get('doctor_id')
        appointment_type = request.form.get('appointment_type')
        appointment_date = request.form.get('appointment_date')
        appointment_time = request.form.get('appointment_time')
        hospital = request.form.get('hospital', '')  # Get hospital from form
        disease_category = request.form.get('disease_category')
        symptoms = request.form.get('symptoms', '')
        notes = request.form.get('notes', '')
        
        # Validation
        if not all([doctor_id, appointment_type, appointment_date, appointment_time, disease_category]):
            flash('Please fill in all required fields.', 'error')
            return redirect(request.url)
        
        # Get doctor
        doctor = Doctor.query.get(doctor_id)
        if not doctor or not doctor.is_approved:
            flash('Selected doctor is not available.', 'error')
            return redirect(request.url)
        
        # Parse date and time
        try:
            appointment_date = datetime.strptime(appointment_date, '%Y-%m-%d').date()
            appointment_time = datetime.strptime(appointment_time, '%H:%M').time()
        except ValueError:
            flash('Invalid date or time format.', 'error')
            return redirect(request.url)
        
        # Check if appointment is in the future - allow booking for tomorrow/day after even if today's time passed
        today = get_pakistan_today()
        current_time = get_pakistan_time()
        
        # If appointment is today, check if time has passed
        if appointment_date == today:
            if appointment_time <= current_time:
                flash('Today\'s time slots have passed. Please select a future date.', 'error')
                return redirect(request.url)
        # If appointment date is in the past, reject
        elif appointment_date < today:
            flash('Appointment date cannot be in the past. Please select a future date.', 'error')
            return redirect(request.url)
        
        # Check if doctor is available at this time
        existing_appointment = find_reserved_appointment(
            doctor_id, appointment_date, appointment_time
        )
        
        if existing_appointment:
            flash('Doctor is not available at the selected time.', 'error')
            return redirect(request.url)
        
        # Calculate charges from time slot
        day_name = appointment_date.strftime('%A').lower()
        selected_time_str = appointment_time.strftime('%H:%M')
        
        from app.utils.slots import get_slot_info
        slot_info = get_slot_info(doctor.time_slots, day_name, selected_time_str)
        
        charges = None
        if slot_info:
            # Get price based on appointment type
            if appointment_type == 'physical':
                charges = slot_info.get('physical_price')
            else:  # video
                charges = slot_info.get('video_price')
        
        # Fallback to doctor's default charges if not found in slot
        if charges is None:
            if appointment_type == 'video':
                charges = getattr(doctor, 'video_charges', 0) if hasattr(doctor, 'video_charges') else 0
            else:
                charges = getattr(doctor, 'physical_charges', 0) if hasattr(doctor, 'physical_charges') else 0
        
        # Create appointment
        appointment = Appointment(
            patient_id=patient.id,
            doctor_id=doctor_id,
            appointment_type=appointment_type,
            appointment_date=appointment_date,
            appointment_time=appointment_time,
            hospital=hospital.strip() if hospital else None,  # Store hospital for this appointment
            disease_category=disease_category,
            symptoms=symptoms,
            notes=notes,
            charges=charges,
            status='pending'
        )
        set_booking_payment_deadline(appointment)
        
        try:
            db.session.add(appointment)
            db.session.commit()
            
            flash('Appointment reserved! Please complete payment now to send the request to your doctor.', 'success')
            return redirect(url_for('appointments.view_appointment', appointment_id=appointment.id))
            
        except Exception as e:
            db.session.rollback()
            flash('Failed to book appointment. Please try again.', 'error')
            print(f'Error booking appointment: {e}')
    
    # GET request - Redirect to patients.book_appointment route for proper handling
    doctor_id = request.args.get('doctor_id')
    if doctor_id:
        # Redirect to the proper booking route in patients blueprint
        appointment_type = request.args.get('type', '')
        practice = request.args.get('practice', '')
        redirect_url = url_for('patients.book_appointment', doctor_id=doctor_id)
        if appointment_type:
            redirect_url += f'?type={appointment_type}'
            if practice:
                redirect_url += f'&practice={practice}'
        return redirect(redirect_url)
    else:
        flash('Please select a doctor to book an appointment.', 'error')
        return redirect(url_for('patients.find_doctors'))
    
    # Get available time slots for the doctor
    available_slots = []
    if doctor:
        # Generate time slots for the next 30 days
        for i in range(1, 31):
            slot_date = date.today() + timedelta(days=i)
            if doctor.time_slots:
                day_name = slot_date.strftime('%A').lower()
                if day_name in doctor.time_slots:
                    for time_slot in doctor.time_slots[day_name]:
                        # Handle both old format (string) and new format (dict with time and hospital)
                        if isinstance(time_slot, dict):
                            slot_time = time_slot.get('time', '')
                            slot_hospital = time_slot.get('hospital', '')
                        else:
                            slot_time = time_slot
                            slot_hospital = ''  # Hospital affiliation removed - get from time slot only
                        
                        available_slots.append({
                            'date': slot_date,
                            'time': slot_time,
                            'hospital': slot_hospital
                        })
    
    return render_template('appointments/book.html', 
                         doctor=doctor, 
                         available_slots=available_slots)

@appointments_bp.route('/<int:appointment_id>/approve', methods=['POST'])
@doctor_required
def approve_appointment(appointment_id):
    """Doctor approves an appointment"""
    # Check if doctor is approved
    approval_check = check_doctor_approval()
    if approval_check:
        return approval_check
    
    user = get_current_user()
    doctor = user.doctor_profile
    
    appointment = Appointment.query.get_or_404(appointment_id)
    
    # Check if this doctor owns the appointment
    if appointment.doctor_id != doctor.id:
        flash('You can only approve your own appointments.', 'error')
        return redirect(url_for('doctors.appointments'))
    
    if appointment.status != 'pending':
        flash('This appointment has already been processed.', 'error')
        return redirect(url_for('doctors.appointments'))

    if appointment.payment_status != 'approved':
        flash('This appointment is waiting for patient payment. You can approve it after payment is confirmed.', 'warning')
        return redirect(url_for('doctors.appointments'))
    
    # Approve appointment
    appointment.status = 'approved'
    appointment.approved_at = get_pakistan_now()
    
    try:
        db.session.commit()
        
        # Send notification email to Patient
        try:
            send_appointment_approved_email(
                patient_email=appointment.patient.user.email,
                patient_name=appointment.patient.user.name,
                doctor_name=doctor.user.name,
                appointment_date=appointment.appointment_date,
                appointment_time=appointment.appointment_time,
                charges=appointment.charges
            )
        except Exception as e:
            print(f'Error sending approval email to patient: {e}')
            
        flash('Appointment approved successfully!', 'success')
    except Exception as e:
        db.session.rollback()
        flash('Failed to approve appointment.', 'error')
        print(f'Error approving appointment: {e}')
    
    return redirect(url_for('doctors.appointments'))

@appointments_bp.route('/<int:appointment_id>/reject', methods=['POST'])
@doctor_required
def reject_appointment(appointment_id):
    """Doctor rejects an appointment"""
    # Check if doctor is approved
    approval_check = check_doctor_approval()
    if approval_check:
        return approval_check
    
    user = get_current_user()
    doctor = user.doctor_profile
    
    appointment = Appointment.query.get_or_404(appointment_id)
    
    # Check if this doctor owns the appointment
    if appointment.doctor_id != doctor.id:
        flash('You can only reject your own appointments.', 'error')
        return redirect(url_for('doctors.appointments'))
    
    if appointment.status != 'pending':
        flash('This appointment has already been processed.', 'error')
        return redirect(url_for('doctors.appointments'))
    
    rejection_reason = request.form.get('rejection_reason', 'No reason provided')
    
    # If patient had already paid (edge case), create refund for admin to process
    if appointment.payment_status == 'approved':
        from app.services.accounts_service import create_refund
        create_refund(appointment, reason='rejection', amount=appointment.charges)
    
    appointment.status = 'rejected'
    appointment.notes = f"Rejected: {rejection_reason}"
    
    try:
        db.session.commit()
        flash('Appointment rejected.' + (' Refund will be processed by admin.' if appointment.payment_status == 'approved' else ''), 'info')
    except Exception as e:
        db.session.rollback()
        flash('Failed to reject appointment.', 'error')
        print(f'Error rejecting appointment: {e}')
    
    return redirect(url_for('doctors.appointments'))

@appointments_bp.route('/<int:appointment_id>/complete/patient', methods=['POST'])
@patient_required
def patient_complete_appointment(appointment_id):
    """Patient marks appointment as completed - Must be done first"""
    user = get_current_user()
    patient = user.patient_profile
    
    appointment = Appointment.query.get_or_404(appointment_id)
    
    # Check if this patient owns the appointment
    if appointment.patient_id != patient.id:
        flash('You can only complete your own appointments.', 'error')
        return redirect(url_for('patients.appointments'))
    
    if appointment.status != 'approved':
        flash('Only approved appointments can be marked as complete.', 'error')
        return redirect(url_for('patients.appointments'))
    
    if appointment.patient_completed:
        flash('You have already marked this appointment as complete.', 'info')
        return redirect(url_for('appointments.view_appointment', appointment_id=appointment_id))
        
    # Check if doctor has marked it complete first
    if not appointment.doctor_completed:
        flash('The doctor must mark the appointment as complete first.', 'warning')
        return redirect(url_for('appointments.view_appointment', appointment_id=appointment_id))
    
    # Patient marks as complete
    appointment.patient_completed = True
    appointment.patient_completed_at = get_pakistan_now()
    
    # If doctor has also completed, finalize appointment
    if appointment.doctor_completed:
        from app.utils.appointment_status import finalize_appointment_completion
        finalize_appointment_completion(appointment)
    
    try:
        db.session.commit()
        if appointment.status == 'completed':
            flash('Appointment completed! Both you and the doctor have marked it as complete.', 'success')
        else:
            flash('You have marked the appointment as complete. Waiting for doctor confirmation.', 'success')
    except Exception as e:
        db.session.rollback()
        flash('Failed to complete appointment.', 'error')
        print(f'Error completing appointment: {e}')
    
    return redirect(url_for('appointments.view_appointment', appointment_id=appointment_id))

@appointments_bp.route('/<int:appointment_id>/complete', methods=['POST'])
@doctor_required
def complete_appointment(appointment_id):
    """Doctor marks appointment as completed - REQUIRES PRESCRIPTION FIRST (Hybrid Assurance Model)"""
    # Check if doctor is approved
    approval_check = check_doctor_approval()
    if approval_check:
        return approval_check
    
    user = get_current_user()
    doctor = user.doctor_profile
    
    appointment = Appointment.query.get_or_404(appointment_id)
    
    # Check if this doctor owns the appointment
    if appointment.doctor_id != doctor.id:
        flash('You can only complete your own appointments.', 'error')
        return redirect(url_for('doctors.appointments'))
    
    if appointment.status != 'approved':
        flash('Only approved appointments can be completed.', 'error')
        return redirect(url_for('doctors.appointments'))
    
    # HYBRID ASSURANCE: Check if prescription exists (MANDATORY)
    if not hasattr(appointment, 'prescription') or not appointment.prescription:
        flash('You must write a prescription before marking this appointment as complete.', 'warning')
        return redirect(url_for('prescriptions.create_prescription', appointment_id=appointment_id))
    
    if appointment.doctor_completed:
        flash('You have already marked this appointment as complete.', 'info')
        return redirect(url_for('appointments.view_appointment', appointment_id=appointment_id))
    
    # Doctor marks as complete
    appointment.doctor_completed = True
    appointment.doctor_completed_at = pkt_now_naive()
    
    # HYBRID ASSURANCE: Set status to "Pending Patient Review" (not fully completed yet)
    appointment.status = 'completed_pending_review'
    
    # Set 24-hour review deadline
    from datetime import timedelta
    appointment.completion_review_deadline = pkt_now_naive() + timedelta(hours=24)
    
    try:
        db.session.commit()
        
        # TODO: Send notification to patient (Email + SocketIO)
        # from app.services.socketio_events import notify_completion_review
        # notify_completion_review(appointment)
        
        flash('Appointment marked as complete! The patient can rate, confirm, or dispute within 24 hours.', 'success')
    except Exception as e:
        db.session.rollback()
        flash('Failed to complete appointment.', 'error')
        print(f'Error completing appointment: {e}')
    
    return redirect(url_for('appointments.view_appointment', appointment_id=appointment_id))

@appointments_bp.route('/<int:appointment_id>/confirm_completion', methods=['POST'])
@patient_required
def confirm_completion(appointment_id):
    """Patient confirms satisfaction during 24-hour review window → completed immediately."""
    user = get_current_user()
    patient = user.patient_profile
    
    appointment = Appointment.query.get_or_404(appointment_id)
    
    # Check if this patient owns the appointment
    if appointment.patient_id != patient.id:
        flash('You can only review your own appointments.', 'error')
        return redirect(url_for('patients.appointments'))
    
    if appointment.status != 'completed_pending_review':
        flash('This appointment is not awaiting your review.', 'info')
        return redirect(url_for('patients.appointments'))
    
    if appointment.patient_completed or appointment.status == 'completed':
        flash('You have already confirmed this appointment.', 'info')
        return redirect(url_for('patients.appointments'))

    now_pkt = pkt_now_naive()
    if appointment.completion_review_deadline and now_pkt >= appointment.completion_review_deadline:
        flash('The confirmation period for this appointment has ended.', 'warning')
        return redirect(url_for('patients.appointments'))

    # Patient confirms satisfaction — finalize immediately (no 24h wait).
    appointment.patient_completed = True
    appointment.patient_completed_at = pkt_now_naive()

    try:
        from app.utils.appointment_status import finalize_appointment_completion
        finalize_appointment_completion(appointment)
        flash('Thank you for confirming. This appointment is now marked as completed.', 'success')
    except Exception as e:
        db.session.rollback()
        flash('Failed to confirm completion.', 'error')
        print(f'Error confirming completion: {e}')
    
    return redirect(url_for('patients.appointments'))


@appointments_bp.route('/<int:appointment_id>/skip_post_visit_review', methods=['POST'])
@patient_required
def skip_post_visit_review(appointment_id):
    """Patient declines to leave a star rating; still allows dispute during review window."""
    user = get_current_user()
    patient = user.patient_profile
    appointment = Appointment.query.get_or_404(appointment_id)
    if appointment.patient_id != patient.id:
        flash('You can only update your own appointments.', 'error')
        return redirect(url_for('patients.appointments'))
    if appointment.status not in ('completed', 'completed_pending_review'):
        flash('This appointment is not in a review phase.', 'info')
        return redirect(url_for('appointments.view_appointment', appointment_id=appointment_id))
    now_pkt = pkt_now_naive()
    if appointment.completion_review_deadline and now_pkt >= appointment.completion_review_deadline:
        flash('The review period for this appointment has ended.', 'warning')
        return redirect(url_for('appointments.view_appointment', appointment_id=appointment_id))
    if appointment.review:
        flash('You have already submitted a review.', 'info')
        return redirect(url_for('appointments.view_appointment', appointment_id=appointment_id))
    if appointment.patient_review_skipped:
        return redirect(url_for('appointments.view_appointment', appointment_id=appointment_id))
    appointment.patient_review_skipped = True
    try:
        db.session.commit()
        flash('You skipped the rating step. You can still report an issue below if needed.', 'info')
    except Exception as e:
        db.session.rollback()
        flash('Could not update your preference. Please try again.', 'error')
        print(f'Error skip_post_visit_review: {e}')
    return redirect(url_for('appointments.view_appointment', appointment_id=appointment_id))


@appointments_bp.route('/<int:appointment_id>/dispute_completion', methods=['POST'])
@patient_required
def dispute_completion(appointment_id):
    """Patient raises dispute about completed appointment"""
    user = get_current_user()
    patient = user.patient_profile
    
    appointment = Appointment.query.get_or_404(appointment_id)
    
    # Check if this patient owns the appointment
    if appointment.patient_id != patient.id:
        flash('You can only dispute your own appointments.', 'error')
        return redirect(url_for('patients.appointments'))
    
    if appointment.status != 'completed_pending_review':
        flash('This appointment is not awaiting your review.', 'info')
        return redirect(url_for('patients.appointments'))

    now_pkt = pkt_now_naive()
    if appointment.patient_completed:
        flash('You already confirmed this visit. Disputes are no longer available.', 'info')
        return redirect(url_for('appointments.view_appointment', appointment_id=appointment_id))
    if appointment.completion_review_deadline and now_pkt >= appointment.completion_review_deadline:
        flash('The dispute window for this appointment has closed.', 'warning')
        return redirect(url_for('appointments.view_appointment', appointment_id=appointment_id))

    # Get dispute reason from form
    dispute_reason = request.form.get('dispute_reason', '').strip()
    if not dispute_reason:
        flash('Please provide a reason for the dispute.', 'warning')
        return redirect(url_for('appointments.view_appointment', appointment_id=appointment_id))
    
    # Mark as disputed
    appointment.status = 'disputed'
    appointment.patient_disputed = True
    appointment.dispute_reason = dispute_reason
    
    try:
        db.session.commit()
        # TODO: Send notification to admin and doctor
        flash('Your dispute has been submitted. Admin will review and contact you within 24 hours.', 'info')
    except Exception as e:
        db.session.rollback()
        flash('Failed to submit dispute.', 'error')
        print(f'Error submitting dispute: {e}')
    
    return redirect(url_for('appointments.view_appointment', appointment_id=appointment_id))


@appointments_bp.route('/<int:appointment_id>/cancel', methods=['POST'])
@login_required
def cancel_appointment(appointment_id):
    """Cancel an appointment"""
    user = get_current_user()
    
    appointment = Appointment.query.get_or_404(appointment_id)
    
    # Check if user has access to this appointment
    if user.role == 'doctor' and appointment.doctor.user_id != user.id:
        flash('You can only cancel your own appointments.', 'error')
        return redirect(url_for('doctors.appointments'))
    elif user.role == 'patient' and appointment.patient.user_id != user.id:
        flash('You can only cancel your own appointments.', 'error')
        return redirect(url_for('patients.appointments'))
    
    if appointment.status in ['completed', 'cancelled']:
        flash('This appointment cannot be cancelled.', 'error')
        return redirect(url_for('appointments.view_appointment', appointment_id=appointment_id))
    
    cancellation_reason = request.form.get('cancellation_reason', 'No reason provided')
    is_doctor_cancel = (user.role == 'doctor')
    now = get_pakistan_now()
    
    # Refund eligibility (only if payment was approved)
    refund_amount = 0
    refund_policy = 'none'
    if appointment.payment_status == 'approved':
        from app.services.accounts_service import get_cancellation_refund_policy, create_refund
        refund_amount, refund_policy = get_cancellation_refund_policy(appointment, now, is_doctor_cancel)
        if refund_amount > 0:
            create_refund(
                appointment,
                reason='cancellation_doctor' if is_doctor_cancel else 'cancellation_patient',
                amount=refund_amount
            )
    
    appointment.status = 'cancelled'
    appointment.cancellation_requested = True
    appointment.cancellation_reason = cancellation_reason
    appointment.refund_policy_applied = refund_policy
    
    try:
        db.session.commit()
        if refund_amount > 0:
            flash(f'Appointment cancelled. Refund of PKR {refund_amount:.0f} will be processed by admin.', 'info')
        else:
            flash('Appointment cancelled successfully.', 'info')
    except Exception as e:
        db.session.rollback()
        flash('Failed to cancel appointment.', 'error')
        print(f'Error cancelling appointment: {e}')
    
    if user.role == 'doctor':
        return redirect(url_for('doctors.appointments'))
    else:
        return redirect(url_for('patients.appointments'))

@appointments_bp.route('/<int:appointment_id>')
@login_required
def view_appointment(appointment_id):
    """View appointment details"""
    user = get_current_user()
    appointment = Appointment.query.get(appointment_id)
    
    if not appointment:
        flash('This appointment does not exist or has been deleted.', 'error')
        if user.role == 'doctor':
            return redirect(url_for('doctors.appointments'))
        elif user.role == 'patient':
            return redirect(url_for('patients.appointments'))
        else:
            return redirect(url_for('home.index'))
    
    # Check if user has access to this appointment
    if user.role == 'doctor' and appointment.doctor.user_id != user.id:
        flash('You do not have access to this appointment.', 'error')
        return redirect(url_for('doctors.appointments'))
    elif user.role == 'patient' and appointment.patient.user_id != user.id:
        flash('You do not have access to this appointment.', 'error')
        return redirect(url_for('patients.appointments'))
    
    # ── Auto-detect completed Safepay payment ──────────────────────────────
    # If we stored a pending Safepay tracker, silently check if it succeeded.
    # This handles the case where Safepay's redirect didn't fire (browser closed,
    # mobile back button, etc.) but payment actually went through.
    if (
        user.role == 'patient'
        and appointment.payment_status != 'approved'
        and appointment.payment_screenshot
        and appointment.payment_screenshot.startswith('safepay_pending_')
    ):
        tracker_token = appointment.payment_screenshot.replace('safepay_pending_', '')
        try:
            import requests as _req
            _headers = {
                'Content-Type': 'application/json',
                'Accept': 'application/json',
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }
            r = _req.get(
                f'https://sandbox.api.getsafepay.com/order/v1/{tracker_token}',
                headers=_headers,
                timeout=5
            )
            if r.status_code == 200:
                state = r.json().get('data', {}).get('state', '')
                print(f'[SAFEPAY AUTO-CHECK] Tracker {tracker_token} state: {state}')
                if state in ('TRACKER_ENDED', 'PAYMENT_SUCCESSFUL', 'CHARGED'):
                    if mark_appointment_paid(appointment, tracker_token):
                        flash('Payment received! Your request has been sent to the doctor for approval.', 'success')
                    else:
                        flash(
                            'Payment received but this slot was just taken by another patient. '
                            'Refund will be processed.',
                            'warning',
                        )
        except Exception as _e:
            print(f'[SAFEPAY AUTO-CHECK] Error: {_e}')
    # ──────────────────────────────────────────────────────────────────────
    
    # ── Fetch Patient Medical History for Doctors ─────────────────────────
    from app.models import MedicalHistory, MedicalDocument
    patient_history = []
    patient_documents = []
    if user.role == 'doctor':
        patient_history = MedicalHistory.query.filter(
            MedicalHistory.patient_id == appointment.patient.id,
            MedicalHistory.appointment_id != appointment.id # Don't show current if already created
        ).order_by(MedicalHistory.created_at.desc()).all()
        
        patient_documents = MedicalDocument.query.filter_by(
            patient_id=appointment.patient.id,
            is_visible_to_doctor=True
        ).order_by(MedicalDocument.uploaded_at.desc()).all()
    # ──────────────────────────────────────────────────────────────────────
    
    return render_template('appointments/view.html', 
                           appointment=appointment,
                           patient_history=patient_history,
                           patient_documents=patient_documents)


@appointments_bp.route('/<int:appointment_id>/verify-payment', methods=['POST'])
@patient_required
def verify_safepay_payment(appointment_id):
    """
    Manual payment verification endpoint.
    Called when the patient clicks the 'Verify Payment' button.
    Checks Safepay's tracker API and updates the appointment if paid.
    """
    user = get_current_user()
    patient = user.patient_profile
    appointment = Appointment.query.filter_by(
        id=appointment_id, patient_id=patient.id
    ).first_or_404()

    if appointment.payment_status == 'approved':
        flash('Payment is already confirmed!', 'info')
        return redirect(url_for('appointments.view_appointment', appointment_id=appointment_id))

    tracker_token = None
    if appointment.payment_screenshot and appointment.payment_screenshot.startswith('safepay_pending_'):
        tracker_token = appointment.payment_screenshot.replace('safepay_pending_', '')
    
    if not tracker_token:
        flash('No pending Safepay transaction found. Please make a payment first.', 'warning')
        return redirect(url_for('appointments.view_appointment', appointment_id=appointment_id))

    try:
        import requests as _req
        _headers = {
            'Content-Type': 'application/json',
            'Accept': 'application/json',
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        r = _req.get(
            f'https://sandbox.api.getsafepay.com/order/v1/{tracker_token}',
            headers=_headers,
            timeout=8
        )
        if r.status_code == 200:
            state = r.json().get('data', {}).get('state', '')
            print(f'[SAFEPAY MANUAL VERIFY] Tracker {tracker_token} state: {state}')
            if state in ('TRACKER_ENDED', 'PAYMENT_SUCCESSFUL', 'CHARGED'):
                if mark_appointment_paid(appointment, tracker_token):
                    flash('Payment received! Your request has been sent to the doctor for approval.', 'success')
                else:
                    flash(
                        'Payment received but this slot was just taken by another patient. '
                        'Refund will be processed.',
                        'warning',
                    )
                return redirect(url_for('appointments.view_appointment', appointment_id=appointment_id))
            else:
                flash(
                    f'Payment not yet confirmed (status: {state}). '
                    'If you completed payment on Safepay, please wait a moment and try again.',
                    'warning'
                )
        else:
            flash('Could not reach payment gateway. Please try again.', 'error')
    except Exception as _e:
        print(f'[SAFEPAY MANUAL VERIFY] Error: {_e}')
        flash('Error contacting payment gateway. Please try again.', 'error')

    return redirect(url_for('appointments.view_appointment', appointment_id=appointment_id))

@appointments_bp.route('/<int:appointment_id>/chat')
@login_required
def chat(appointment_id):
    """Chat room for appointment"""
    user = get_current_user()
    appointment = Appointment.query.get_or_404(appointment_id)
    
    # Check if user has access to this appointment
    if user.role == 'doctor' and appointment.doctor.user_id != user.id:
        flash('You do not have access to this appointment.', 'error')
        return redirect(url_for('doctors.appointments'))
    elif user.role == 'patient' and appointment.patient.user_id != user.id:
        flash('You do not have access to this appointment.', 'error')
        return redirect(url_for('patients.appointments'))
    
    # Allow chat history access for post-consultation states as well.
    allowed_chat_statuses = ['approved', 'completed', 'completed_pending_review', 'disputed']
    if appointment.status not in allowed_chat_statuses:
        flash('Chat is only available for active or completed consultation appointments.', 'error')
        return redirect(url_for('appointments.view_appointment', appointment_id=appointment_id))
    
    # Check if payment is approved (only for patients)
    if user.role == 'patient' and appointment.payment_status != 'approved':
        flash('Please complete payment approval before accessing chat.', 'error')
        return redirect(url_for('appointments.view_appointment', appointment_id=appointment_id))
    
    # Pass user information to template
    return render_template('appointments/chat.html', 
                         appointment=appointment,
                         current_user=user)

@appointments_bp.route('/api/send-message', methods=['POST'])
@login_required
def api_send_message():
    """HTTP API endpoint for sending chat messages.
    Uses HTTP POST instead of Socket.IO to avoid multi-socket session confusion.
    After saving, broadcasts via socketio to update all connected clients."""
    from flask import jsonify, request as http_request
    from app import socketio
    from app.models import MedicalHistory
    from sqlalchemy.orm.attributes import flag_modified
    from datetime import datetime
    import uuid

    user = get_current_user()
    data = http_request.get_json()

    appointment_id = data.get('appointment_id')
    message_text = (data.get('message') or '').strip()

    if not appointment_id or not message_text:
        return jsonify({'success': False, 'error': 'Missing appointment_id or message'}), 400

    appointment = Appointment.query.get(appointment_id)
    if not appointment:
        return jsonify({'success': False, 'error': 'Appointment not found'}), 404

    # Access check
    has_access = False
    if user.role == 'doctor' and appointment.doctor.user_id == user.id:
        has_access = True
    elif user.role == 'patient' and appointment.patient.user_id == user.id:
        has_access = True
    if not has_access:
        return jsonify({'success': False, 'error': 'Access denied'}), 403

    if appointment.status != 'approved':
        return jsonify({'success': False, 'error': 'Chat only available for approved appointments'}), 400

    if user.role == 'patient' and appointment.payment_status != 'approved':
        return jsonify({'success': False, 'error': 'Payment must be approved before chatting'}), 400

    # Build message object
    message_data = {
        'id': str(uuid.uuid4()),
        'user_id': user.id,
        'user_name': user.name,
        'user_role': user.role,
        'message': message_text,
        'timestamp': datetime.now().isoformat(),
        'appointment_id': appointment_id
    }

    # Save to MedicalHistory
    medical_history = MedicalHistory.query.filter_by(appointment_id=appointment_id).first()
    if not medical_history:
        medical_history = MedicalHistory(
            patient_id=appointment.patient_id,
            doctor_id=appointment.doctor_id,
            appointment_id=appointment_id,
            disease=appointment.disease_category,
            chat_logs=[]
        )
        db.session.add(medical_history)
        db.session.flush()

    logs = list(medical_history.chat_logs or [])
    logs.append(message_data)
    medical_history.chat_logs = logs
    flag_modified(medical_history, 'chat_logs')

    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500

    # Track that the doctor sent a chat message (for logging/history purposes)
    if user.role == 'doctor' and not appointment.doctor_sent_chat:
        appointment.doctor_sent_chat = True
        try:
            db.session.commit()
        except Exception:
            db.session.rollback()

    # Broadcast via Socket.IO to the room (default namespace) - best-effort real-time
    room = f'appointment_{appointment_id}'
    socketio.emit('new_message', message_data, room=room)

    return jsonify({'success': True, 'message': message_data})

@appointments_bp.route('/api/messages/<int:appointment_id>')
@login_required
def api_get_messages(appointment_id):
    """HTTP API endpoint to fetch all chat messages for an appointment.
    Used by the frontend polling mechanism as a reliable fallback to Socket.IO."""
    from app.models import MedicalHistory
    import json as _json

    user = get_current_user()
    appointment = Appointment.query.get(appointment_id)
    if not appointment:
        return jsonify({'success': False, 'error': 'Appointment not found'}), 404

    # Access check
    has_access = False
    if user.role == 'doctor' and appointment.doctor.user_id == user.id:
        has_access = True
    elif user.role == 'patient' and appointment.patient.user_id == user.id:
        has_access = True
    if not has_access:
        return jsonify({'success': False, 'error': 'Access denied'}), 403

    medical_history = MedicalHistory.query.filter_by(appointment_id=appointment_id).first()
    messages = []
    if medical_history and medical_history.chat_logs:
        logs = medical_history.chat_logs
        if isinstance(logs, str):
            try:
                logs = _json.loads(logs)
            except Exception:
                logs = []
        messages = logs or []

    return jsonify({'success': True, 'messages': messages})

@appointments_bp.route('/api/available-dates/<int:doctor_id>')
@login_required
def get_available_dates(doctor_id):
    """Get available dates (dates with slots) for a doctor"""
    doctor = Doctor.query.get_or_404(doctor_id)
    
    if not doctor.is_approved:
        return jsonify({'error': 'Doctor not available'}), 400
    
    # Get appointment type and practice from query params
    appointment_type = request.args.get('type', 'physical')
    practice_name = request.args.get('practice', '')
    max_days = int(request.args.get('max_days', 90))  # Search up to 90 days to find 30 dates with available slots
    
    today = get_pakistan_today()
    current_time = get_pakistan_time()
    available_dates = []
    
    # Get doctor's time slots
    if not doctor.time_slots:
        return jsonify({'available_dates': []})
    
    # Organize by practice if needed
    from app.utils.practice_organizer import organize_by_practice
    practices = organize_by_practice(doctor.time_slots) if doctor.time_slots else {}
    
    # Determine slot duration
    slot_duration = APPOINTMENT_SLOT_INTERVAL_MINUTES
    
    # Check each day for the next max_days days
    for day_offset in range(max_days):
        check_date = today + timedelta(days=day_offset)
        day_name = check_date.strftime('%A').lower()
        
        # Check if doctor has slots for this day
        has_slots = False
        
        # CRITICAL FIX: If practice is specified, ONLY check that practice's schedule
        if practice_name and practices:
            practice_data = practices.get(practice_name)
            
            # Check if THIS SPECIFIC PRACTICE has slots for this day
            if practice_data and practice_data.get('days') and day_name in practice_data['days']:
                practice_day_config = practice_data['days'][day_name]
                start_time = practice_day_config.get('start_time', '')
                end_time = practice_day_config.get('end_time', '')
                
                # Generate slots and check if any are available
                from app.utils.slots import generate_slots_from_range
                generated_slots = generate_slots_from_range(start_time, end_time, slot_duration)
                
                for slot_time_str in generated_slots:
                    try:
                        slot_time_obj = datetime.strptime(slot_time_str, '%H:%M').time()
                    except (ValueError, TypeError):
                        continue
                    
                    # For today, skip past slots
                    if check_date == today:
                        if slot_time_obj <= current_time:
                            continue
                    
                    # Check if slot is available
                    existing_appointment = find_reserved_appointment(
                        doctor_id, check_date, slot_time_obj
                    )
                    
                    if not existing_appointment:
                        has_slots = True
                        break
        
        # If NO practice specified, check general doctor schedule
        elif day_name in doctor.time_slots:
            day_config = doctor.time_slots[day_name]
            
            # Handle new structure (time range based)
            if isinstance(day_config, dict) and 'start_time' in day_config:
                start_time = day_config.get('start_time', '')
                end_time = day_config.get('end_time', '')
                
                # If practice is specified, check practice-specific slots
                if practice_name and practices:
                    practice_data = practices.get(practice_name)
                    if practice_data and practice_data.get('days') and day_name in practice_data['days']:
                        practice_day_config = practice_data['days'][day_name]
                        start_time = practice_day_config.get('start_time', start_time)
                        end_time = practice_day_config.get('end_time', end_time)
                
                # Generate slots and check if any are available
                from app.utils.slots import generate_slots_from_range
                generated_slots = generate_slots_from_range(start_time, end_time, slot_duration)
                
                for slot_time_str in generated_slots:
                    try:
                        slot_time_obj = datetime.strptime(slot_time_str, '%H:%M').time()
                    except (ValueError, TypeError):
                        continue
                    
                    # For today, skip past slots
                    if check_date == today:
                        if slot_time_obj <= current_time:
                            continue
                    
                    # Check if slot is available
                    existing_appointment = find_reserved_appointment(
                        doctor_id, check_date, slot_time_obj
                    )
                    
                    if not existing_appointment:
                        has_slots = True
                        break
            
            # Handle old structure (list of slots)
            elif isinstance(day_config, list):
                for time_slot in day_config:
                    if isinstance(time_slot, dict):
                        slot_time = time_slot.get('time', '')
                    else:
                        slot_time = time_slot
                    
                    try:
                        slot_time_obj = datetime.strptime(slot_time, '%H:%M').time()
                    except (ValueError, TypeError):
                        continue
                    
                    # For today, skip past slots
                    if check_date == today:
                        if slot_time_obj <= current_time:
                            continue
                    
                    # Check if slot is available
                    existing_appointment = find_reserved_appointment(
                        doctor_id, check_date, slot_time_obj
                    )
                    
                    if not existing_appointment:
                        has_slots = True
                        break
        
        if has_slots:
            available_dates.append(check_date.strftime('%Y-%m-%d'))
            
            # Stop once we have 30 dates with available slots
            if len(available_dates) >= 30:
                break
    # Return formatted dates for datalist display in Day - DD Mon format
    formatted_dates = []
    for date_str in available_dates:
        date_obj = datetime.strptime(date_str, '%Y-%m-%d').date()
        formatted_dates.append({
            'value': date_str,  # ISO format for backend processing
            'display': date_obj.strftime('%a - %d %b')  # Day - DD Mon format (e.g., "Wed - 28 Jan")
        })
    
    return jsonify({
        'available_dates': available_dates,
        'formatted_dates': formatted_dates,
        'doctor_id': doctor_id
    })


@appointments_bp.route('/api/available-slots/<int:doctor_id>')
@login_required
def get_available_slots(doctor_id):
    """Get available time slots for a doctor"""
    doctor = Doctor.query.get_or_404(doctor_id)
    
    if not doctor.is_approved:
        return jsonify({'error': 'Doctor not available'}), 400
    
    # Get requested date, appointment type, and practice
    requested_date = request.args.get('date')
    appointment_type = request.args.get('type', 'physical')  # Default to physical
    
    # Decode practice name as it comes encoded from frontend
    from urllib.parse import unquote
    practice_name = unquote(request.args.get('practice', ''))  # Practice name if specified
    
    if not requested_date:
        return jsonify({'error': 'Date required'}), 400
    
    try:
        slot_date = datetime.strptime(requested_date, '%Y-%m-%d').date()
    except ValueError:
        return jsonify({'error': 'Invalid date format'}), 400
    
    # Allow booking for today if time hasn't passed, or any future date
    today = get_pakistan_today()
    current_time = get_pakistan_time()
    
    if slot_date < today:
        return jsonify({'error': 'Date cannot be in the past'}), 400
    
    # Determine slot duration based on appointment type
    slot_duration = APPOINTMENT_SLOT_INTERVAL_MINUTES
    
    # Get doctor's time slots for this day
    day_name = slot_date.strftime('%A').lower()
    available_times = []
    
    # If practice is specified, organize by practice to get specific practice slots
    from app.utils.practice_organizer import organize_by_practice
    practices = {}
    if doctor.time_slots:
        practices = organize_by_practice(doctor.time_slots)
    
    # CRITICAL FIX: If practice is specified, ONLY check that practice's schedule
    # Don't fall back to general doctor.time_slots which includes ALL practices
    if practice_name and practices:
        practice_data = practices.get(practice_name)
        
        # Check if THIS SPECIFIC PRACTICE has slots for this day
        if practice_data and practice_data.get('days') and day_name in practice_data['days']:
            practice_day_config = practice_data['days'][day_name]
            
            from app.utils.slots import generate_slots_from_range
            
            start_time = practice_day_config.get('start_time', '')
            end_time = practice_day_config.get('end_time', '')
            hospital = practice_name
            physical_price = practice_data.get('physical_price')
            video_price = practice_data.get('video_price')
            
            # Determine which price to use based on appointment type
            if appointment_type == 'physical':
                price_to_use = physical_price
            else:
                price_to_use = video_price
            
            # Generate slots from time range with appropriate duration for appointment type
            generated_slots = generate_slots_from_range(start_time, end_time, slot_duration)
            
            # Check each generated slot for availability
            for slot_time_str in generated_slots:
                try:
                    slot_time_obj = datetime.strptime(slot_time_str, '%H:%M').time()
                except (ValueError, TypeError):
                    continue
                
                # For today, filter out slots that have already passed
                if slot_date == today:
                    if slot_time_obj <= current_time:
                        continue  # Skip passed slots for today
                
                # Check if this slot is already booked
                existing_appointment = find_reserved_appointment(
                    doctor_id, slot_date, slot_time_obj
                )
                
                if not existing_appointment:
                    slot_data = {
                        'time': slot_time_str,
                        'hospital': hospital
                    }
                    if physical_price:
                        slot_data['physical_price'] = physical_price
                    if video_price:
                        slot_data['video_price'] = video_price
                    available_times.append(slot_data)
        # Else: Practice doesn't have this day configured, return empty array (correct!)
    
    # If NO practice specified, use general doctor schedule
    elif doctor.time_slots and day_name in doctor.time_slots:
        day_config = doctor.time_slots[day_name]
        
        # Handle new structure (time range based)
        if isinstance(day_config, dict) and 'start_time' in day_config:
            from app.utils.slots import generate_slots_from_range
            
            start_time = day_config.get('start_time', '')
            end_time = day_config.get('end_time', '')
            hospital = day_config.get('hospital', '')
            physical_price = day_config.get('physical_price')
            video_price = day_config.get('video_price')
            
            # If practice is specified, get the practice-specific time range
            if practice_name and practices:
                practice_data = practices.get(practice_name)
                if practice_data and practice_data.get('days') and day_name in practice_data['days']:
                    practice_day_config = practice_data['days'][day_name]
                    start_time = practice_day_config.get('start_time', start_time)
                    end_time = practice_day_config.get('end_time', end_time)
                    hospital = practice_name
                    if appointment_type == 'physical':
                        physical_price = practice_data.get('physical_price', physical_price)
                    else:
                        video_price = practice_data.get('video_price', video_price)
            
            # Generate slots from time range with appropriate duration for appointment type
            generated_slots = generate_slots_from_range(start_time, end_time, slot_duration)
            
            # Check each generated slot for availability
            for slot_time_str in generated_slots:
                try:
                    slot_time_obj = datetime.strptime(slot_time_str, '%H:%M').time()
                except (ValueError, TypeError):
                    continue
                
                # For today, filter out slots that have already passed
                if slot_date == today:
                    if slot_time_obj <= current_time:
                        continue  # Skip passed slots for today
                
                # Check if this slot is already booked
                existing_appointment = find_reserved_appointment(
                    doctor_id, slot_date, slot_time_obj
                )
                
                if not existing_appointment:
                    slot_data = {
                        'time': slot_time_str,
                        'hospital': hospital
                    }
                    if physical_price:
                        slot_data['physical_price'] = physical_price
                    if video_price:
                        slot_data['video_price'] = video_price
                    available_times.append(slot_data)
        
        # Handle old structure (list of individual slots) for backwards compatibility
        elif isinstance(day_config, list):
            for time_slot in day_config:
                # Handle both old format (string) and new format (dict with time and hospital)
                if isinstance(time_slot, dict):
                    slot_time = time_slot.get('time', '')
                    slot_hospital = time_slot.get('hospital', '')
                else:
                    slot_time = time_slot
                    slot_hospital = ''
                
                # Check if this slot is already booked
                try:
                    slot_time_obj = datetime.strptime(slot_time, '%H:%M').time()
                except (ValueError, TypeError):
                    continue  # Skip invalid time slots
                
                # For today, filter out slots that have already passed
                if slot_date == today:
                    if slot_time_obj <= current_time:
                        continue  # Skip passed slots for today
                
                existing_appointment = find_reserved_appointment(
                    doctor_id, slot_date, slot_time_obj
                )
                
                if not existing_appointment:
                    slot_data = {
                        'time': slot_time,
                        'hospital': slot_hospital or ''
                    }
                    # Include prices if available
                    if isinstance(time_slot, dict):
                        if 'physical_price' in time_slot and time_slot['physical_price']:
                            slot_data['physical_price'] = time_slot['physical_price']
                        if 'video_price' in time_slot and time_slot['video_price']:
                            slot_data['video_price'] = time_slot['video_price']
                    available_times.append(slot_data)
    
    # Group times by period for Marham.pk-style display
    def get_time_period(time_str):
        """Determine if time is Morning, Afternoon, or Evening"""
        try:
            time_obj = datetime.strptime(time_str, '%H:%M').time()
            hour = time_obj.hour
            if hour < 12:
                return 'Morning'
            elif hour < 17:
                return 'Afternoon'
            else:
                return 'Evening'
        except:
            return 'Unknown'
    
    # Add period to each slot
    for slot in available_times:
        slot['period'] = get_time_period(slot['time'])
    
    # If no slots available for requested date, find next available date
    next_available_date = None
    if not available_times:
        from app.utils.slots import find_next_available_date
        next_available_date_obj = find_next_available_date(
            doctor.time_slots, 
            doctor_id, 
            start_date=slot_date + timedelta(days=1) if slot_date >= today else today
        )
        if next_available_date_obj:
            next_available_date = next_available_date_obj.strftime('%Y-%m-%d')
    
    return jsonify({
        'date': requested_date,
        'available_times': available_times,
        'doctor_name': doctor.user.name,
        'next_available_date': next_available_date
    })


@appointments_bp.route('/api/validate-slot/<int:doctor_id>')
@login_required
def validate_slot(doctor_id):
    """Validate if a specific time slot is still available (real-time check with comprehensive error handling)"""
    doctor = Doctor.query.get_or_404(doctor_id)
    
    if not doctor.is_approved:
        return jsonify({
            'available': False, 
            'error_code': 'DOCTOR_UNAVAILABLE',
            'message': 'Doctor is not available for appointments'
        }), 400
    
    # Get parameters
    requested_date = request.args.get('date')
    requested_time = request.args.get('time')
    appointment_type = request.args.get('type', 'physical')
    practice_name = request.args.get('practice')
    
    if not requested_date or not requested_time:
        return jsonify({
            'available': False, 
            'error_code': 'MISSING_PARAMS',
            'message': 'Date and time are required'
        }), 400
    
    # Parse date - support multiple formats
    slot_date = None
    date_formats = [
        '%Y-%m-%d',  # 2026-01-27
        '%d/%m/%Y',  # 27/01/2026
        '%d-%m-%Y',  # 27-01-2026
        '%d %b %Y',  # 27 Jan 2026
        '%d %B %Y',  # 27 January 2026
    ]
    
    for fmt in date_formats:
        try:
            slot_date = datetime.strptime(requested_date, fmt).date()
            break
        except ValueError:
            continue
    
    if not slot_date:
        return jsonify({
            'available': False,
            'error_code': 'INVALID_DATE_FORMAT',
            'message': 'Please enter a valid date (e.g., 27 Jan 2026 or 27/01/2026)'
        }), 400
    
    # Parse time - support multiple formats
    slot_time = None
    time_formats = [
        '%H:%M',      # 14:30
        '%I:%M %p',   # 02:30 PM
        '%I:%M%p',    # 02:30PM (no space)
        '%I %p',      # 2 PM
        '%I%p',       # 2PM
    ]
    
    for fmt in time_formats:
        try:
            slot_time = datetime.strptime(requested_time.strip(), fmt).time()
            break
        except ValueError:
            continue
    
    if not slot_time:
        return jsonify({
            'available': False,
            'error_code': 'INVALID_TIME_FORMAT',
            'message': 'Please enter time in format: HH:MM AM/PM (e.g., 10:30 AM)'
        }), 400
    
    # Check if date/time is in the past
    today = get_pakistan_today()
    current_time = get_pakistan_time()
    
    if slot_date < today:
        return jsonify({
            'available': False,
            'error_code': 'DATE_PAST',
            'message': f'Cannot book appointments for past dates ({slot_date.strftime("%d %b %Y")})'
        }), 400
    
    if slot_date == today and slot_time <= current_time:
        return jsonify({
            'available': False,
            'error_code': 'TIME_PAST',
            'message': 'This time has already passed'
        }), 400
    
    # Check if doctor works on this day of week
    day_name = slot_date.strftime('%A')
    
    if not doctor.time_slots or day_name not in doctor.time_slots:
        return jsonify({
            'available': False,
            'error_code': 'DAY_UNAVAILABLE',
            'message': f'Doctor is not available on {day_name}, {slot_date.strftime("%d %b %Y")}'
        }), 400
    
    # If practice is specified, check if doctor works at that practice on this day
    practices = doctor.time_slots.get('practices', {})
    if practice_name and practices:
        practice_data = practices.get(practice_name)
        if not practice_data or not practice_data.get('days') or day_name not in practice_data['days']:
            practice_display = practice_name if practice_name != 'Video Consultation' else 'video consultation'
            return jsonify({
                'available': False,
                'error_code': 'PRACTICE_DAY_UNAVAILABLE',
                'message': f'Doctor does not offer {practice_display} appointments on {day_name}, {slot_date.strftime("%d %b %Y")}'
            }), 400
        
        # Get practice-specific time range
        practice_day_config = practice_data['days'][day_name]
        practice_start = practice_day_config.get('start_time')
        practice_end = practice_day_config.get('end_time')
        
        if practice_start and practice_end:
            try:
                start_time_obj = datetime.strptime(practice_start, '%H:%M').time()
                end_time_obj = datetime.strptime(practice_end, '%H:%M').time()
                
                if slot_time < start_time_obj or slot_time >= end_time_obj:
                    return jsonify({
                        'available': False,
                        'error_code': 'TIME_OUTSIDE_HOURS',
                        'message': f'Doctor is not available at {slot_time.strftime("%I:%M %p")}. Available hours: {start_time_obj.strftime("%I:%M %p")} - {end_time_obj.strftime("%I:%M %p")}'
                    }), 400
            except ValueError:
                pass
    else:
        # Check against general schedule
        day_config = doctor.time_slots.get(day_name, {})
        general_start = day_config.get('start_time')
        general_end = day_config.get('end_time')
        
        if general_start and general_end:
            try:
                start_time_obj = datetime.strptime(general_start, '%H:%M').time()
                end_time_obj = datetime.strptime(general_end, '%H:%M').time()
                
                if slot_time < start_time_obj or slot_time >= end_time_obj:
                    return jsonify({
                        'available': False,
                        'error_code': 'TIME_OUTSIDE_HOURS',
                        'message': f'Doctor is not available at {slot_time.strftime("%I:%M %p")}. Available hours: {start_time_obj.strftime("%I:%M %p")} - {end_time_obj.strftime("%I:%M %p")}'
                    }), 400
            except ValueError:
                pass
    
    # Check if slot is already booked
    exclude_appointment_id = request.args.get('appointment_id', type=int)
    existing_appointment = find_reserved_appointment(
        doctor_id, slot_date, slot_time, exclude_appointment_id=exclude_appointment_id
    )
    
    if existing_appointment:
        return jsonify({
            'available': False,
            'error_code': 'SLOT_BOOKED',
            'message': 'This time slot is already booked. Please select another time.'
        }), 400
    
    # Slot is available
    return jsonify({
        'available': True,
        'error_code': None,
        'message': 'Slot is available'
    })

