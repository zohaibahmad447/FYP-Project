from flask_wtf import FlaskForm
from flask_wtf.file import FileField, FileAllowed, FileRequired
from wtforms import StringField, PasswordField, SubmitField, BooleanField, TextAreaField, SelectField, IntegerField, FloatField, DateField, TimeField, RadioField
from wtforms.validators import DataRequired, Email, Length, EqualTo, ValidationError, Optional
from app.models import User, Doctor
from datetime import date
import re

def validate_password_strength(form, field):
    """Custom validator for password strength requirements"""
    password = field.data
    if not password:
        return
    
    errors = []
    
    # Minimum 8 characters
    if len(password) < 8:
        errors.append('Password must be at least 8 characters long.')
    
    # At least one lowercase letter
    if not re.search(r'[a-z]', password):
        errors.append('Password must contain at least one lowercase letter.')
    
    # At least one uppercase letter
    if not re.search(r'[A-Z]', password):
        errors.append('Password must contain at least one uppercase letter.')
    
    # At least one digit
    if not re.search(r'\d', password):
        errors.append('Password must contain at least one number.')
    
    # At least one special character
    if not re.search(r'[!@#$%^&*(),.?":{}|<>]', password):
        errors.append('Password must contain at least one special character (!@#$%^&*(),.?":{}|<>)')
    
    if errors:
        raise ValidationError(' '.join(errors))

class UnifiedRegistrationForm(FlaskForm):
    # Common fields for both roles
    name = StringField('Full Name', validators=[DataRequired(), Length(min=2, max=100)])
    email = StringField('Email', validators=[DataRequired(), Email()])
    phone = StringField('Phone Number', validators=[DataRequired(), Length(min=13, max=13)])  # +92 + 10 digits = 13 characters
    cnic = StringField('CNIC Number', validators=[DataRequired(), Length(min=13, max=13)], 
                      render_kw={"placeholder": "1234512345671"})
    password = PasswordField('Password', validators=[DataRequired(), Length(min=8), validate_password_strength],
                            render_kw={"placeholder": "Min 8 chars, 1 uppercase, 1 lowercase, 1 number, 1 special char"})
    password2 = PasswordField('Confirm Password', validators=[DataRequired(), EqualTo('password')])
    date_of_birth = StringField('Date of Birth', validators=[Optional()])
    gender = SelectField('Gender', choices=[('', 'Select Gender'), ('male', 'Male'), ('female', 'Female'), ('other', 'Other')])
    
    # Profile Picture (for both roles)
    profile_picture = FileField('Profile Picture', validators=[Optional(), FileAllowed(['jpg', 'jpeg', 'png'], 'Only image files (JPG, PNG) are allowed!')])
    
    # Role selection (no default option, will show as placeholder)
    role = SelectField('I want to register as:', 
                       choices=[('patient', 'Patient'), ('doctor', 'Doctor')],
                       validators=[DataRequired()],
                       render_kw={"class": "role-select", "data-placeholder": "Select your role"})
    
    # Patient specific fields
    blood_group = SelectField('Blood Group', validators=[Optional()],
                             choices=[('', 'Select Blood Group'), 
                                     ('A+', 'A+'), ('A-', 'A-'), 
                                     ('B+', 'B+'), ('B-', 'B-'),
                                     ('AB+', 'AB+'), ('AB-', 'AB-'),
                                     ('O+', 'O+'), ('O-', 'O-')])
    
    allergies = TextAreaField('Allergies (if any)', validators=[Optional()], 
                             render_kw={"placeholder": "List any allergies you have..."})
    
    medical_history = TextAreaField('Medical History', validators=[Optional()],
                                  render_kw={"placeholder": "Any previous medical conditions..."})
    
    emergency_contact = StringField('Emergency Contact Number', validators=[Optional(), Length(min=10, max=20)])
    
    emergency_relation = SelectField('Relation with Emergency Contact', validators=[Optional()],
                                    choices=[('', 'Select Relation'),
                                            ('father', 'Father'), ('mother', 'Mother'),
                                            ('spouse', 'Spouse'), ('brother', 'Brother'),
                                            ('sister', 'Sister'), ('son', 'Son'),
                                            ('daughter', 'Daughter'), ('friend', 'Friend'),
                                            ('other', 'Other')])
    
    # CNIC Document Upload Fields
    cnic_front = FileField('CNIC Front Image', validators=[Optional(), FileAllowed(['jpg', 'jpeg', 'png'], 'Only image files allowed!')])
    cnic_back = FileField('CNIC Back Image', validators=[Optional(), FileAllowed(['jpg', 'jpeg', 'png'], 'Only image files allowed!')])
    
    # Doctor specific fields
    # Specialization field - autocomplete text input (not dropdown)
    # NOTE: Only required for doctors, validated conditionally in validate_specialization method
    specialization = StringField('Medical Category', validators=[Optional(), Length(min=2, max=200)],
                                render_kw={"placeholder": "Type medical category (e.g., Cardiology, Dermatology)", 
                                          "autocomplete": "off",
                                          "list": "specialization-suggestions"})
    
    # Category field (hidden, will be set same as specialization in route)
    category = StringField('Medical Category', validators=[Optional()],
                          render_kw={"style": "display: none;"})
    
    # New field for degrees and qualifications
    qualifications = TextAreaField('Degrees & Qualifications', validators=[Optional()],
                                  render_kw={"placeholder": "List your degrees and qualifications (e.g., MBBS from ABC University, FCPS in Cardiology, etc.)", 
                                           "rows": 5})
    
    experience = FloatField('Years of Experience', validators=[Optional()])
    
    pmc_code = StringField('PMC Code', validators=[Optional(), Length(min=5, max=50)])
    
    education = TextAreaField('Educational Background', validators=[Optional()],
                             render_kw={"placeholder": "MBBS, MD, MS, etc..."})
    
    bio = TextAreaField('Professional Bio', validators=[Optional()],
                       render_kw={"placeholder": "Brief description of your practice..."})
    
    # Hospital affiliation removed - doctors will add hospitals when setting appointment slots
    
    city = StringField('City', validators=[Optional(), Length(min=2, max=100)],
                      render_kw={"placeholder": "Type city name (e.g., Karachi, Lahore, Islamabad)", 
                                "autocomplete": "off",
                                "list": "city-suggestions"})
    
    location = StringField('Hospital/Clinic Address', validators=[Optional(), Length(min=5, max=200)])
    
    # Dynamic Degree Upload Fields (will be handled via JavaScript)
    degree_files = FileField('Degree Documents', validators=[Optional()], 
                            render_kw={"multiple": True, "accept": ".jpg,.jpeg,.png,.pdf"})
    
    # Live Photo Field (hidden, will be populated by JavaScript)
    live_photo_data = StringField('Live Photo Data', validators=[Optional()], 
                                 render_kw={"style": "display: none;"})
    
    submit = SubmitField('Register')
    
    def validate_cnic(self, cnic):
        # Check if CNIC is exactly 13 digits
        if not cnic.data.isdigit():
            raise ValidationError('CNIC must contain only numbers.')
        
        if len(cnic.data) != 13:
            raise ValidationError('CNIC must be exactly 13 digits.')
        
        # Check if CNIC already exists (globally unique - cannot be used again)
        user = User.query.filter_by(cnic=cnic.data).first()
        if user:
            raise ValidationError('This CNIC is already registered. One CNIC can only be used once.')
    
    def validate_email(self, email):
        # Check if email already exists (globally unique - cannot be used again)
        user = User.query.filter_by(email=email.data).first()
        if user:
            raise ValidationError('This email is already registered. One email can only be used once.')
    
    def validate_specialization(self, specialization):
        """Validate specialization field - only required for doctors"""
        if self.role.data == 'doctor':
            if not specialization.data or not specialization.data.strip():
                raise ValidationError('Medical Category is required for doctors.')
    
    def validate_pmc_code(self, pmc_code):
        if self.role.data == 'doctor' and pmc_code.data:
            doctor = Doctor.query.filter_by(pmc_code=pmc_code.data).first()
            if doctor:
                raise ValidationError('PMC Code already registered. Please use a different PMC code.')
    
    def validate_date_of_birth(self, date_of_birth):
        if date_of_birth.data:
            try:
                # Parse the string date
                parsed_date = date.fromisoformat(date_of_birth.data)
                
                if parsed_date > date.today():
                    raise ValidationError('Date of birth cannot be in the future.')
                
                # Check if date is reasonable (not too old)
                min_date = date(1900, 1, 1)
                if parsed_date < min_date:
                    raise ValidationError('Please enter a valid date of birth.')
                    
            except ValueError:
                raise ValidationError('Please enter date in YYYY-MM-DD format.')

class LoginForm(FlaskForm):
    email = StringField('Email', validators=[DataRequired(), Email()])
    password = PasswordField('Password', validators=[DataRequired()])
    submit = SubmitField('Sign In')

class AppointmentBookingForm(FlaskForm):
    appointment_type = RadioField('Appointment Type', 
                                 choices=[('physical', 'Physical Appointment'), ('video', 'Video Consultation')],
                                 validators=[DataRequired()])
    appointment_date = DateField('Preferred Date', validators=[DataRequired()])
    appointment_time = SelectField('Preferred Time', validators=[DataRequired()])
    reason_for_visit = TextAreaField('Reason for Visit', 
                                    validators=[DataRequired(message='Please provide a reason for your visit'), Length(max=500)],
                                    render_kw={"placeholder": "e.g., Fever for 3 days, headache, chest pain, follow-up checkup, etc.", "rows": 4})
    submit = SubmitField('Book Appointment')

class QuestionForm(FlaskForm):
    title = StringField('Question Title', validators=[DataRequired(), Length(min=5, max=200)])
    content = TextAreaField('Question Details', validators=[DataRequired(), Length(min=10)])
    category = StringField('Medical Category', validators=[DataRequired(), Length(min=2, max=100)],
                          render_kw={"placeholder": "Type medical category (e.g., Cardiology, Dermatology)", 
                                    "autocomplete": "off",
                                    "list": "category-suggestions",
                                    "id": "category-input"})
    is_anonymous = BooleanField('Post anonymously')
    submit = SubmitField('Post Question')
    
    def __init__(self, *args, **kwargs):
        super(QuestionForm, self).__init__(*args, **kwargs)
        # Categories will be provided via JavaScript autocomplete from utils.categories

class AnswerForm(FlaskForm):
    content = TextAreaField('Your Answer', validators=[DataRequired(), Length(min=10)])
    submit = SubmitField('Post Answer')

class BlogForm(FlaskForm):
    title = StringField('Article Title', validators=[DataRequired(), Length(min=5, max=200)])
    category = StringField('Medical Category', validators=[DataRequired(), Length(min=2, max=100)],
                          render_kw={"placeholder": "Type medical category (e.g., Cardiology, General Health, Diet & Nutrition)", 
                                    "autocomplete": "off",
                                    "list": "category-suggestions"})
    featured_image = FileField('Featured Cover Photo', validators=[Optional(), FileAllowed(['jpg', 'jpeg', 'png', 'webp'], 'Images only!')])
    content = TextAreaField('Article Content', validators=[DataRequired(), Length(min=50)])
    excerpt = TextAreaField('Article Excerpt (Short Summary)', validators=[Optional()])
    references = TextAreaField('Medical References & Citations', validators=[Optional()])
    meta_title = StringField('SEO Title', validators=[Optional(), Length(max=250)])
    meta_description = TextAreaField('SEO Description', validators=[Optional(), Length(max=500)])
    tags = StringField('Tags (comma-separated)', validators=[Optional()])
    submit = SubmitField('Publish Article')

class DiseaseForm(FlaskForm):
    name = StringField('Disease Name', validators=[DataRequired(), Length(min=2, max=100)])
    category = SelectField('Category', validators=[DataRequired()],
                          choices=[('', 'Select Category'),
                                  ('infectious', 'Infectious Diseases'),
                                  ('chronic', 'Chronic Diseases'),
                                  ('genetic', 'Genetic Disorders'),
                                  ('mental', 'Mental Health'),
                                  ('cardiovascular', 'Cardiovascular'),
                                  ('respiratory', 'Respiratory'),
                                  ('digestive', 'Digestive System'),
                                  ('neurological', 'Neurological'),
                                  ('endocrine', 'Endocrine System'),
                                  ('other', 'Other')])
    description = TextAreaField('Description', validators=[DataRequired()])
    symptoms = TextAreaField('Symptoms', validators=[DataRequired()])
    causes = TextAreaField('Causes', validators=[Optional()])
    prevention = TextAreaField('Prevention', validators=[Optional()])
    treatment = TextAreaField('Treatment', validators=[Optional()])
    severity_level = SelectField('Severity Level', validators=[Optional()],
                                choices=[('', 'Select Severity'),
                                        ('mild', 'Mild'),
                                        ('moderate', 'Moderate'),
                                        ('severe', 'Severe')])
    age_group = SelectField('Age Group', validators=[Optional()],
                           choices=[('', 'Select Age Group'),
                                   ('children', 'Children'),
                                   ('adults', 'Adults'),
                                   ('elderly', 'Elderly'),
                                   ('all', 'All Ages')])
    gender_preference = SelectField('Gender Preference', validators=[Optional()],
                                   choices=[('', 'Select Gender'),
                                           ('male', 'Male'),
                                           ('female', 'Female'),
                                           ('both', 'Both')])
    submit = SubmitField('Add Disease Information')
