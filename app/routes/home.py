import os

from flask import Blueprint, current_app, jsonify, render_template, request, send_from_directory
from app.models import Doctor, Blog, Disease, User
from app.database import db
from app.utils.auth import get_current_user, login_required
from app.utils.geocoding import geocode_address
from sqlalchemy import func

home_bp = Blueprint('home', __name__)


@home_bp.route('/favicon.ico')
def favicon():
    """Serve favicon from static assets to avoid browser 404 noise."""
    return send_from_directory(
        os.path.join(current_app.root_path, 'static'),
        'favicon.svg',
        mimetype='image/svg+xml',
    )

@home_bp.route('/')
def index():
    """Home page - Modern SaaS landing page"""
    from app.utils.categories import get_featured_specialties
    featured = get_featured_specialties()
    
    # Fetch top 4 approved and verified doctors for the homepage
    # We fetch them ordered by creation date to show the newest professionals
    doctors = Doctor.query.filter_by(
        is_approved=True, 
        is_verified=True
    ).order_by(Doctor.created_at.desc()).limit(4).all()
    
    # Fetch 3 latest published blogs for the homepage blog section
    latest_blogs = Blog.query.filter_by(status='published').order_by(Blog.created_at.desc()).limit(3).all()

    return render_template('home/landing.html', 
                         featured_specialties=featured,
                         doctors=doctors,
                         latest_blogs=latest_blogs)

@home_bp.route('/about')
def about():
    """About page"""
    return render_template('home/about.html')

@home_bp.route('/how-it-works')
def how_it_works():
    """How the platform works"""
    return render_template('home/how_it_works.html')

@home_bp.route('/faq')
def faq():
    """Frequently asked questions"""
    return render_template('home/faq.html')


@home_bp.route('/contact', methods=['GET', 'POST'])
def contact():
    """Contact page"""
    from flask import flash, redirect, url_for
    if request.method == 'POST':
        name = (request.form.get('name') or '').strip()
        email = (request.form.get('email') or '').strip()
        message = (request.form.get('message') or '').strip()
        if not name or not email or not message:
            flash('Please fill in all required fields.', 'warning')
        else:
            flash('Thank you! Your message has been received. We will reply to you at ' + email + '.', 'success')
            return redirect(url_for('home.contact'))
    return render_template('home/contact.html')

@home_bp.route('/newsletter', methods=['POST'])
def newsletter_subscribe():
    """Newsletter signup (acknowledgement only)."""
    from flask import flash, redirect, request, url_for
    email = (request.form.get('email') or '').strip()
    if email:
        flash('Thanks for subscribing! You will hear from us at ' + email + '.', 'success')
    else:
        flash('Please enter a valid email address.', 'warning')
    return redirect(request.referrer or url_for('home.index'))

@home_bp.route('/privacy')
def privacy():
    """Privacy policy page"""
    return render_template('home/privacy.html')

@home_bp.route('/terms')
def terms():
    """Terms of service page"""
    return render_template('home/terms.html')

@home_bp.route('/doctors')
def doctors():
    """Public doctors listing page"""
    # Get filter parameters
    specialty = request.args.get('specialty', '')
    appointment_type = request.args.get('type', 'all')
    gender = request.args.get('gender', 'all')
    city = request.args.get('city', 'all')
    
    # Build query for approved doctors only
    query = Doctor.query.filter_by(is_approved=True, is_verified=True)
    
    # Apply filters
    if specialty:
        query = query.filter_by(specialization=specialty)
    
    if appointment_type != 'all':
        if appointment_type == 'video':
            query = query.filter(Doctor.video_charges.isnot(None))
        elif appointment_type == 'physical':
            query = query.filter(Doctor.physical_charges.isnot(None))
    
    if gender != 'all':
        query = query.join(User).filter(User.gender == gender)
    
    if city != 'all':
        query = query.filter(Doctor.city.ilike(f'%{city}%'))
    
    # Get paginated results
    page = request.args.get('page', 1, type=int)
    doctors = query.order_by(Doctor.created_at.desc()).paginate(
        page=page, per_page=12, error_out=False
    )
    
    # Get available cities for filter
    cities = db.session.query(Doctor.city).filter(
        Doctor.city.isnot(None),
        Doctor.city != ''
    ).distinct().all()
    cities = [city[0] for city in cities if city[0]]
    
    return render_template('home/doctors.html', 
                         doctors=doctors,
                         current_specialty=specialty,
                         current_type=appointment_type,
                         current_gender=gender,
                         current_city=city,
                         cities=cities)

@home_bp.route('/doctor/<int:doctor_id>')
@login_required
def doctor_profile(doctor_id):
    """Public doctor profile view - Shows both approved and pending doctors (login required)"""
    # Query doctor with fresh data from database (SQLAlchemy will query from DB)
    doctor = Doctor.query.filter_by(id=doctor_id).first_or_404()
    
    # Check if doctor is approved
    is_approved = doctor.is_approved and doctor.is_verified
    is_pending = not doctor.is_approved and doctor.appeal_status == 'pending'
    is_rejected = not doctor.is_approved and doctor.appeal_status == 'rejected'
    is_suspended = not doctor.is_approved and doctor.appeal_status == 'suspended'
    
    return render_template('home/doctor_profile.html', 
                         doctor=doctor, 
                         is_approved=is_approved,
                         is_pending=is_pending,
                         is_rejected=is_rejected,
                         is_suspended=is_suspended,
                         is_own_profile=False)


@home_bp.route('/api/geocode')
def geocode_lookup():
    """Proxy Geoapify geocoding so the API key stays server-side."""
    query = (request.args.get('q') or '').strip()
    if not query:
        return jsonify({'success': False, 'message': 'Address is required.'}), 400

    api_key = current_app.config.get('GEOAPIFY_API_KEY', '')
    if not api_key:
        return jsonify({
            'success': False,
            'message': 'Geocoding is not configured. Add GEOAPIFY_API_KEY on the server.',
        }), 503

    lat, lon, label = geocode_address(query, api_key)
    if lat is None or lon is None:
        return jsonify({'success': False, 'message': 'Location not found.'}), 404

    return jsonify({
        'success': True,
        'lat': lat,
        'lon': lon,
        'label': label,
    })
