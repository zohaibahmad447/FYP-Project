from functools import wraps
from flask import session, redirect, url_for, flash, request
from sqlalchemy import func
from app.models import User, Doctor, Patient, Admin

def login_required(f):
    """Decorator to require login"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please log in to access this page.', 'warning')
            # Store the requested URL to redirect after login
            session['next_url'] = request.url
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated_function

def role_required(required_role):
    """Decorator to require specific role"""
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if 'user_id' not in session:
                flash('Please log in to access this page.', 'warning')
                return redirect(url_for('auth.login'))
            
            user = User.query.get(session['user_id'])
            if not user or user.role != required_role:
                flash('You do not have permission to access this page.', 'error')
                return redirect(url_for('home.index'))
            
            return f(*args, **kwargs)
        return decorated_function
    return decorator

def doctor_required(f):
    """Decorator to require doctor role"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please log in to access this page.', 'warning')
            return redirect(url_for('auth.login'))
        
        user = User.query.get(session['user_id'])
        if not user or user.role != 'doctor':
            flash('Only doctors can access this page.', 'error')
            return redirect(url_for('home.index'))
        
        # Allow access to pending doctors - they will see pending dashboard
        return f(*args, **kwargs)
    return decorated_function

def patient_required(f):
    """Decorator to require patient role"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please log in to access this page.', 'warning')
            # Store the requested URL to redirect after login
            session['next_url'] = request.url
            return redirect(url_for('auth.login'))
        
        user = User.query.get(session['user_id'])
        if not user:
            # User doesn't exist - clear session and redirect
            session.clear()
            flash('Your session has expired. Please log in again.', 'warning')
            session['next_url'] = request.url
            return redirect(url_for('auth.login'))
        
        if user.role != 'patient':
            flash('Only patients can access this page.', 'error')
            return redirect(url_for('home.index'))
        
        return f(*args, **kwargs)
    return decorated_function

def admin_required(f):
    """Decorator to require admin role"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        from flask import jsonify
        
        # Check if this is an AJAX/JSON request
        is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest' or \
                  request.headers.get('Content-Type') == 'application/json' or \
                  request.is_json or \
                  request.path.endswith('-json') or \
                  request.path.endswith('.json')
        
        # Check if user_id exists in session
        if 'user_id' not in session:
            if is_ajax:
                return jsonify({'error': 'Authentication required', 'redirect': url_for('auth.login')}), 401
            flash('Please log in to access this page.', 'warning')
            # Store the requested URL to redirect after login
            session['next_url'] = request.url
            return redirect(url_for('auth.login'))
        
        # Get user from database
        try:
            user = User.query.get(session['user_id'])
            if not user:
                # User doesn't exist in database - clear session
                session.clear()
                if is_ajax:
                    return jsonify({'error': 'Session expired', 'redirect': url_for('auth.login')}), 401
                flash('Your session has expired. Please log in again.', 'warning')
                return redirect(url_for('auth.login'))
            
            # Check if user is active
            if not user.is_active:
                session.clear()
                if is_ajax:
                    return jsonify({'error': 'Account deactivated', 'redirect': url_for('auth.login')}), 403
                flash('Your account has been deactivated. Please contact support.', 'error')
                return redirect(url_for('auth.login'))
            
            # Check if user has admin role
            if user.role != 'admin':
                print(f"[AUTH DENIED] User {user.id} ({user.email}) attempted admin access with role '{user.role}'")
                if is_ajax:
                    return jsonify({'error': 'Admin access required', 'redirect': url_for('home.index')}), 403
                flash('Only administrators can access this page.', 'error')
                return redirect(url_for('home.index'))
            
            return f(*args, **kwargs)
        except Exception as e:
            # Handle any database errors
            import traceback
            print(f'Error in admin_required decorator: {e}')
            traceback.print_exc()
            if is_ajax:
                return jsonify({'error': 'Database error', 'message': str(e)}), 500
            flash('An error occurred. Please try again.', 'error')
            return redirect(url_for('auth.login'))
    return decorated_function

def get_current_user():
    """Get current logged in user"""
    if 'user_id' in session:
        return User.query.get(session['user_id'])
    return None

def get_user_profile():
    """Get current user's profile based on role"""
    user = get_current_user()
    if not user:
        return None
    
    if user.role == 'doctor':
        return user.doctor_profile
    elif user.role == 'patient':
        return user.patient_profile
    elif user.role == 'admin':
        return user.admin_profile
    
    return None


def normalize_email(email):
    """Normalize email for lookup (staff and user logins are case-insensitive)."""
    return (email or '').strip().lower()


def find_user_by_email(email):
    """Find a user by email, ignoring case differences."""
    normalized = normalize_email(email)
    if not normalized:
        return None
    return User.query.filter(func.lower(User.email) == normalized).first()
