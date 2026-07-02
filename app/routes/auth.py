from flask import Blueprint, render_template, request, flash, redirect, url_for, session, jsonify, make_response
from app.models import User, Doctor, Patient, Admin
from app.database import db
from app.forms import LoginForm, UnifiedRegistrationForm
from app.services.email_service import send_welcome_patient_email, send_welcome_doctor_email
from app.utils.auth import login_required, get_current_user, find_user_by_email
from app.utils.admin_permissions import get_admin_landing_endpoint, get_accessible_panel_keys, is_super_admin
from app.utils.file_upload import save_uploaded_file
from app.utils.categories import normalize_category
from werkzeug.security import check_password_hash
from datetime import datetime, date
import base64
import uuid
import os

auth_bp = Blueprint('auth', __name__)

def save_base64_image(base64_data, subfolder):
    """Save base64 image data to file"""
    try:
        if not base64_data:
            return None
        
        # Remove data URL prefix if present
        if ',' in base64_data:
            base64_data = base64_data.split(',')[1]
        
        # Decode base64 data
        image_data = base64.b64decode(base64_data)
        
        # Generate unique filename
        filename = f"{uuid.uuid4().hex}.jpg"
        
        # Create upload directory
        upload_path = os.path.join('app', 'static', 'uploads', subfolder)
        os.makedirs(upload_path, exist_ok=True)
        
        # Save file
        file_path = os.path.join(upload_path, filename)
        with open(file_path, 'wb') as f:
            f.write(image_data)
        
        # Return relative path for database storage
        relative_path = os.path.join(subfolder, filename).replace('\\', '/')
        return relative_path
        
    except Exception as e:
        print(f"Error saving base64 image: {e}")
        return None

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    """User login"""
    # GET only: skip login screen if already signed in (go to role home).
    # POST must always run so users can switch accounts (e.g. patient -> admin).
    if request.method == 'GET' and 'user_id' in session:
        user = get_current_user()
        if user:
            if user.role == 'admin':
                if not is_super_admin(user) and not get_accessible_panel_keys(user):
                    session.clear()
                    flash('Your admin account has no panel access. Contact the super administrator.', 'error')
                    return redirect(url_for('auth.login'))
                return redirect(url_for(get_admin_landing_endpoint(user)))
            if user.role == 'doctor':
                return redirect(url_for('doctors.dashboard'))
            if user.role == 'patient':
                return redirect(url_for('patients.dashboard'))
        return redirect(url_for('home.index'))
    
    # Clear any session-based form data
    session.pop('form_data', None)
    session.pop('registration_data', None)
    session.pop('temp_form_data', None)
    
    # Always create a fresh form on GET requests (no pre-filled data)
    form = LoginForm()
    
    # On GET requests, create fresh form with cache-control headers
    if request.method == 'GET':
        form = LoginForm(obj=None, data=None)
        # Render template with cache-control headers to prevent browser caching
        response = make_response(render_template('auth/login.html', form=form))
        response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate, max-age=0'
        response.headers['Pragma'] = 'no-cache'
        response.headers['Expires'] = '0'
        return response
    
    if form.validate_on_submit():
        user = find_user_by_email(form.email.data)
        
        if user and user.check_password(form.password.data) and user.is_active:
            # Clear any existing session data first
            session.clear()
            
            # Mark user as online
            user.is_online = True
            db.session.commit()
            
            session['user_id'] = user.id
            session['user_role'] = user.role
            session['user_name'] = user.name
            
            # Always set session as permanent - users logout manually only
            # Sessions persist for 1 year regardless of debug/production mode
            session.permanent = True
            session.modified = True
            
            flash(f'Welcome back, {user.name}!', 'success')
            
            # Check if there's a next URL to redirect to
            next_url = session.pop('next_url', None) or request.form.get('next_url')
            if next_url:
                return redirect(next_url)
            
            # Redirect based on role
            if user.role == 'doctor':
                return redirect(url_for('doctors.dashboard'))
            elif user.role == 'patient':
                # Check if patient profile is complete
                patient = user.patient_profile
                if patient and not patient.is_profile_complete():
                    session['profile_incomplete'] = True
                    flash('Please complete your profile to access all features.', 'warning')
                return redirect(url_for('patients.dashboard'))
            elif user.role == 'admin':
                if not is_super_admin(user) and not get_accessible_panel_keys(user):
                    session.clear()
                    flash('Your admin account has no panel access. Contact the super administrator.', 'error')
                    return redirect(url_for('auth.login'))
                return redirect(url_for(get_admin_landing_endpoint(user)))
            else:
                return redirect(url_for('home.index'))
        else:
            # Invalid credentials - redirect to prevent form resubmission warning
            flash('Invalid email or password.', 'error')
            return redirect(url_for('auth.login'))
    else:
        # Form validation errors - redirect to prevent form resubmission warning
        if request.method == 'POST':
            # Store field-specific errors in flash messages
            for field, errors in form.errors.items():
                for error in errors:
                    flash(f'{getattr(form, field).label.text}: {error}', 'error')
            return redirect(url_for('auth.login'))
    
    # On GET requests (including after redirect), render with cache-control headers
    response = make_response(render_template('auth/login.html', form=form))
    response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate, max-age=0'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    return response

@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    """Unified registration for both patients and doctors"""
    if 'user_id' in session:
        return redirect(url_for('home.index'))
    
    # Clear any session-based form data
    session.pop('form_data', None)
    session.pop('registration_data', None)
    session.pop('temp_form_data', None)
    
    # Always create a fresh form on GET requests (no pre-filled data)
    # On POST with validation errors, form will contain submitted data
    form = UnifiedRegistrationForm()
    
    # Clear form data if this is a fresh GET request (not a validation error redirect)
    if request.method == 'GET':
        # Create a completely fresh form instance
        form = UnifiedRegistrationForm(obj=None, data=None)
        
        # Render template with cache-control headers to prevent browser caching
        response = make_response(render_template('auth/register.html', form=form))
        response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate, max-age=0'
        response.headers['Pragma'] = 'no-cache'
        response.headers['Expires'] = '0'
        return response
    
    if form.validate_on_submit():
        
        # Initialize file paths first (before creating User object)
        profile_picture_path = None
        cnic_front_path = None
        cnic_back_path = None
        degree_documents = []
        live_photo_path = None
        
        # Handle file uploads BEFORE creating user
        # Upload profile picture (for both roles)
        if form.profile_picture.data:
            success, file_path, error = save_uploaded_file(form.profile_picture.data, 'profile_pictures')
            if success:
                profile_picture_path = file_path
            else:
                flash(f'Error uploading profile picture: {error}', 'error')
                return render_template('auth/register.html', form=form)
        
        # Convert string date to date object
        date_of_birth_obj = None
        if form.date_of_birth.data:
            try:
                date_of_birth_obj = date.fromisoformat(form.date_of_birth.data)
            except ValueError:
                flash('Invalid date format. Please use YYYY-MM-DD format.', 'error')
                return render_template('auth/register.html', form=form)
        
        # Check if user already exists (prevent duplicate registration)
        existing_user = User.query.filter(
            (User.email == form.email.data) | (User.cnic == form.cnic.data)
        ).first()
        if existing_user:
            flash('Email or CNIC already registered. Please use different credentials.', 'error')
            return render_template('auth/register.html', form=form)
        
        # Check if doctor profile already exists for this user (prevent duplicate doctor profiles)
        if form.role.data == 'doctor':
            # Check if PMC code is already in use
            existing_doctor = Doctor.query.filter_by(pmc_code=form.pmc_code.data).first()
            if existing_doctor:
                flash('PMC Code already registered. Please use a different PMC code.', 'error')
                return render_template('auth/register.html', form=form)
        
        # Create user
        user = User(
            name=form.name.data,
            email=form.email.data,
            phone=form.phone.data,
            cnic=form.cnic.data,
            role=form.role.data,
            date_of_birth=date_of_birth_obj,
            gender=form.gender.data,
            address=None,  # Address field removed - only city is needed
            profile_picture=profile_picture_path,
            is_active=True
        )
        user.set_password(form.password.data)  # Set password using the method
        
        db.session.add(user)
        db.session.flush()  # Get user ID - this commits user to database temporarily
        
        # Check if doctor profile already exists for this user_id (prevent duplicate after flush)
        if form.role.data == 'doctor':
            existing_doctor_profile = Doctor.query.filter_by(user_id=user.id).first()
            if existing_doctor_profile:
                db.session.rollback()
                flash('Doctor profile already exists for this account.', 'error')
                return render_template('auth/register.html', form=form)
        
        # Upload CNIC images (only for doctors - patients will upload during profile completion)
        if form.role.data == 'doctor':
            if form.cnic_front.data:
                success, file_path, error = save_uploaded_file(form.cnic_front.data, 'cnic')
                if success:
                    cnic_front_path = file_path
                else:
                    flash(f'Error uploading CNIC front image: {error}', 'error')
                    return render_template('auth/register.html', form=form)
            
            if form.cnic_back.data:
                success, file_path, error = save_uploaded_file(form.cnic_back.data, 'cnic')
                if success:
                    cnic_back_path = file_path
                else:
                    flash(f'Error uploading CNIC back image: {error}', 'error')
                    return render_template('auth/register.html', form=form)
        
        # Upload degree documents (for doctors)
        degree_files = request.files.getlist('degree_files[]')
        
        if form.role.data == 'doctor' and degree_files:
            for degree_file in degree_files:
                if degree_file.filename:
                    success, file_path, error = save_uploaded_file(degree_file, 'degrees')
                    if success:
                        degree_documents.append(file_path)
                    else:
                        flash(f'Error uploading degree document: {error}', 'error')
                        return render_template('auth/register.html', form=form)
        
        # Handle live photo (for doctors)
        if form.role.data == 'doctor' and form.live_photo_data.data:
            live_photo_path = save_base64_image(form.live_photo_data.data, 'live_photos')
        
        # Create role-specific profile (with duplicate check)
        if form.role.data == 'patient':
            # For patients, create minimal profile - profile completion will happen after registration
            # CNIC images will be uploaded during profile completion, not during registration
            patient = Patient(
                user_id=user.id,
                emergency_contact=form.emergency_contact.data if form.emergency_contact.data else None,
                emergency_relation=form.emergency_relation.data if form.emergency_relation.data else None,
                blood_group=form.blood_group.data if form.blood_group.data else None,
                allergies=form.allergies.data if form.allergies.data else None,
                medical_history=form.medical_history.data if form.medical_history.data else None,
                cnic_front_image=None,  # Will be uploaded during profile completion
                cnic_back_image=None    # Will be uploaded during profile completion
            )
            db.session.add(patient)
            
        elif form.role.data == 'doctor':
            # Double-check: Verify no doctor profile exists for this user
            existing_doctor_profile = Doctor.query.filter_by(user_id=user.id).first()
            if existing_doctor_profile:
                db.session.rollback()
                flash('Doctor profile already exists for this account. Registration failed.', 'error')
                return render_template('auth/register.html', form=form)
            
            # Normalize category from specialization input (convert person names to category names)
            specialization_input = form.specialization.data or form.category.data or ''
            doctor_category = normalize_category(specialization_input)
            
            # Get qualifications from form or request
            qualifications_text = ''
            if hasattr(form, 'qualifications') and form.qualifications.data:
                qualifications_text = form.qualifications.data
            elif 'qualifications' in request.form:
                qualifications_text = request.form.get('qualifications', '')
            
            # Use qualifications as education field (qualifications replaces education)
            education_text = qualifications_text or (form.education.data if hasattr(form, 'education') and form.education.data else '')
            
            # Create doctor profile (only once)
            # Hospital affiliation removed - doctors will add hospitals when setting appointment slots
            doctor = Doctor(
                user_id=user.id,
                category=doctor_category,  # Use specialization value as category
                specialization=doctor_category,  # Specialization is now the category
                experience=form.experience.data,
                pmc_code=form.pmc_code.data,
                education=education_text,  # Qualifications text
                bio=form.bio.data,
                # Hospital affiliation removed - doctors add hospitals per time slot
                city=form.city.data,
                location=form.location.data if form.location.data else '',  # Hospital/Clinic address
                cnic_front_image=cnic_front_path,
                cnic_back_image=cnic_back_path,
                degree_documents=degree_documents,
                live_photo=live_photo_path,
                is_approved=False,  # Requires admin approval
                is_verified=False
            )
            db.session.add(doctor)
        
        try:
            db.session.commit()
            
            # After commit, verify no duplicate doctor profiles were created
            if form.role.data == 'doctor':
                doctor_count = Doctor.query.filter_by(user_id=user.id).count()
                if doctor_count > 1:
                    # Remove duplicate profiles, keep only the first one
                    duplicate_doctors = Doctor.query.filter_by(user_id=user.id).order_by(Doctor.id).all()
                    for duplicate in duplicate_doctors[1:]:  # Remove all except first
                        db.session.delete(duplicate)
                    db.session.commit()
                    flash('Duplicate profile detected and removed.', 'warning')
            
            flash(f'Registration successful! Welcome, {user.name}!', 'success')
            
            # Auto-login after registration
            session.clear()  # Clear any existing session data first
            session['user_id'] = user.id
            session['user_role'] = user.role
            session['user_name'] = user.name
            session.permanent = True  # Set session as permanent for proper CSRF handling
            session.modified = True
            
            # Redirect based on role
            if user.role == 'doctor':
                flash('Your doctor account is pending admin approval.', 'info')
                # Send welcome / pending approval email to doctor
                try:
                    send_welcome_doctor_email(user.email, user.name)
                except Exception as e:
                    print(f'Error sending doctor welcome email: {e}')
                return redirect(url_for('home.index'))
            elif user.role == 'patient':
                # Query patient profile directly to ensure it's loaded after commit
                try:
                    patient = Patient.query.filter_by(user_id=user.id).first()
                    if not patient:
                        # This should not happen - patient should have been created
                        # Log error but still redirect (user account exists)
                        print(f'WARNING: Patient profile not found for user_id {user.id} after registration')
                        flash('Registration successful, but profile setup encountered an issue. Please contact support.', 'warning')
                    else:
                        # Check if profile is incomplete
                        if not patient.is_profile_complete():
                            session['profile_incomplete'] = True
                            flash('Please complete your profile to access all features.', 'warning')
                except Exception as e:
                    # Log error but still allow redirect (user account was created successfully)
                    print(f'Error checking patient profile after registration: {e}')
                    import traceback
                    traceback.print_exc()
                
                # Force session save (already set above, but ensure it's marked as modified)
                session.permanent = True
                session.modified = True
                
                # Send welcome email to new patient
                try:
                    send_welcome_patient_email(user.email, user.name)
                except Exception as e:
                    print(f'Error sending patient welcome email: {e}')
                
                # Redirect to patient dashboard
                return redirect(url_for('patients.dashboard'))
            else:
                return redirect(url_for('home.index'))
                
        except Exception as e:
            db.session.rollback()
            # Check if error is due to duplicate entry
            error_msg = str(e).lower()
            if 'unique' in error_msg or 'duplicate' in error_msg or 'integrity' in error_msg:
                flash('Account already exists. Please login or use different credentials.', 'error')
            else:
                flash('Registration failed. Please try again.', 'error')
                print(f'Registration error: {e}')
                import traceback
                traceback.print_exc()
                # Return to registration form on error
                return render_template('auth/register.html', form=form)
    
    # Render template with cache-control headers to prevent browser caching
    # Pass form errors to template so JavaScript can detect them
    response = make_response(render_template('auth/register.html', form=form, form_errors=form.errors))
    response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate, max-age=0'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    return response

@auth_bp.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    """Handle forgot password — send reset link via email"""
    if 'user_id' in session:
        return redirect(url_for('home.index'))

    if request.method == 'POST':
        email = request.form.get('email', '').strip()
        user = find_user_by_email(email)

        # Always show the same message to avoid user enumeration
        flash('If that email address is registered, a password reset link has been sent.', 'info')

        if user:
            import secrets
            from datetime import timedelta
            from app.services.email_service import send_password_reset_email

            # Generate a secure random token
            token = secrets.token_urlsafe(48)
            user.reset_token = token
            user.reset_token_expiry = datetime.utcnow() + timedelta(hours=1)
            db.session.commit()

            # Build the reset URL
            reset_url = url_for('auth.reset_password', token=token, _external=True)

            # Send the email
            try:
                send_password_reset_email(user.email, user.name, token)
            except Exception as e:
                print(f'Error sending password reset email: {e}')

        return redirect(url_for('auth.forgot_password'))

    return render_template('auth/forgot_password.html')

@auth_bp.route('/reset-password/<token>', methods=['GET', 'POST'])
def reset_password(token):
    """Handle password reset via email token"""
    if 'user_id' in session:
        return redirect(url_for('home.index'))

    # Find user with this token
    user = User.query.filter_by(reset_token=token).first()

    # Validate token exists and is not expired
    if not user or not user.reset_token_expiry or datetime.utcnow() > user.reset_token_expiry:
        flash('This password reset link is invalid or has expired. Please request a new one.', 'error')
        return redirect(url_for('auth.forgot_password'))

    if request.method == 'POST':
        password = request.form.get('password', '').strip()
        confirm_password = request.form.get('confirm_password', '').strip()

        # Market-standard password strength checks
        import re
        password_errors = []
        if len(password) < 8:
            password_errors.append('at least 8 characters')
        if not re.search(r'[A-Z]', password):
            password_errors.append('at least one uppercase letter (A-Z)')
        if not re.search(r'[a-z]', password):
            password_errors.append('at least one lowercase letter (a-z)')
        if not any(ch.isdigit() for ch in password):
            password_errors.append('at least one number (0-9)')
        if not any(ch in set('!@#$%^&*()-_=+[]{}|;:,.<>?/`~"\' ') for ch in password):
            password_errors.append('at least one special character (!@#$%^&* etc.)')

        if password_errors:
            flash(f'Password must contain: {", ".join(password_errors)}.', 'error')
            return render_template('auth/reset_password.html', token=token)

        if password != confirm_password:
            flash('Passwords do not match. Please try again.', 'error')
            return render_template('auth/reset_password.html', token=token)

        # Prevent using the same password as before
        if user.check_password(password):
            flash('New password must be different from the current one.', 'error')
            return render_template('auth/reset_password.html', token=token)

        # Update password and clear the token
        user.set_password(password)
        user.reset_token = None
        user.reset_token_expiry = None
        db.session.commit()

        flash('Your password has been reset successfully! You can now log in.', 'success')
        return redirect(url_for('auth.login'))

    return render_template('auth/reset_password.html', token=token)

@auth_bp.route('/logout')
@login_required
def logout():
    """User logout"""
    user_name = session.get('user_name', 'User')
    
    # Mark user as offline
    user_id = session.get('user_id')
    if user_id:
        user = User.query.get(user_id)
        if user:
            user.is_online = False
            db.session.commit()
    
    session.clear()
    flash(f'Goodbye, {user_name}! You have been logged out.', 'info')
    return redirect(url_for('home.index'))

@auth_bp.route('/logout-session', methods=['POST'])
def logout_session():
    """Clear session on tab close (called via AJAX)"""
    session.clear()
    return jsonify({'status': 'success'}), 200

@auth_bp.route('/profile')
@login_required
def profile():
    """User profile page"""
    user = User.query.get(session['user_id'])
    
    if user.role == 'doctor':
        return redirect(url_for('doctors.profile'))
    elif user.role == 'patient':
        return redirect(url_for('patients.profile'))
    elif user.role == 'admin':
        return redirect(url_for('admin.profile'))
    
    return redirect(url_for('home.index'))
