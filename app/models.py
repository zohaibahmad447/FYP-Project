from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash
from app.database import db
from sqlalchemy import UniqueConstraint

class User(db.Model):
    """Base user model"""
    __tablename__ = 'users'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    phone = db.Column(db.String(20), nullable=False)
    cnic = db.Column(db.String(13), unique=True, nullable=False)  # CNIC number (13 digits)
    password_hash = db.Column(db.String(128), nullable=False)
    role = db.Column(db.String(20), nullable=False)  # 'doctor', 'patient', 'admin'
    date_of_birth = db.Column(db.Date)
    gender = db.Column(db.String(10))
    address = db.Column(db.Text)
    profile_picture = db.Column(db.String(255))  # Profile picture file path
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    is_active = db.Column(db.Boolean, default=True)
    is_online = db.Column(db.Boolean, default=False)  # Tracks if user is currently logged in
    reset_token = db.Column(db.String(100), unique=True, nullable=True)
    reset_token_expiry = db.Column(db.DateTime, nullable=True)
    
    # Relationships
    doctor_profile = db.relationship('Doctor', backref='user', uselist=False, cascade='all, delete-orphan')
    patient_profile = db.relationship('Patient', backref='user', uselist=False, cascade='all, delete-orphan')
    admin_profile = db.relationship('Admin', backref='user', uselist=False, cascade='all, delete-orphan')
    
    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
    
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)
    
    def __repr__(self):
        return f'<User {self.email}>'

class Doctor(db.Model):
    """Doctor profile model"""
    __tablename__ = 'doctors'
    __table_args__ = (
        UniqueConstraint('user_id', name='unique_doctor_user_id'),  # Ensure one doctor profile per user
    )
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, unique=True)
    
    # Professional Information
    category = db.Column(db.String(100), nullable=False)  # Cardiology, Neurology, etc.
    specialization = db.Column(db.String(200), nullable=False)
    experience = db.Column(db.Float, nullable=False)  # years (allows decimal values)
    pmc_code = db.Column(db.String(50), unique=True, nullable=False)
    education = db.Column(db.Text, nullable=False)
    bio = db.Column(db.Text, nullable=False)
    # Hospital affiliation removed - doctors add hospitals per time slot
    
    # Location
    city = db.Column(db.String(100), nullable=False)
    location = db.Column(db.String(200), nullable=False)  # Hospital/Clinic address
    
    # Status
    is_approved = db.Column(db.Boolean, default=False)
    is_verified = db.Column(db.Boolean, default=False)
    profile_completed = db.Column(db.Boolean, default=False)
    
    # Appeal System
    appeal_status = db.Column(db.String(20), default='pending')  # pending, approved, rejected
    rejection_reason = db.Column(db.Text)  # Admin's reason for rejection
    rejection_date = db.Column(db.DateTime)  # When the rejection occurred
    appeal_count = db.Column(db.Integer, default=0)  # Number of appeals made
    
    # Time slots (JSON format: {"monday": ["09:00", "10:00"], ...})
    time_slots = db.Column(db.JSON, default={})
    
    # Earnings tracking
    balance = db.Column(db.Float, default=0.0)  # Current balance
    total_earned = db.Column(db.Float, default=0.0)  # Lifetime earnings
    total_withdrawn = db.Column(db.Float, default=0.0)  # Total withdrawn
    total_penalties = db.Column(db.Float, default=0.0)  # Lifetime penalties
    
    # Services/procedures offered (comma-separated, e.g. "Heart Failure Management, Angiography")
    services = db.Column(db.String(500), nullable=True)
    
    # Document uploads
    cnic_front_image = db.Column(db.String(255))  # CNIC front image path
    cnic_back_image = db.Column(db.String(255))   # CNIC back image path
    degree_documents = db.Column(db.JSON, default=[])  # List of degree document paths
    live_photo = db.Column(db.String(255))  # Live face detection photo path
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    appointments = db.relationship('Appointment', backref='doctor', lazy='dynamic')
    medical_histories = db.relationship('MedicalHistory', backref='doctor', lazy='dynamic')
    answers = db.relationship('Answer', backref='doctor', lazy='dynamic')
    blogs = db.relationship('Blog', backref='doctor', lazy='dynamic')
    reviews = db.relationship('Review', backref='doctor', lazy='dynamic')

    @property
    def average_rating(self):
        """Compute average star rating from public, cleared patient reviews."""
        visible = [
            r.rating for r in self.reviews
            if r.is_visible and (r.fraud_status or 'clear') == 'clear'
        ]
        return round(sum(visible) / len(visible), 1) if visible else None

    @property
    def review_count(self):
        """Total number of public, cleared patient reviews."""
        return sum(
            1 for r in self.reviews
            if r.is_visible and (r.fraud_status or 'clear') == 'clear'
        )

    def __repr__(self):
        return f'<Doctor {self.user.name}>'

class DoctorTransaction(db.Model):
    """Transaction history for doctor earnings, penalties, and withdrawals"""
    __tablename__ = 'doctor_transactions'
    
    id = db.Column(db.Integer, primary_key=True)
    doctor_id = db.Column(db.Integer, db.ForeignKey('doctors.id'), nullable=False)
    appointment_id = db.Column(db.Integer, db.ForeignKey('appointments.id'), nullable=True)
    
    # Transaction details
    transaction_type = db.Column(db.String(50), nullable=False)  # 'earning', 'penalty', 'withdrawal'
    amount = db.Column(db.Float, nullable=False)  # Positive for earnings, negative for penalties/withdrawals
    description = db.Column(db.Text, nullable=False)
    commission_deducted = db.Column(db.Float, nullable=True)  # Platform commission on this earning
    
    # Admin approval for withdrawals
    status = db.Column(db.String(20), default='completed')  # 'pending', 'completed', 'rejected' (for withdrawals)
    admin_notes = db.Column(db.Text, nullable=True)
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationships
    doctor = db.relationship('Doctor', backref='transactions')
    appointment = db.relationship('Appointment')
    
    def __repr__(self):
        return f'<DoctorTransaction {self.transaction_type} - PKR {self.amount}>'

class Patient(db.Model):
    """Patient profile model"""
    __tablename__ = 'patients'
    __table_args__ = (
        UniqueConstraint('user_id', name='unique_patient_user_id'),  # Ensure one patient profile per user
    )
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, unique=True)
    
    # Basic Information
    emergency_contact = db.Column(db.String(20))
    emergency_relation = db.Column(db.String(20))
    
    # Medical Information
    blood_group = db.Column(db.String(5))
    allergies = db.Column(db.Text)
    medical_history = db.Column(db.Text)
    
    # Document uploads
    cnic_front_image = db.Column(db.String(255))  # CNIC front image path
    cnic_back_image = db.Column(db.String(255))   # CNIC back image path
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    appointments = db.relationship('Appointment', backref='patient', lazy='dynamic')
    medical_histories = db.relationship('MedicalHistory', backref='patient', lazy='dynamic')
    questions = db.relationship('Question', backref='patient', lazy='dynamic')
    question_bookmarks = db.relationship('QuestionBookmark', backref='patient', lazy='dynamic', cascade='all, delete-orphan')
    answer_helpful_votes = db.relationship('AnswerHelpfulVote', backref='patient', lazy='dynamic', cascade='all, delete-orphan')
    
    def is_profile_complete(self):
        """Check if patient profile is complete with all required fields"""
        required_fields = [
            self.user.date_of_birth,
            self.user.gender,
            self.emergency_contact,
            self.blood_group
        ]
        # Profile is complete if all required fields are filled
        # Note: Address field removed - only city is needed
        return all(field for field in required_fields)
    
    def __repr__(self):
        return f'<Patient {self.user.name}>'

class Admin(db.Model):
    """Admin profile model"""
    __tablename__ = 'admins'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    
    # super = full access + staff management; staff = panel grants only
    admin_level = db.Column(db.String(20), default='super')
    staff_role = db.Column(db.String(50))  # e.g. accountant, doctors_accounts_manager
    permissions = db.Column(db.JSON, default={})  # legacy; use panel_grants
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    panel_grants = db.relationship(
        'AdminPanelGrant',
        backref='admin',
        cascade='all, delete-orphan',
        lazy='joined',
    )
    
    def __repr__(self):
        return f'<Admin {self.user.name}>'


class AdminPanelGrant(db.Model):
    """Per-panel permissions for a staff admin (many panels per user; many users per panel)."""
    __tablename__ = 'admin_panel_grants'
    __table_args__ = (
        UniqueConstraint('admin_id', 'panel_key', name='uq_admin_panel_grant'),
    )

    id = db.Column(db.Integer, primary_key=True)
    admin_id = db.Column(db.Integer, db.ForeignKey('admins.id', ondelete='CASCADE'), nullable=False)
    panel_key = db.Column(db.String(50), nullable=False)
    can_view = db.Column(db.Boolean, default=True)
    can_create = db.Column(db.Boolean, default=False)
    can_edit = db.Column(db.Boolean, default=False)
    can_delete = db.Column(db.Boolean, default=False)
    can_approve = db.Column(db.Boolean, default=False)

    def __repr__(self):
        return f'<AdminPanelGrant admin={self.admin_id} panel={self.panel_key}>'

class Appointment(db.Model):
    """Appointment model"""
    __tablename__ = 'appointments'
    
    id = db.Column(db.Integer, primary_key=True)
    patient_id = db.Column(db.Integer, db.ForeignKey('patients.id'), nullable=False)
    doctor_id = db.Column(db.Integer, db.ForeignKey('doctors.id'), nullable=False)
    
    # Appointment Details
    appointment_type = db.Column(db.String(20), nullable=False)  # 'physical' or 'video'
    appointment_date = db.Column(db.Date, nullable=False)
    appointment_time = db.Column(db.Time, nullable=False)
    duration = db.Column(db.Integer, default=30)  # minutes
    hospital = db.Column(db.String(200), nullable=True)  # Hospital/clinic for this appointment
    
    # Status and Charges
    status = db.Column(db.String(20), default='pending')  # pending, approved, rejected, completed, cancelled
    charges = db.Column(db.Float, nullable=False)
    
    # Medical Information
    disease_category = db.Column(db.String(100), nullable=False)
    symptoms = db.Column(db.Text)
    notes = db.Column(db.Text)
    
    # Cancellation
    cancellation_requested = db.Column(db.Boolean, default=False)
    cancellation_reason = db.Column(db.Text)
    cancellation_approved = db.Column(db.Boolean, default=False)
    
    # Payment Information
    payment_status = db.Column(db.String(20), default='pending')  # pending, submitted, approved, rejected, disputed
    payment_screenshot = db.Column(db.String(255), nullable=True)  # Payment screenshot file path
    payment_submitted_at = db.Column(db.DateTime, nullable=True)  # When patient submitted payment
    payment_rejection_reason = db.Column(db.Text, nullable=True)  # Admin's reason for rejection
    payment_approved_at = db.Column(db.DateTime, nullable=True)  # When admin approved payment
    payment_deadline = db.Column(db.DateTime, nullable=True)  # Deadline for payment (min of 15 mins or appointment start)
    
    # Completion tracking - Patient must mark complete first, then doctor
    patient_completed = db.Column(db.Boolean, default=False)  # Patient has marked as complete
    patient_completed_at = db.Column(db.DateTime, nullable=True)  # When patient marked complete
    doctor_completed = db.Column(db.Boolean, default=False)  # Doctor has marked as complete
    doctor_completed_at = db.Column(db.DateTime, nullable=True)  # When doctor marked complete
    
    # Video Call State Persistence (for late-joining patients)
    is_call_active = db.Column(db.Boolean, default=False)  # Whether video call is currently active
    call_started_at = db.Column(db.DateTime, nullable=True)  # When doctor started the call
    
    # Video Session Tracking (for no-show detection)
    patient_joined_video = db.Column(db.Boolean, default=False)  # Patient obtained video token
    doctor_joined_video = db.Column(db.Boolean, default=False)  # Doctor obtained video token
    patient_joined_at = db.Column(db.DateTime, nullable=True)  # When patient joined
    doctor_joined_at = db.Column(db.DateTime, nullable=True)  # When doctor joined
    
    # Consultation Gate Fields (Enforce interaction before prescription)
    mutual_call_start = db.Column(db.DateTime, nullable=True)   # When BOTH doctor + patient were in the call simultaneously
    doctor_sent_chat = db.Column(db.Boolean, default=False)     # Doctor has sent at least one chat (tracking only)
    prescription_unlocked = db.Column(db.Boolean, default=False)  # True after 3+ min mutual video (see video.check_unlock) or no-show path
    patient_review_skipped = db.Column(db.Boolean, default=False)  # Patient chose not to rate; unlocks dispute step during review window
    
    # Completion Review Fields (Hybrid Assurance Workflow)
    completion_review_deadline = db.Column(db.DateTime, nullable=True)  # 24 hours after doctor completion
    patient_disputed = db.Column(db.Boolean, default=False)  # True if patient raised dispute
    dispute_reason = db.Column(db.Text, nullable=True)  # Patient's dispute explanation
    
    # Accounts: commission and doctor earning
    platform_commission_percent = db.Column(db.Float, default=20.0)
    platform_commission_amount = db.Column(db.Float, nullable=True)
    doctor_earning_credited_at = db.Column(db.DateTime, nullable=True)
    # Refund policy applied when cancelled (full, partial, none)
    refund_policy_applied = db.Column(db.String(20), nullable=True)
    # Dropped call: duration in seconds (if < 180, treat as dropped)
    video_call_duration_seconds = db.Column(db.Integer, nullable=True)
    
    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    approved_at = db.Column(db.DateTime)
    completed_at = db.Column(db.DateTime)  # Final completion time (when both marked complete)
    
    # Relationships
    medical_history = db.relationship('MedicalHistory', backref='appointment', uselist=False)
    
    @property
    def can_review(self):
        """Check if the appointment is within its review window."""
        if self.status not in ('completed', 'completed_pending_review'):
            return False
        from datetime import datetime, timedelta
        from app.utils.timezone import pkt_now_naive
        if self.status == 'completed_pending_review':
            if not self.completion_review_deadline:
                return False
            return pkt_now_naive() < self.completion_review_deadline
        if not self.completed_at:
            return False
        return datetime.utcnow() < (self.completed_at + timedelta(days=7))

    def __repr__(self):
        return f'<Appointment {self.patient.user.name} - {self.doctor.user.name}>'

class MedicalHistory(db.Model):
    """Medical history model"""
    __tablename__ = 'medical_histories'
    
    id = db.Column(db.Integer, primary_key=True)
    patient_id = db.Column(db.Integer, db.ForeignKey('patients.id'), nullable=False)
    doctor_id = db.Column(db.Integer, db.ForeignKey('doctors.id'), nullable=False)
    appointment_id = db.Column(db.Integer, db.ForeignKey('appointments.id'), nullable=True)
    
    # Medical Information
    disease = db.Column(db.String(100), nullable=False)
    diagnosis = db.Column(db.Text)
    prescription = db.Column(db.Text)   # Serialized medicine list (human-readable summary)
    treatment_notes = db.Column(db.Text)  # Advice + vitals + recommended tests
    
    # Source tracking — how this entry was created
    # 'auto_prescription' = auto-created when appointment is completed
    # 'manual_upload'     = created by importing/uploading a document
    # 'chat_only'         = created by the chat system (legacy, no prescription yet)
    source = db.Column(db.String(30), default='chat_only')
    
    # Chat logs (JSON format) - IMPORTANT: using list callable prevents mutable default argument leakage!
    chat_logs = db.Column(db.JSON, default=list)
    
    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def __repr__(self):
        return f'<MedicalHistory {self.patient.user.name} - {self.disease}>'

class Question(db.Model):
    """Q&A Questions model"""
    __tablename__ = 'questions'
    
    id = db.Column(db.Integer, primary_key=True)
    patient_id = db.Column(db.Integer, db.ForeignKey('patients.id'), nullable=False)
    
    # Question Details
    title = db.Column(db.String(200), nullable=False)
    content = db.Column(db.Text, nullable=False)
    category = db.Column(db.String(100), nullable=False)
    
    # Status
    is_answered = db.Column(db.Boolean, default=False)
    is_anonymous = db.Column(db.Boolean, default=False)
    view_count = db.Column(db.Integer, default=0)
    last_activity_at = db.Column(db.DateTime)
    is_deleted = db.Column(db.Boolean, default=False)
    deletion_reason = db.Column(db.Text)
    
    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    answers = db.relationship('Answer', backref='question', lazy='dynamic', cascade='all, delete-orphan')
    bookmarks = db.relationship('QuestionBookmark', backref='question', lazy='dynamic', cascade='all, delete-orphan')

    @property
    def answer_count(self):
        return self.answers.filter_by(is_deleted=False).count()
    
    def __repr__(self):
        return f'<Question {self.title}>'


class QuestionView(db.Model):
    """Tracks unique question views per user."""
    __tablename__ = 'question_views'
    __table_args__ = (
        UniqueConstraint('question_id', 'user_id', name='unique_question_user_view'),
    )

    id = db.Column(db.Integer, primary_key=True)
    question_id = db.Column(db.Integer, db.ForeignKey('questions.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    viewed_at = db.Column(db.DateTime, default=datetime.utcnow)

    question = db.relationship('Question', backref='views')
    user = db.relationship('User')

class Answer(db.Model):
    """Q&A Answers model"""
    __tablename__ = 'answers'
    
    id = db.Column(db.Integer, primary_key=True)
    question_id = db.Column(db.Integer, db.ForeignKey('questions.id'), nullable=False)
    doctor_id = db.Column(db.Integer, db.ForeignKey('doctors.id'), nullable=False)
    
    # Answer Details
    content = db.Column(db.Text, nullable=False)
    
    # Status
    is_deleted = db.Column(db.Boolean, default=False)
    deletion_reason = db.Column(db.Text)
    
    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    helpful_votes = db.relationship('AnswerHelpfulVote', backref='answer', lazy='dynamic', cascade='all, delete-orphan')
    not_helpful_votes = db.relationship('AnswerNotHelpfulVote', backref='answer', lazy='dynamic', cascade='all, delete-orphan')
    replies = db.relationship('AnswerReply', backref='answer', lazy='dynamic', cascade='all, delete-orphan')

    @property
    def helpful_count(self):
        return self.helpful_votes.count()

    @property
    def not_helpful_count(self):
        return self.not_helpful_votes.count()
    
    def __repr__(self):
        return f'<Answer by {self.doctor.user.name}>'


class AnswerReply(db.Model):
    """Follow-up reply thread for an answer."""
    __tablename__ = 'answer_replies'

    id = db.Column(db.Integer, primary_key=True)
    answer_id = db.Column(db.Integer, db.ForeignKey('answers.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    content = db.Column(db.Text, nullable=False)
    photo_path = db.Column(db.String(255), nullable=True)
    is_deleted = db.Column(db.Boolean, default=False)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user = db.relationship('User', backref='answer_replies')

    def __repr__(self):
        return f'<AnswerReply a={self.answer_id} u={self.user_id}>'


class QuestionBookmark(db.Model):
    """Bookmark questions by patients"""
    __tablename__ = 'question_bookmarks'
    __table_args__ = (
        UniqueConstraint('question_id', 'patient_id', name='uq_question_bookmark_patient'),
    )

    id = db.Column(db.Integer, primary_key=True)
    question_id = db.Column(db.Integer, db.ForeignKey('questions.id'), nullable=False)
    patient_id = db.Column(db.Integer, db.ForeignKey('patients.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f'<QuestionBookmark q={self.question_id} p={self.patient_id}>'


class AnswerHelpfulVote(db.Model):
    """Helpful votes on answers by patients"""
    __tablename__ = 'answer_helpful_votes'
    __table_args__ = (
        UniqueConstraint('answer_id', 'patient_id', name='uq_answer_helpful_vote_patient'),
    )

    id = db.Column(db.Integer, primary_key=True)
    answer_id = db.Column(db.Integer, db.ForeignKey('answers.id'), nullable=False)
    patient_id = db.Column(db.Integer, db.ForeignKey('patients.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f'<AnswerHelpfulVote a={self.answer_id} p={self.patient_id}>'


class AnswerNotHelpfulVote(db.Model):
    """Not helpful votes on answers by patients"""
    __tablename__ = 'answer_not_helpful_votes'
    __table_args__ = (
        UniqueConstraint('answer_id', 'patient_id', name='uq_answer_not_helpful_vote_patient'),
    )

    id = db.Column(db.Integer, primary_key=True)
    answer_id = db.Column(db.Integer, db.ForeignKey('answers.id'), nullable=False)
    patient_id = db.Column(db.Integer, db.ForeignKey('patients.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f'<AnswerNotHelpfulVote a={self.answer_id} p={self.patient_id}>'

class Blog(db.Model):
    """Blog/Articles model"""
    __tablename__ = 'blogs'
    
    id = db.Column(db.Integer, primary_key=True)
    doctor_id = db.Column(db.Integer, db.ForeignKey('doctors.id'), nullable=False)
    
    # Blog Details
    title = db.Column(db.String(200), nullable=False)
    content = db.Column(db.Text, nullable=False)
    excerpt = db.Column(db.Text)
    tags = db.Column(db.String(200))  # legacy support
    category = db.Column(db.String(100), nullable=True)
    featured_image = db.Column(db.String(255), nullable=True)
    references = db.Column(db.Text, nullable=True)
    
    # Status
    status = db.Column(db.String(20), default='pending')  # pending, published, rejected, deleted
    admin_feedback = db.Column(db.Text, nullable=True)
    is_deleted = db.Column(db.Boolean, default=False)
    deletion_reason = db.Column(db.Text)
    
    # SEO
    slug = db.Column(db.String(250), unique=True)
    meta_title = db.Column(db.String(250), nullable=True)
    meta_description = db.Column(db.String(500), nullable=True)
    
    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    published_at = db.Column(db.DateTime)
    
    def __repr__(self):
        return f'<Blog {self.title}>'

class MedicalDocument(db.Model):
    """Medical documents model — manually uploaded by patients (lab reports, X-rays, etc.)"""
    __tablename__ = 'medical_documents'
    
    id = db.Column(db.Integer, primary_key=True)
    patient_id = db.Column(db.Integer, db.ForeignKey('patients.id'), nullable=False)
    appointment_id = db.Column(db.Integer, db.ForeignKey('appointments.id'), nullable=True)
    
    # File Information
    filename = db.Column(db.String(255), nullable=False)    # Original filename shown to user
    file_path = db.Column(db.String(500), nullable=False)   # Stored path on disk
    file_type = db.Column(db.String(50), nullable=False)    # 'image' or 'pdf'
    file_size = db.Column(db.Integer, nullable=False)       # bytes
    
    # Document Details
    document_type = db.Column(db.String(100))   # Legacy field kept for compatibility
    description = db.Column(db.Text)            # Patient's optional note
    
    # Rich category — for display and filtering
    # Values: 'lab_report' | 'xray' | 'ct_scan' | 'mri' | 'old_prescription' | 'other'
    document_category = db.Column(db.String(50), default='other')
    
    # Privacy control — patient can hide sensitive docs from doctor view
    is_visible_to_doctor = db.Column(db.Boolean, default=True)
    
    # Verification
    is_verified = db.Column(db.Boolean, default=False)
    verified_by = db.Column(db.Integer, db.ForeignKey('doctors.id'), nullable=True)
    verified_at = db.Column(db.DateTime)
    
    # Timestamps
    uploaded_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    patient = db.relationship('Patient', backref='medical_documents')
    appointment = db.relationship('Appointment', backref='medical_documents')
    verifier = db.relationship('Doctor', backref='verified_documents')
    
    @property
    def category_display(self):
        """Human-readable category label."""
        labels = {
            'lab_report': 'Lab Report',
            'xray': 'X-Ray',
            'ct_scan': 'CT Scan',
            'mri': 'MRI',
            'old_prescription': 'Old Prescription',
            'other': 'Other'
        }
        return labels.get(self.document_category, 'Other')
    
    def __repr__(self):
        return f'<MedicalDocument {self.filename}>'

class Disease(db.Model):
    """Diseases Information model"""
    __tablename__ = 'diseases'
    
    id = db.Column(db.Integer, primary_key=True)
    
    # Disease Information
    name = db.Column(db.String(100), nullable=False, unique=True)
    category = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text, nullable=False)
    symptoms = db.Column(db.Text, nullable=False)
    causes = db.Column(db.Text)
    prevention = db.Column(db.Text)
    treatment = db.Column(db.Text)
    
    # Additional Information
    severity_level = db.Column(db.String(20))  # mild, moderate, severe
    age_group = db.Column(db.String(50))  # children, adults, elderly, all
    gender_preference = db.Column(db.String(20))  # male, female, both
    
    # Admin Information
    uploaded_by = db.Column(db.String(100))  # admin name
    is_active = db.Column(db.Boolean, default=True)
    
    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def __repr__(self):
        return f'<Disease {self.name}>'

class Prescription(db.Model):
    """Prescription model for storing medical prescriptions"""
    __tablename__ = 'prescriptions'
    
    id = db.Column(db.Integer, primary_key=True)
    appointment_id = db.Column(db.Integer, db.ForeignKey('appointments.id'), nullable=False)
    
    # Vitals
    vitals_weight = db.Column(db.Float)  # in kg
    vitals_bp = db.Column(db.String(20))  # e.g., "120/80"
    vitals_temp = db.Column(db.Float)  # in Fahrenheit
    vitals_pulse = db.Column(db.Integer)  # beats per minute
    
    # Medical Information
    diagnosis = db.Column(db.Text, nullable=False)  # Primary diagnosis
    chief_complaints = db.Column(db.Text)  # Patient's main concerns
    advice = db.Column(db.Text)  # Lifestyle advice, instructions
    
    # Follow-up
    follow_up_date = db.Column(db.Date)
    follow_up_notes = db.Column(db.Text)
    
    # PDF Storage (optional - for caching generated PDF)
    pdf_path = db.Column(db.String(255))
    
    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    appointment = db.relationship('Appointment', backref=db.backref('prescription', uselist=False))
    medicines = db.relationship('PrescriptionMedicine', backref='prescription', lazy=True, cascade='all, delete-orphan')
    tests = db.relationship('PrescriptionTest', backref='prescription', lazy=True, cascade='all, delete-orphan')
    
    def __repr__(self):
        return f'<Prescription {self.id} for Appointment {self.appointment_id}>'

class PrescriptionMedicine(db.Model):
    """Medicine entries for prescriptions"""
    __tablename__ = 'prescription_medicines'
    
    id = db.Column(db.Integer, primary_key=True)
    prescription_id = db.Column(db.Integer, db.ForeignKey('prescriptions.id'), nullable=False)
    
    # Medicine Details
    medicine_name = db.Column(db.String(200), nullable=False)  # e.g., "Tab. Panadol"
    dosage = db.Column(db.String(100), nullable=False)  # e.g., "500mg"
    frequency = db.Column(db.String(100), nullable=False)  # e.g., "1-0-1" (Morning-Afternoon-Night)
    duration = db.Column(db.String(100), nullable=False)  # e.g., "5 Days"
    instructions = db.Column(db.Text)  # e.g., "After meal", "With warm water"
    
    # Display order
    order = db.Column(db.Integer, default=0)
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    def __repr__(self):
        return f'<Medicine {self.medicine_name} - {self.dosage}>'

class PrescriptionTest(db.Model):
    """Lab test recommendations for prescriptions"""
    __tablename__ = 'prescription_tests'
    
    id = db.Column(db.Integer, primary_key=True)
    prescription_id = db.Column(db.Integer, db.ForeignKey('prescriptions.id'), nullable=False)
    
    # Test Details
    test_name = db.Column(db.String(200), nullable=False)  # e.g., "CBC", "Lipid Profile"
    instructions = db.Column(db.Text)  # e.g., "Fasting required", "Morning sample"
    
    # Display order
    order = db.Column(db.Integer, default=0)
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    def __repr__(self):
        return f'<Test {self.test_name}>'


class Review(db.Model):
    """Patient review/rating left after a completed appointment."""
    __tablename__ = 'reviews'

    id             = db.Column(db.Integer, primary_key=True)
    appointment_id = db.Column(db.Integer, db.ForeignKey('appointments.id'), nullable=False, unique=True)
    patient_id     = db.Column(db.Integer, db.ForeignKey('patients.id'),     nullable=False)
    doctor_id      = db.Column(db.Integer, db.ForeignKey('doctors.id'),      nullable=False)

    rating         = db.Column(db.Integer, nullable=False)          # 1–5 stars
    tags           = db.Column(db.JSON,    default=list)            # quick-tap chip labels
    comment        = db.Column(db.Text,    nullable=True)           # optional free-text

    # Admin moderation: set to False to hide from public profile
    is_visible     = db.Column(db.Boolean, default=True)

    # Fraud / network signals (IP stored as hash only)
    submitter_ip_hash = db.Column(db.String(64), nullable=True, index=True)
    geo_city          = db.Column(db.String(100), nullable=True)
    geo_region        = db.Column(db.String(100), nullable=True)
    flag_reasons      = db.Column(db.JSON, default=list)
    fraud_status      = db.Column(db.String(20), default='clear')  # clear, flagged, blocked

    created_at     = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationships
    appointment    = db.relationship('Appointment', backref=db.backref('review', uselist=False))
    patient        = db.relationship('Patient',     backref=db.backref('reviews', lazy='dynamic'))

    def __repr__(self):
        return f'<Review apt={self.appointment_id} rating={self.rating}>'


class PlatformRevenue(db.Model):
    """Platform revenue (commission, etc.) for reporting."""
    __tablename__ = 'platform_revenues'
    id = db.Column(db.Integer, primary_key=True)
    appointment_id = db.Column(db.Integer, db.ForeignKey('appointments.id'), nullable=True)
    amount = db.Column(db.Float, nullable=False)
    source = db.Column(db.String(50), nullable=False)  # 'commission', 'cancellation_fee', etc.
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    appointment = db.relationship('Appointment', backref=db.backref('platform_revenue_entries', lazy='dynamic'))


class Refund(db.Model):
    """Refund record: admin processes refund (bank/card); no patient wallet."""
    __tablename__ = 'refunds'
    id = db.Column(db.Integer, primary_key=True)
    appointment_id = db.Column(db.Integer, db.ForeignKey('appointments.id'), nullable=False)
    patient_id = db.Column(db.Integer, db.ForeignKey('patients.id'), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    reason = db.Column(db.String(50), nullable=False)  # cancellation_patient, cancellation_doctor, rejection, doctor_no_show, mutual_no_show, dropped_call
    status = db.Column(db.String(20), default='pending')  # pending, processed
    processed_at = db.Column(db.DateTime, nullable=True)
    admin_notes = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    appointment = db.relationship('Appointment', backref=db.backref('refunds', lazy='dynamic'))
    patient = db.relationship('Patient', backref=db.backref('refunds', lazy='dynamic'))


class RefundPayoutDetail(db.Model):
    """Patient-provided payout details for processing a refund."""
    __tablename__ = 'refund_payout_details'

    id = db.Column(db.Integer, primary_key=True)
    refund_id = db.Column(db.Integer, db.ForeignKey('refunds.id'), nullable=False, unique=True)

    # Patient-provided payout destination
    payment_method = db.Column(db.String(30), nullable=False)  # bank_transfer, easypaisa, jazzcash, other
    account_title = db.Column(db.String(120), nullable=False)
    account_number = db.Column(db.String(64), nullable=True)
    iban = db.Column(db.String(64), nullable=True)
    bank_name = db.Column(db.String(120), nullable=True)
    wallet_provider = db.Column(db.String(40), nullable=True)
    wallet_number = db.Column(db.String(30), nullable=True)

    # Optional patient note
    patient_note = db.Column(db.Text, nullable=True)

    # Admin-side proof record after transfer
    admin_proof_path = db.Column(db.String(255), nullable=True)
    admin_proof_note = db.Column(db.Text, nullable=True)

    submitted_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    refund = db.relationship('Refund', backref=db.backref('payout_detail', uselist=False, cascade='all, delete-orphan'))


class DoctorPayoutRequest(db.Model):
    """Doctor withdrawal request; admin approves/rejects and marks paid."""
    __tablename__ = 'doctor_payout_requests'
    id = db.Column(db.Integer, primary_key=True)
    doctor_id = db.Column(db.Integer, db.ForeignKey('doctors.id'), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    # Destination snapshot captured at request time
    payout_method = db.Column(db.String(30), nullable=True)  # bank_transfer, mobile_wallet, visa_card
    account_title = db.Column(db.String(120), nullable=True)
    provider_name = db.Column(db.String(120), nullable=True)  # bank or wallet provider
    account_number = db.Column(db.String(64), nullable=True)  # bank account or wallet number
    iban = db.Column(db.String(64), nullable=True)  # Optional for bank transfers
    visa_card_holder_name = db.Column(db.String(120), nullable=True)
    visa_card_last4 = db.Column(db.String(4), nullable=True)
    visa_recipient_id = db.Column(db.String(120), nullable=True)  # token/id used by payout processor
    status = db.Column(db.String(20), default='pending')  # pending, approved, rejected, paid
    requested_at = db.Column(db.DateTime, default=datetime.utcnow)
    processed_at = db.Column(db.DateTime, nullable=True)
    admin_notes = db.Column(db.Text, nullable=True)
    doctor = db.relationship('Doctor', backref=db.backref('payout_requests', lazy='dynamic'))


class VideoCallRecording(db.Model):
    """Video call recording per mutual session (all linked to appointment)."""
    __tablename__ = 'video_call_recordings'

    id = db.Column(db.Integer, primary_key=True)
    appointment_id = db.Column(db.Integer, db.ForeignKey('appointments.id'), nullable=False)

    # Agora identifiers
    agora_resource_id = db.Column(db.String(64), nullable=True)  # from acquire
    agora_sid = db.Column(db.String(64), nullable=True)         # recording id from start

    # Recording metadata
    file_url = db.Column(db.String(512), nullable=True)         # playback URL when ready
    file_path = db.Column(db.String(512), nullable=True)        # storage path (S3 key, etc.)
    status = db.Column(db.String(20), default='recording')      # recording, stopping, ready, failed
    duration_seconds = db.Column(db.Integer, nullable=True)     # set when stopped
    error_message = db.Column(db.Text, nullable=True)           # if failed

    started_at = db.Column(db.DateTime, default=datetime.utcnow)
    ended_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    appointment = db.relationship('Appointment', backref=db.backref('video_recordings', lazy='dynamic'))
