from flask import Blueprint, render_template, request, flash, redirect, url_for, session, jsonify, current_app, send_from_directory
from app.models import (
    Patient,
    Doctor,
    Appointment,
    MedicalHistory,
    MedicalDocument,
    Question,
    Answer,
    Refund,
    RefundPayoutDetail,
    Review,
    Blog,
)
from app.database import db
from app.forms import AppointmentBookingForm, QuestionForm
from app.utils.auth import patient_required, get_current_user, login_required
from app.utils.categories import normalize_category, get_category_display_name
from sqlalchemy import func, and_, or_
from datetime import datetime, date, time, timedelta
import json
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import joinedload
import uuid
import os
from werkzeug.utils import secure_filename
import datetime as dt
from app.services.email_service import send_manual_payment_admin_notification
from app.utils.appointment_workflow import set_booking_payment_deadline

patients_bp = Blueprint('patients', __name__)

@patients_bp.route('/dashboard')
@patient_required
def dashboard():
    """Patient dashboard"""
    user = get_current_user()
    patient = user.patient_profile
    
    # Get appointment statistics
    total_appointments = Appointment.query.filter_by(patient_id=patient.id).count()
    pending_appointments = Appointment.query.filter_by(
        patient_id=patient.id, 
        status='pending'
    ).count()
    approved_appointments = Appointment.query.filter_by(
        patient_id=patient.id, 
        status='approved'
    ).count()
    completed_appointments = Appointment.query.filter_by(
        patient_id=patient.id, 
        status='completed'
    ).count()

    pending_refunds_count = Refund.query.filter_by(patient_id=patient.id, status='pending').count()
    
    # Get recent appointments
    recent_appointments = Appointment.query.filter_by(
        patient_id=patient.id
    ).order_by(Appointment.created_at.desc()).limit(5).all()
    
    # Get upcoming appointments
    upcoming_appointments = Appointment.query.filter(
        Appointment.patient_id == patient.id,
        Appointment.status == 'approved',
        Appointment.appointment_date >= date.today()
    ).order_by(Appointment.appointment_date, Appointment.appointment_time).limit(3).all()
    
    # Check if profile is incomplete
    profile_incomplete = not patient.is_profile_complete()
    if profile_incomplete:
        session['profile_incomplete'] = True
    
    stats = {
        'total': total_appointments,
        'pending': pending_appointments,
        'approved': approved_appointments,
        'completed': completed_appointments,
        'pending_refunds': pending_refunds_count,
    }
    
    return render_template('patients/dashboard.html',
                         patient=patient,
                         stats=stats,
                         recent_appointments=recent_appointments,
                         upcoming_appointments=upcoming_appointments,
                         profile_incomplete=profile_incomplete)

@patients_bp.route('/profile')
@patient_required
def profile():
    """Patient profile view page - shows profile information and patient-related data"""
    user = get_current_user()
    patient = user.patient_profile
    
    # Check if profile is incomplete
    profile_incomplete = not patient.is_profile_complete()
    
    # Get appointment statistics
    total_appointments = Appointment.query.filter_by(patient_id=patient.id).count()
    pending_appointments = Appointment.query.filter_by(
        patient_id=patient.id, 
        status='pending'
    ).count()
    approved_appointments = Appointment.query.filter_by(
        patient_id=patient.id, 
        status='approved'
    ).count()
    completed_appointments = Appointment.query.filter_by(
        patient_id=patient.id, 
        status='completed'
    ).count()
    
    # Get recent appointments (last 5)
    recent_appointments = Appointment.query.filter_by(
        patient_id=patient.id
    ).order_by(Appointment.created_at.desc()).limit(5).all()
    
    # Get upcoming appointments
    upcoming_appointments = Appointment.query.filter(
        Appointment.patient_id == patient.id,
        Appointment.status == 'approved',
        Appointment.appointment_date >= date.today()
    ).order_by(Appointment.appointment_date, Appointment.appointment_time).limit(5).all()
    
    # Get questions count
    questions_count = Question.query.filter_by(patient_id=patient.id).count()
    
    # Get medical history count
    medical_history_count = MedicalHistory.query.filter_by(patient_id=patient.id).count()
    
    stats = {
        'total_appointments': total_appointments,
        'pending': pending_appointments,
        'approved': approved_appointments,
        'completed': completed_appointments,
        'questions': questions_count,
        'medical_history': medical_history_count
    }
    
    return render_template('patients/profile.html', 
                         patient=patient, 
                         profile_incomplete=profile_incomplete,
                         stats=stats,
                         recent_appointments=recent_appointments,
                         upcoming_appointments=upcoming_appointments)

@patients_bp.route('/complete-profile')
@patient_required
def complete_profile():
    """Redirect to edit profile page to complete profile"""
    user = get_current_user()
    patient = user.patient_profile
    
    profile_incomplete = not patient.is_profile_complete()
    if profile_incomplete:
        flash('Please complete all required fields to access all features.', 'info')
        return redirect(url_for('patients.edit_profile'))
    else:
        flash('Your profile is already complete!', 'success')
        return redirect(url_for('patients.profile'))

@patients_bp.route('/profile/edit', methods=['GET', 'POST'])
@patient_required
def edit_profile():
    """Edit patient profile"""
    user = get_current_user()
    patient = user.patient_profile
    
    if request.method == 'POST':
        # Update user info
        user.name = request.form.get('name', user.name)
        user.phone = request.form.get('phone', user.phone)
        
        # Parse date of birth
        date_of_birth_str = request.form.get('date_of_birth', '')
        if date_of_birth_str:
            try:
                user.date_of_birth = datetime.strptime(date_of_birth_str, '%Y-%m-%d').date()
            except ValueError:
                flash('Invalid date format. Please use YYYY-MM-DD format.', 'error')
                profile_incomplete = not patient.is_profile_complete()
                today = date.today()
                return render_template('patients/edit_profile.html', patient=patient, profile_incomplete=profile_incomplete, today=today)
        
        # Update user profile fields
        user.gender = request.form.get('gender', user.gender) or user.gender
        # Address field removed - only city is needed
        
        # Update patient info
        patient.emergency_contact = request.form.get('emergency_contact', patient.emergency_contact) or patient.emergency_contact
        patient.emergency_relation = request.form.get('emergency_relation', patient.emergency_relation) or patient.emergency_relation
        patient.blood_group = request.form.get('blood_group', patient.blood_group) or patient.blood_group
        patient.allergies = request.form.get('allergies', patient.allergies) or patient.allergies
        patient.medical_history = request.form.get('medical_history', patient.medical_history) or patient.medical_history
        
        # Handle profile picture upload
        from app.utils.file_upload import save_uploaded_file
        
        if 'profile_picture' in request.files:
            profile_picture_file = request.files['profile_picture']
            if profile_picture_file and profile_picture_file.filename:
                success, file_path, error = save_uploaded_file(profile_picture_file, 'profile_pictures')
                if success:
                    user.profile_picture = file_path
                else:
                    flash(f'Error uploading profile picture: {error}', 'error')
                    profile_incomplete = not patient.is_profile_complete()
                    today = date.today()
                    return render_template('patients/edit_profile.html', patient=patient, profile_incomplete=profile_incomplete, today=today)
        
        # Handle CNIC image uploads
        if 'cnic_front' in request.files:
            cnic_front_file = request.files['cnic_front']
            if cnic_front_file and cnic_front_file.filename:
                success, file_path, error = save_uploaded_file(cnic_front_file, 'cnic')
                if success:
                    patient.cnic_front_image = file_path
                else:
                    flash(f'Error uploading CNIC front image: {error}', 'error')
                    profile_incomplete = not patient.is_profile_complete()
                    today = date.today()
                    return render_template('patients/edit_profile.html', patient=patient, profile_incomplete=profile_incomplete, today=today)
        
        if 'cnic_back' in request.files:
            cnic_back_file = request.files['cnic_back']
            if cnic_back_file and cnic_back_file.filename:
                success, file_path, error = save_uploaded_file(cnic_back_file, 'cnic')
                if success:
                    patient.cnic_back_image = file_path
                else:
                    flash(f'Error uploading CNIC back image: {error}', 'error')
                    profile_incomplete = not patient.is_profile_complete()
                    today = date.today()
                    return render_template('patients/edit_profile.html', patient=patient, profile_incomplete=profile_incomplete, today=today)
        
        patient.updated_at = datetime.utcnow()
        
        db.session.commit()
        
        # Check if profile is now complete
        if patient.is_profile_complete():
            session.pop('profile_incomplete', None)
            flash('Profile completed successfully! You can now book appointments and post questions.', 'success')
        else:
            flash('Profile updated successfully! Please complete all required fields to access all features.', 'info')
        
        return redirect(url_for('patients.profile'))
    
    # Check if profile is incomplete
    profile_incomplete = not patient.is_profile_complete()
    
    # Get today's date for max date in date picker
    today = date.today()
    
    return render_template('patients/edit_profile.html', 
                         patient=patient, 
                         profile_incomplete=profile_incomplete,
                         today=today)

@patients_bp.route('/find-doctors')
def find_doctors():
    """Find doctors page with category selection - Show curated common categories"""
    from app.utils.categories import (
        DISPLAY_CATEGORIES, get_category_display_name, normalize_category,
        get_category_icon
    )
    
    # Get specialty parameter from URL
    specialty = request.args.get('specialty', '')
    
    # If specialty is specified, normalize it and redirect to doctors list with that category
    if specialty:
        normalized_specialty = normalize_category(specialty)
        return redirect(url_for('patients.doctors_by_category', category=normalized_specialty.lower()))
    
    # Build category list with icon info (curated list only)
    all_categories = []
    for category in DISPLAY_CATEGORIES:
        display_name = get_category_display_name(category)
        normalized = normalize_category(category).lower()
        icon = get_category_icon(category)
        all_categories.append({
            'display': display_name,
            'slug': normalized,
            'png': icon['png'],
            'fa': icon['fa'],
        })
    
    # Sort alphabetically
    all_categories = sorted(all_categories, key=lambda x: x['display'])
    
    return render_template('patients/find_doctors.html', categories=all_categories)

@patients_bp.route('/doctors/category/<category>')
def doctors_by_category(category):
    """Show doctors by category with filters - Only show doctors who have time slots configured"""
    from app.utils.practice_organizer import organize_by_practice
    from app.utils.categories import normalize_category
    from sqlalchemy import func
    
    # Normalize the category from URL to match database format
    normalized_category = normalize_category(category)
    
    # Get filter parameters
    appointment_type = request.args.get('type', 'all')
    gender = request.args.get('gender', 'all')
    city = request.args.get('city', 'all')
    fee_range = request.args.get('fee_range', 'all')
    
    # Build query - Only doctors who have time slots (have listed appointments)
    # Use case-insensitive comparison to handle any case mismatches
    query = Doctor.query.filter(
        Doctor.is_approved == True,
        Doctor.is_verified == True,
        func.lower(Doctor.category) == func.lower(normalized_category),
        Doctor.time_slots.isnot(None),
        Doctor.time_slots != {}
    )
    
    if city != 'all':
        query = query.filter(Doctor.city == city)
    
    if gender != 'all':
        query = query.join(User).filter(User.gender == gender)
    
    doctors = query.order_by(Doctor.created_at.desc()).all()
    
    # Filter doctors by appointment type and extract pricing info
    # Only include doctors who have actually configured appointment slots
    filtered_doctors = []
    for doctor in doctors:
        practices = organize_by_practice(doctor.time_slots) if doctor.time_slots else {}
        
        # Skip doctors who don't have any valid appointment slots configured
        # (organize_by_practice only includes days with start_time/end_time)
        if not practices:
            continue
        
        # Also check that time_slots has at least one day with valid appointment configuration
        has_valid_slots = False
        if doctor.time_slots:
            for day, day_config in doctor.time_slots.items():
                if isinstance(day_config, dict) and day_config.get('start_time') and day_config.get('end_time'):
                    has_valid_slots = True
                    break
        
        if not has_valid_slots:
            continue
        
        has_video = False
        has_physical = False
        video_price = None
        physical_price = None
        
        for practice_name, practice_data in practices.items():
            if practice_data.get('video_price'):
                has_video = True
                if video_price is None or practice_data['video_price'] < video_price:
                    video_price = practice_data['video_price']
            
            if practice_data.get('physical_price'):
                has_physical = True
                if physical_price is None or practice_data['physical_price'] < physical_price:
                    physical_price = practice_data['physical_price']
        
        # Apply appointment type filter
        if appointment_type == 'video' and not has_video:
            continue
        elif appointment_type == 'physical' and not has_physical:
            continue
        
        # Apply fee range filter
        if fee_range != 'all' and fee_range:
            min_fee = float('inf')
            if has_video and video_price:
                min_fee = min(min_fee, video_price)
            if has_physical and physical_price:
                min_fee = min(min_fee, physical_price)
            
            if fee_range == 'below_1000' and min_fee >= 1000:
                continue
            elif fee_range == '1000_2000' and (min_fee < 1000 or min_fee > 2000):
                continue
            elif fee_range == '2000_3000' and (min_fee < 2000 or min_fee > 3000):
                continue
            elif fee_range == '3000_5000' and (min_fee < 3000 or min_fee > 5000):
                continue
            elif fee_range == 'above_5000' and min_fee <= 5000:
                continue
        
        # ── Compute dynamic availability label per practice ──────────────────
        def get_next_available_label(practice_days: dict) -> str:
            """Return 'Available Today', 'Available Tomorrow', or 'Available from [Date]'."""
            from datetime import date, timedelta
            day_names = ['monday','tuesday','wednesday','thursday','friday','saturday','sunday']
            today = date.today()
            for offset in range(0, 14):  # Check next 14 days
                check_date = today + timedelta(days=offset)
                day_name = check_date.strftime('%A').lower()
                if day_name in practice_days:
                    if offset == 0:
                        return 'Available Today'
                    elif offset == 1:
                        return 'Available Tomorrow'
                    else:
                        return f'Available from {check_date.strftime("%b")} {check_date.day}'
            return 'Check Schedule'

        # Enrich each practice with its availability label
        for practice_name, practice_data in practices.items():
            practice_days = practice_data.get('days', {})
            practice_data['availability_label'] = get_next_available_label(practice_days)

        # Add pricing info and practices to doctor object (for template use)
        doctor.video_price = video_price
        doctor.physical_price = physical_price
        doctor.has_video = has_video
        doctor.has_physical = has_physical
        doctor.practices = practices  # Store practices for template

        filtered_doctors.append(doctor)

    
    # Get available cities for filter
    cities = Doctor.query.filter(
        Doctor.is_approved == True,
        Doctor.is_verified == True,
        func.lower(Doctor.category) == func.lower(normalized_category),
        Doctor.time_slots.isnot(None),
        Doctor.time_slots != {}
    ).with_entities(Doctor.city).distinct().all()
    cities = sorted([c[0] for c in cities if c[0]])
    
    # Get category display name
    from app.utils.categories import get_category_display_name
    category_display = get_category_display_name(normalized_category)
    
    return render_template('patients/doctors_list.html',
                         doctors=filtered_doctors,
                         category=category,
                         category_display=category_display,
                         current_type=appointment_type,
                         current_gender=gender,
                         current_city=city,
                         current_fee_range=fee_range,
                         cities=cities)

@patients_bp.route('/doctor/<int:doctor_id>')
@login_required
def doctor_profile(doctor_id):
    """View doctor profile - Shows both approved and pending doctors (login required)"""
    from app.utils.practice_organizer import organize_by_practice
    from datetime import date, timedelta
    
    # Query doctor with fresh data from database (SQLAlchemy will query from DB)
    doctor = Doctor.query.filter_by(id=doctor_id).first_or_404()
    
    # Check if doctor is approved
    is_approved = doctor.is_approved and doctor.is_verified
    is_pending = not doctor.is_approved and doctor.appeal_status == 'pending'
    is_rejected = not doctor.is_approved and doctor.appeal_status == 'rejected'
    is_suspended = not doctor.is_approved and doctor.appeal_status == 'suspended'
    
    # Organize practices for appointment booking
    practices = {}
    if doctor.time_slots:
        practices = organize_by_practice(doctor.time_slots)

    # Keep completed appointment count for profile template compatibility
    completed_appointments = doctor.appointments.filter_by(status='completed').count()
    
    # ─── Real review stats from patient reviews (persisted in `reviews` table) ───
    now_utc = datetime.utcnow()
    from app.utils.review_fraud import public_reviews_query
    visible_reviews = (
        public_reviews_query()
        .options(joinedload(Review.patient).joinedload(Patient.user))
        .filter_by(doctor_id=doctor.id)
        .order_by(Review.created_at.desc())
        .all()
    )
    total_reviews = len(visible_reviews)

    # Published articles only (same rules as public blog listing)
    published_blogs = (
        Blog.query.filter(
            Blog.doctor_id == doctor.id,
            Blog.status == "published",
            Blog.is_deleted == False,
            or_(Blog.published_at.is_(None), Blog.published_at <= now_utc),
        )
        .order_by(Blog.published_at.desc().nullslast(), Blog.updated_at.desc())
        .limit(3)
        .all()
    )

    if total_reviews > 0:
        avg = round(sum(r.rating for r in visible_reviews) / total_reviews, 1)
        # Collect all selected tags for breakdown display
        tag_counts = {}
        for r in visible_reviews:
            for tag in (r.tags or []):
                tag_counts[tag] = tag_counts.get(tag, 0) + 1
        review_stats = {
            'average_rating': avg,
            'total_reviews': total_reviews,
            'top_tags': sorted(tag_counts, key=tag_counts.get, reverse=True)[:3],
            # Keep legacy keys so template doesn't break (set to 0 when real data exists)
            'wait_time': 0,
            'avg_consultation_time': 0,
            'patient_satisfaction': avg,
            'diagnosis_accuracy': avg,
            'staff_behaviour': avg,
            'clinic_environment': avg,
        }
    else:
        review_stats = {
            'average_rating': 0,
            'total_reviews': 0,
            'top_tags': [],
            'wait_time': 0,
            'avg_consultation_time': 0,
            'patient_satisfaction': 0,
            'diagnosis_accuracy': 0,
            'staff_behaviour': 0,
            'clinic_environment': 0,
        }

    
    # Get doctor's answered questions
    doctor_questions = doctor.answers.order_by(Answer.created_at.desc()).limit(5).all()
    
    # ─── Similar doctors in same category (for carousel) ──────────────
    similar_doctors = (
        Doctor.query.options(joinedload(Doctor.user))
        .filter(
            Doctor.is_approved == True,
            Doctor.is_verified == True,
            Doctor.category == doctor.category,
            Doctor.id != doctor.id,
        )
        .order_by(Doctor.created_at.desc())
        .limit(48)
        .all()
    )
    
    return render_template('patients/doctor_profile.html', 
                             doctor=doctor,
                             is_approved=is_approved,
                             is_pending=is_pending,
                             is_rejected=is_rejected,
                             is_suspended=is_suspended,
                             is_own_profile=False,
                             practices=practices,
                             completed_appointments=completed_appointments,
                             review_stats=review_stats,
                             visible_reviews=visible_reviews,
                             published_blogs=published_blogs,
                             similar_doctors=similar_doctors,
                             doctor_questions=doctor_questions,
                             today=date.today())

@patients_bp.route('/doctor/<int:doctor_id>/book', methods=['GET', 'POST'])
@patient_required
def book_appointment(doctor_id):
    """Book appointment with doctor - Only allowed for approved doctors"""
    user = get_current_user()
    patient = user.patient_profile
    
    # Check if patient profile is complete
    if not patient.is_profile_complete():
        flash('Please complete your profile before booking appointments. All required fields must be filled.', 'error')
        return redirect(url_for('patients.edit_profile'))
    
    doctor = Doctor.query.filter_by(id=doctor_id).first_or_404()
    
    # Check if doctor is approved
    if not (doctor.is_approved and doctor.is_verified):
        flash('This doctor is not approved yet. Appointments cannot be booked until admin approval.', 'warning')
        return redirect(url_for('patients.doctor_profile', doctor_id=doctor_id))
    
    form = AppointmentBookingForm()
    
    # Get appointment type and practice from query params
    appointment_type_param = request.args.get('type', '')
    practice_param = request.args.get('practice', '')
    
    # Pre-fill form with appointment type if provided
    if appointment_type_param and appointment_type_param in ['video', 'physical']:
        form.appointment_type.data = appointment_type_param
    
    # Find next available date if today's slots have passed or are booked
    today = date.today()
    from app.utils.slots import find_next_available_date
    next_available = find_next_available_date(doctor.time_slots, doctor.id, start_date=today)
    default_date = next_available if next_available else today + timedelta(days=1)
    
    # Populate time slots dynamically based on selected date (will be updated via JS or default to tomorrow)
    # We'll generate slots for the default date first
    time_choices = []
    if doctor.time_slots:
        from app.utils.slots import generate_slots_from_range
        
        # Get the day name for default date
        default_day_name = default_date.strftime('%A').lower()
        
        # Check if doctor has slots for this day
        if default_day_name in doctor.time_slots:
            day_config = doctor.time_slots[default_day_name]
            
            # Handle new structure (time range based)
            if isinstance(day_config, dict) and 'start_time' in day_config:
                start_time = day_config.get('start_time', '')
                end_time = day_config.get('end_time', '')
                duration = day_config.get('duration', 30)
                
                # Generate slots for this day
                generated_slots = generate_slots_from_range(start_time, end_time, duration)
                for slot_time in generated_slots:
                    time_choices.append((slot_time, slot_time))
            
            # Handle old structure (list of slots) for backwards compatibility
            elif isinstance(day_config, list):
                for slot in day_config:
                    if isinstance(slot, dict):
                        slot_time = slot.get('time', '')
                        if slot_time:
                            time_choices.append((slot_time, slot_time))
                    elif isinstance(slot, str):
                        time_choices.append((slot, slot))
        
        # If no slots for default day, try to find slots from any available day
        if not time_choices:
            for day_name, day_config in doctor.time_slots.items():
                if isinstance(day_config, dict) and 'start_time' in day_config:
                    start_time = day_config.get('start_time', '')
                    end_time = day_config.get('end_time', '')
                    duration = day_config.get('duration', 30)
                    generated_slots = generate_slots_from_range(start_time, end_time, duration)
                    for slot_time in generated_slots:
                        time_choices.append((slot_time, slot_time))
                    break  # Use first available day
    
    form.appointment_time.choices = time_choices if time_choices else [('', 'No slots available')]
    
    # Set default date in form if not already set
    if not form.appointment_date.data:
        form.appointment_date.data = default_date
    
    # Organize practices for getting price/hospital info (needed for both GET and POST)
    from app.utils.practice_organizer import organize_by_practice
    practices_dict = {}
    if doctor.time_slots:
        practices_dict = organize_by_practice(doctor.time_slots)
    
    if form.validate_on_submit():
        # Get appointment type from form or request (from selected practice card)
        appointment_type = request.form.get('appointment_type') or form.appointment_type.data
        selected_practice = request.form.get('practice') or request.form.get('selected_practice')
        
        # Validate appointment date - allow booking for tomorrow/day after even if today's time passed
        selected_date = form.appointment_date.data
        selected_time = form.appointment_time.data
        today = date.today()
        current_time = datetime.now().time()
        
        # If appointment is today, check if time has passed
        if selected_date == today:
            try:
                appointment_time_obj = datetime.strptime(selected_time, '%H:%M').time()
                if appointment_time_obj <= current_time:
                    flash('Today\'s time slots have passed. Please select a future date.', 'error')
                    return redirect(request.url)
            except ValueError:
                pass  # Time format error will be caught by form validation
        
        # If appointment date is in the past, reject
        if selected_date < today:
            flash('Appointment date cannot be in the past. Please select a future date.', 'error')
            return redirect(request.url)
        
        # Get hospital and price from the selected time slot or practice
        hospital = None
        charges = None
        
        # Try to get info from practice first
        if selected_practice and practices_dict:
            # Decode URL-encoded practice name
            from urllib.parse import unquote
            practice_name_decoded = unquote(selected_practice)
            practice_data = practices_dict.get(practice_name_decoded)
            if practice_data:
                if appointment_type == 'physical' and practice_data.get('physical_price'):
                    charges = practice_data.get('physical_price')
                    hospital = practice_data.get('location', '')
                elif appointment_type == 'video' and practice_data.get('video_price'):
                    charges = practice_data.get('video_price')
                    hospital = 'Online'
        
        # If not found in practice, get from time slot
        if charges is None:
            day_name = selected_date.strftime('%A').lower()
            from app.utils.slots import get_slot_info
            slot_info = get_slot_info(doctor.time_slots, day_name, selected_time)
            
            if slot_info:
                hospital = slot_info.get('hospital', hospital)
                if appointment_type == 'physical':
                    charges = slot_info.get('physical_price')
                else:  # video
                    charges = slot_info.get('video_price')
        
        # Fallback to doctor's default charges if not found
        if charges is None:
            if appointment_type == 'physical':
                charges = getattr(doctor, 'physical_charges', 0) if hasattr(doctor, 'physical_charges') else 0
            else:
                charges = getattr(doctor, 'video_charges', 0) if hasattr(doctor, 'video_charges') else 0
        
        appointment = Appointment(
            patient_id=patient.id,
            doctor_id=doctor.id,
            appointment_type=appointment_type,
            appointment_date=selected_date,
            appointment_time=datetime.strptime(selected_time, '%H:%M').time(),
            hospital=hospital.strip() if hospital else None,
            disease_category=form.reason_for_visit.data if form.reason_for_visit.data else None,
            symptoms=form.reason_for_visit.data if form.reason_for_visit.data else None,  # Store in both fields for compatibility
            notes=None,  # Notes field removed
            charges=charges,
            status='pending'
        )
        set_booking_payment_deadline(appointment)
        
        db.session.add(appointment)
        db.session.commit()
        
        flash('Appointment reserved! Please complete payment now to send the request to your doctor.', 'success')
        return redirect(url_for('appointments.view_appointment', appointment_id=appointment.id))
    
    completed_appointments = doctor.appointments.filter_by(status='completed').count()

    from app.utils.review_fraud import public_reviews_query
    visible_reviews = public_reviews_query().filter_by(doctor_id=doctor.id).all()
    total_reviews = len(visible_reviews)
    if total_reviews > 0:
        avg = round(sum(r.rating for r in visible_reviews) / total_reviews, 1)
        tag_counts = {}
        for r in visible_reviews:
            for tag in (r.tags or []):
                tag_counts[tag] = tag_counts.get(tag, 0) + 1
        review_stats = {
            'average_rating': avg,
            'total_reviews': total_reviews,
            'top_tags': sorted(tag_counts, key=tag_counts.get, reverse=True)[:3],
            'wait_time': 0,
            'avg_consultation_time': 0,
            'patient_satisfaction': avg,
            'diagnosis_accuracy': avg,
            'staff_behaviour': avg,
            'clinic_environment': avg,
        }
    else:
        review_stats = {
            'average_rating': 0,
            'total_reviews': 0,
            'top_tags': [],
            'wait_time': 0,
            'avg_consultation_time': 0,
            'patient_satisfaction': 0,
            'diagnosis_accuracy': 0,
            'staff_behaviour': 0,
            'clinic_environment': 0,
        }

    return render_template('patients/book_appointment.html',
                         form=form,
                         doctor=doctor,
                         practices=practices_dict,
                         completed_appointments=completed_appointments,
                         review_stats=review_stats,
                         practice_name=practice_param,
                         appointment_type_param=appointment_type_param)

@patients_bp.route('/appointments')
@patient_required
def appointments():
    """Patient appointments"""
    user = get_current_user()
    patient = user.patient_profile
    
    # Get filter parameters
    status = request.args.get('status', 'all')
    
    # Build query
    query = Appointment.query.filter_by(patient_id=patient.id)
    
    if status != 'all':
        query = query.filter_by(status=status)
    
    appointments = query.order_by(
        Appointment.appointment_date.desc(),
        Appointment.appointment_time.desc()
    ).all()
    
    return render_template('patients/appointments.html',
                         appointments=appointments,
                         current_status=status)

@patients_bp.route('/appointments/<int:appointment_id>/cancel', methods=['POST'])
@patient_required
def cancel_appointment(appointment_id):
    """Cancel appointment (if more than 3 hours before)"""
    user = get_current_user()
    patient = user.patient_profile
    
    appointment = Appointment.query.filter_by(
        id=appointment_id,
        patient_id=patient.id
    ).first()
    
    if not appointment:
        flash('Appointment not found.', 'error')
        return redirect(url_for('patients.appointments'))
    
    if appointment.status != 'approved':
        flash('Only approved appointments can be cancelled.', 'error')
        return redirect(url_for('patients.appointments'))
    
    # Check if more than 3 hours before appointment
    appointment_datetime = datetime.combine(
        appointment.appointment_date,
        appointment.appointment_time
    )
    time_diff = appointment_datetime - datetime.now()
    
    if time_diff.total_seconds() < 3 * 3600:  # Less than 3 hours
        flash('Appointments can only be cancelled more than 3 hours before the scheduled time.', 'error')
        return redirect(url_for('patients.appointments'))
    
    appointment.cancellation_requested = True
    appointment.cancellation_reason = request.form.get('reason', '')
    db.session.commit()
    
    flash('Cancellation request submitted. Doctor will review and approve.', 'success')
    return redirect(url_for('patients.appointments'))

@patients_bp.route('/appointments/<int:appointment_id>/upload-payment', methods=['GET', 'POST'])
@patient_required
def upload_payment(appointment_id):
    """Upload payment screenshot before doctor approval."""
    user = get_current_user()
    patient = user.patient_profile
    
    appointment = Appointment.query.filter_by(
        id=appointment_id,
        patient_id=patient.id
    ).first_or_404()
    
    if appointment.status != 'pending':
        flash('Payment can only be uploaded while the appointment is awaiting doctor approval.', 'error')
        return redirect(url_for('appointments.view_appointment', appointment_id=appointment_id))
    
    if request.method == 'GET':
        # Clear any existing payment screenshot to force re-upload after showing payment options
        if appointment.payment_status == 'pending' and appointment.payment_screenshot:
            appointment.payment_screenshot = None
            try:
                db.session.commit()
            except Exception as e:
                db.session.rollback()
                print(f'Error clearing payment screenshot: {e}')
        return redirect(url_for('appointments.view_appointment', appointment_id=appointment_id))
    
    # POST: Handle file upload

    # Hard boundary: once slot start time has passed, payment cannot proceed.
    # If payment was already submitted but unapproved, move it to disputed review.
    from app.utils.timezone import get_pakistan_now, PAKISTAN_TZ
    current_time = get_pakistan_now()
    slot_start_naive = datetime.combine(appointment.appointment_date, appointment.appointment_time)
    slot_start = PAKISTAN_TZ.localize(slot_start_naive)

    if current_time > slot_start:
        if appointment.payment_status == 'submitted':
            appointment.status = 'cancelled'
            appointment.payment_status = 'disputed'
            appointment.cancellation_reason = (
                f'Appointment slot started at {slot_start_naive.strftime("%I:%M %p on %d %b %Y")} '
                f'before payment approval. Case moved to disputed review.'
            )
            db.session.commit()
            flash(
                'Appointment slot has already started and payment was not approved in time. '
                'Your payment is now in disputed review. Admin will verify proof and process refund if valid.',
                'warning'
            )
            return redirect(url_for('appointments.view_appointment', appointment_id=appointment_id))

        flash('Appointment slot has already started. Payment upload is no longer allowed for this appointment.', 'error')
        return redirect(url_for('appointments.view_appointment', appointment_id=appointment_id))
    
    # ====================================================================
    # PAYMENT DEADLINE VALIDATION (Industry Standard - Zocdoc/Oladoc/Teladoc)
    # ====================================================================
    # Check if payment deadline has expired
    if appointment.payment_deadline:
        
        # Ensure payment_deadline is timezone-aware
        if appointment.payment_deadline.tzinfo is None:
            appointment.payment_deadline = PAKISTAN_TZ.localize(appointment.payment_deadline)
        
        if current_time > appointment.payment_deadline:
            # Calculate how late the payment is
            time_diff = current_time - appointment.payment_deadline
            minutes_late = int(time_diff.total_seconds() / 60)
            
            # Format deadline for display
            deadline_str = appointment.payment_deadline.strftime('%I:%M %p')
            
            flash(
                f'Payment deadline has expired ({deadline_str}). '
                f'You are {minutes_late} minute(s) late. '
                f'This appointment has been automatically cancelled. Please book a new appointment.',
                'error'
            )
            
            # Auto-cancel the appointment
            appointment.status = 'cancelled'
            appointment.cancellation_reason = f'Payment deadline expired at {deadline_str}. No payment received.'
            db.session.commit()
            
            return redirect(url_for('appointments.view_appointment', appointment_id=appointment_id))
    
    # Check if payment screenshot is provided
    if 'payment_screenshot' not in request.files:
        flash('Please select a payment screenshot.', 'error')
        return redirect(url_for('appointments.view_appointment', appointment_id=appointment_id))
    
    file = request.files['payment_screenshot']
    
    if file.filename == '':
        flash('Please select a payment screenshot.', 'error')
        return redirect(url_for('appointments.view_appointment', appointment_id=appointment_id))
    
    # Save payment screenshot
    from app.utils.file_upload import save_uploaded_file
    from flask import current_app
    
    success, file_path, error = save_uploaded_file(
        file, 
        current_app.config['UPLOAD_FOLDER'], 
        subfolder='payment_screenshots'
    )
    
    if not success:
        flash(f'Error uploading payment screenshot: {error}', 'error')
        return redirect(url_for('appointments.view_appointment', appointment_id=appointment_id))
    
    payment_method = request.form.get('payment_method', 'Manual Payment').title()
    
    # Update appointment with payment information (admin must approve before doctor sees it)
    appointment.payment_screenshot = file_path
    appointment.payment_status = 'submitted'
    appointment.payment_submitted_at = datetime.utcnow()
    appointment.payment_approved_at = None
    appointment.payment_rejection_reason = None
    
    try:
        db.session.commit()
        
        # Send notification email to Admin
        try:
            send_manual_payment_admin_notification(
                patient_name=patient.user.name,
                doctor_name=appointment.doctor.user.name,
                appointment_date=appointment.appointment_date,
                charges=appointment.charges,
                payment_method=payment_method
            )
        except Exception as e:
            print(f'Error sending admin payment notification email: {e}')
            
        flash('Payment screenshot uploaded successfully! Admin will review and approve it.', 'success')
    except Exception as e:
        db.session.rollback()
        flash('Error saving payment information. Please try again.', 'error')
        print(f'Error uploading payment: {e}')
    
    return redirect(url_for('appointments.view_appointment', appointment_id=appointment_id))

@patients_bp.route('/appointments/<int:appointment_id>/reset-payment', methods=['POST'])
@patient_required
def reset_payment(appointment_id):
    """Reset payment proof to allow patient to upload again"""
    user = get_current_user()
    patient = user.patient_profile
    
    appointment = Appointment.query.filter_by(
        id=appointment_id,
        patient_id=patient.id
    ).first_or_404()
    
    if appointment.status != 'pending':
        flash('Payment can only be reset while the appointment is awaiting doctor approval.', 'error')
        return redirect(url_for('appointments.view_appointment', appointment_id=appointment_id))
    
    # Only allow reset if payment_status is submitted or rejected
    if appointment.payment_status not in ['submitted', 'rejected']:
        flash('Payment can only be reset if it has been submitted or rejected.', 'error')
        return redirect(url_for('appointments.view_appointment', appointment_id=appointment_id))
    
    # Reset payment information
    appointment.payment_screenshot = None
    appointment.payment_status = 'pending'
    appointment.payment_submitted_at = None
    appointment.payment_rejection_reason = None
    appointment.payment_approved_at = None
    
    try:
        db.session.commit()
        flash('Payment proof removed. You can now upload a new payment screenshot.', 'success')
    except Exception as e:
        db.session.rollback()
        flash('Error resetting payment. Please try again.', 'error')
        print(f'Error resetting payment: {e}')
    
    return redirect(url_for('appointments.view_appointment', appointment_id=appointment_id))

@patients_bp.route('/medical-history')
@patient_required
def medical_history():
    """Patient medical history — unified chronological view of consultation entries + uploaded documents"""
    from flask import request
    user = get_current_user()
    patient = user.patient_profile
    
    from app.models import Appointment
    # Include visits still in the 24h review window (and disputed), not only fully "completed"
    base_query = MedicalHistory.query.join(Appointment).filter(
        MedicalHistory.patient_id == patient.id,
        Appointment.status.in_(['completed', 'completed_pending_review', 'disputed']),
    )
    
    # Extract ALL available doctor specialties for the autocomplete search
    from app.models import Doctor
    specialties = sorted([r.category for r in Doctor.query.with_entities(Doctor.category).distinct().all() if r.category])
    
    # Optional specialty filter
    current_specialty = request.args.get('specialty', '').strip()
    if current_specialty:
        from app.models import Doctor
        query = base_query.join(Doctor).filter(Doctor.category == current_specialty)
    else:
        query = base_query
        
    histories = query.order_by(MedicalHistory.created_at.desc()).all()
    
    # Manually uploaded documents
    documents = MedicalDocument.query.filter_by(
        patient_id=patient.id
    ).order_by(MedicalDocument.uploaded_at.desc()).all()
    
    # Distinct categories the patient has actually visited
    patient_categories_count = len(set(h.appointment.doctor.category for h in histories if h.appointment and h.appointment.doctor and h.appointment.doctor.category))
    
    return render_template('patients/medical_history.html',
                         histories=histories,
                         specialties=specialties,
                         current_specialty=current_specialty,
                         documents=documents,
                         patient_categories_count=patient_categories_count,
                         patient=patient)

@patients_bp.route('/medical-history/import', methods=['GET', 'POST'])
@patient_required
def import_medical_history():
    """Import medical history to new appointment"""
    user = get_current_user()
    patient = user.patient_profile
    
    if request.method == 'POST':
        selected_histories = request.form.getlist('histories')
        target_doctor_id = request.form.get('target_doctor')
        
        if selected_histories and target_doctor_id:
            flash('Medical history will be imported during appointment booking.', 'info')
            return redirect(url_for('patients.book_appointment', doctor_id=target_doctor_id))
    
    histories = MedicalHistory.query.filter_by(
        patient_id=patient.id
    ).order_by(MedicalHistory.created_at.desc()).all()
    
    doctors = Doctor.query.filter_by(
        is_approved=True,
        is_verified=True
    ).all()
    
    return render_template('patients/import_history.html',
                         histories=histories,
                         doctors=doctors)


# ============================================================================
# MANUAL DOCUMENT UPLOAD — Lab Reports, X-Rays, Old Records, etc.
# ============================================================================

ALLOWED_DOC_EXTENSIONS = {'pdf', 'jpg', 'jpeg', 'png', 'webp'}
MAX_DOC_SIZE_BYTES = 10 * 1024 * 1024  # 10 MB

DOCUMENT_CATEGORIES = [
    ('lab_report',       'Lab Report'),
    ('xray',             'X-Ray'),
    ('ct_scan',          'CT Scan'),
    ('mri',              'MRI'),
    ('old_prescription', 'Old Prescription'),
    ('other',            'Other / General'),
]


def _allowed_doc_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_DOC_EXTENSIONS


@patients_bp.route('/documents', methods=['GET'])
@patient_required
def list_documents():
    """View and manage uploaded medical documents"""
    user = get_current_user()
    patient = user.patient_profile
    
    documents = MedicalDocument.query.filter_by(
        patient_id=patient.id
    ).order_by(MedicalDocument.uploaded_at.desc()).all()
    
    return render_template('patients/documents.html',
                         documents=documents,
                         document_categories=DOCUMENT_CATEGORIES)


@patients_bp.route('/documents/upload', methods=['POST'])
@patient_required
def upload_document():
    """Handle manual medical document upload by patient"""
    user = get_current_user()
    patient = user.patient_profile
    
    # ── File validation ────────────────────────────────────────────────────
    if 'document' not in request.files:
        flash('No file selected. Please choose a file to upload.', 'error')
        return redirect(url_for('patients.list_documents'))
    
    file = request.files['document']
    if not file or file.filename == '':
        flash('No file selected. Please choose a file to upload.', 'error')
        return redirect(url_for('patients.list_documents'))
    
    if not _allowed_doc_file(file.filename):
        flash('Invalid file type. Allowed: PDF, JPG, PNG, WebP.', 'error')
        return redirect(url_for('patients.list_documents'))
    
    # Read file to check size (stream)
    file_bytes = file.read()
    if len(file_bytes) > MAX_DOC_SIZE_BYTES:
        flash('File is too large. Maximum size is 10 MB.', 'error')
        return redirect(url_for('patients.list_documents'))
    file.seek(0)  # Reset stream for saving
    
    # ── Determine file type label ──────────────────────────────────────────
    ext = file.filename.rsplit('.', 1)[1].lower()
    file_type = 'pdf' if ext == 'pdf' else 'image'
    
    # ── Build storage path ─────────────────────────────────────────────────
    original_name = secure_filename(file.filename)
    unique_name   = f"{uuid.uuid4().hex}_{original_name}"
    upload_base   = current_app.config.get('UPLOAD_FOLDER', 'app/static/uploads')
    patient_folder = os.path.join(upload_base, 'medical_documents', str(patient.id))
    os.makedirs(patient_folder, exist_ok=True)
    
    save_path = os.path.join(patient_folder, unique_name)
    
    try:
        file.save(save_path)
    except Exception as e:
        flash(f'Error saving file: {str(e)}', 'error')
        return redirect(url_for('patients.list_documents'))
    
    # ── Create DB record ───────────────────────────────────────────────────
    relative_path = f"uploads/medical_documents/{patient.id}/{unique_name}"
    
    doc = MedicalDocument(
        patient_id        = patient.id,
        filename          = original_name,           # Human-readable name
        file_path         = relative_path,           # Relative to static/
        file_type         = file_type,
        file_size         = len(file_bytes),
        document_category = request.form.get('document_category', 'other'),
        document_type     = request.form.get('document_category', 'other'),  # Legacy compat
        description       = request.form.get('description', '').strip() or None,
        is_visible_to_doctor = True,
        is_verified       = False,
    )
    
    try:
        db.session.add(doc)
        db.session.commit()
        flash(f'"{original_name}" uploaded successfully!', 'success')
    except Exception as e:
        db.session.rollback()
        # Clean up saved file on DB failure
        try:
            os.remove(save_path)
        except Exception:
            pass
        flash(f'Error saving document record: {str(e)}', 'error')
    
    return redirect(url_for('patients.list_documents'))


@patients_bp.route('/documents/<int:doc_id>/delete', methods=['POST'])
@patient_required
def delete_document(doc_id):
    """Delete a patient's uploaded document"""
    user = get_current_user()
    patient = user.patient_profile
    
    doc = MedicalDocument.query.filter_by(
        id=doc_id,
        patient_id=patient.id   # Security: only own documents
    ).first_or_404()
    
    # Try to remove the physical file
    try:
        upload_base = current_app.config.get('UPLOAD_FOLDER', 'app/static/uploads')
        # file_path is stored relative to static/
        full_path = os.path.join(
            current_app.root_path, 'static', doc.file_path
        )
        if os.path.exists(full_path):
            os.remove(full_path)
    except Exception as e:
        print(f'[DocDelete] Could not remove file: {e}')
    
    filename = doc.filename
    try:
        db.session.delete(doc)
        db.session.commit()
        flash(f'"{filename}" deleted successfully.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error deleting document: {str(e)}', 'error')
    
    # Redirect back to referrer (could be medical_history page or documents page)
    return redirect(request.referrer or url_for('patients.list_documents'))


@patients_bp.route('/documents/<int:doc_id>/toggle-visibility', methods=['POST'])
@patient_required
def toggle_document_visibility(doc_id):
    """Toggle whether a document is visible to doctors"""
    user = get_current_user()
    patient = user.patient_profile
    
    doc = MedicalDocument.query.filter_by(
        id=doc_id,
        patient_id=patient.id
    ).first_or_404()
    
    doc.is_visible_to_doctor = not doc.is_visible_to_doctor
    
    try:
        db.session.commit()
        status = 'visible to doctors' if doc.is_visible_to_doctor else 'hidden from doctors'
        flash(f'"{doc.filename}" is now {status}.', 'success')
    except Exception as e:
        db.session.rollback()
        flash('Error updating document visibility.', 'error')
    
    return redirect(request.referrer or url_for('patients.list_documents'))


@patients_bp.route('/refunds')
@patient_required
def refunds():
    """Patient refund center: submit payout details for pending refunds."""
    user = get_current_user()
    patient = user.patient_profile

    refunds = Refund.query.filter_by(patient_id=patient.id).order_by(Refund.created_at.desc()).all()

    # Read-only summary cards for refund/dispute visibility.
    total_disputes = Appointment.query.filter_by(
        patient_id=patient.id,
        status='cancelled',
        payment_status='disputed',
    ).count()

    pending_refunds = Refund.query.filter_by(patient_id=patient.id, status='pending').count()
    processed_refunds = Refund.query.filter_by(patient_id=patient.id, status='processed').count()

    # Rejected disputes are timeout-closure cases that ended as payment rejected.
    rejected_disputes = Appointment.query.filter(
        Appointment.patient_id == patient.id,
        Appointment.status == 'cancelled',
        Appointment.payment_status == 'rejected',
        Appointment.cancellation_reason.ilike('%before payment approval%'),
    ).count()

    refund_stats = {
        'total_disputes': total_disputes,
        'pending_refunds': pending_refunds,
        'processed_refunds': processed_refunds,
        'rejected_disputes': rejected_disputes,
    }

    return render_template('patients/refunds.html', refunds=refunds, patient=patient, refund_stats=refund_stats)


@patients_bp.route('/refunds/<int:refund_id>/submit-details', methods=['POST'])
@patient_required
def submit_refund_details(refund_id):
    """Submit or update payout details for a pending refund request."""
    user = get_current_user()
    patient = user.patient_profile

    refund = Refund.query.filter_by(id=refund_id, patient_id=patient.id).first_or_404()
    if refund.status != 'pending':
        flash('This refund is already completed and cannot be edited.', 'info')
        return redirect(url_for('patients.refunds'))

    payment_method = (request.form.get('payment_method') or '').strip().lower()
    account_title = (request.form.get('account_title') or '').strip()
    account_number = (request.form.get('account_number') or '').strip()
    iban = (request.form.get('iban') or '').strip()
    bank_name = (request.form.get('bank_name') or '').strip()
    wallet_provider = (request.form.get('wallet_provider') or '').strip()
    wallet_number = (request.form.get('wallet_number') or '').strip()
    visa_provider = (request.form.get('visa_provider') or '').strip()
    visa_recipient_id = (request.form.get('visa_recipient_id') or '').strip()
    patient_note = (request.form.get('patient_note') or '').strip()

    # Backward compatibility: normalize old wallet-specific values
    if payment_method in ('easypaisa', 'jazzcash'):
        if not wallet_provider:
            wallet_provider = payment_method.title()
        payment_method = 'mobile_wallet'

    if payment_method not in ('bank_transfer', 'mobile_wallet', 'visa_card'):
        flash('Please select a valid payment method.', 'error')
        return redirect(url_for('patients.refunds'))

    if payment_method == 'bank_transfer':
        if not account_title:
            flash('Account title is required for bank transfer.', 'error')
            return redirect(url_for('patients.refunds'))
        if not bank_name:
            flash('Bank name is required for bank transfer.', 'error')
            return redirect(url_for('patients.refunds'))
        if not account_number:
            flash('Account number is required for bank transfer.', 'error')
            return redirect(url_for('patients.refunds'))

        # Clear non-bank fields
        wallet_provider = ''
        wallet_number = ''

    elif payment_method == 'mobile_wallet':
        if not account_title:
            flash('Account title is required for wallet refund.', 'error')
            return redirect(url_for('patients.refunds'))
        if not wallet_provider:
            flash('Wallet provider is required for wallet refund.', 'error')
            return redirect(url_for('patients.refunds'))
        if not wallet_number:
            flash('Wallet number is required for wallet refund.', 'error')
            return redirect(url_for('patients.refunds'))

        # Clear bank-only fields
        account_number = ''
        iban = ''
        bank_name = ''

    elif payment_method == 'visa_card':
        # For visa refunds, account_title is used as card holder name,
        # bank_name stores provider bank/network, account_number stores recipient id/account.
        if not account_title:
            flash('Card holder name is required for Visa refund.', 'error')
            return redirect(url_for('patients.refunds'))
        if not visa_provider:
            flash('Visa provider/bank is required for Visa refund.', 'error')
            return redirect(url_for('patients.refunds'))
        if not visa_recipient_id:
            flash('Visa recipient ID/account number is required.', 'error')
            return redirect(url_for('patients.refunds'))

        bank_name = visa_provider
        account_number = visa_recipient_id

        # Clear non-visa fields
        iban = ''
        wallet_provider = ''
        wallet_number = ''

    detail = refund.payout_detail
    if not detail:
        detail = RefundPayoutDetail(refund_id=refund.id, payment_method=payment_method, account_title=account_title)
        db.session.add(detail)

    detail.payment_method = payment_method
    detail.account_title = account_title
    detail.account_number = account_number or None
    detail.iban = iban or None
    detail.bank_name = bank_name or None
    detail.wallet_provider = wallet_provider or None
    detail.wallet_number = wallet_number or None
    detail.patient_note = patient_note or None

    try:
        db.session.commit()
        flash('Refund payout details submitted successfully. Admin will process and attach proof.', 'success')
    except Exception as e:
        db.session.rollback()
        flash('Failed to submit refund details. Please try again.', 'error')
        print(f'[RefundDetails] submit failed: {e}')

    return redirect(url_for('patients.refunds'))

@patients_bp.route('/qa')
@patient_required
def qa():
    """Q&A section for patients - Redirect to main Q&A forum"""
    return redirect(url_for('qa.index'))

@patients_bp.route('/qa/ask', methods=['GET', 'POST'])
@patient_required
def ask_question():
    """Ask a question"""
    user = get_current_user()
    patient = user.patient_profile
    
    # Check if patient profile is complete
    if not patient.is_profile_complete():
        flash('Please complete your profile before posting questions. All required fields must be filled.', 'error')
        return redirect(url_for('patients.edit_profile'))
    
    # Get all medical categories for autocomplete
    from app.utils.categories import get_all_categories
    all_categories = sorted(get_all_categories())
    
    form = QuestionForm()
    if form.validate_on_submit():
        # Normalize category before saving
        from app.utils.categories import normalize_category
        normalized_category = normalize_category(form.category.data)
        
        question = Question(
            patient_id=patient.id,
            title=form.title.data,
            content=form.content.data,
            category=normalized_category,
            is_anonymous=bool(form.is_anonymous.data)
        )
        
        db.session.add(question)
        db.session.commit()
        
        flash('Question posted successfully! Doctors will review and answer.', 'success')
        return redirect(url_for('qa.index'))
    
    return render_template('patients/ask_question.html', form=form, all_categories=all_categories)
