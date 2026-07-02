from flask import Flask
from flask_migrate import Migrate
from flask_socketio import SocketIO
from config import config
from datetime import timedelta
import os

# Import db from database module to ensure single instance
from app.database import db

# Initialize extensions
migrate = Migrate()
socketio = SocketIO()

def create_app(config_name=None):
    """Application factory pattern"""
    flask_app = Flask(__name__)
    
    # Load configuration
    config_name = config_name or os.environ.get('FLASK_ENV', 'development')
    flask_app.config.from_object(config[config_name])
    
    # Configure session - Persistent sessions (never auto-logout)
    # Sessions will persist for 1 year - users logout manually only
    flask_app.config['SESSION_COOKIE_EXPIRES'] = timedelta(days=365)  # 1 year cookie expiry
    flask_app.config['SESSION_COOKIE_NAME'] = 'quickcare_session_simple'
    flask_app.config['SESSION_COOKIE_PATH'] = '/'
    flask_app.config['SESSION_COOKIE_DOMAIN'] = None
    # Respect ProductionConfig (secure cookies on HTTPS); base Config keeps False for HTTP dev
    flask_app.config.setdefault('SESSION_COOKIE_SECURE', False)
    flask_app.config['SESSION_COOKIE_HTTPONLY'] = True
    flask_app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
    # Session lifetime - Maximum (1 year) - users logout manually only
    # Users will remain logged in indefinitely until they explicitly logout
    # Sessions persist across browser restarts and system reboots
    flask_app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=365)  # 1 year - users logout manually only
    
    # Initialize extensions with app
    db.init_app(flask_app)
    migrate.init_app(flask_app, db)
    
    # Ensure DB schema is up to date (including accounts columns) before scheduler runs
    with flask_app.app_context():
        db.create_all()
        try:
            from app.utils.accounts_migration import ensure_accounts_schema
            ensure_accounts_schema()
        except Exception:
            pass
        try:
            from app.utils.qa_migration import ensure_qa_schema
            ensure_qa_schema()
        except Exception:
            pass
        try:
            from app.utils.review_flow_migration import ensure_review_flow_schema
            ensure_review_flow_schema()
        except Exception:
            pass
        try:
            from app.utils.review_fraud_migration import ensure_review_fraud_schema
            ensure_review_fraud_schema()
        except Exception:
            pass
        try:
            from app.utils.admin_rbac_migration import ensure_admin_rbac_schema, ensure_legacy_super_admins, migrate_legacy_staff_roles
            ensure_admin_rbac_schema()
            ensure_legacy_super_admins()
            migrate_legacy_staff_roles()
        except Exception:
            pass
    
    # Use threading mode for Python 3.12 compatibility (eventlet is not compatible)
    socketio.init_app(flask_app, cors_allowed_origins="*", async_mode='threading', logger=False, engineio_logger=False)
    
    # Initialize email service
    from app.services.email_service import init_mail
    init_mail(flask_app)
    
    # Initialize background scheduler (for auto-cleanup jobs)
    from app.scheduler import init_scheduler
    init_scheduler(flask_app)
    
    # Register blueprints
    from app.routes.home import home_bp
    from app.routes.auth import auth_bp
    from app.routes.doctors import doctors_bp
    from app.routes.patients import patients_bp
    from app.routes.admin import admin_bp
    from app.routes.appointments import appointments_bp
    from app.routes.blogs import blogs_bp
    from app.routes.qa import qa_bp
    from app.routes.diseases import diseases_bp
    from app.routes.video import video_bp
    from app.routes.prescriptions import prescriptions_bp
    from app.routes.payments import payments_bp
    from app.routes.reviews import reviews_bp
    
    flask_app.register_blueprint(home_bp)
    flask_app.register_blueprint(auth_bp, url_prefix='/auth')
    flask_app.register_blueprint(doctors_bp, url_prefix='/doctors')
    flask_app.register_blueprint(patients_bp, url_prefix='/patients')
    flask_app.register_blueprint(admin_bp, url_prefix='/admin')
    flask_app.register_blueprint(appointments_bp, url_prefix='/appointments')
    flask_app.register_blueprint(blogs_bp, url_prefix='/blogs')
    flask_app.register_blueprint(qa_bp, url_prefix='/qa')
    flask_app.register_blueprint(diseases_bp, url_prefix='/diseases')
    flask_app.register_blueprint(video_bp, url_prefix='/video')
    flask_app.register_blueprint(prescriptions_bp)
    flask_app.register_blueprint(payments_bp)
    flask_app.register_blueprint(reviews_bp)

    @flask_app.after_request
    def prevent_admin_page_cache(response):
        from flask import request
        if request.path.startswith('/admin'):
            response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
            response.headers['Pragma'] = 'no-cache'
            response.headers['Expires'] = '0'
        return response
    
    @flask_app.errorhandler(404)
    def not_found(e):
        from flask import render_template
        return render_template('errors/404.html'), 404
    
    # Import SocketIO events
    with flask_app.app_context():
        import app.services.socketio_events
    
    # Add template context processors
    from app.utils.auth import get_current_user
    
    @flask_app.context_processor
    def inject_user():
        """Make get_current_user available in all templates"""
        from flask import url_for
        from app.utils.timezone import get_pakistan_now, pkt_now_naive
        from app.utils.blog_covers import blog_static_image_path

        def static_asset(filename):
            version = flask_app.config.get('STATIC_ASSET_VERSION', '1')
            return url_for('static', filename=filename, v=version)
        
        def date_time_combine(d, t):
            """Combine date and time objects into datetime"""
            from datetime import datetime
            return datetime.combine(d, t)

        def admin_can(panel_key, action='view'):
            from app.utils.admin_permissions import admin_can as _admin_can
            user = get_current_user()
            return _admin_can(user, panel_key, action)

        def admin_is_super():
            from app.utils.admin_permissions import is_super_admin
            return is_super_admin(get_current_user())

        def admin_display_name():
            from app.utils.admin_permissions import get_staff_role_label, is_super_admin
            user = get_current_user()
            if not user:
                return ''
            if user.role == 'admin' and user.admin_profile and not is_super_admin(user):
                return get_staff_role_label(user.admin_profile)
            return user.name
            
        return dict(
            get_current_user=get_current_user,
            now_local=get_pakistan_now,
            now_pkt_naive=pkt_now_naive,
            date_time_combine=date_time_combine,
            timedelta=timedelta,
            blog_static_image_path=blog_static_image_path,
            static_asset=static_asset,
            admin_can=admin_can,
            admin_is_super=admin_is_super,
            admin_display_name=admin_display_name,
            geocode_api_url=lambda: url_for('home.geocode_lookup'),
            openfreemap_style_url=flask_app.config.get(
                'OPENFREEMAP_STYLE_URL',
                'https://tiles.openfreemap.org/styles/liberty',
            ),
            maps_geocoding_enabled=bool(flask_app.config.get('GEOAPIFY_API_KEY')),
        )
    
    # Add custom Jinja2 filters
    @flask_app.template_filter('appt_status_label')
    def appt_status_label_filter(appointment):
        from app.utils.appointment_status import appointment_status_label
        return appointment_status_label(appointment)

    @flask_app.template_filter('appt_status_badge')
    def appt_status_badge_filter(appointment):
        from app.utils.appointment_status import appointment_status_badge_class
        return appointment_status_badge_class(appointment)

    @flask_app.template_filter('format_phone')
    def format_phone_filter(phone):
        """Format phone number with +92 prefix and proper spacing
        
        Args:
            phone: Phone number string (e.g., '3001234567' or '+923001234567')
        
        Returns:
            Formatted phone number (e.g., '+92 300 1234567')
        """
        if not phone:
            return ''
        
        # Remove any existing spaces, dashes, or +92 prefix
        phone_clean = str(phone).replace(' ', '').replace('-', '').replace('+92', '')
        
        # If phone is already clean (10 digits), format it
        if phone_clean.isdigit() and len(phone_clean) == 10:
            # Format as: +92 XXX XXXXXXX (e.g., +92 300 1234567)
            return f'+92 {phone_clean[:3]} {phone_clean[3:]}'
        elif phone_clean.isdigit() and len(phone_clean) == 11 and phone_clean.startswith('0'):
            # Remove leading 0 and format (e.g., 03001234567 -> +92 300 1234567)
            phone_clean = phone_clean[1:]
            return f'+92 {phone_clean[:3]} {phone_clean[3:]}'
        else:
            # Return as is if format is unexpected
            return phone
    
    # Create upload directory
    upload_dir = os.path.join('app', 'static', 'uploads')
    if not os.path.exists(upload_dir):
        os.makedirs(upload_dir)
    
    return flask_app
