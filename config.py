import os
from datetime import timedelta
from dotenv import load_dotenv

load_dotenv()

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'dev-secret-key-change-in-production'
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or 'sqlite:///quickcare.db'
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    
    # Session configuration - Persistent sessions (never auto-logout)
    SESSION_COOKIE_SECURE = False
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'
    SESSION_COOKIE_DOMAIN = None
    SESSION_COOKIE_NAME = 'quickcare_session_simple'
    SESSION_COOKIE_PATH = '/'
    # Set cookie to expire after 1 year (persists across browser restarts)
    SESSION_COOKIE_EXPIRES = timedelta(days=365)  # 1 year - persistent session
    # Session lifetime - Maximum (1 year) - users logout manually only
    # Users will remain logged in indefinitely until they explicitly logout
    PERMANENT_SESSION_LIFETIME = timedelta(days=365)  # 1 year - users logout manually only
    
    # CSRF Configuration
    WTF_CSRF_ENABLED = False  # Disable CSRF to avoid session conflicts
    
    # Upload configuration
    UPLOAD_FOLDER = 'app/static/uploads'
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16MB max file size
    
    # Static asset cache bust (bump when video-call.js or Agora SDK changes)
    STATIC_ASSET_VERSION = os.environ.get('STATIC_ASSET_VERSION', '20260614')
    DOCTORS_PER_PAGE = 12
    
    # Email configuration (optional — set ENABLE_EMAILS=true to send)
    MAIL_SERVER = os.environ.get('MAIL_SERVER', '')
    MAIL_PORT = int(os.environ.get('MAIL_PORT') or 587)
    MAIL_USE_TLS = os.environ.get('MAIL_USE_TLS', 'true').lower() in ['true', 'on', '1']
    MAIL_USE_SSL = os.environ.get('MAIL_USE_SSL', 'false').lower() in ['true', 'on', '1']
    MAIL_USERNAME = os.environ.get('MAIL_USERNAME', '')
    MAIL_PASSWORD = os.environ.get('MAIL_PASSWORD', '')
    MAIL_DEFAULT_SENDER_NAME = os.environ.get('MAIL_DEFAULT_SENDER_NAME', 'Quick Care Connect')
    MAIL_DEFAULT_SENDER_EMAIL = os.environ.get('MAIL_DEFAULT_SENDER_EMAIL', 'noreply@quickcareconnect.com')
    ENABLE_EMAILS = os.environ.get('ENABLE_EMAILS', 'false').lower() in ('true', '1', 'yes')

    # Safepay payment gateway (sandbox or production — set in .env)
    SAFEPAY_API_KEY = os.environ.get('SAFEPAY_API_KEY', '')
    SAFEPAY_SECRET_KEY = os.environ.get('SAFEPAY_SECRET_KEY', '')
    SAFEPAY_BASE_URL = os.environ.get('SAFEPAY_BASE_URL', 'https://sandbox.api.getsafepay.com')
    SAFEPAY_CHECKOUT_URL = os.environ.get('SAFEPAY_CHECKOUT_URL') or os.environ.get(
        'SAFEPAY_BASE_URL', 'https://sandbox.api.getsafepay.com'
    )
    SAFEPAY_ENVIRONMENT = os.environ.get('SAFEPAY_ENVIRONMENT', 'sandbox')
    
    # Agora Video Calling Configuration
    AGORA_APP_ID = os.environ.get('AGORA_APP_ID') or 'c9cda7c593234eea8414b65b1c8ba64c'
    AGORA_APP_CERTIFICATE = os.environ.get('AGORA_APP_CERTIFICATE') or '42abe44abd1e45a397dbe8de2c208bab'

    # Agora Cloud Recording: set AGORA_ENABLE_RECORDING=true plus CUSTOMER_ID/SECRET and S3 (or other vendor) keys.
    AGORA_ENABLE_RECORDING = os.environ.get('AGORA_ENABLE_RECORDING', 'false').lower() in ('true', '1', 'yes')
    AGORA_CUSTOMER_ID = os.environ.get('AGORA_CUSTOMER_ID', '')
    AGORA_CUSTOMER_SECRET = os.environ.get('AGORA_CUSTOMER_SECRET', '')
    # Storage for Agora Cloud Recording (see https://docs.agora.io/en/cloud-recording/reference/region-vendor )
    # vendor: 1=Amazon S3, 2=Alibaba, 3=Tencent, 5=Azure, 6=Google, 11=S3-compatible + extensionParams
    AGORA_RECORDING_STORAGE_VENDOR = int(os.environ.get('AGORA_RECORDING_STORAGE_VENDOR', 1))  # 1 = AWS S3
    AGORA_RECORDING_STORAGE_REGION = int(os.environ.get('AGORA_RECORDING_STORAGE_REGION', 0))
    AGORA_RECORDING_STORAGE_BUCKET = os.environ.get('AGORA_RECORDING_STORAGE_BUCKET', '')
    AGORA_RECORDING_STORAGE_ACCESS_KEY = os.environ.get('AGORA_RECORDING_STORAGE_ACCESS_KEY', '')
    AGORA_RECORDING_STORAGE_SECRET_KEY = os.environ.get('AGORA_RECORDING_STORAGE_SECRET_KEY', '')
    # S3-compatible endpoint (required for vendor 11 — DigitalOcean Spaces)
    AGORA_RECORDING_STORAGE_ENDPOINT = os.environ.get('AGORA_RECORDING_STORAGE_ENDPOINT') or os.environ.get(
        'DO_SPACES_ENDPOINT', ''
    )
    AGORA_RECORDING_FILE_PREFIX = os.environ.get('AGORA_RECORDING_FILE_PREFIX', 'recordings')
    # Cloud Recording REST API (use sd-rtn.com if api.agora.io is unreachable from your server)
    AGORA_API_BASE = os.environ.get('AGORA_API_BASE', 'https://api.sd-rtn.com/v1/apps')

    # DigitalOcean Spaces — private bucket playback via boto3 presigned URLs
    DO_SPACES_REGION = os.environ.get('DO_SPACES_REGION', '')
    DO_SPACES_BUCKET = os.environ.get('DO_SPACES_BUCKET', '')
    DO_SPACES_ENDPOINT = os.environ.get('DO_SPACES_ENDPOINT', '')
    DO_SPACES_ACCESS_KEY = os.environ.get('DO_SPACES_ACCESS_KEY', '')
    DO_SPACES_SECRET_KEY = os.environ.get('DO_SPACES_SECRET_KEY', '')
    DO_SPACES_PRESIGN_EXPIRES = int(os.environ.get('DO_SPACES_PRESIGN_EXPIRES', 3600))

    # AI chatbot (Q&A pages)
    GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY', '')
    OPENROUTER_API_KEY = os.environ.get('OPENROUTER_API_KEY', '')
    OPENROUTER_MODEL = os.environ.get('OPENROUTER_MODEL', 'openrouter/free')
    OPENROUTER_HTTP_REFERER = os.environ.get('OPENROUTER_HTTP_REFERER', 'http://127.0.0.1:5000')
    OPENROUTER_APP_TITLE = os.environ.get('OPENROUTER_APP_TITLE', 'Quick Care AI')

    # Maps — Geoapify geocoding (tiles use OpenFreeMap, no key required)
    GEOAPIFY_API_KEY = os.environ.get('GEOAPIFY_API_KEY', '')
    OPENFREEMAP_STYLE_URL = os.environ.get(
        'OPENFREEMAP_STYLE_URL',
        'https://tiles.openfreemap.org/styles/liberty',
    )

    # Admin bootstrap (scripts/reset_admin_login.py)
    ADMIN_EMAIL = os.environ.get('ADMIN_EMAIL', 'admin@quickcare.pk')
    ADMIN_PASSWORD = os.environ.get('ADMIN_PASSWORD', '')

    # Accounts: platform commission and refunds (no patient wallet)
    PLATFORM_COMMISSION_PERCENT = float(os.environ.get('PLATFORM_COMMISSION_PERCENT', 20))
    MIN_PAYOUT_PKR = float(os.environ.get('MIN_PAYOUT_PKR', 1000))
    CANCELLATION_FULL_REFUND_HOURS = int(os.environ.get('CANCELLATION_FULL_REFUND_HOURS', 24))
    CANCELLATION_PARTIAL_REFUND_HOURS = int(os.environ.get('CANCELLATION_PARTIAL_REFUND_HOURS', 2))
    PARTIAL_REFUND_PERCENT = int(os.environ.get('PARTIAL_REFUND_PERCENT', 50))
    DROPPED_CALL_MAX_SECONDS = int(os.environ.get('DROPPED_CALL_MAX_SECONDS', 180))

class DevelopmentConfig(Config):
    DEBUG = True
    SQLALCHEMY_DATABASE_URI = os.environ.get('DEV_DATABASE_URL') or 'sqlite:///quickcare_dev.db'
    TEMPLATES_AUTO_RELOAD = True  # Auto-reload templates in development
    SEND_FILE_MAX_AGE_DEFAULT = 0  # Disable static file caching in development
    # Session configuration for debug mode
    # Maximum session lifetime (1 year) - users logout manually only
    # Auto-logout is disabled - users logout manually only
    # Sessions persist across browser restarts
    PERMANENT_SESSION_LIFETIME = timedelta(days=365)  # 1 year - users logout manually only
    SESSION_COOKIE_EXPIRES = timedelta(days=365)  # 1 year - persistent session across browser restarts

class ProductionConfig(Config):
    DEBUG = False
    # False until HTTPS (Phase 4). Set SESSION_COOKIE_SECURE=true in .env after SSL.
    SESSION_COOKIE_SECURE = os.environ.get('SESSION_COOKIE_SECURE', 'false').lower() in ('true', '1', 'yes')

class TestingConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'
    WTF_CSRF_ENABLED = False

config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'testing': TestingConfig,
    'default': DevelopmentConfig
}
