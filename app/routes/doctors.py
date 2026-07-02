from flask import Blueprint, render_template, request, flash, redirect, url_for, session, jsonify
from app.models import Doctor, Appointment, MedicalHistory, Blog, Answer, Question, DoctorTransaction, DoctorPayoutRequest
from app.database import db
from app.forms import BlogForm
from app.utils.auth import doctor_required, get_current_user
from app.utils.categories import normalize_category
from app.utils.practice_organizer import organize_by_practice, convert_practices_to_time_slots
from sqlalchemy import func, and_, or_
from datetime import datetime, date, time, timedelta
import json
from app.utils.timezone import get_pakistan_now, PAKISTAN_TZ, pkt_now_naive
from app.services.email_service import send_appointment_approved_email
from flask import current_app

doctors_bp = Blueprint('doctors', __name__)

def check_doctor_approval():
    """Check if doctor is approved, redirect to pending dashboard if not"""
    user = get_current_user()
    doctor = user.doctor_profile
    
    if not doctor.is_approved:
        flash('Your account is pending admin approval. This feature is restricted until approval.', 'warning')
        return render_template('doctors/pending_dashboard.html', doctor=doctor)
    return None

@doctors_bp.route('/dashboard')
@doctor_required
def dashboard():
    """Doctor dashboard"""
    user = get_current_user()
    doctor_id = user.doctor_profile.id
    
    # Re-query doctor to get latest data from database (important for rejection_date updates)
    # This ensures we get the most recent rejection_date after appeal rejections
    doctor = Doctor.query.filter_by(id=doctor_id).first_or_404()
    user = doctor.user
    
    # Check if doctor is approved
    if not doctor.is_approved:
        # For pending doctors, show the InstaCare style profile instead of basic dashboard
        is_approved = False
        is_pending = not doctor.is_approved and doctor.appeal_status == 'pending'
        is_rejected = not doctor.is_approved and doctor.appeal_status == 'rejected'
        is_suspended = not doctor.is_approved and doctor.appeal_status == 'suspended'
        
        return render_template('home/doctor_profile.html', 
                             doctor=doctor,
                             is_approved=is_approved,
                             is_pending=is_pending,
                             is_rejected=is_rejected,
                             is_suspended=is_suspended,
                             is_own_profile=True)
    
    # Get appointment statistics
    total_appointments = Appointment.query.filter_by(doctor_id=doctor.id).count()
    pending_appointments = Appointment.query.filter_by(
        doctor_id=doctor.id,
        status='pending',
    ).filter(Appointment.payment_status == 'approved').count()
    approved_appointments = Appointment.query.filter_by(
        doctor_id=doctor.id, 
        status='approved'
    ).count()
    completed_appointments = Appointment.query.filter_by(
        doctor_id=doctor.id, 
        status='completed'
    ).count()
    no_show_appointments = Appointment.query.filter(
        Appointment.doctor_id == doctor.id,
        Appointment.status.in_(['expired_mutual_noshow', 'expired_provider_failure'])
    ).count()
    
    # Get recent appointments
    recent_appointments = Appointment.query.filter_by(
        doctor_id=doctor.id
    ).order_by(Appointment.created_at.desc()).limit(5).all()
    
    # Get recent articles
    recent_blogs = Blog.query.filter_by(doctor_id=doctor.id).order_by(
        Blog.created_at.desc()
    ).limit(3).all()
    
    # Get cancellation requests
    cancellation_requests = Appointment.query.filter(
        Appointment.doctor_id == doctor.id,
        Appointment.cancellation_requested == True,
        Appointment.cancellation_approved == False
    ).all()
    
    # This month statistics
    today = date.today()
    this_month_start = today.replace(day=1)
    
    this_month_appointments = Appointment.query.filter(
        Appointment.doctor_id == doctor.id,
        Appointment.appointment_date >= this_month_start
    ).count()
    
    this_month_completed = Appointment.query.filter(
        Appointment.doctor_id == doctor.id,
        Appointment.status == 'completed',
        Appointment.appointment_date >= this_month_start
    ).count()
    
    # Get doctor rating
    from app.models import Review
    from app.utils.review_fraud import public_reviews_query
    visible_reviews = public_reviews_query().filter_by(doctor_id=doctor.id).all()
    avg_rating = 0
    if visible_reviews:
        avg_rating = round(sum(r.rating for r in visible_reviews) / len(visible_reviews), 1)
    
    stats = {
        'total': total_appointments,
        'pending': pending_appointments,
        'approved': approved_appointments,
        'completed': completed_appointments,
        'no_show': no_show_appointments,
        'this_month': this_month_appointments,
        'this_month_completed': this_month_completed,
        'avg_rating': avg_rating
    }
    
    return render_template('doctors/dashboard.html',
                         doctor=doctor,
                         stats=stats,
                         recent_appointments=recent_appointments,
                         cancellation_requests=cancellation_requests,
                         recent_blogs=recent_blogs)


@doctors_bp.route('/patients/<int:patient_id>/medical-history')
@doctor_required
def patient_medical_history(patient_id):
    """Read-only patient medical history view for doctors (patient template layout)."""
    from app.models import Appointment, Doctor as DoctorModel, MedicalDocument, Patient

    user = get_current_user()
    doctor = user.doctor_profile
    patient = Patient.query.get_or_404(patient_id)

    # Privacy guard: doctor can view only patients they have at least one appointment with.
    has_relationship = Appointment.query.filter_by(
        doctor_id=doctor.id,
        patient_id=patient.id,
    ).first()
    if not has_relationship:
        flash('You can only view history for your own patients.', 'error')
        return redirect(url_for('doctors.appointments'))

    base_query = MedicalHistory.query.join(Appointment).filter(
        MedicalHistory.patient_id == patient.id,
        Appointment.status.in_(['completed', 'completed_pending_review', 'disputed']),
    )

    specialties = sorted([
        r.category for r in DoctorModel.query.with_entities(DoctorModel.category).distinct().all() if r.category
    ])

    current_specialty = request.args.get('specialty', '').strip()
    if current_specialty:
        query = base_query.join(Doctor).filter(Doctor.category == current_specialty)
    else:
        query = base_query

    histories = query.order_by(MedicalHistory.created_at.desc()).all()
    documents = MedicalDocument.query.filter_by(
        patient_id=patient.id,
        is_visible_to_doctor=True,
    ).order_by(MedicalDocument.uploaded_at.desc()).all()

    patient_categories_count = len(set(
        h.appointment.doctor.category
        for h in histories
        if h.appointment and h.appointment.doctor and h.appointment.doctor.category
    ))

    return render_template(
        'patients/medical_history.html',
        histories=histories,
        specialties=specialties,
        current_specialty=current_specialty,
        documents=documents,
        patient_categories_count=patient_categories_count,
        patient=patient,
        doctor_view=True,
    )

@doctors_bp.route('/profile')
@doctor_required
def profile():
    """Doctor profile page - Comprehensive view with all doctor modules"""
    user = get_current_user()
    doctor_id = user.doctor_profile.id
    
    # Re-query doctor to get latest data from database (important for rejection_date updates)
    # This ensures we get the most recent rejection_date after appeal rejections
    doctor = Doctor.query.filter_by(id=doctor_id).first_or_404()
    
    # Check if doctor is approved
    is_approved = doctor.is_approved and doctor.is_verified
    is_pending = not doctor.is_approved and doctor.appeal_status == 'pending'
    is_rejected = not doctor.is_approved and doctor.appeal_status == 'rejected'
    is_suspended = not doctor.is_approved and doctor.appeal_status == 'suspended'
    
    # Get statistics
    total_appointments = Appointment.query.filter_by(doctor_id=doctor.id).count()
    pending_appointments = Appointment.query.filter_by(
        doctor_id=doctor.id, status='pending'
    ).filter(Appointment.payment_status == 'approved').count()
    approved_appointments = Appointment.query.filter_by(doctor_id=doctor.id, status='approved').count()
    completed_appointments = Appointment.query.filter_by(doctor_id=doctor.id, status='completed').count()
    
    # Get recent appointments
    recent_appointments = Appointment.query.filter_by(doctor_id=doctor.id).order_by(
        Appointment.appointment_date.desc(), Appointment.appointment_time.desc()
    ).limit(5).all()
    
    # Get recent blogs
    recent_blogs = Blog.query.filter_by(doctor_id=doctor.id).order_by(
        Blog.created_at.desc()
    ).limit(5).all()
    
    # Get unanswered questions in doctor's category
    unanswered_questions = Question.query.filter(
        Question.category == doctor.category,
        Question.is_answered == False,
        Question.is_deleted == False
    ).order_by(Question.created_at.desc()).limit(5).all()
    
    # Get recent answers
    recent_answers = Answer.query.filter_by(doctor_id=doctor.id).order_by(
        Answer.created_at.desc()
    ).limit(5).all()
    
    # Get total blogs count
    total_blogs = Blog.query.filter_by(doctor_id=doctor.id).count()
    
    # Get total answers count
    total_answers = Answer.query.filter_by(doctor_id=doctor.id).count()
    
    stats = {
        'total_appointments': total_appointments,
        'pending_appointments': pending_appointments,
        'approved_appointments': approved_appointments,
        'completed_appointments': completed_appointments,
        'total_blogs': total_blogs,
        'total_answers': total_answers
    }
    
    return render_template('doctors/profile.html', 
                         doctor=doctor,
                         is_approved=is_approved,
                         is_pending=is_pending,
                         is_rejected=is_rejected,
                         is_suspended=is_suspended,
                         stats=stats,
                         recent_appointments=recent_appointments,
                         recent_blogs=recent_blogs,
                         unanswered_questions=unanswered_questions,
                         recent_answers=recent_answers)

@doctors_bp.route('/earnings')
@doctor_required
def earnings():
    """Doctor earnings dashboard: balance, pending, transactions, payout requests"""
    approval_check = check_doctor_approval()
    if approval_check:
        return approval_check
    user = get_current_user()
    doctor = user.doctor_profile
    doctor = Doctor.query.get(doctor.id)
    min_payout = getattr(current_app.config, 'MIN_PAYOUT_PKR', 1000)
    transactions = DoctorTransaction.query.filter_by(doctor_id=doctor.id).order_by(
        DoctorTransaction.created_at.desc()
    ).limit(50).all()
    payout_requests = DoctorPayoutRequest.query.filter_by(doctor_id=doctor.id).order_by(
        DoctorPayoutRequest.requested_at.desc()
    ).limit(20).all()
    pending_earnings = 0
    from app.models import Appointment as Appt
    pct = getattr(current_app.config, 'PLATFORM_COMMISSION_PERCENT', 20) / 100.0
    pending_appts = Appt.query.filter(
        Appt.doctor_id == doctor.id,
        Appt.payment_status == 'approved',
        Appt.doctor_earning_credited_at.is_(None),
        Appt.status.in_(['approved', 'completed_pending_review'])
    ).all()
    for a in pending_appts:
        pending_earnings += (a.charges or 0) * (1 - pct)
    return render_template('doctors/earnings.html',
                           doctor=doctor,
                           transactions=transactions,
                           payout_requests=payout_requests,
                           min_payout=min_payout,
                           pending_earnings=round(pending_earnings, 2))

@doctors_bp.route('/earnings/payout-request', methods=['POST'])
@doctor_required
def request_payout():
    """Request withdrawal of balance (admin will process)"""
    approval_check = check_doctor_approval()
    if approval_check:
        return approval_check
    user = get_current_user()
    doctor = user.doctor_profile
    doctor = Doctor.query.get(doctor.id)
    min_payout = getattr(current_app.config, 'MIN_PAYOUT_PKR', 1000)
    try:
        amount = float(request.form.get('amount', 0))
    except (TypeError, ValueError):
        flash('Invalid amount.', 'error')
        return redirect(url_for('doctors.earnings'))

    payout_method = (request.form.get('payout_method') or '').strip().lower()
    account_title = (request.form.get('account_title') or '').strip()
    provider_name = (request.form.get('provider_name') or '').strip()
    account_number = (request.form.get('account_number') or '').strip()
    iban = (request.form.get('iban') or '').strip().upper()
    visa_card_holder_name = (request.form.get('visa_card_holder_name') or '').strip()
    visa_card_last4 = (request.form.get('visa_card_last4') or '').strip()
    visa_recipient_id = (request.form.get('visa_recipient_id') or '').strip()

    allowed_methods = {'bank_transfer', 'mobile_wallet', 'visa_card'}
    if payout_method not in allowed_methods:
        flash('Please select a valid payout method.', 'error')
        return redirect(url_for('doctors.earnings'))

    if not account_title:
        flash('Account title is required.', 'error')
        return redirect(url_for('doctors.earnings'))

    if payout_method in {'bank_transfer', 'mobile_wallet'}:
        if not provider_name:
            flash('Bank/Wallet name is required.', 'error')
            return redirect(url_for('doctors.earnings'))
        if not account_number:
            flash('Account number is required.', 'error')
            return redirect(url_for('doctors.earnings'))
        # IBAN is only a bank detail, not a separate method.
        if payout_method != 'bank_transfer':
            iban = None
        visa_card_holder_name = None
        visa_card_last4 = None
        visa_recipient_id = None
    else:
        provider_name = 'Visa'
        account_number = None
        iban = None
        if not visa_card_holder_name:
            flash('Card holder name is required for Visa payouts.', 'error')
            return redirect(url_for('doctors.earnings'))
        if not (visa_card_last4.isdigit() and len(visa_card_last4) == 4):
            flash('Enter valid Visa card last 4 digits.', 'error')
            return redirect(url_for('doctors.earnings'))
        if not visa_recipient_id:
            flash('Visa receiving ID is required.', 'error')
            return redirect(url_for('doctors.earnings'))

    if amount < min_payout:
        flash(f'Minimum withdrawal is PKR {min_payout:,.0f}.', 'error')
        return redirect(url_for('doctors.earnings'))
    if amount > doctor.balance:
        flash('Insufficient balance.', 'error')
        return redirect(url_for('doctors.earnings'))
    req = DoctorPayoutRequest(
        doctor_id=doctor.id,
        amount=amount,
        payout_method=payout_method,
        account_title=account_title,
        provider_name=provider_name,
        account_number=account_number,
        iban=iban,
        visa_card_holder_name=visa_card_holder_name,
        visa_card_last4=visa_card_last4,
        visa_recipient_id=visa_recipient_id,
        status='pending',
    )
    db.session.add(req)
    db.session.commit()
    flash(f'Payout request of PKR {amount:,.0f} submitted. Admin will process it shortly.', 'success')
    return redirect(url_for('doctors.earnings'))

@doctors_bp.route('/profile/edit', methods=['GET', 'POST'])
@doctor_required
def edit_profile():
    """Edit doctor profile - Only allowed if approved or rejected (for appeals)"""
    user = get_current_user()
    doctor = user.doctor_profile
    
    # Restrict editing if pending approval
    if not doctor.is_approved and doctor.appeal_status == 'pending':
        flash('You cannot edit your profile while it is pending approval. Please wait for admin review.', 'warning')
        return redirect(url_for('doctors.profile'))
    
    if request.method == 'POST':
        # Update basic info
        doctor.specialization = request.form.get('specialization', doctor.specialization)
        doctor.education = request.form.get('education', doctor.education)
        doctor.bio = request.form.get('bio', doctor.bio)
        # Hospital affiliation removed - doctors add hospitals per time slot
        doctor.location = request.form.get('location', doctor.location)
        
        # Save services/procedures (comma-separated tags shown on listing card)
        services_raw = request.form.get('services', '').strip()
        # Normalize: strip each Tag, remove empties, re-join cleanly
        doctor.services = ', '.join(
            s.strip() for s in services_raw.split(',') if s.strip()
        ) or None
        
        doctor.updated_at = datetime.utcnow()
        
        db.session.commit()
        flash('Profile updated successfully!', 'success')
        return redirect(url_for('doctors.profile'))

    
    return render_template('doctors/edit_profile.html', doctor=doctor)

@doctors_bp.route('/appointment-settings', methods=['GET', 'POST'])
@doctor_required
def appointment_settings():
    """Appointment settings page - Manage practice locations and schedules"""
    user = get_current_user()
    doctor = user.doctor_profile
    
    # Restrict editing if pending approval
    if not doctor.is_approved and doctor.appeal_status == 'pending':
        flash('You cannot edit appointment settings while your profile is pending approval.', 'warning')
        return redirect(url_for('doctors.profile'))
    
    # Organize time slots by practice/hospital for display (separate physical and video)
    all_practices = organize_by_practice(doctor.time_slots) if doctor.time_slots else {}
    
    # Separate physical and video practices
    physical_practices = {}
    video_practices = {}
    
    for practice_name, practice_data in all_practices.items():
        if practice_data.get('physical_price'):
            physical_practices[practice_name] = practice_data
        if practice_data.get('video_price'):
            video_practices[practice_name] = practice_data
    
    return render_template('doctors/appointment_settings.html', 
                         doctor=doctor, 
                         practices=all_practices,
                         physical_practices=physical_practices,
                         video_practices=video_practices)

@doctors_bp.route('/save-practice', methods=['POST'])
@doctor_required
def save_practice():
    """Save individual practice settings via AJAX"""
    user = get_current_user()
    doctor = user.doctor_profile
    
    try:
        practice_type = request.form.get('practice_type')
        practice_name = request.form.get('practice_name', '').strip()
        practice_location = request.form.get('practice_location', '').strip()
        physical_price_str = request.form.get('physical_price', '').strip()
        video_price_str = request.form.get('video_price', '').strip()
        
        # Get existing practices
        all_practices = organize_by_practice(doctor.time_slots) if doctor.time_slots else {}
        
        # Determine practice name
        if practice_type == 'video':
            final_practice_name = 'Video Consultation'
        else:
            final_practice_name = practice_name if practice_name else 'Physical Practice'
        
        # Initialize practice if it doesn't exist
        if final_practice_name not in all_practices:
            all_practices[final_practice_name] = {
                'location': practice_location if practice_type == 'physical' else 'Online',
                'physical_price': None,
                'video_price': None,
                'days': {}
            }
        
        # Update prices
        if practice_type == 'physical' and physical_price_str:
            try:
                all_practices[final_practice_name]['physical_price'] = float(physical_price_str)
            except (ValueError, TypeError):
                pass
        
        if practice_type == 'video' and video_price_str:
            try:
                all_practices[final_practice_name]['video_price'] = float(video_price_str)
            except (ValueError, TypeError):
                pass
        
        # Update location for physical practices
        if practice_type == 'physical' and practice_location:
            all_practices[final_practice_name]['location'] = practice_location
        
        # Update practice name if changed
        if practice_type == 'physical' and practice_name and practice_name != final_practice_name:
            # If name changed, create new entry
            all_practices[practice_name] = all_practices.pop(final_practice_name, {})
            final_practice_name = practice_name
        
        # Get days data
        days = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']
        practice_index = request.form.get('practice_index')
        
        for day in days:
            day_enabled = request.form.get(f'days[{day}][enabled]') == 'on'
            if day_enabled:
                start_time = request.form.get(f'days[{day}][start_time]', '').strip()
                end_time = request.form.get(f'days[{day}][end_time]', '').strip()
                
                # Video and physical appointments use the same slot interval
                if practice_type == 'video':
                    duration = 30
                else:
                    duration_str = request.form.get(f'days[{day}][duration]', '30').strip()
                    duration = int(duration_str) if duration_str else 30
                
                if start_time and end_time:
                    all_practices[final_practice_name]['days'][day] = {
                        'start_time': start_time,
                        'end_time': end_time,
                        'duration': duration
                    }
            else:
                # Remove day if unchecked
                if day in all_practices[final_practice_name]['days']:
                    del all_practices[final_practice_name]['days'][day]
        
        # Convert back to time_slots format
        doctor.time_slots = convert_practices_to_time_slots(all_practices)
        doctor.updated_at = datetime.utcnow()
        
        db.session.commit()
        
        # Get updated practice data for view mode
        updated_practices = organize_by_practice(doctor.time_slots) if doctor.time_slots else {}
        practice_data = updated_practices.get(final_practice_name, {})
        
        return jsonify({
            'success': True,
            'message': 'Practice saved successfully!',
            'practice_id': final_practice_name,
            'practice_data': practice_data
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'message': f'Error saving practice: {str(e)}'
        }), 400

@doctors_bp.route('/delete-practice', methods=['POST'])
@doctor_required
def delete_practice():
    """Delete a practice via AJAX"""
    user = get_current_user()
    doctor = user.doctor_profile
    
    try:
        data = request.get_json()
        practice_id = data.get('practice_id')
        
        if not practice_id:
            return jsonify({'success': False, 'message': 'Practice ID required'}), 400
        
        # Get existing practices
        all_practices = organize_by_practice(doctor.time_slots) if doctor.time_slots else {}
        
        # Remove practice
        if practice_id in all_practices:
            del all_practices[practice_id]
            
            # Convert back to time_slots format
            doctor.time_slots = convert_practices_to_time_slots(all_practices)
            doctor.updated_at = datetime.utcnow()
            
            db.session.commit()
            
            return jsonify({
                'success': True,
                'message': 'Practice deleted successfully!'
            })
        else:
            return jsonify({
                'success': False,
                'message': 'Practice not found'
            }), 404
        
    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'message': f'Error deleting practice: {str(e)}'
        }), 400

@doctors_bp.route('/appointments')
@doctor_required
def appointments():
    """Doctor appointments management"""
    user = get_current_user()
    doctor = user.doctor_profile
    
    # Get filter parameters
    status = request.args.get('status', 'all')
    appointment_type = request.args.get('type', 'all')
    date_filter = request.args.get('date', '')
    
    # Build query — hide unpaid bookings until patient pays
    query = Appointment.query.filter_by(doctor_id=doctor.id).filter(
        ~and_(Appointment.status == 'pending', Appointment.payment_status != 'approved')
    )
    
    if status != 'all':
        query = query.filter_by(status=status)
    
    if appointment_type != 'all':
        query = query.filter_by(appointment_type=appointment_type)
    
    if date_filter:
        try:
            filter_date = datetime.strptime(date_filter, '%Y-%m-%d').date()
            query = query.filter_by(appointment_date=filter_date)
        except ValueError:
            pass
    
    appointments = query.order_by(Appointment.appointment_date.desc(), 
                                 Appointment.appointment_time.desc()).all()
    
    return render_template('doctors/appointments.html',
                         appointments=appointments,
                         current_status=status,
                         current_type=appointment_type,
                         current_date=date_filter)

@doctors_bp.route('/appointments/<int:appointment_id>/queue')
@doctor_required
def doctor_queue(appointment_id):
    """Doctor's virtual queue/lobby before joining video call"""
    user = get_current_user()
    doctor = user.doctor_profile
    
    # Verify this appointment belongs to this doctor
    appointment = Appointment.query.filter_by(
        id=appointment_id,
        doctor_id=doctor.id
    ).first_or_404()
    
    # Verify it's a video appointment
    if appointment.appointment_type != 'video':
        flash('Queue is only for video appointments.', 'error')
        return redirect(url_for('appointments.view_appointment', appointment_id=appointment_id))
    
    # Verify appointment is approved
    if appointment.status != 'approved':
        flash('Only approved appointments can be accessed.', 'error')
        return redirect(url_for('appointments.view_appointment', appointment_id=appointment_id))
    
    return render_template('doctors/doctor-queue.html', appointment=appointment)


@doctors_bp.route('/appointments/<int:appointment_id>/approve', methods=['POST'])
@doctor_required
def approve_appointment(appointment_id):
    """Approve an appointment"""
    user = get_current_user()
    doctor = user.doctor_profile
    
    appointment = Appointment.query.filter_by(
        id=appointment_id,
        doctor_id=doctor.id
    ).first()
    
    if not appointment:
        flash('Appointment not found.', 'error')
        return redirect(url_for('doctors.appointments'))

    if appointment.status != 'pending':
        flash('This appointment has already been processed.', 'error')
        return redirect(url_for('doctors.appointments'))

    if appointment.payment_status != 'approved':
        flash('Patient payment is not confirmed yet.', 'warning')
        return redirect(url_for('doctors.appointments'))
    
    appointment.status = 'approved'
    appointment.approved_at = get_pakistan_now()
    
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
    return redirect(url_for('doctors.appointments'))

@doctors_bp.route('/appointments/<int:appointment_id>/reject', methods=['POST'])
@doctor_required
def reject_appointment(appointment_id):
    """Reject an appointment"""
    user = get_current_user()
    doctor = user.doctor_profile
    
    appointment = Appointment.query.filter_by(
        id=appointment_id,
        doctor_id=doctor.id
    ).first()
    
    if not appointment:
        flash('Appointment not found.', 'error')
        return redirect(url_for('doctors.appointments'))

    if appointment.status != 'pending':
        flash('This appointment has already been processed.', 'error')
        return redirect(url_for('doctors.appointments'))

    if appointment.payment_status == 'approved':
        from app.services.accounts_service import create_refund
        create_refund(appointment, reason='rejection', amount=appointment.charges)
    
    appointment.status = 'rejected'
    db.session.commit()
    
    flash(
        'Appointment rejected.'
        + (' Refund will be processed by admin.' if appointment.payment_status == 'approved' else ''),
        'info',
    )
    return redirect(url_for('doctors.appointments'))

@doctors_bp.route('/appointments/<int:appointment_id>/complete', methods=['POST'])
@doctor_required
def complete_appointment(appointment_id):
    """Mark appointment as completed - Can only do after patient marks it"""
    from app.utils.timezone import get_pakistan_now
    
    user = get_current_user()
    doctor = user.doctor_profile
    
    appointment = Appointment.query.filter_by(
        id=appointment_id,
        doctor_id=doctor.id
    ).first()
    
    if not appointment:
        flash('Appointment not found.', 'error')
        return redirect(url_for('doctors.appointments'))
    
    if appointment.status != 'approved':
        flash('Only approved appointments can be completed.', 'error')
        return redirect(url_for('doctors.appointments'))
    
    if appointment.doctor_completed:
        flash('You have already marked this appointment as complete.', 'info')
        return redirect(url_for('doctors.appointments'))
    
    # ─── CONSULTATION GATE: Enforce interaction before prescription ───
    if not appointment.prescription_unlocked:
        flash(
            'You must complete a video consultation with the patient first: both join the call, '
            'stay connected for at least 3 minutes, then the prescription section unlocks automatically.',
            'error',
        )
        return redirect(url_for('appointments.view_appointment', appointment_id=appointment.id))
    
    # Retrieve medical details from form
    diagnosis = request.form.get('diagnosis', '').strip()
    treatment_notes = request.form.get('treatment_notes', '').strip()
    
    # Retrieve medicine rows (arrays from the dynamic form)
    med_names = request.form.getlist('med_name[]')
    med_dosages = request.form.getlist('med_dosage[]')
    med_frequencies = request.form.getlist('med_frequency[]')
    med_durations = request.form.getlist('med_duration[]')
    med_instructions = request.form.getlist('med_instructions[]')
    
    # ENFORCE PRESCRIPTION REQUIREMENT — at least one medicine with a name
    valid_medicines = [n for n in med_names if n.strip()]
    if not valid_medicines:
        flash('You must add at least one medicine before completing the appointment.', 'error')
        return redirect(url_for('appointments.view_appointment', appointment_id=appointment.id))

    # Doctor marks as complete and starts 24-hour patient dispute/review window.
    now_pkt = pkt_now_naive()
    appointment.doctor_completed = True
    appointment.doctor_completed_at = now_pkt
    appointment.status = 'completed_pending_review'
    appointment.completion_review_deadline = now_pkt + timedelta(hours=24)
    appointment.completed_at = None
    
    # 1) Create or update MedicalHistory entry (for patient's medical records)
    from app.models import MedicalHistory
    # Build a simple text summary of medicines for the medical history
    medicine_summary = '\n'.join([
        f"{med_names[i]} — {med_dosages[i]} — {med_frequencies[i]} — {med_durations[i]}"
        for i in range(len(med_names)) if med_names[i].strip()
    ])
    
    # Avoid duplicate MedicalHistory entries if chat created one already
    medical_history = MedicalHistory.query.filter_by(appointment_id=appointment.id).first()
    if medical_history:
        medical_history.diagnosis = diagnosis
        medical_history.prescription = medicine_summary
        medical_history.treatment_notes = treatment_notes
        medical_history.source = 'auto_prescription'
    else:
        medical_history = MedicalHistory(
            patient_id=appointment.patient_id,
            doctor_id=doctor.id,
            appointment_id=appointment.id,
            disease=appointment.disease_category,
            diagnosis=diagnosis,
            prescription=medicine_summary,
            treatment_notes=treatment_notes,
            source='auto_prescription'
        )
        db.session.add(medical_history)

    # 2) Create Prescription record (so patients can VIEW the prescription document)
    from app.models import Prescription, PrescriptionMedicine
    # Only create if one doesn't already exist for this appointment
    if not appointment.prescription:
        rx = Prescription(
            appointment_id=appointment.id,
            diagnosis=diagnosis or appointment.disease_category or 'Consultation',
            chief_complaints=appointment.symptoms,
            advice=treatment_notes,  # Only store doctor's advice, NOT medicines
        )
        db.session.add(rx)
        db.session.flush()  # Get the rx.id before adding medicines
        
        # 3) Create PrescriptionMedicine records for each medicine row
        for i, name in enumerate(med_names):
            name = name.strip()
            if not name:
                continue
            med = PrescriptionMedicine(
                prescription_id=rx.id,
                medicine_name=name,
                dosage=med_dosages[i].strip() if i < len(med_dosages) else '',
                frequency=med_frequencies[i].strip() if i < len(med_frequencies) else '',
                duration=med_durations[i].strip() if i < len(med_durations) else '',
                instructions=med_instructions[i].strip() if i < len(med_instructions) else '',
                order=i
            )
            db.session.add(med)
    
    try:
        db.session.commit()
        flash('Prescription saved. Appointment is now pending 24-hour patient review before final payout release.', 'success')
    except Exception as e:
        db.session.rollback()
        flash('Failed to complete appointment.', 'error')
        print(f'Error completing appointment: {e}')
    
    return redirect(url_for('doctors.appointments'))



@doctors_bp.route('/cancellation/<int:appointment_id>/approve', methods=['POST'])
@doctor_required
def approve_cancellation(appointment_id):
    """Approve appointment cancellation"""
    user = get_current_user()
    doctor = user.doctor_profile
    
    appointment = Appointment.query.filter_by(
        id=appointment_id,
        doctor_id=doctor.id
    ).first()
    
    if not appointment:
        flash('Appointment not found.', 'error')
        return redirect(url_for('doctors.dashboard'))
    
    appointment.cancellation_approved = True
    appointment.status = 'cancelled'
    db.session.commit()
    
    flash('Cancellation approved. Patient will be refunded.', 'success')
    return redirect(url_for('doctors.dashboard'))

@doctors_bp.route('/cancellation/<int:appointment_id>/reject', methods=['POST'])
@doctor_required
def reject_cancellation(appointment_id):
    """Reject appointment cancellation"""
    user = get_current_user()
    doctor = user.doctor_profile
    
    appointment = Appointment.query.filter_by(
        id=appointment_id,
        doctor_id=doctor.id
    ).first()
    
    if not appointment:
        flash('Appointment not found.', 'error')
        return redirect(url_for('doctors.dashboard'))
    
    appointment.cancellation_requested = False
    appointment.cancellation_reason = None
    db.session.commit()
    
    flash('Cancellation request rejected.', 'info')
    return redirect(url_for('doctors.dashboard'))

@doctors_bp.route('/blogs')
@doctor_required
def blogs():
    """Doctor's blogs management"""
    user = get_current_user()
    doctor = user.doctor_profile
    
    blogs = Blog.query.filter_by(doctor_id=doctor.id).order_by(
        Blog.created_at.desc()
    ).all()
    
    return render_template('doctors/blogs.html', blogs=blogs)

@doctors_bp.route('/blogs/new', methods=['GET', 'POST'])
@doctor_required
def new_blog():
    """Create new blog post"""
    # Check if doctor is approved
    approval_check = check_doctor_approval()
    if approval_check:
        return approval_check
    
    user = get_current_user()
    doctor = user.doctor_profile
    
    form = BlogForm()
    if form.validate_on_submit():
        # Handle featured image upload
        featured_image_path = None
        if 'featured_image' in request.files and request.files['featured_image'].filename:
            from app.utils.file_upload import save_uploaded_file
            file = request.files['featured_image']
            success, file_path, error = save_uploaded_file(file, 'blog_covers')
            if success:
                featured_image_path = file_path
            else:
                flash(f'Error uploading featured image: {error}', 'error')
                return render_template('doctors/new_blog.html', form=form)

        # Enforce draft first workflow
        status = 'draft'
        published_at = None

        blog = Blog(
            doctor_id=doctor.id,
            title=form.title.data,
            content=form.content.data,
            excerpt=form.excerpt.data,
            tags=form.tags.data,
            category=form.category.data,
            featured_image=featured_image_path,
            references=form.references.data,
            meta_title=form.meta_title.data,
            meta_description=form.meta_description.data,
            status=status,
            published_at=published_at
        )
        
        db.session.add(blog)
        db.session.commit()
        
        flash('Blog post saved as draft! You can preview it and submit for admin review when ready.', 'success')
        return redirect(url_for('doctors.blogs'))
    
    return render_template('doctors/new_blog.html', form=form)

@doctors_bp.route('/blogs/<int:blog_id>/edit', methods=['GET', 'POST'])
@doctor_required
def edit_blog(blog_id):
    """
    Edit existing blog post
    IMPORTANT: Doctors can edit their own articles at any time, even after publishing.
    No approval or permission is required - authors have full control over their content.
    """
    user = get_current_user()
    doctor = user.doctor_profile
    
    # Only allow editing if the blog belongs to this doctor
    # No status checks - authors can edit published articles without restrictions
    blog = Blog.query.filter_by(id=blog_id, doctor_id=doctor.id).first_or_404()
    
    form = BlogForm()
    if form.validate_on_submit():
        blog.title = form.title.data
        blog.content = form.content.data
        blog.excerpt = form.excerpt.data
        blog.tags = form.tags.data
        blog.category = form.category.data
        blog.references = form.references.data
        blog.meta_title = form.meta_title.data
        blog.meta_description = form.meta_description.data
        blog.updated_at = datetime.utcnow()
        
        # Handle featured image changing
        if 'featured_image' in request.files and request.files['featured_image'].filename:
            from app.utils.file_upload import save_uploaded_file
            import os
            file = request.files['featured_image']
            success, file_path, error = save_uploaded_file(file, 'blog_covers')
            if success:
                # Delete old image if exists
                if blog.featured_image:
                    old_path = os.path.join(current_app.config['UPLOAD_FOLDER'], blog.featured_image.replace('/static/uploads/', ''))
                    # wait, file_path from save_uploaded_file is relative to UPLOAD_FOLDER or already has static?
                    # The previous logic in new_blog didn't prepend anything, save_uploaded_file returns 'blog_covers/filename.jpg'
                    # So we construct full path
                    old_path = os.path.join(current_app.config['UPLOAD_FOLDER'], blog.featured_image)
                    if os.path.exists(old_path):
                        try:
                            os.remove(old_path)
                        except Exception as e:
                            print(f"Error removing old image: {e}")
                blog.featured_image = file_path
            else:
                flash(f'Error uploading featured image: {error}', 'error')
                return render_template('doctors/edit_blog.html', form=form, blog=blog)

        # Force draft status upon any edits so doctor can preview before submitting for review
        blog.status = 'draft'
        blog.admin_feedback = None # Clear old feedback
        
        db.session.commit()
        
        flash('Blog post updated and saved as draft. You can submit it for review when satisfied.', 'success')
        return redirect(url_for('doctors.blogs'))
    
    # Populate form with existing data
    form.title.data = blog.title
    form.content.data = blog.content
    form.excerpt.data = blog.excerpt
    form.tags.data = blog.tags
    form.category.data = blog.category
    form.references.data = blog.references
    form.meta_title.data = blog.meta_title
    form.meta_description.data = blog.meta_description
    
    return render_template('doctors/edit_blog.html', form=form, blog=blog)

@doctors_bp.route('/blogs/<int:blog_id>/submit_for_review', methods=['POST'])
@doctor_required
def submit_for_review_blog(blog_id):
    """
    Submits a draft blog for admin review.
    """
    user = get_current_user()
    doctor = user.doctor_profile
    if not doctor:
        flash('Patient accounts cannot submit blogs.', 'error')
        return redirect(url_for('home.index'))
        
    blog = Blog.query.filter_by(id=blog_id, doctor_id=doctor.id).first_or_404()
    
    if blog.status == 'draft' or blog.status == 'rejected':
        blog.status = 'pending'
        blog.admin_feedback = None
        db.session.commit()
        flash('Article submitted successfully for admin review.', 'success')
    else:
        flash('Only drafts or rejected articles can be submitted for review.', 'error')
        
    return redirect(url_for('doctors.blogs'))

@doctors_bp.route('/blogs/<int:blog_id>/delete', methods=['POST'])
@doctor_required
def delete_blog(blog_id):
    """
    Delete blog post
    IMPORTANT: Doctors can delete their own articles at any time, even after publishing.
    No approval or permission is required - authors have full control over their content.
    """
    user = get_current_user()
    doctor = user.doctor_profile
    
    # Only allow deletion if the blog belongs to this doctor
    # No status checks - authors can delete published articles without restrictions
    blog = Blog.query.filter_by(id=blog_id, doctor_id=doctor.id).first_or_404()
    
    try:
        # Delete featured image if exists
        if blog.featured_image:
            import os
            file_path = os.path.join(current_app.config['UPLOAD_FOLDER'], blog.featured_image)
            if os.path.exists(file_path):
                try:
                    os.remove(file_path)
                except Exception as e:
                    print(f"Error removing image file: {e}")
                    
        db.session.delete(blog)
        db.session.commit()
        flash('Blog post deleted successfully!', 'success')
    except Exception as e:
        db.session.rollback()
        flash('Error deleting blog post. Please try again.', 'error')
        print(f'Error deleting blog: {e}')
    
    return redirect(url_for('doctors.blogs'))

@doctors_bp.route('/blogs/upload-image', methods=['POST'])
@doctor_required
def upload_blog_image():
    """Upload image for blog post"""
    if 'image' not in request.files:
        return jsonify({'success': False, 'error': 'No image file provided'}), 400
    
    file = request.files['image']
    
    if file.filename == '':
        return jsonify({'success': False, 'error': 'No image file selected'}), 400
    
    # Check file type
    if not file.content_type.startswith('image/'):
        return jsonify({'success': False, 'error': 'File must be an image'}), 400
    
    # Save image
    from app.utils.file_upload import save_uploaded_file
    
    success, file_path, error = save_uploaded_file(
        file,
        current_app.config['UPLOAD_FOLDER'],
        subfolder='blog_images'
    )
    
    if not success:
        return jsonify({'success': False, 'error': error}), 400
    
    # Return URL for the image
    image_url = f'/static/uploads/{file_path}'
    return jsonify({'success': True, 'url': image_url})

@doctors_bp.route('/qa')
@doctor_required
def qa():
    """Q&A section for doctors"""
    # Check if doctor is approved
    approval_check = check_doctor_approval()
    if approval_check:
        return approval_check
    
    user = get_current_user()
    doctor = user.doctor_profile
    
    # Get unanswered questions in doctor's category (normalized matching)
    from app.utils.categories import normalize_category
    doctor_category = normalize_category(doctor.category)
    
    # Get all questions and filter by normalized category
    all_questions = Question.query.filter_by(
        is_deleted=False
    ).order_by(Question.created_at.desc()).all()
    
    # Filter questions that match doctor's category (case-insensitive normalized)
    questions = []
    for q in all_questions:
        question_category = normalize_category(q.category)
        if question_category.lower() == doctor_category.lower():
            q.pending_days = max((datetime.utcnow() - q.created_at).days, 0)
            q.is_stale = (not q.is_answered) and q.pending_days >= 2
            questions.append(q)

    unanswered_questions = [q for q in questions if not q.is_answered]
    answered_questions = [q for q in questions if q.is_answered]

    return render_template(
        'doctors/qa.html',
        questions=questions,
        unanswered_questions=unanswered_questions,
        answered_questions=answered_questions,
        doctor_category=doctor.category
    )

@doctors_bp.route('/qa/answer/<int:question_id>', methods=['GET', 'POST'])
@doctor_required
def answer_question(question_id):
    """Answer a question - Only doctors in the same category can answer"""
    from app.utils.categories import normalize_category
    from app.utils.timezone import get_pakistan_now
    
    # Check if doctor is approved
    approval_check = check_doctor_approval()
    if approval_check:
        return approval_check
    
    user = get_current_user()
    doctor = user.doctor_profile
    
    question = Question.query.filter_by(
        id=question_id,
        is_deleted=False
    ).first_or_404()
    is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
    
    # Check if doctor's category matches question category
    doctor_category = normalize_category(doctor.category)
    question_category = normalize_category(question.category)
    
    if doctor_category.lower() != question_category.lower():
        if is_ajax:
            return jsonify({
                'success': False,
                'message': f'You can only answer questions in your category ({doctor.category}).'
            }), 403
        flash(f'You can only answer questions in your category ({doctor.category}). This question is in {question.category} category.', 'error')
        return redirect(url_for('doctors.qa'))
    
    if request.method == 'POST':
        content = request.form.get('content', '').strip()
        if not content:
            if is_ajax:
                return jsonify({'success': False, 'message': 'Answer content cannot be empty.'}), 400
            flash('Answer content cannot be empty.', 'error')
            return render_template('doctors/answer_question.html', question=question)
        
        # Check if doctor already answered this question
        existing_answer = Answer.query.filter_by(
            question_id=question.id,
            doctor_id=doctor.id,
            is_deleted=False
        ).first()
        
        if existing_answer:
            if is_ajax:
                return jsonify({'success': False, 'message': 'You have already answered this question.'}), 409
            flash('You have already answered this question.', 'info')
            return redirect(url_for('qa.view_question', question_id=question.id))
        
        answer = Answer(
            question_id=question.id,
            doctor_id=doctor.id,
            content=content
        )
        
        # Mark question as answered if it wasn't already
        if not question.is_answered:
            question.is_answered = True
        question.updated_at = get_pakistan_now()
        question.last_activity_at = get_pakistan_now()
        
        db.session.add(answer)
        
        try:
            db.session.commit()
            if is_ajax:
                return jsonify({
                    'success': True,
                    'message': 'Answer posted successfully!',
                    'answer': {
                        'id': answer.id,
                        'doctor_name': answer.doctor.user.name,
                        'doctor_category': answer.doctor.category,
                        'doctor_experience': int(answer.doctor.experience) if answer.doctor.experience is not None else None,
                        'created_at': answer.created_at.strftime('%b %d, %Y'),
                        'content': answer.content,
                        'book_url': url_for('patients.find_doctors') + f'?category={answer.doctor.category}'
                    }
                })
            flash('Answer posted successfully!', 'success')
            return redirect(url_for('qa.view_question', question_id=question.id))
        except Exception as e:
            db.session.rollback()
            if is_ajax:
                return jsonify({'success': False, 'message': 'Failed to post answer. Please try again.'}), 500
            flash('Failed to post answer. Please try again.', 'error')
            print(f'Error posting answer: {e}')
    
    # Get existing answers for this question
    answers = Answer.query.filter_by(
        question_id=question_id,
        is_deleted=False
    ).order_by(Answer.created_at.asc()).all()
    
    return render_template('doctors/answer_question.html', question=question, answers=answers)

@doctors_bp.route('/submit-appeal', methods=['POST'])
@doctor_required
def submit_appeal():
    """Submit appeal for rejected registration"""
    user = get_current_user()
    doctor = user.doctor_profile
    
    if doctor.appeal_status not in ['rejected', 'suspended']:
        flash('No appeal needed. Your registration is not rejected.', 'info')
        return redirect(url_for('doctors.dashboard'))
    
    if doctor.appeal_status == 'suspended' or doctor.appeal_count >= 3:
        flash('Your account is suspended. Maximum appeals reached.', 'error')
        return redirect(url_for('doctors.dashboard'))
    
    # Update appeal count and status
    doctor.appeal_count += 1
    doctor.appeal_status = 'pending'
    doctor.rejection_reason = None  # Clear previous rejection reason
    doctor.rejection_date = None
    
    db.session.commit()
    
    flash('Your appeal has been submitted successfully. Admin will review it soon.', 'success')
    return redirect(url_for('doctors.dashboard'))

@doctors_bp.route('/edit-registration')
@doctor_required
def edit_registration():
    """Edit registration form for appeals"""
    user = get_current_user()
    doctor = user.doctor_profile
    
    # Refresh doctor object from database to get latest status
    db.session.refresh(doctor)
    
    # Check if appeal is still allowed
    if doctor.appeal_status not in ['rejected', 'suspended']:
        if doctor.appeal_status == 'pending':
            flash('Your appeal is already pending review. Please wait for admin approval.', 'info')
        else:
            flash('No appeal needed. Your registration is not rejected.', 'info')
        return redirect(url_for('doctors.dashboard'))
    
    if doctor.appeal_status == 'suspended' or doctor.appeal_count >= 3:
        flash('Your account is suspended. Maximum appeals reached.', 'error')
        return redirect(url_for('doctors.dashboard'))
    
    # Import here to avoid circular imports
    from app.forms import UnifiedRegistrationForm
    from app.models import User
    from wtforms.validators import ValidationError, Optional, Length, EqualTo
    from wtforms import PasswordField
    
    # Create a custom form class that excludes current user from validation and makes password optional
    class AppealRegistrationForm(UnifiedRegistrationForm):
        # Make password fields optional for appeals (don't require password change)
        # Import password validator
        from app.forms import validate_password_strength
        password = PasswordField('Password', validators=[Optional(), Length(min=8), validate_password_strength])
        password2 = PasswordField('Confirm Password', validators=[Optional(), EqualTo('password')])
        
        def validate_email(self, email):
            # Allow current user's email - only check if email is used by another user
            existing_user = User.query.filter_by(email=email.data).first()
            if existing_user and existing_user.id != user.id:
                raise ValidationError('This email is already registered. One email can only be used once.')
        
        def validate_cnic(self, cnic):
            # Check if CNIC is exactly 13 digits
            if not cnic.data.isdigit():
                raise ValidationError('CNIC must contain only numbers.')
            
            if len(cnic.data) != 13:
                raise ValidationError('CNIC must be exactly 13 digits.')
            
            # Allow current user's CNIC - only check if CNIC is used by another user
            existing_user = User.query.filter_by(cnic=cnic.data).first()
            if existing_user and existing_user.id != user.id:
                raise ValidationError('This CNIC is already registered. One CNIC can only be used once.')
    
    # Pre-populate form with existing data
    form = AppealRegistrationForm()
    
    # Populate form with existing doctor data
    form.name.data = user.name
    form.email.data = user.email
    form.phone.data = user.phone
    form.cnic.data = user.cnic
    
    # Format date of birth as string (YYYY-MM-DD) for the form
    if user.date_of_birth:
        if isinstance(user.date_of_birth, str):
            form.date_of_birth.data = user.date_of_birth
        else:
            form.date_of_birth.data = user.date_of_birth.isoformat()
    else:
        form.date_of_birth.data = None
    
    form.gender.data = user.gender
    # Address field removed - only city is needed
    form.role.data = 'doctor'
    
    # Doctor specific fields
    form.category.data = doctor.category
    form.specialization.data = doctor.specialization
    form.experience.data = doctor.experience
    form.pmc_code.data = doctor.pmc_code
    form.education.data = doctor.education
    form.bio.data = doctor.bio
    # Hospital affiliation removed
    form.city.data = doctor.city
    form.location.data = doctor.location
    
    return render_template('doctors/edit_registration.html', form=form, doctor=doctor)

@doctors_bp.route('/update-registration', methods=['POST'])
@doctor_required
def update_registration():
    """Update registration and submit appeal"""
    user = get_current_user()
    doctor = user.doctor_profile
    
    # Refresh doctor object from database to get latest status
    db.session.refresh(doctor)
    
    if doctor.appeal_status not in ['rejected', 'suspended']:
        flash('No appeal needed. Your registration is not rejected.', 'info')
        return redirect(url_for('doctors.dashboard'))
    
    if doctor.appeal_status == 'suspended' or doctor.appeal_count >= 3:
        flash('Your account is suspended. Maximum appeals reached.', 'error')
        return redirect(url_for('doctors.dashboard'))
    
    # Import here to avoid circular imports
    from app.forms import UnifiedRegistrationForm
    from app.utils.file_upload import save_uploaded_file
    from flask import request
    from app.models import User
    from wtforms.validators import ValidationError, Optional, Length, EqualTo
    from wtforms import PasswordField
    
    # Create a custom form class that excludes current user from validation and makes password optional
    from wtforms import SelectField
    
    class AppealRegistrationForm(UnifiedRegistrationForm):
        # Make password fields optional for appeals (don't require password change)
        # Import password validator
        from app.forms import validate_password_strength
        password = PasswordField('Password', validators=[Optional(), Length(min=8), validate_password_strength])
        password2 = PasswordField('Confirm Password', validators=[Optional(), EqualTo('password')])
        
        # Override role field to always be 'doctor' for appeals (make it hidden/optional)
        role = SelectField('I want to register as:', 
                          choices=[('doctor', 'Doctor')],
                          default='doctor',
                          validators=[Optional()])  # Make optional since it's always doctor for appeals
        
        def validate_email(self, email):
            # Allow current user's email - only check if email is used by another user
            if email.data:
                existing_user = User.query.filter_by(email=email.data).first()
                if existing_user and existing_user.id != user.id:
                    raise ValidationError('This email is already registered. One email can only be used once.')
        
        def validate_cnic(self, cnic):
            # Check if CNIC is exactly 13 digits
            if cnic.data:
                if not cnic.data.isdigit():
                    raise ValidationError('CNIC must contain only numbers.')
                
                if len(cnic.data) != 13:
                    raise ValidationError('CNIC must be exactly 13 digits.')
                
                # Allow current user's CNIC - only check if CNIC is used by another user
                existing_user = User.query.filter_by(cnic=cnic.data).first()
                if existing_user and existing_user.id != user.id:
                    raise ValidationError('This CNIC is already registered. One CNIC can only be used once.')
        
        def validate_password(self, password):
            # Only validate if password is provided - use the same strong password requirements
            if password.data:
                from app.forms import validate_password_strength
                validate_password_strength(self, password)
        
        def validate_password2(self, password2):
            # Only validate password match if password is provided
            if self.password.data:
                if not password2.data:
                    raise ValidationError('Please confirm your password.')
                if self.password.data != password2.data:
                    raise ValidationError('Passwords must match.')
        
        def validate_pmc_code(self, pmc_code):
            # Allow current doctor's PMC code - only check if used by another doctor
            if pmc_code.data:
                from app.models import Doctor
                existing_doctor = Doctor.query.filter_by(pmc_code=pmc_code.data).first()
                if existing_doctor and existing_doctor.id != doctor.id:
                    raise ValidationError('PMC Code already registered. Please use a different PMC code.')
        
        def validate_role(self, role):
            # Always set role to 'doctor' for appeals - no validation needed
            # This ensures the role field is always set correctly
            pass
    
    form = AppealRegistrationForm()
    
    # For POST requests, process the form data first
    if request.method == 'POST':
        # Process form data from POST request
        form.process(formdata=request.form, data={'role': 'doctor'})
        # Ensure role is set to 'doctor' (appeals are always for doctors)
        form.role.data = 'doctor'
    else:
        # For GET requests, just set the default
        form.role.data = 'doctor'
    
    if form.validate_on_submit():
        try:
            # Update user data
            user.name = form.name.data
            user.email = form.email.data
            user.phone = form.phone.data
            user.cnic = form.cnic.data
            
            # Handle date of birth - convert string to date object if provided
            if form.date_of_birth.data:
                try:
                    from datetime import date
                    if isinstance(form.date_of_birth.data, str):
                        user.date_of_birth = date.fromisoformat(form.date_of_birth.data)
                    else:
                        user.date_of_birth = form.date_of_birth.data
                except (ValueError, TypeError):
                    pass  # Keep existing date if conversion fails
            
            user.gender = form.gender.data
            # Address field removed - only city is needed
            
            # Update password only if provided
            if form.password.data and form.password.data.strip():
                user.set_password(form.password.data)
            
            # Update doctor data - normalize category
            specialization_input = form.specialization.data or form.category.data or ''
            normalized_category = normalize_category(specialization_input)
            doctor.category = normalized_category
            doctor.specialization = normalized_category
            doctor.experience = form.experience.data
            doctor.pmc_code = form.pmc_code.data
            doctor.education = form.education.data
            doctor.bio = form.bio.data
            # Hospital affiliation removed
            doctor.city = form.city.data
            doctor.location = form.location.data
            
            # Handle file uploads if provided
            # Check if CNIC front should be removed
            if request.form.get('remove_cnic_front') == '1':
                doctor.cnic_front_image = None
            
            if form.cnic_front.data:
                success, file_path, error = save_uploaded_file(form.cnic_front.data, 'cnic')
                if success:
                    doctor.cnic_front_image = file_path
            
            # Check if CNIC back should be removed
            if request.form.get('remove_cnic_back') == '1':
                doctor.cnic_back_image = None
            
            if form.cnic_back.data:
                success, file_path, error = save_uploaded_file(form.cnic_back.data, 'cnic')
                if success:
                    doctor.cnic_back_image = file_path
            
            # Handle degree documents - remove specified documents first
            remove_degree_docs = request.form.get('remove_degree_docs', '')
            if remove_degree_docs:
                # Get indices to remove
                indices_to_remove = [int(idx) for idx in remove_degree_docs.split(',') if idx.strip()]
                if doctor.degree_documents and indices_to_remove:
                    # Remove documents at specified indices (reverse order to maintain indices)
                    current_docs = doctor.degree_documents.copy()
                    for idx in sorted(indices_to_remove, reverse=True):
                        if 0 <= idx < len(current_docs):
                            current_docs.pop(idx)
                    doctor.degree_documents = current_docs if current_docs else []
            
            # Handle new degree documents upload
            degree_files = request.files.getlist('degree_files[]')
            if degree_files:
                new_degree_documents = []
                for degree_file in degree_files:
                    if degree_file.filename:  # Only process if a file was actually selected
                        success, file_path, error = save_uploaded_file(degree_file, 'degrees')
                        if success:
                            new_degree_documents.append(file_path)
                # Append new documents to existing ones (if any remain after removal)
                if new_degree_documents:
                    if doctor.degree_documents:
                        doctor.degree_documents.extend(new_degree_documents)
                    else:
                        doctor.degree_documents = new_degree_documents
            
            # Handle live photo - only update if new photo is captured
            if form.live_photo_data.data:
                from app.routes.auth import save_base64_image
                live_photo_path = save_base64_image(form.live_photo_data.data, 'live_photos')
                if live_photo_path:
                    doctor.live_photo = live_photo_path
            # If no new photo captured, existing photo remains unchanged
            
            # Submit appeal - update status BEFORE commit to ensure redirect works
            doctor.appeal_count += 1
            doctor.appeal_status = 'pending'
            doctor.rejection_reason = None
            doctor.rejection_date = None
            
            # Commit all changes to database
            db.session.commit()
            
            # Get the updated appeal count for the success message (before redirect)
            appeal_count = doctor.appeal_count
            
            # IMPORTANT: Set flash message and redirect IMMEDIATELY after commit
            # This ensures we never render the template after a successful submission
            flash(f'Your registration has been updated and appeal #{appeal_count} submitted successfully! Admin will review your appeal shortly.', 'success')
            
            # CRITICAL: Always redirect after successful commit - never render template
            # Redirect to dashboard which will show the profile page for pending doctors
            return redirect(url_for('doctors.dashboard'))
            
        except Exception as e:
            # Only rollback on exception - don't redirect
            db.session.rollback()
            flash(f'Error updating registration: {str(e)}. Please try again.', 'error')
            import traceback
            traceback.print_exc()  # Print to console for debugging
            print(f"Error in update_registration: {traceback.format_exc()}")
            # Fall through to show form with errors - this is the ONLY case where we render template after POST
    
    # If form validation failed, Flask-WTF keeps the submitted data in form.data
    # We only need to populate with existing data if this is a GET request or if form has no data
    # For POST requests with validation errors, the form already has the submitted data
    
    # Handle form validation failures
    if request.method == 'POST' and not form.validate():
        # Form validation failed - show errors
        error_count = len(form.errors)
        if error_count > 0:
            flash(f'Please correct {error_count} error(s) in the form below.', 'error')
        else:
            flash('Please correct the errors in the form below.', 'error')
        # Don't redirect - show form with errors
    
    # Populate form with existing data if this is a GET request or if form has no data
    # For POST requests with validation errors, Flask-WTF already has the submitted data
    if request.method == 'GET' or not form.name.data:
        form.name.data = user.name
        form.email.data = user.email
        form.phone.data = user.phone
        form.cnic.data = user.cnic
        
        # Format date of birth as string (YYYY-MM-DD) for the form
        if user.date_of_birth:
            if isinstance(user.date_of_birth, str):
                form.date_of_birth.data = user.date_of_birth
            else:
                form.date_of_birth.data = user.date_of_birth.isoformat()
        else:
            form.date_of_birth.data = None
        
        form.gender.data = user.gender
        # Address field removed - only city is needed
        form.role.data = 'doctor'
        
        # Doctor specific fields
        form.category.data = doctor.category
        form.specialization.data = doctor.specialization
        form.experience.data = doctor.experience
        form.pmc_code.data = doctor.pmc_code
        form.education.data = doctor.education
        form.bio.data = doctor.bio
        # Hospital affiliation removed
        form.city.data = doctor.city
        form.location.data = doctor.location
    
    return render_template('doctors/edit_registration.html', form=form, doctor=doctor)
