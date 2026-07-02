import os
import uuid

from flask import Blueprint, render_template, request, flash, redirect, url_for, session, jsonify, current_app, Response, abort, send_file
from werkzeug.utils import secure_filename

from app.models import Doctor, User, Patient, Disease, Blog, Question, Answer, Appointment, MedicalHistory, Refund, RefundPayoutDetail, PlatformRevenue, DoctorPayoutRequest, DoctorTransaction, VideoCallRecording
from app.database import db
from app.forms import DiseaseForm
from app.utils.auth import admin_required, get_current_user
from app.utils.categories import normalize_category, get_category_display_name, CATEGORY_FA_ICONS
from app.utils.timezone import get_pakistan_today, get_pakistan_now, to_pakistan_time
from datetime import datetime, timedelta
from sqlalchemy import func, and_, exists
from app.services.accounts_service import create_refund
from app.utils.appointment_workflow import on_payment_marked_approved

admin_bp = Blueprint('admin', __name__)

@admin_bp.route('/no-access')
@admin_required
def no_access():
    """Shown when a staff admin has no panel grants."""
    from app.utils.admin_permissions import get_accessible_panel_keys, is_super_admin

    user = get_current_user()
    if is_super_admin(user) or get_accessible_panel_keys(user):
        return redirect(url_for('admin.dashboard'))
    return render_template('admin/no_access.html')


@admin_bp.route('/dashboard')
@admin_required
def dashboard():
    """Admin dashboard"""
    # Get statistics
    total_doctors = Doctor.query.count()
    approved_doctors = Doctor.query.filter_by(is_approved=True).count()
    # Pending Requests = New registrations only (appeal_count = 0)
    pending_requests = Doctor.query.filter_by(is_approved=False, appeal_status='pending').filter(Doctor.appeal_count == 0).count()
    # Pending Appeals = Appeals only (appeal_count > 0)
    pending_appeals = Doctor.query.filter_by(is_approved=False, appeal_status='pending').filter(Doctor.appeal_count > 0).count()
    rejected_doctors = Doctor.query.filter_by(is_approved=False, appeal_status='rejected').count()
    suspended_doctors = Doctor.query.filter_by(is_approved=False, appeal_status='suspended').count()
    total_patients = User.query.filter_by(role='patient').count()
    total_appointments = Appointment.query.count()
    today_date = get_pakistan_today()
    today_appointments = Appointment.query.filter(func.date(Appointment.appointment_date) == today_date).count()
    pending_payments = Appointment.query.filter_by(payment_status='submitted').count()
    total_blogs = Blog.query.count()
    total_questions = Question.query.count()
    
    # Financial basic stats (pending requests)
    pending_payouts = DoctorPayoutRequest.query.filter_by(status='pending').count()
    
    stats = {
        'doctors': {'total': total_doctors, 'approved': approved_doctors, 'pending': pending_requests, 'rejected': rejected_doctors, 'suspended': suspended_doctors},
        'patients': total_patients,
        'appointments': {
            'total': total_appointments,
            'today': today_appointments
        },
        'pending_payments': pending_payments,
        'blogs': total_blogs,
        'questions': total_questions,
        'appeals': pending_appeals,
        'pending_payouts': pending_payouts
    }
    
    # Get pending doctor registrations (NEW registrations only - appeal_count = 0)
    pending_doctors = Doctor.query.filter_by(is_approved=False, appeal_status='pending').order_by(Doctor.created_at.desc()).limit(6).all()
    
    # Get recent pending payments 
    recent_pending_payments = Appointment.query.filter_by(payment_status='submitted').order_by(Appointment.payment_submitted_at.desc()).limit(6).all()
    
    # Get recent payout requests
    recent_payouts = DoctorPayoutRequest.query.filter_by(status='pending').order_by(DoctorPayoutRequest.requested_at.desc()).limit(6).all()
    
    # Get pending blogs
    pending_blogs = Blog.query.filter_by(status='pending').order_by(Blog.created_at.desc()).limit(6).all()
    
    return render_template('admin/dashboard.html',
                         stats=stats,
                         pending_doctors=pending_doctors,
                         recent_pending_payments=recent_pending_payments,
                         recent_payouts=recent_payouts,
                         pending_blogs=pending_blogs)

@admin_bp.route('/suspended')
@admin_required
def suspended_doctors():
    """View suspended doctors"""
    suspended_doctors = Doctor.query.filter_by(is_approved=False, appeal_status='suspended').all()
    return render_template('admin/suspended_doctors.html', suspended_doctors=suspended_doctors)

@admin_bp.route('/doctors')
@admin_required
def doctors():
    """Manage doctors - load all doctors for client-side filtering"""
    # Load ALL doctors (we'll filter client-side to avoid page reloads)
    all_doctors = Doctor.query.order_by(Doctor.created_at.desc()).all()
    
    # Get statistics for management sections
    total_doctors = Doctor.query.count()
    approved_doctors = Doctor.query.filter_by(is_approved=True).count()
    # Pending Requests = New registrations only (appeal_count = 0)
    pending_requests = Doctor.query.filter_by(is_approved=False, appeal_status='pending').filter(Doctor.appeal_count == 0).count()
    # Pending Appeals = Appeals only (appeal_count > 0)
    pending_appeals = Doctor.query.filter_by(is_approved=False, appeal_status='pending').filter(Doctor.appeal_count > 0).count()
    rejected_doctors = Doctor.query.filter_by(is_approved=False, appeal_status='rejected').count()
    suspended_doctors = Doctor.query.filter_by(is_approved=False, appeal_status='suspended').count()
    
    stats = {
        'doctors': {'total': total_doctors, 'approved': approved_doctors, 'pending': pending_requests, 'rejected': rejected_doctors, 'suspended': suspended_doctors},
        'appeals': pending_appeals
    }
    
    # Get initial filter from query parameter (default: approved)
    filter_type = request.args.get('filter', 'approved')
    
    # Pass ALL predefined categories instead of just the ones currently registered
    all_categories = sorted(list(CATEGORY_FA_ICONS.keys()))
    
    return render_template('admin/doctors.html', doctors=all_doctors, stats=stats, current_filter=filter_type, categories=all_categories)

@admin_bp.route('/doctors/<int:doctor_id>/view')
@admin_required
def view_doctor_details(doctor_id):
    """View detailed doctor registration information"""
    doctor = Doctor.query.get_or_404(doctor_id)
    user = doctor.user
    
    # Prepare document URLs
    documents = {
        'cnic_front': f"/static/uploads/{doctor.cnic_front_image}" if doctor.cnic_front_image else None,
        'cnic_back': f"/static/uploads/{doctor.cnic_back_image}" if doctor.cnic_back_image else None,
        'live_photo': f"/static/uploads/{doctor.live_photo}" if doctor.live_photo else None,
        'degrees': [f"/static/uploads/{doc}" for doc in doctor.degree_documents] if doctor.degree_documents else []
    }
    
    return render_template('admin/doctor_details.html', 
                         doctor=doctor, 
                         user=user, 
                         documents=documents)

@admin_bp.route('/doctors/<int:doctor_id>/details-json')
@admin_required
def get_doctor_details_json(doctor_id):
    """Get doctor details as JSON for slide-up panel"""
    doctor = Doctor.query.get_or_404(doctor_id)
    user = doctor.user
    
    # Prepare document URLs
    documents = {
        'cnic_front': f"/static/uploads/{doctor.cnic_front_image}" if doctor.cnic_front_image else None,
        'cnic_back': f"/static/uploads/{doctor.cnic_back_image}" if doctor.cnic_back_image else None,
        'live_photo': f"/static/uploads/{doctor.live_photo}" if doctor.live_photo else None,
        'degrees': [f"/static/uploads/{doc}" for doc in doctor.degree_documents] if doctor.degree_documents else []
    }
    
    # Determine status
    if doctor.is_approved:
        status = 'approved'
    elif doctor.appeal_status == 'rejected':
        status = 'rejected'
    elif doctor.appeal_status == 'suspended':
        status = 'suspended'
    elif doctor.appeal_count > 0 and doctor.appeal_status == 'pending':
        status = 'appeals'
    else:
        status = 'pending'
    
    return jsonify({
        'id': doctor.id,
        'user': {
            'name': user.name or 'Not provided',
            'email': user.email or 'Not provided',
            'phone': user.phone or 'Not provided',
            'cnic': user.cnic or 'Not provided',
            'date_of_birth': user.date_of_birth.strftime('%B %d, %Y') if user.date_of_birth else None,
            'gender': user.gender.title() if user.gender else None,
            'address': None,  # Address field removed - only city is needed
            'profile_picture': f"/static/uploads/{user.profile_picture}" if user.profile_picture else None
        },
        'doctor': {
            'category': doctor.category or 'Not provided',
            'specialization': doctor.specialization or 'Not provided',
            'experience': doctor.experience if doctor.experience is not None else 0,
            'pmc_code': doctor.pmc_code or 'Not provided',
            'education': doctor.education or 'Not provided',
            'bio': doctor.bio or 'Not provided',
            # Hospital affiliation removed
            'city': doctor.city or 'Not provided',
            'location': doctor.location or 'Not provided',
            'created_at': doctor.created_at.strftime('%B %d, %Y at %I:%M %p') if doctor.created_at else 'Not available',
            'is_approved': doctor.is_approved,
            'appeal_status': doctor.appeal_status or 'pending',
            'appeal_count': doctor.appeal_count or 0,
            'rejection_reason': doctor.rejection_reason,
            'rejection_date': doctor.rejection_date.strftime('%B %d, %Y at %I:%M %p') if doctor.rejection_date else None
        },
        'documents': documents,
        'status': status
    })

@admin_bp.route('/doctors/<int:doctor_id>/approve', methods=['POST'])
@admin_required
def approve_doctor(doctor_id):
    """Approve doctor registration"""
    doctor = Doctor.query.get_or_404(doctor_id)
    
    doctor.is_approved = True
    doctor.is_verified = True
    doctor.appeal_status = 'approved'
    doctor.rejection_reason = None  # Clear rejection reason
    doctor.rejection_date = None
    db.session.commit()
    
    flash(f'Doctor {doctor.user.name} has been approved!', 'success')
    return redirect(url_for('admin.doctors'))

@admin_bp.route('/doctors/<int:doctor_id>/reject', methods=['POST'])
@admin_required
def reject_doctor(doctor_id):
    """Reject doctor registration with reason"""
    doctor = Doctor.query.get_or_404(doctor_id)
    
    # Get rejection reason from form
    rejection_reason = request.form.get('rejection_reason', '').strip()
    
    if not rejection_reason:
        flash('Please provide a reason for rejection.', 'error')
        return redirect(url_for('admin.view_doctor_details', doctor_id=doctor_id))
    
    # Get current timestamp for rejection - create fresh datetime object
    rejection_timestamp = datetime.utcnow()
    print(f"DEBUG: Creating new rejection timestamp: {rejection_timestamp}")
    
    # Update doctor status instead of deleting
    doctor.is_approved = False
    doctor.appeal_status = 'rejected'
    doctor.rejection_reason = rejection_reason
    doctor.rejection_date = rejection_timestamp  # Set the new rejection date
    
    # Explicitly flush and commit to ensure database update
    try:
        # Mark the object as modified to ensure SQLAlchemy tracks the change
        from sqlalchemy.orm.attributes import flag_modified
        flag_modified(doctor, 'rejection_date')
        
        db.session.flush()  # Flush changes to database
        db.session.commit()  # Commit the transaction
        
        # Verify by re-querying from database (bypass session cache)
        db.session.expire(doctor)  # Expire this specific object
        db.session.refresh(doctor)  # Force refresh from database
        
        # Also verify with a fresh query
        fresh_doctor = Doctor.query.filter_by(id=doctor_id).first()
        print(f"DEBUG: After commit - doctor.rejection_date: {doctor.rejection_date}")
        print(f"DEBUG: After commit - fresh_doctor.rejection_date: {fresh_doctor.rejection_date if fresh_doctor else 'None'}")
        print(f"DEBUG: Original timestamp was: {rejection_timestamp}")
        
    except Exception as e:
        db.session.rollback()
        flash('Failed to reject doctor. Please try again.', 'error')
        print(f'Error rejecting doctor: {e}')
        import traceback
        traceback.print_exc()
        return redirect(url_for('admin.view_doctor_details', doctor_id=doctor_id))
    
    flash(f'Doctor registration rejected. Doctor can appeal with improvements.', 'info')
    return redirect(url_for('admin.doctors'))

@admin_bp.route('/doctors/<int:doctor_id>/appeal', methods=['POST'])
@admin_required
def process_appeal(doctor_id):
    """Process doctor appeal"""
    doctor = Doctor.query.get_or_404(doctor_id)
    
    # Get appeal decision from form
    appeal_decision = request.form.get('appeal_decision')
    appeal_reason = request.form.get('appeal_reason', '').strip()
    
    if appeal_decision == 'approve':
        doctor.is_approved = True
        doctor.is_verified = True
        doctor.appeal_status = 'approved'
        doctor.rejection_reason = None
        doctor.rejection_date = None
        flash(f'Doctor {doctor.user.name} appeal approved!', 'success')
        db.session.commit()
    elif appeal_decision == 'reject':
        if not appeal_reason:
            flash('Please provide a reason for rejection.', 'error')
            return redirect(url_for('admin.view_doctor_details', doctor_id=doctor_id))
        
        # Get current timestamp for rejection - create fresh datetime object
        rejection_timestamp = datetime.utcnow()
        print(f"DEBUG: Creating new rejection timestamp: {rejection_timestamp}")
        
        # Update doctor status
        doctor.is_approved = False
        doctor.appeal_status = 'rejected'
        doctor.rejection_reason = appeal_reason
        doctor.rejection_date = rejection_timestamp  # Set the new rejection date
        
        # Check if this is the 3rd rejection (permanent suspension)
        if doctor.appeal_count >= 3:
            doctor.appeal_status = 'suspended'
            flash(f'Doctor appeal rejected. Account permanently suspended after 3 appeals.', 'warning')
        else:
            flash(f'Doctor appeal rejected. Reason provided.', 'info')
    
        # Explicitly flush and commit to ensure database update
        try:
            # Mark the object as modified to ensure SQLAlchemy tracks the change
            from sqlalchemy.orm.attributes import flag_modified
            flag_modified(doctor, 'rejection_date')
            
            db.session.flush()  # Flush changes to database
            db.session.commit()  # Commit the transaction
            
            # Verify by re-querying from database (bypass session cache)
            db.session.expire(doctor)  # Expire this specific object
            db.session.refresh(doctor)  # Force refresh from database
            
            # Also verify with a fresh query
            fresh_doctor = Doctor.query.filter_by(id=doctor_id).first()
            print(f"DEBUG: After commit - doctor.rejection_date: {doctor.rejection_date}")
            print(f"DEBUG: After commit - fresh_doctor.rejection_date: {fresh_doctor.rejection_date if fresh_doctor else 'None'}")
            print(f"DEBUG: Original timestamp was: {rejection_timestamp}")
            
        except Exception as e:
            db.session.rollback()
            flash('Failed to update rejection. Please try again.', 'error')
            print(f'Error updating rejection: {e}')
            import traceback
            traceback.print_exc()
            return redirect(url_for('admin.view_doctor_details', doctor_id=doctor_id))
    
    return redirect(url_for('admin.doctors'))

@admin_bp.route('/appeals')
@admin_required
def appeals():
    """Manage doctor appeals"""
    # Get doctors who have submitted appeals
    appeals = Doctor.query.filter_by(is_approved=False, appeal_status='pending').filter(Doctor.appeal_count > 0).all()
    
    return render_template('admin/appeals.html', appeals=appeals)

@admin_bp.route('/rejected')
@admin_required
def rejected_doctors():
    """View rejected doctors"""
    # Get rejected doctors
    rejected_doctors = Doctor.query.filter_by(is_approved=False, appeal_status='rejected').all()
    
    return render_template('admin/rejected_doctors.html', rejected_doctors=rejected_doctors)

@admin_bp.route('/diseases')
@admin_required
def diseases():
    """Manage diseases information"""
    diseases = Disease.query.order_by(Disease.created_at.desc()).all()
    return render_template('admin/diseases.html', diseases=diseases)

@admin_bp.route('/diseases/add', methods=['GET', 'POST'])
@admin_required
def add_disease():
    """Add new disease information"""
    form = DiseaseForm()
    if form.validate_on_submit():
        disease = Disease(
            name=form.name.data,
            category=form.category.data,
            description=form.description.data,
            symptoms=form.symptoms.data,
            causes=form.causes.data,
            prevention=form.prevention.data,
            treatment=form.treatment.data,
            severity_level=form.severity_level.data,
            age_group=form.age_group.data,
            gender_preference=form.gender_preference.data,
            uploaded_by=get_current_user().name
        )
        
        db.session.add(disease)
        db.session.commit()
        
        flash('Disease information added successfully!', 'success')
        return redirect(url_for('admin.diseases'))
    
    return render_template('admin/add_disease.html', form=form)

@admin_bp.route('/diseases/<int:disease_id>/edit', methods=['GET', 'POST'])
@admin_required
def edit_disease(disease_id):
    """Edit disease information"""
    disease = Disease.query.get_or_404(disease_id)
    form = DiseaseForm(obj=disease)
    
    if form.validate_on_submit():
        disease.name = form.name.data
        disease.category = form.category.data
        disease.description = form.description.data
        disease.symptoms = form.symptoms.data
        disease.causes = form.causes.data
        disease.prevention = form.prevention.data
        disease.treatment = form.treatment.data
        disease.severity_level = form.severity_level.data
        disease.age_group = form.age_group.data
        disease.gender_preference = form.gender_preference.data
        disease.updated_at = datetime.utcnow()
        
        db.session.commit()
        
        flash('Disease information updated successfully!', 'success')
        return redirect(url_for('admin.diseases'))
    
    return render_template('admin/edit_disease.html', form=form, disease=disease)

@admin_bp.route('/diseases/<int:disease_id>/delete', methods=['POST'])
@admin_required
def delete_disease(disease_id):
    """Delete disease information"""
    disease = Disease.query.get_or_404(disease_id)
    
    db.session.delete(disease)
    db.session.commit()
    
    flash('Disease information deleted successfully!', 'success')
    return redirect(url_for('admin.diseases'))

@admin_bp.route('/blogs')
@admin_required
def blogs():
    """Manage blogs"""
    blogs = Blog.query.order_by(Blog.created_at.desc()).all()
    return render_template('admin/blogs.html', blogs=blogs)

@admin_bp.route('/blogs/<int:blog_id>/delete', methods=['POST'])
@admin_required
def delete_blog(blog_id):
    """Delete blog with reason"""
    blog = Blog.query.get_or_404(blog_id)
    
    reason = request.form.get('reason', '')
    if not reason:
        flash('Please provide a reason for deletion.', 'error')
        return redirect(url_for('admin.blogs'))
    
    blog.is_deleted = True
    blog.deletion_reason = reason
    blog.status = 'deleted'
    db.session.commit()
    
    flash('Blog deleted successfully!', 'success')
    return redirect(url_for('admin.blogs'))

@admin_bp.route('/blogs/<int:blog_id>/approve', methods=['POST'])
@admin_required
def approve_blog(blog_id):
    """Approve a pending blog for publication"""
    blog = Blog.query.get_or_404(blog_id)
    
    blog.status = 'published'
    blog.published_at = datetime.utcnow()
    blog.admin_feedback = None # Clear any previous feedback
    
    db.session.commit()
    flash(f'Article "{blog.title}" has been successfully published.', 'success')
    return redirect(url_for('admin.blogs'))

@admin_bp.route('/blogs/<int:blog_id>/reject', methods=['POST'])
@admin_required
def reject_blog(blog_id):
    """Reject a pending blog with feedback to the doctor"""
    blog = Blog.query.get_or_404(blog_id)
    
    feedback = request.form.get('feedback', '').strip()
    if not feedback:
        flash('You must provide feedback to the doctor explaining the rejection.', 'error')
        return redirect(url_for('admin.blogs'))
        
    blog.status = 'rejected'
    blog.admin_feedback = feedback
    
    db.session.commit()
    flash(f'Article "{blog.title}" has been rejected. The doctor will be notified to revise.', 'info')
    return redirect(url_for('admin.blogs'))

@admin_bp.route('/qa')
@admin_required
def qa():
    """Manage Q&A content"""
    page = request.args.get('page', 1, type=int)
    per_page = 5
    qa_filter = (request.args.get('filter') or 'all').strip().lower()
    if qa_filter not in ('all', 'answered', 'pending'):
        qa_filter = 'all'

    # Enforce category matching: remove questions answered by non-matching or multi-category doctors
    mismatch_ids = db.session.query(Question.id).join(Answer).join(Doctor).filter(
        Question.is_deleted.is_(False),
        Answer.is_deleted.is_(False),
        func.lower(Doctor.category) != func.lower(Question.category)
    ).distinct().all()

    multi_ids = db.session.query(Question.id).join(Answer).join(Doctor).filter(
        Question.is_deleted.is_(False),
        Answer.is_deleted.is_(False)
    ).group_by(Question.id).having(
        func.count(func.distinct(func.lower(Doctor.category))) > 1
    ).all()

    invalid_ids = {qid for (qid,) in mismatch_ids + multi_ids}
    if invalid_ids:
        for question in Question.query.filter(Question.id.in_(invalid_ids)).all():
            db.session.delete(question)
        db.session.commit()

    has_active_answer = exists().where(
        and_(
            Answer.question_id == Question.id,
            Answer.is_deleted.is_(False),
        )
    )
    q_base = Question.query.filter(Question.is_deleted.is_(False))
    if qa_filter == 'answered':
        q_filtered = q_base.filter(has_active_answer)
    elif qa_filter == 'pending':
        q_filtered = q_base.filter(~has_active_answer)
    else:
        q_filtered = q_base

    pagination = q_filtered.order_by(Question.created_at.desc()).paginate(
        page=page,
        per_page=per_page,
        error_out=False
    )

    total_questions = Question.query.filter_by(is_deleted=False).count()
    answered_count = db.session.query(Question.id).join(Answer).filter(
        Question.is_deleted.is_(False),
        Answer.is_deleted == False
    ).distinct().count()
    unanswered_count = max(total_questions - answered_count, 0)

    return render_template(
        'admin/qa.html',
        questions=pagination.items,
        pagination=pagination,
        total_questions=total_questions,
        answered_count=answered_count,
        unanswered_count=unanswered_count,
        qa_filter=qa_filter,
    )

@admin_bp.route('/qa/question/<int:question_id>/delete', methods=['POST'])
@admin_required
def delete_question(question_id):
    """Delete question with reason"""
    question = Question.query.get_or_404(question_id)
    
    reason = request.form.get('reason', '')
    if not reason:
        flash('Please provide a reason for deletion.', 'error')
        return redirect(url_for('admin.qa'))
    
    question.is_deleted = True
    question.deletion_reason = reason
    db.session.commit()
    
    flash('Question deleted successfully!', 'success')
    return redirect(url_for('admin.qa'))

@admin_bp.route('/qa/answer/<int:answer_id>/delete', methods=['POST'])
@admin_required
def delete_answer(answer_id):
    """Delete answer with reason"""
    answer = Answer.query.get_or_404(answer_id)
    
    reason = request.form.get('reason', '')
    if not reason:
        flash('Please provide a reason for deletion.', 'error')
        return redirect(url_for('admin.qa'))
    
    answer.is_deleted = True
    answer.deletion_reason = reason
    db.session.commit()
    
    flash('Answer deleted successfully!', 'success')
    return redirect(url_for('admin.qa'))

@admin_bp.route('/patients')
@admin_required
def patients():
    """List all patients"""
    try:
        # Get filter parameter
        filter_type = request.args.get('filter', 'all')
        
        # Build query
        query = User.query.filter_by(role='patient')
        
        # Apply filters if needed (can add more filters later)
        patients_list = query.order_by(User.created_at.desc()).all()
        
        # Get statistics
        total_patients = User.query.filter_by(role='patient').count()
        
        # Profiles Complete: count patients with all required medical info
        profiles_complete = sum(
            1
            for patient_user in patients_list
            if patient_user.patient_profile and patient_user.patient_profile.is_profile_complete()
        )
        
        # Active This Month: count patients with at least 1 appointment this month
        today = get_pakistan_today()
        month_start = today.replace(day=1)
        month_end = (month_start + timedelta(days=32)).replace(day=1) - timedelta(days=1)
        
        active_this_month = db.session.query(func.count(func.distinct(Appointment.patient_id))).filter(
            Appointment.appointment_date >= month_start,
            Appointment.appointment_date <= month_end
        ).scalar() or 0

        patient_filter_flags = {}
        for patient_user in patients_list:
            uid = patient_user.id
            p = patient_user.patient_profile
            if not p:
                patient_filter_flags[uid] = {'profile_complete': False, 'active_this_month': False}
                continue
            prof_ok = p.is_profile_complete()
            active_mo = p.appointments.filter(
                Appointment.appointment_date >= month_start,
                Appointment.appointment_date <= month_end
            ).first() is not None
            patient_filter_flags[uid] = {
                'profile_complete': prof_ok,
                'active_this_month': active_mo,
            }

        return render_template('admin/patients.html', 
                             patients=patients_list, 
                             total_patients=total_patients,
                             profiles_complete=profiles_complete,
                             active_this_month=active_this_month,
                             current_filter=filter_type,
                             patient_filter_flags=patient_filter_flags)
    except Exception as e:
        print(f"Error in patients route: {e}")
        import traceback
        traceback.print_exc()
        flash('An error occurred loading patients. Please try again.', 'error')
        return redirect(url_for('admin.dashboard'))

@admin_bp.route('/patients/<int:patient_id>/view')
@admin_required
def view_patient(patient_id):
    """View patient profile and information"""
    patient_user = User.query.filter_by(id=patient_id, role='patient').first_or_404()
    patient = patient_user.patient_profile
    
    if not patient:
        flash('Patient profile not found.', 'error')
        return redirect(url_for('admin.patients'))
    
    # Get appointment statistics
    total_appointments = Appointment.query.filter_by(patient_id=patient.id).count()
    pending_appointments = Appointment.query.filter_by(patient_id=patient.id, status='pending').count()
    approved_appointments = Appointment.query.filter_by(patient_id=patient.id, status='approved').count()
    completed_appointments = Appointment.query.filter_by(patient_id=patient.id, status='completed').count()
    
    stats = {
        'total': total_appointments,
        'pending': pending_appointments,
        'approved': approved_appointments,
        'completed': completed_appointments
    }
    
    return render_template('admin/patient_details.html',
                         patient=patient,
                         patient_user=patient_user,
                         stats=stats)

@admin_bp.route('/patients/<int:patient_id>/appointments')
@admin_required
def view_patient_appointments(patient_id):
    """View all appointments for a specific patient"""
    patient_user = User.query.filter_by(id=patient_id, role='patient').first_or_404()
    patient = patient_user.patient_profile
    
    if not patient:
        flash('Patient profile not found.', 'error')
        return redirect(url_for('admin.patients'))
    
    # Get filter parameter
    status = request.args.get('status', 'all')
    
    # Build query
    query = Appointment.query.filter_by(patient_id=patient.id)
    
    if status != 'all':
        query = query.filter_by(status=status)
    
    appointments = query.order_by(
        Appointment.appointment_date.desc(),
        Appointment.appointment_time.desc()
    ).all()
    
    return render_template('admin/patient_appointments.html',
                         patient=patient,
                         patient_user=patient_user,
                         appointments=appointments,
                         current_status=status)

@admin_bp.route('/appointments/<int:appointment_id>/recordings')
@admin_required
def appointment_recordings(appointment_id):
    """View video call recordings for an appointment (admin only; for dispute review)."""
    from app.utils.spaces_storage import get_presigned_playback_url, is_hls_playlist
    from app.utils.recording_playback import make_playback_token

    appointment = Appointment.query.get_or_404(appointment_id)
    recordings = VideoCallRecording.query.filter_by(appointment_id=appointment_id).order_by(
        VideoCallRecording.started_at.desc()
    ).all()

    recording_items = []
    for rec in recordings:
        playback_url = None
        if rec.status == 'ready' and rec.file_path:
            if is_hls_playlist(rec.file_path):
                fname = rec.file_path.rsplit('/', 1)[-1]
                pt = make_playback_token(rec.id)
                playback_url = url_for(
                    'admin.recording_hls_asset',
                    recording_id=rec.id,
                    filename=fname,
                    pt=pt,
                )
            else:
                playback_url = get_presigned_playback_url(rec.file_path)
        ready = rec.status == 'ready' and rec.file_path
        recording_items.append({
            'recording': rec,
            'playback_url': playback_url,
            'is_hls': is_hls_playlist(rec.file_path),
            'watch_url': url_for('admin.recording_watch', recording_id=rec.id) if ready else None,
            'download_url': url_for('admin.recording_download', recording_id=rec.id) if ready else None,
        })

    return render_template(
        'admin/appointment_recordings.html',
        appointment=appointment,
        recording_items=recording_items,
    )


@admin_bp.route('/recordings/<int:recording_id>/watch')
@admin_required
def recording_watch(recording_id):
    """Dedicated fullscreen-style player page (opens in new tab)."""
    from app.utils.spaces_storage import get_presigned_playback_url, is_hls_playlist
    from app.utils.recording_playback import make_playback_token

    rec = VideoCallRecording.query.get_or_404(recording_id)
    if rec.status != 'ready' or not rec.file_path:
        flash('Recording is not available for playback.', 'error')
        return redirect(url_for('admin.appointment_recordings', appointment_id=rec.appointment_id))

    appointment = rec.appointment
    patient_name = appointment.patient.user.name if appointment.patient and appointment.patient.user else 'Patient'
    doctor_name = appointment.doctor.user.name if appointment.doctor and appointment.doctor.user else 'Doctor'

    is_hls = is_hls_playlist(rec.file_path)
    if is_hls:
        pt = make_playback_token(rec.id)
        fname = rec.file_path.rsplit('/', 1)[-1]
        playback_url = url_for(
            'admin.recording_hls_asset',
            recording_id=rec.id,
            filename=fname,
            pt=pt,
        )
    else:
        playback_url = get_presigned_playback_url(rec.file_path)

    return render_template(
        'admin/recording_watch.html',
        recording=rec,
        appointment=appointment,
        patient_name=patient_name,
        doctor_name=doctor_name,
        playback_url=playback_url,
        is_hls=is_hls,
        back_url=url_for('admin.appointment_recordings', appointment_id=appointment.id),
        download_url=url_for('admin.recording_download', recording_id=rec.id),
    )


@admin_bp.route('/recordings/<int:recording_id>/download')
@admin_required
def recording_download(recording_id):
    """Download recording bundle (HLS zip) or single file for admin archival."""
    import io
    import zipfile

    from app.utils.spaces_storage import (
        fetch_spaces_object,
        is_hls_playlist,
        list_recording_bundle_keys,
    )

    rec = VideoCallRecording.query.get_or_404(recording_id)
    if rec.status != 'ready' or not rec.file_path:
        flash('Recording is not available for download.', 'error')
        return redirect(url_for('admin.appointment_recordings', appointment_id=rec.appointment_id))

    appointment_id = rec.appointment_id
    base_name = f'quickcare_appt{appointment_id}_session{rec.id}'

    if is_hls_playlist(rec.file_path):
        keys = list_recording_bundle_keys(rec.file_path)
        if not keys:
            flash('Recording files were not found in cloud storage.', 'error')
            return redirect(url_for('admin.appointment_recordings', appointment_id=appointment_id))

        buf = io.BytesIO()
        with zipfile.ZipFile(buf, 'w', zipfile.ZIP_STORED) as zf:
            zf.writestr(
                'README.txt',
                (
                    'Quick Care — video call recording (HLS)\n\n'
                    '1. Extract this ZIP on your computer.\n'
                    '2. Open the .m3u8 file in VLC Media Player (or another HLS player).\n'
                    '3. Keep all .ts segment files in the same folder as the playlist.\n'
                ),
            )
            added = 0
            for object_key in keys:
                data = fetch_spaces_object(object_key)
                if not data:
                    continue
                arcname = object_key.rsplit('/', 1)[-1]
                zf.writestr(arcname, data)
                added += 1
        if added == 0:
            flash('Could not read recording files from cloud storage.', 'error')
            return redirect(url_for('admin.appointment_recordings', appointment_id=appointment_id))

        buf.seek(0)
        return send_file(
            buf,
            mimetype='application/zip',
            as_attachment=True,
            download_name=f'{base_name}_recording.zip',
        )

    data = fetch_spaces_object(rec.file_path)
    if not data:
        flash('Recording file was not found in cloud storage.', 'error')
        return redirect(url_for('admin.appointment_recordings', appointment_id=appointment_id))

    ext = rec.file_path.rsplit('.', 1)[-1] if '.' in rec.file_path else 'bin'
    return send_file(
        io.BytesIO(data),
        mimetype='application/octet-stream',
        as_attachment=True,
        download_name=f'{base_name}.{ext}',
    )


@admin_bp.route('/recordings/<int:recording_id>/hls/<path:filename>')
def recording_hls_asset(recording_id, filename):
    """
    Serve rewritten HLS playlist (manifest only). Each .ts line is a presigned Spaces URL
    so video segments do not block the app server (gunicorn worker).
    Auth: short-lived signed ?pt= token.
    """
    from app.utils.spaces_storage import fetch_spaces_object, playlist_base_prefix
    from app.utils.recording_playback import verify_playback_token

    pt = request.args.get('pt', '')
    if not verify_playback_token(recording_id, pt):
        abort(403)

    if '..' in filename or filename.startswith('/'):
        abort(400)
    if not filename.lower().endswith('.m3u8'):
        abort(404)

    rec = VideoCallRecording.query.get_or_404(recording_id)
    if rec.status != 'ready' or not rec.file_path:
        abort(404)

    raw = fetch_spaces_object(rec.file_path)
    if raw is None:
        abort(404)

    lines = []
    for line in raw.decode('utf-8', errors='replace').splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith('#') and '.ts' in stripped:
            seg_name = stripped.split('/')[-1]
            lines.append(url_for(
                'admin.recording_hls_segment',
                recording_id=recording_id,
                filename=seg_name,
                pt=pt,
            ))
        else:
            lines.append(line)
    body = '\n'.join(lines) + '\n'

    resp = Response(body, mimetype='application/vnd.apple.mpegurl')
    resp.headers['Cache-Control'] = 'no-store'
    return resp


@admin_bp.route('/recordings/<int:recording_id>/seg/<path:filename>')
def recording_hls_segment(recording_id, filename):
    """Proxy a single .ts segment (same-origin for browsers when Spaces CORS is unavailable)."""
    from app.utils.spaces_storage import fetch_spaces_object, playlist_base_prefix
    from app.utils.recording_playback import verify_playback_token

    pt = request.args.get('pt', '')
    if not verify_playback_token(recording_id, pt):
        abort(403)
    if '..' in filename or filename.startswith('/') or not filename.lower().endswith('.ts'):
        abort(400)

    rec = VideoCallRecording.query.get_or_404(recording_id)
    if rec.status != 'ready' or not rec.file_path:
        abort(404)

    object_key = f'{playlist_base_prefix(rec.file_path)}{filename.split("/")[-1]}'
    raw = fetch_spaces_object(object_key)
    if raw is None:
        abort(404)

    resp = Response(raw, mimetype='video/mp2t')
    resp.headers['Cache-Control'] = 'private, max-age=300'
    return resp


@admin_bp.route('/appointments')
@admin_required
def appointments():
    """View and filter appointments (payment approvals handled on /payments)."""
    # Get filter parameters
    status = request.args.get('status', 'all')
    filter_category = request.args.get('filter_category', '')

    # Build base query
    query = Appointment.query

    # Apply category-first filters
    if filter_category == 'status':
        if status and status != 'all':
            query = query.filter_by(status=status)
    elif filter_category == 'date':
        df = request.args.get('date_from')
        dt = request.args.get('date_to')
        try:
            if df:
                # parse YYYY-MM-DD from HTML date input to a date object
                dfrom = datetime.strptime(df, '%Y-%m-%d').date()
                query = query.filter(Appointment.appointment_date >= dfrom)
            if dt:
                dto = datetime.strptime(dt, '%Y-%m-%d').date()
                query = query.filter(Appointment.appointment_date <= dto)
        except Exception:
            # ignore parse errors and continue without date filter
            pass
    elif filter_category == 'email':
        email = request.args.get('email','').strip()
        if email:
            query = query.join(Patient).join(User).filter(User.email.ilike(f"%{email}%"))
    elif filter_category == 'patient':
        pid = request.args.get('patient_id')
        pname = request.args.get('patient_name','').strip()
        if pid:
            try:
                query = query.filter(Appointment.patient_id == int(pid))
            except Exception:
                pass
        elif pname:
            query = query.join(Patient).filter(Patient.full_name.ilike(f"%{pname}%"))
    elif filter_category == 'doctor':
        did = request.args.get('doctor_id')
        dname = request.args.get('doctor_name','').strip()
        if did:
            try:
                query = query.filter(Appointment.doctor_id == int(did))
            except Exception:
                pass
        elif dname:
            query = query.join(Doctor).filter(Doctor.full_name.ilike(f"%{dname}%"))

    appointments = query.order_by(
        Appointment.appointment_date.desc(),
        Appointment.appointment_time.desc()
    ).all()
    
    # Get statistics
    total_appointments = Appointment.query.count()
    pending_appointments = Appointment.query.filter_by(status='pending').count()
    approved_appointments = Appointment.query.filter_by(status='approved').count()
    completed_appointments = Appointment.query.filter_by(status='completed').count()
    rejected_appointments = Appointment.query.filter_by(status='rejected').count()
    cancelled_appointments = Appointment.query.filter_by(status='cancelled').count()
    pending_payments = Appointment.query.filter_by(payment_status='submitted').count()
    
    stats = {
        'total': total_appointments,
        'pending': pending_appointments,
        'approved': approved_appointments,
        'completed': completed_appointments,
        'rejected': rejected_appointments,
        'cancelled': cancelled_appointments,
        'pending_payments': pending_payments
    }
    
    # prepare auxiliary lists for template (limit to reasonable number)
    # Order patients/doctors by the linked User.name (Patient/Doctor don't have full_name fields)
    patients = Patient.query.join(User, Patient.user).order_by(User.name.asc()).limit(500).all()
    doctors = Doctor.query.join(User, Doctor.user).order_by(User.name.asc()).limit(500).all()
    status_options = ['pending','approved','completed','rejected','cancelled','disputed','completed_pending_review','expired_patient_noshow','expired_provider_failure','expired_mutual_noshow']

    return render_template('admin/appointments.html',
                         appointments=appointments,
                         stats=stats,
                         current_status=status,
                         patients=patients,
                         doctors=doctors,
                         status_options=status_options)

@admin_bp.route('/payments')
@admin_required
def payments():
    """View pending payment approvals"""
    # Manual payment proofs awaiting admin (patient pays before doctor approval)
    pending_payments = Appointment.query.filter(
        Appointment.payment_status == 'submitted',
        Appointment.status.in_(['pending', 'approved']),
    ).order_by(Appointment.payment_submitted_at.desc()).all()

    # Disputed timeout payments (slot started before admin approval)
    disputed_payments = Appointment.query.filter_by(
        payment_status='disputed',
        status='cancelled'
    ).order_by(Appointment.updated_at.desc()).all()
    
    # Get approved and rejected payments for reference
    approved_payments = Appointment.query.filter_by(payment_status='approved').order_by(Appointment.payment_approved_at.desc()).limit(20).all()
    rejected_payments = Appointment.query.filter_by(payment_status='rejected').order_by(Appointment.payment_submitted_at.desc()).limit(20).all()
    
    return render_template('admin/payments.html',
                         pending_payments=pending_payments,
                         disputed_payments=disputed_payments,
                         approved_payments=approved_payments,
                         rejected_payments=rejected_payments)

@admin_bp.route('/payments/<int:appointment_id>/approve', methods=['POST'])
@admin_required
def approve_payment(appointment_id):
    """Approve payment for appointment"""
    appointment = Appointment.query.get_or_404(appointment_id)
    
    if appointment.payment_status != 'submitted':
        flash('This payment is not pending approval.', 'error')
        return redirect(url_for('admin.payments'))
    
    appointment.payment_status = 'approved'
    appointment.payment_approved_at = datetime.utcnow()
    appointment.payment_rejection_reason = None

    from app.utils.slots import find_reserved_appointment
    conflict = find_reserved_appointment(
        appointment.doctor_id,
        appointment.appointment_date,
        appointment.appointment_time,
        exclude_appointment_id=appointment.id,
    )
    if conflict:
        appointment.status = 'cancelled'
        appointment.cancellation_reason = (
            'Slot was taken by another paid booking before this payment could be approved.'
        )
        try:
            create_refund(appointment, reason='slot_unavailable', amount=appointment.charges)
        except Exception as e:
            print(f'Error creating slot conflict refund for appointment #{appointment.id}: {e}')
    else:
        on_payment_marked_approved(appointment)
    
    try:
        db.session.commit()
        flash('Payment approved successfully!', 'success')
    except Exception as e:
        db.session.rollback()
        flash('Error approving payment.', 'error')
        print(f'Error approving payment: {e}')
    
    return redirect(url_for('admin.payments'))

@admin_bp.route('/payments/<int:appointment_id>/reject', methods=['POST'])
@admin_required
def reject_payment(appointment_id):
    """Reject payment for appointment"""
    appointment = Appointment.query.get_or_404(appointment_id)
    
    if appointment.payment_status != 'submitted':
        flash('This payment is not pending approval.', 'error')
        return redirect(url_for('admin.payments'))
    
    rejection_reason = request.form.get('rejection_reason', '').strip()
    
    if not rejection_reason:
        flash('Please provide a reason for rejection.', 'error')
        return redirect(url_for('admin.payments'))
    
    appointment.payment_status = 'rejected'
    appointment.payment_rejection_reason = rejection_reason
    
    try:
        db.session.commit()
        flash('Payment rejected. Patient will be notified with the reason.', 'info')
    except Exception as e:
        db.session.rollback()
        flash('Error rejecting payment.', 'error')
        print(f'Error rejecting payment: {e}')
    
    return redirect(url_for('admin.payments'))


@admin_bp.route('/payments/<int:appointment_id>/dispute-approve', methods=['POST'])
@admin_required
def approve_disputed_payment(appointment_id):
    """Approve disputed timeout payment and create refund record."""
    appointment = Appointment.query.get_or_404(appointment_id)

    if appointment.payment_status != 'disputed' or appointment.status != 'cancelled':
        flash('This appointment is not in disputed timeout review.', 'error')
        return redirect(url_for('admin.payments'))

    # Idempotency: do not create duplicate refund for the same timeout dispute
    existing_refund = Refund.query.filter_by(
        appointment_id=appointment.id,
        reason='payment_timeout_valid_proof'
    ).first()

    if not existing_refund:
        create_refund(
            appointment,
            reason='payment_timeout_valid_proof',
            amount=appointment.charges,
        )

    appointment.payment_status = 'approved'
    appointment.payment_approved_at = datetime.utcnow()
    appointment.payment_rejection_reason = None

    try:
        db.session.commit()
        flash('Dispute approved. Payment proof is valid and refund record has been added for processing.', 'success')
    except Exception as e:
        db.session.rollback()
        flash('Error resolving disputed payment.', 'error')
        print(f'Error resolving disputed payment (approve): {e}')

    return redirect(url_for('admin.payments'))


@admin_bp.route('/payments/<int:appointment_id>/dispute-reject', methods=['POST'])
@admin_required
def reject_disputed_payment(appointment_id):
    """Reject disputed timeout payment and close the case without refund."""
    appointment = Appointment.query.get_or_404(appointment_id)

    if appointment.payment_status != 'disputed' or appointment.status != 'cancelled':
        flash('This appointment is not in disputed timeout review.', 'error')
        return redirect(url_for('admin.payments'))

    rejection_reason = request.form.get('rejection_reason', '').strip()
    if not rejection_reason:
        flash('Please provide a reason for dispute rejection.', 'error')
        return redirect(url_for('admin.payments'))

    appointment.payment_status = 'rejected'
    appointment.payment_rejection_reason = rejection_reason

    try:
        db.session.commit()
        flash('Dispute rejected. Appointment is closed and no refund will be created.', 'info')
    except Exception as e:
        db.session.rollback()
        flash('Error rejecting disputed payment.', 'error')
        print(f'Error resolving disputed payment (reject): {e}')

    return redirect(url_for('admin.payments'))

# ─── Accounts (refunds, payouts, analytics) ───────────────────────────────────

def _doctor_share(charges, commission_percent=20):
    """Doctor share after platform commission (e.g. 80%)."""
    return round((charges or 0) * (1 - commission_percent / 100.0), 2)


@admin_bp.route('/accounts')
@admin_required
def accounts():
    """Accounts dashboard: payment flow, reserve, disputes, payouts, no-show, analytics"""
    from flask import current_app
    day_options = [1, 10, 25, 30]
    selected_days = request.args.get('days', 30, type=int)
    if selected_days not in day_options:
        selected_days = 30

    commission_pct = getattr(current_app.config, 'PLATFORM_COMMISSION_PERCENT', 20)
    pending_refunds = Refund.query.filter_by(status='pending').order_by(Refund.created_at.desc()).all()
    pending_payouts = DoctorPayoutRequest.query.filter_by(status='pending').order_by(DoctorPayoutRequest.requested_at.desc()).all()
    total_platform_revenue = db.session.query(func.coalesce(func.sum(PlatformRevenue.amount), 0)).scalar() or 0
    total_refunds_pending = db.session.query(func.coalesce(func.sum(Refund.amount), 0)).filter(Refund.status == 'pending').scalar() or 0
    disputes = Appointment.query.filter_by(status='completed_pending_review', patient_disputed=True).order_by(Appointment.updated_at.desc()).all()
    # Reserve: money held after payment approval until doctor earning is credited.
    # Includes upcoming approved appointments and completed_pending_review appointments.
    reserve_appointments = Appointment.query.filter(
        Appointment.payment_status == 'approved',
        Appointment.doctor_earning_credited_at.is_(None),
        Appointment.status.in_(['approved', 'completed_pending_review'])
    ).order_by(
        Appointment.payment_approved_at.desc(),
        Appointment.doctor_completed_at.desc(),
        Appointment.created_at.desc(),
    ).all()
    # Reserve card shows full held payment amount (100%).
    # Split into doctor/platform happens only at payout release.
    reserve_total = sum(float(a.charges or 0) for a in reserve_appointments)
    reserve_count = len(reserve_appointments)
    # Payment flow log: appointments with payment activity (recent first)
    payment_flow = Appointment.query.filter(
        Appointment.payment_status.in_(['submitted', 'approved', 'rejected', 'disputed'])
    ).order_by(Appointment.updated_at.desc()).limit(50).all()
    # No-show cases
    no_show_statuses = ('expired_mutual_noshow', 'expired_patient_noshow', 'expired_provider_failure')
    no_show_cases = Appointment.query.filter(
        Appointment.status.in_(no_show_statuses)
    ).order_by(Appointment.updated_at.desc()).limit(50).all()
    # Total paid out to doctors (approved/paid payout requests)
    total_paid_out = db.session.query(func.coalesce(func.sum(DoctorPayoutRequest.amount), 0)).filter(
        DoctorPayoutRequest.status.in_(['approved', 'paid'])
    ).scalar() or 0
    # Chart data: platform revenue by day (selected range)
    today = datetime.utcnow().date()
    start_day = today - timedelta(days=selected_days - 1)
    revenues = PlatformRevenue.query.filter(
        PlatformRevenue.created_at >= datetime.combine(start_day, datetime.min.time())
    ).all()

    from collections import defaultdict
    by_day = defaultdict(float)
    for rev in revenues:
        if rev.created_at:
            by_day[rev.created_at.date()] += float(rev.amount)

    revenue_labels = []
    revenue_data = []
    for offset in range(selected_days):
        day = start_day + timedelta(days=offset)
        revenue_labels.append(day.strftime('%d %b'))
        revenue_data.append(round(by_day.get(day, 0.0), 2))
    revenue_has_data = any(value > 0 for value in revenue_data)

    status_counts = db.session.query(Appointment.status, func.count(Appointment.id)).filter(
        Appointment.created_at >= datetime.combine(start_day, datetime.min.time())
    ).group_by(Appointment.status).all()

    status_labels = [((s[0] or 'other').replace('_', ' ').title()) for s in status_counts]
    status_data = [s[1] for s in status_counts]
    status_has_data = sum(status_data) > 0
    return render_template('admin/accounts.html',
                           pending_refunds=pending_refunds,
                           pending_payouts=pending_payouts,
                           total_platform_revenue=total_platform_revenue,
                           total_refunds_pending=total_refunds_pending,
                           total_paid_out=total_paid_out,
                           disputes=disputes,
                           reserve_total=reserve_total,
                           reserve_count=reserve_count,
                           reserve_appointments=reserve_appointments,
                           payment_flow=payment_flow,
                           no_show_cases=no_show_cases,
                           commission_pct=commission_pct,
                           revenue_labels=revenue_labels,
                           revenue_data=revenue_data,
                           revenue_has_data=revenue_has_data,
                           selected_days=selected_days,
                           day_options=day_options,
                           status_labels=status_labels,
                           status_data=status_data,
                           status_has_data=status_has_data)

@admin_bp.route('/accounts/payment-flow')
@admin_required
def accounts_payment_flow():
    """Full payment flow log: all appointments with payment timeline"""
    from flask import current_app
    commission_pct = getattr(current_app.config, 'PLATFORM_COMMISSION_PERCENT', 20)
    page = request.args.get('page', 1, type=int)
    per_page = 30
    q = Appointment.query.filter(
        Appointment.payment_status.in_(['submitted', 'approved', 'rejected', 'disputed'])
    ).order_by(Appointment.updated_at.desc())
    pagination = q.paginate(page=page, per_page=per_page, error_out=False)
    return render_template('admin/accounts_payment_flow.html',
                           pagination=pagination,
                           commission_pct=commission_pct)

@admin_bp.route('/accounts/refunds')
@admin_required
def accounts_refunds():
    """List all refunds (pending and processed)"""
    status_filter = request.args.get('status', '')
    q = Refund.query.order_by(Refund.created_at.desc())
    if status_filter in ('pending', 'processed', 'completed'):
        q = q.filter_by(status=status_filter)
    refunds = q.limit(100).all()
    return render_template('admin/accounts_refunds.html', refunds=refunds, status_filter=status_filter)

@admin_bp.route('/accounts/refunds/<int:refund_id>/mark-processed', methods=['POST'])
@admin_required
def refund_mark_processed(refund_id):
    """Mark refund as completed after transfer proof is attached."""
    r = Refund.query.get_or_404(refund_id)
    if r.status != 'pending':
        flash('Refund already processed.', 'info')
        return redirect(url_for('admin.accounts_refunds'))

    # Patient must submit payout details first.
    detail = r.payout_detail
    if not detail:
        flash('Patient payout details are missing. Ask patient to submit details in Refund Center.', 'warning')
        return redirect(url_for('admin.accounts_refunds'))

    # Admin proof is mandatory before completion.
    proof_file = request.files.get('refund_proof')
    if not proof_file or not proof_file.filename:
        flash('Attach refund transfer proof before marking completed.', 'error')
        return redirect(url_for('admin.accounts_refunds'))

    ext = proof_file.filename.rsplit('.', 1)[-1].lower() if '.' in proof_file.filename else ''
    if ext not in {'png', 'jpg', 'jpeg', 'pdf', 'webp'}:
        flash('Invalid proof file type. Allowed: PNG, JPG, JPEG, PDF, WEBP.', 'error')
        return redirect(url_for('admin.accounts_refunds'))

    upload_base = current_app.config.get('UPLOAD_FOLDER', 'app/static/uploads')
    proofs_dir = os.path.join(upload_base, 'refund_proofs')
    os.makedirs(proofs_dir, exist_ok=True)

    filename = secure_filename(proof_file.filename)
    unique_name = f"refund_{r.id}_{uuid.uuid4().hex}_{filename}"
    abs_path = os.path.join(proofs_dir, unique_name)

    try:
        proof_file.save(abs_path)
    except Exception as e:
        flash(f'Could not save refund proof: {e}', 'error')
        return redirect(url_for('admin.accounts_refunds'))

    # Store path relative to static/uploads/ for easy url_for('static', filename='uploads/...')
    detail.admin_proof_path = f"refund_proofs/{unique_name}"
    detail.admin_proof_note = request.form.get('admin_notes', '').strip() or detail.admin_proof_note

    r.status = 'completed'
    r.processed_at = datetime.utcnow()
    r.admin_notes = request.form.get('admin_notes', '').strip() or r.admin_notes

    db.session.commit()
    flash('Refund marked as completed and proof attached.', 'success')
    return redirect(url_for('admin.accounts_refunds'))

@admin_bp.route('/accounts/payouts')
@admin_required
def accounts_payouts():
    """List payout requests; approve/reject"""
    payout_requests = DoctorPayoutRequest.query.order_by(DoctorPayoutRequest.requested_at.desc()).limit(50).all()
    return render_template('admin/accounts_payouts.html', payout_requests=payout_requests)

@admin_bp.route('/accounts/payouts/<int:request_id>/approve', methods=['POST'])
@admin_required
def payout_approve(request_id):
    """Approve payout: deduct from doctor balance, create withdrawal transaction"""
    req = DoctorPayoutRequest.query.get_or_404(request_id)
    if req.status != 'pending':
        flash('Request already processed.', 'info')
        return redirect(url_for('admin.accounts_payouts'))
    doctor = req.doctor
    if req.amount > doctor.balance:
        flash('Doctor balance is insufficient.', 'error')
        return redirect(url_for('admin.accounts_payouts'))
    doctor.balance -= req.amount
    doctor.total_withdrawn += req.amount
    req.status = 'approved'
    req.processed_at = datetime.utcnow()
    req.admin_notes = request.form.get('admin_notes', '').strip()
    db.session.add(DoctorTransaction(
        doctor_id=doctor.id,
        appointment_id=None,
        transaction_type='withdrawal',
        amount=-req.amount,
        description=f"Payout request #{req.id} approved",
        status='completed',
        admin_notes=req.admin_notes
    ))
    db.session.commit()
    flash(f'Payout of PKR {req.amount:,.0f} approved. Deducted from doctor balance.', 'success')
    return redirect(url_for('admin.accounts_payouts'))

@admin_bp.route('/accounts/payouts/<int:request_id>/reject', methods=['POST'])
@admin_required
def payout_reject(request_id):
    """Reject payout request"""
    req = DoctorPayoutRequest.query.get_or_404(request_id)
    if req.status != 'pending':
        flash('Request already processed.', 'info')
        return redirect(url_for('admin.accounts_payouts'))
    req.status = 'rejected'
    req.processed_at = datetime.utcnow()
    req.admin_notes = request.form.get('admin_notes', '').strip()
    db.session.commit()
    flash('Payout request rejected.', 'info')
    return redirect(url_for('admin.accounts_payouts'))

@admin_bp.route('/accounts/doctors/<int:doctor_id>/financials')
@admin_required
def doctor_financials(doctor_id):
    """View one doctor's full financial history"""
    doctor = Doctor.query.get_or_404(doctor_id)
    transactions = DoctorTransaction.query.filter_by(doctor_id=doctor.id).order_by(DoctorTransaction.created_at.desc()).limit(100).all()
    payout_requests = DoctorPayoutRequest.query.filter_by(doctor_id=doctor.id).order_by(DoctorPayoutRequest.requested_at.desc()).all()
    return render_template('admin/doctor_financials.html', doctor=doctor, transactions=transactions, payout_requests=payout_requests)

@admin_bp.route('/patients/<int:patient_id>/medical-history')
@admin_required
def view_patient_medical_history(patient_id):
    """View medical history for a specific patient"""
    patient_user = User.query.filter_by(id=patient_id, role='patient').first_or_404()
    patient = patient_user.patient_profile
    
    if not patient:
        flash('Patient profile not found.', 'error')
        return redirect(url_for('admin.patients'))
    
    # Get medical histories grouped by disease
    histories = MedicalHistory.query.filter_by(
        patient_id=patient.id
    ).order_by(MedicalHistory.created_at.desc()).all()
    
    # Group by disease
    grouped_histories = {}
    for history in histories:
        disease = history.disease
        if disease not in grouped_histories:
            grouped_histories[disease] = []
        grouped_histories[disease].append(history)
    
    return render_template('admin/patient_medical_history.html',
                         patient=patient,
                         patient_user=patient_user,
                         grouped_histories=grouped_histories)

# ─── Review Moderation ─────────────────────────────────────────────────────────

@admin_bp.route('/reviews')
@admin_required
def reviews():
    """List all patient reviews for moderation."""
    from app.models import Review
    from app.utils.review_fraud import FLAG_REASON_LABELS, FRAUD_STATUS_LABELS, flag_reason_label

    all_reviews = Review.query.order_by(Review.created_at.desc()).all()
    flagged_count = sum(1 for r in all_reviews if (r.fraud_status or 'clear') != 'clear')
    return render_template(
        'admin/reviews.html',
        reviews=all_reviews,
        flagged_count=flagged_count,
        flag_reason_labels=FLAG_REASON_LABELS,
        fraud_status_labels=FRAUD_STATUS_LABELS,
        flag_reason_label=flag_reason_label,
    )


@admin_bp.route('/reviews/<int:review_id>/approve', methods=['POST'])
@admin_required
def approve_review(review_id):
    """Approve a flagged review — make public."""
    from app.models import Review
    review = Review.query.get_or_404(review_id)
    review.fraud_status = 'clear'
    review.is_visible = True
    db.session.commit()
    flash('Review approved and is now public.', 'success')
    return redirect(url_for('admin.reviews'))


@admin_bp.route('/reviews/<int:review_id>/reject', methods=['POST'])
@admin_required
def reject_review(review_id):
    """Reject a suspicious review — keep hidden."""
    from app.models import Review
    review = Review.query.get_or_404(review_id)
    review.fraud_status = 'blocked'
    review.is_visible = False
    db.session.commit()
    flash('Review rejected and hidden from public profiles.', 'warning')
    return redirect(url_for('admin.reviews'))


@admin_bp.route('/reviews/<int:review_id>/toggle-visibility', methods=['POST'])
@admin_required
def toggle_review_visibility(review_id):
    """Toggle a review's public visibility (admin moderation)."""
    from app.models import Review
    review = Review.query.get_or_404(review_id)
    review.is_visible = not review.is_visible
    db.session.commit()
    status = 'visible' if review.is_visible else 'hidden'
    flash(f'Review is now {status}.', 'success')
    return redirect(url_for('admin.reviews'))


from app.utils.admin_permissions import register_admin_rbac

register_admin_rbac(admin_bp)

import app.routes.admin_staff  # noqa: F401, E402

