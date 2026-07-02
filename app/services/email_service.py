from flask import current_app
from flask_mail import Mail, Message
import os
from threading import Thread
from datetime import datetime

# Initialize Flask-Mail
mail = Mail()

def init_mail(app):
    """Initialize Flask-Mail from app config / environment variables."""
    sender_name = app.config.get('MAIL_DEFAULT_SENDER_NAME', 'Quick Care Connect')
    sender_email = app.config.get('MAIL_DEFAULT_SENDER_EMAIL', 'noreply@quickcareconnect.com')
    app.config['MAIL_DEFAULT_SENDER'] = (sender_name, sender_email)

    enable = app.config.get('ENABLE_EMAILS', False)
    app.config['MAIL_SUPPRESS_SEND'] = not enable

    mail.init_app(app)

def send_async_email(app, msg):
    """Send email asynchronously"""
    with app.app_context():
        try:
            mail.send(msg)
        except Exception as e:
            print(f'Error sending email: {e}')

def send_email(to, subject, template, **kwargs):
    """Send email with template"""
    app = current_app._get_current_object()
    msg = Message(
        subject=subject,
        recipients=[to],
        html=template,
        sender=app.config['MAIL_DEFAULT_SENDER']
    )
    
    # Send asynchronously
    thr = Thread(target=send_async_email, args=[app, msg])
    thr.start()
    return thr

def send_welcome_patient_email(patient_email, patient_name):
    """Send a welcome email to a newly registered patient"""
    subject = "Welcome to Quick Care Connect! 🏥"
    template = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <title>Welcome to Quick Care Connect</title>
        <style>
            body {{ font-family: 'Segoe UI', Arial, sans-serif; line-height: 1.6; color: #333; background: #f0f4f8; margin: 0; padding: 0; }}
            .wrapper {{ padding: 40px 20px; }}
            .container {{ max-width: 600px; margin: 0 auto; background: white; border-radius: 16px; overflow: hidden; box-shadow: 0 4px 24px rgba(0,0,0,0.08); }}
            .header {{ background: linear-gradient(135deg, #10b981 0%, #059669 100%); color: white; padding: 40px 30px; text-align: center; }}
            .header h1 {{ margin: 0 0 8px; font-size: 28px; }}
            .header p {{ margin: 0; opacity: 0.9; font-size: 15px; }}
            .content {{ padding: 36px 32px; }}
            .feature-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 16px; margin: 24px 0; }}
            .feature-card {{ background: #f0fdf4; border-radius: 10px; padding: 16px; border-left: 4px solid #10b981; }}
            .feature-card h4 {{ margin: 0 0 6px; color: #065f46; font-size: 14px; }}
            .feature-card p {{ margin: 0; color: #555; font-size: 13px; }}
            .cta-btn {{ display: block; background: linear-gradient(135deg, #10b981, #059669); color: white; text-align: center; padding: 14px 24px; text-decoration: none; border-radius: 8px; font-weight: 600; font-size: 16px; margin: 28px 0; }}
            .footer {{ background: #f8f9fa; padding: 20px 32px; text-align: center; color: #888; font-size: 13px; border-top: 1px solid #eee; }}
            .logo {{ font-size: 22px; font-weight: 700; color: white; }}
            .logo span {{ opacity: 0.8; font-weight: 400; }}
        </style>
    </head>
    <body>
        <div class="wrapper">
            <div class="container">
                <div class="header">
                    <div class="logo">Quick Care <span>Connect</span></div>
                    <h1>Welcome, {patient_name}! 👋</h1>
                    <p>Your healthcare journey starts here</p>
                </div>
                <div class="content">
                    <p>Dear {patient_name},</p>
                    <p>We're thrilled to have you on board! Quick Care Connect makes it easy for you to access quality healthcare anytime, anywhere.</p>

                    <div class="feature-grid">
                        <div class="feature-card">
                            <h4>🩺 Browse Doctors</h4>
                            <p>Find specialists near you filtered by specialty, area, and fees.</p>
                        </div>
                        <div class="feature-card">
                            <h4>📅 Book Appointments</h4>
                            <p>Schedule in-person or video consultations in minutes.</p>
                        </div>
                        <div class="feature-card">
                            <h4>💬 Chat Consultations</h4>
                            <p>Message your doctor directly through our secure chat system.</p>
                        </div>
                        <div class="feature-card">
                            <h4>📋 Digital Prescriptions</h4>
                            <p>Get and store your prescriptions online forever.</p>
                        </div>
                    </div>

                    <a href="https://quickcareconnect.com" class="cta-btn">Start Exploring Doctors →</a>

                    <p>If you have any questions or need help, our support team is always happy to assist.</p>
                    <p>Stay healthy! 💚</p>
                    <p><strong>The Quick Care Connect Team</strong></p>
                </div>
                <div class="footer">
                    <p>Quick Care Connect &amp; AI Healthcare Assistance</p>
                    <p>This is an automated message. Please do not reply to this email.</p>
                </div>
            </div>
        </div>
    </body>
    </html>
    """
    send_email(patient_email, subject, template)

def send_welcome_doctor_email(doctor_email, doctor_name):
    """Send a registration receipt email to a newly registered doctor (pending approval)"""
    subject = "Doctor Registration Received — Quick Care Connect"
    template = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <title>Registration Received</title>
        <style>
            body {{ font-family: 'Segoe UI', Arial, sans-serif; line-height: 1.6; color: #333; background: #f0f4f8; margin: 0; padding: 0; }}
            .wrapper {{ padding: 40px 20px; }}
            .container {{ max-width: 600px; margin: 0 auto; background: white; border-radius: 16px; overflow: hidden; box-shadow: 0 4px 24px rgba(0,0,0,0.08); }}
            .header {{ background: linear-gradient(135deg, #3b82f6 0%, #1d4ed8 100%); color: white; padding: 40px 30px; text-align: center; }}
            .header h1 {{ margin: 0 0 8px; font-size: 26px; }}
            .header p {{ margin: 0; opacity: 0.9; font-size: 15px; }}
            .content {{ padding: 36px 32px; }}
            .status-box {{ background: #eff6ff; border: 1px solid #bfdbfe; border-radius: 10px; padding: 20px; margin: 24px 0; text-align: center; }}
            .status-box h3 {{ margin: 0 0 8px; color: #1d4ed8; }}
            .status-box p {{ margin: 0; color: #555; font-size: 14px; }}
            .steps {{ margin: 24px 0; }}
            .step {{ display: flex; align-items: flex-start; gap: 12px; margin-bottom: 14px; }}
            .step-num {{ background: #3b82f6; color: white; border-radius: 50%; width: 26px; height: 26px; display: flex; align-items: center; justify-content: center; font-size: 13px; font-weight: 700; flex-shrink: 0; margin-top: 2px; }}
            .footer {{ background: #f8f9fa; padding: 20px 32px; text-align: center; color: #888; font-size: 13px; border-top: 1px solid #eee; }}
            .logo {{ font-size: 22px; font-weight: 700; color: white; }}
            .logo span {{ opacity: 0.8; font-weight: 400; }}
        </style>
    </head>
    <body>
        <div class="wrapper">
            <div class="container">
                <div class="header">
                    <div class="logo">Quick Care <span>Connect</span></div>
                    <h1>Registration Received, Dr. {doctor_name}!</h1>
                    <p>Your application is under review</p>
                </div>
                <div class="content">
                    <p>Dear Dr. {doctor_name},</p>
                    <p>Thank you for registering as a healthcare provider on Quick Care Connect. We have received your application and our admin team is currently reviewing your credentials.</p>

                    <div class="status-box">
                        <h3>⏳ Pending Admin Approval</h3>
                        <p>Your application is in the review queue. This process typically takes <strong>1–2 business days</strong>.</p>
                    </div>

                    <div class="steps">
                        <p><strong>What happens next:</strong></p>
                        <div class="step">
                            <div class="step-num">1</div>
                            <div>Our admin team reviews your PMC code, degree documents, and CNIC.</div>
                        </div>
                        <div class="step">
                            <div class="step-num">2</div>
                            <div>You receive an approval confirmation email once verified.</div>
                        </div>
                        <div class="step">
                            <div class="step-num">3</div>
                            <div>You can then log in, set up your schedule, and start receiving appointments.</div>
                        </div>
                    </div>

                    <p>If you have any questions about the approval process, please contact our support team.</p>
                    <p>We look forward to welcoming you to the Quick Care Connect professional community!</p>
                    <p><strong>The Quick Care Connect Team</strong></p>
                </div>
                <div class="footer">
                    <p>Quick Care Connect &amp; AI Healthcare Assistance</p>
                    <p>This is an automated message. Please do not reply to this email.</p>
                </div>
            </div>
        </div>
    </body>
    </html>
    """
    send_email(doctor_email, subject, template)

def send_appointment_request_email(doctor_email, doctor_name, patient_name, appointment_date, appointment_time, appointment_type, disease_category, symptoms=None):
    """Send appointment request notification email to doctor"""
    subject = f"New Appointment Request from {patient_name} - Quick Care Connect"
    
    # Format time explicitly for readability
    if isinstance(appointment_time, str):
        time_str = appointment_time
    else:
        time_str = appointment_time.strftime('%I:%M %p')
        
    date_str = appointment_date if isinstance(appointment_date, str) else appointment_date.strftime('%A, %b %d, %Y')
    
    type_badge = "📹 Video Consultation" if appointment_type == 'video' else "🏥 In-Person Visit"
    symptoms_text = f"<p><strong>Reported Symptoms:</strong> {symptoms}</p>" if symptoms and symptoms.strip() else ""

    try:
        from flask import url_for
        review_link = url_for('doctors.dashboard', _external=True)
    except Exception:
        review_link = "http://localhost:5000/doctors/dashboard"

    template = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <style>
            body {{ font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; line-height: 1.6; color: #334155; margin: 0; padding: 0; background-color: #f8fafc; }}
            .container {{ max-width: 600px; margin: 0 auto; background-color: #ffffff; border-radius: 8px; overflow: hidden; box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1); margin-top: 20px; margin-bottom: 20px; border: 1px solid #e2e8f0; }}
            .header {{ background-color: #10b981; color: #ffffff; padding: 24px; text-align: center; }}
            .header h2 {{ margin: 0; font-size: 24px; font-weight: 600; letter-spacing: -0.025em; }}
            .content {{ padding: 32px; }}
            .content h3 {{ color: #0f172a; font-size: 20px; font-weight: 600; margin-top: 0; }}
            .details-card {{ background-color: #f1f5f9; border-radius: 8px; padding: 20px; margin: 24px 0; border: 1px solid #e2e8f0; }}
            .details-card h4 {{ margin-top: 0; margin-bottom: 16px; color: #334155; font-size: 16px; border-bottom: 1px solid #cbd5e1; padding-bottom: 8px; }}
            .detail-row {{ margin-bottom: 12px; display: flex; }}
            .detail-label {{ font-weight: 600; width: 140px; color: #475569; }}
            .detail-value {{ color: #1e293b; font-weight: 500; }}
            .badge {{ display: inline-block; padding: 4px 12px; border-radius: 9999px; font-size: 14px; font-weight: 500; background-color: #dbeafe; color: #1e40af; border: 1px solid #bfdbfe; }}
            .btn-primary {{ display: inline-block; padding: 12px 24px; background-color: #10b981; color: #ffffff !important; text-decoration: none; border-radius: 6px; font-weight: 500; text-align: center; width: auto; margin-top: 16px; }}
            .footer {{ background-color: #f8fafc; padding: 16px; text-align: center; font-size: 14px; color: #94a3b8; border-top: 1px solid #e2e8f0; }}
            .footer p {{ margin: 4px 0; }}
        </style>
    </head>
    <body>
        <div style="padding: 20px;">
            <div class="container">
                <div class="header">
                    <h2>New Appointment Request</h2>
                </div>
                <div class="content">
                    <h3>Dear {doctor_name},</h3>
                    <p>You have received a new appointment request from <strong>{patient_name}</strong>. Please review the details below and take action from your dashboard.</p>

                    <div class="details-card">
                        <h4>📅 Appointment Details</h4>
                        
                        <div class="detail-row">
                            <div class="detail-label">Type:</div>
                            <div class="detail-value"><span class="badge">{type_badge}</span></div>
                        </div>
                        
                        <div class="detail-row">
                            <div class="detail-label">Date:</div>
                            <div class="detail-value">{date_str}</div>
                        </div>
                        
                        <div class="detail-row">
                            <div class="detail-label">Time:</div>
                            <div class="detail-value">{time_str}</div>
                        </div>
                        
                        <div class="detail-row">
                            <div class="detail-label">Reason:</div>
                            <div class="detail-value">{disease_category}</div>
                        </div>
                        
                        {symptoms_text}
                    </div>

                    <p style="text-align: center;">
                        <a href="{review_link}" class="btn-primary">Review Appointment Overview</a>
                    </p>
                </div>
                <div class="footer">
                    <p>Quick Care Connect &copy; {datetime.now().year}</p>
                    <p>This is an automated notification. Please do not reply.</p>
                </div>
            </div>
        </div>
    </body>
    </html>
    """
    send_email(doctor_email, subject, template)

def send_appointment_confirmation_email(patient_email, patient_name, doctor_name, appointment_date, appointment_time, appointment_type):
    """Send appointment confirmation email to patient"""
    subject = f"Appointment Confirmed with Dr. {doctor_name}"
    
    template = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <title>Appointment Confirmation</title>
        <style>
            body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
            .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
            .header {{ background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 30px; text-align: center; border-radius: 10px 10px 0 0; }}
            .content {{ background: #f8f9fa; padding: 30px; border-radius: 0 0 10px 10px; }}
            .appointment-details {{ background: white; padding: 20px; border-radius: 8px; margin: 20px 0; border-left: 4px solid #28a745; }}
            .detail-row {{ display: flex; justify-content: space-between; margin: 10px 0; padding: 8px 0; border-bottom: 1px solid #eee; }}
            .detail-label {{ font-weight: bold; color: #666; }}
            .detail-value {{ color: #333; }}
            .footer {{ text-align: center; margin-top: 30px; color: #666; font-size: 14px; }}
            .btn {{ display: inline-block; background: #10b981; color: white; padding: 12px 24px; text-decoration: none; border-radius: 5px; margin: 10px 0; }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>Appointment Confirmed!</h1>
                <p>Your appointment has been successfully scheduled</p>
            </div>
            <div class="content">
                <p>Dear {patient_name},</p>
                <p>We're pleased to confirm your appointment with Dr. {doctor_name}.</p>
                
                <div class="appointment-details">
                    <h3>Appointment Details</h3>
                    <div class="detail-row">
                        <span class="detail-label">Doctor:</span>
                        <span class="detail-value">Dr. {doctor_name}</span>
                    </div>
                    <div class="detail-row">
                        <span class="detail-label">Date:</span>
                        <span class="detail-value">{appointment_date}</span>
                    </div>
                    <div class="detail-row">
                        <span class="detail-label">Time:</span>
                        <span class="detail-value">{appointment_time}</span>
                    </div>
                    <div class="detail-row">
                        <span class="detail-label">Type:</span>
                        <span class="detail-value">{appointment_type.title()}</span>
                    </div>
                </div>
                
                <p><strong>Important Reminders:</strong></p>
                <ul>
                    <li>Please arrive 15 minutes before your scheduled time</li>
                    <li>Bring a valid ID and insurance information</li>
                    <li>For video consultations, ensure you have a stable internet connection</li>
                    <li>If you need to reschedule, please contact us at least 24 hours in advance</li>
                </ul>
                
                <p>If you have any questions or need to make changes to your appointment, please contact us immediately.</p>
                
                <p>Thank you for choosing Quick Care Connect for your healthcare needs!</p>
                
                <div class="footer">
                    <p>Quick Care Connect & AI Healthcare Assistance</p>
                    <p>This is an automated message. Please do not reply to this email.</p>
                </div>
            </div>
        </div>
    </body>
    </html>
    """
    
    send_email(patient_email, subject, template)

def send_appointment_approval_email(patient_email, patient_name, doctor_name, appointment_date, appointment_time):
    """Send appointment approval email to patient"""
    subject = f"Appointment Approved - Dr. {doctor_name}"
    
    template = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <title>Appointment Approved</title>
        <style>
            body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
            .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
            .header {{ background: linear-gradient(135deg, #28a745 0%, #20c997 100%); color: white; padding: 30px; text-align: center; border-radius: 10px 10px 0 0; }}
            .content {{ background: #f8f9fa; padding: 30px; border-radius: 0 0 10px 10px; }}
            .appointment-details {{ background: white; padding: 20px; border-radius: 8px; margin: 20px 0; border-left: 4px solid #28a745; }}
            .detail-row {{ display: flex; justify-content: space-between; margin: 10px 0; padding: 8px 0; border-bottom: 1px solid #eee; }}
            .detail-label {{ font-weight: bold; color: #666; }}
            .detail-value {{ color: #333; }}
            .footer {{ text-align: center; margin-top: 30px; color: #666; font-size: 14px; }}
            .btn {{ display: inline-block; background: #28a745; color: white; padding: 12px 24px; text-decoration: none; border-radius: 5px; margin: 10px 0; }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>Appointment Approved!</h1>
                <p>Your appointment request has been approved by the doctor</p>
            </div>
            <div class="content">
                <p>Dear {patient_name},</p>
                <p>Great news! Dr. {doctor_name} has approved your appointment request.</p>
                
                <div class="appointment-details">
                    <h3>Approved Appointment Details</h3>
                    <div class="detail-row">
                        <span class="detail-label">Doctor:</span>
                        <span class="detail-value">Dr. {doctor_name}</span>
                    </div>
                    <div class="detail-row">
                        <span class="detail-label">Date:</span>
                        <span class="detail-value">{appointment_date}</span>
                    </div>
                    <div class="detail-row">
                        <span class="detail-label">Time:</span>
                        <span class="detail-value">{appointment_time}</span>
                    </div>
                </div>
                
                <p><strong>What's Next?</strong></p>
                <ul>
                    <li>Your appointment is now confirmed</li>
                    <li>You can start chatting with the doctor once the appointment time arrives</li>
                    <li>Make sure to prepare any questions or concerns you'd like to discuss</li>
                    <li>Keep your appointment details handy for easy reference</li>
                </ul>
                
                <p>We look forward to providing you with excellent healthcare service!</p>
                
                <div class="footer">
                    <p>Quick Care Connect & AI Healthcare Assistance</p>
                    <p>This is an automated message. Please do not reply to this email.</p>
                </div>
            </div>
        </div>
    </body>
    </html>
    """
    
    send_email(patient_email, subject, template)

def send_appointment_rejection_email(patient_email, patient_name, doctor_name, reason=""):
    """Send appointment rejection email to patient"""
    subject = f"Appointment Update - Dr. {doctor_name}"
    
    template = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <title>Appointment Update</title>
        <style>
            body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
            .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
            .header {{ background: linear-gradient(135deg, #dc3545 0%, #fd7e14 100%); color: white; padding: 30px; text-align: center; border-radius: 10px 10px 0 0; }}
            .content {{ background: #f8f9fa; padding: 30px; border-radius: 0 0 10px 10px; }}
            .message-box {{ background: white; padding: 20px; border-radius: 8px; margin: 20px 0; border-left: 4px solid #dc3545; }}
            .footer {{ text-align: center; margin-top: 30px; color: #666; font-size: 14px; }}
            .btn {{ display: inline-block; background: #10b981; color: white; padding: 12px 24px; text-decoration: none; border-radius: 5px; margin: 10px 0; }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>Appointment Update</h1>
                <p>Your appointment request has been updated</p>
            </div>
            <div class="content">
                <p>Dear {patient_name},</p>
                <p>We regret to inform you that your appointment request with Dr. {doctor_name} could not be approved at this time.</p>
                
                <div class="message-box">
                    <h3>Reason for Rejection</h3>
                    <p>{reason if reason else "The doctor is not available for the requested time slot. Please try booking a different time."}</p>
                </div>
                
                <p><strong>What You Can Do:</strong></p>
                <ul>
                    <li>Try booking with a different doctor in the same specialty</li>
                    <li>Select a different time slot with the same doctor</li>
                    <li>Contact our support team for assistance</li>
                    <li>Browse other available doctors in your area</li>
                </ul>
                
                <p>We apologize for any inconvenience and encourage you to try booking again with alternative options.</p>
                
                <div class="footer">
                    <p>Quick Care Connect & AI Healthcare Assistance</p>
                    <p>This is an automated message. Please do not reply to this email.</p>
                </div>
            </div>
        </div>
    </body>
    </html>
    """
    
    send_email(patient_email, subject, template)

def send_doctor_approval_email(doctor_email, doctor_name):
    """Send doctor approval email"""
    subject = "Doctor Registration Approved - Quick Care Connect"
    
    template = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <title>Registration Approved</title>
        <style>
            body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
            .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
            .header {{ background: linear-gradient(135deg, #28a745 0%, #20c997 100%); color: white; padding: 30px; text-align: center; border-radius: 10px 10px 0 0; }}
            .content {{ background: #f8f9fa; padding: 30px; border-radius: 0 0 10px 10px; }}
            .welcome-box {{ background: white; padding: 20px; border-radius: 8px; margin: 20px 0; border-left: 4px solid #28a745; }}
            .footer {{ text-align: center; margin-top: 30px; color: #666; font-size: 14px; }}
            .btn {{ display: inline-block; background: #28a745; color: white; padding: 12px 24px; text-decoration: none; border-radius: 5px; margin: 10px 0; }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>Welcome to Quick Care Connect!</h1>
                <p>Your doctor registration has been approved</p>
            </div>
            <div class="content">
                <p>Dear Dr. {doctor_name},</p>
                <p>Congratulations! Your registration as a healthcare provider on Quick Care Connect has been approved.</p>
                
                <div class="welcome-box">
                    <h3>What's Next?</h3>
                    <ul>
                        <li>Complete your profile setup</li>
                        <li>Set your availability and consultation fees</li>
                        <li>Start receiving appointment requests from patients</li>
                        <li>Access your doctor dashboard for managing appointments</li>
                    </ul>
                </div>
                
                <p><strong>Getting Started:</strong></p>
                <ol>
                    <li>Log in to your account</li>
                    <li>Complete your professional profile</li>
                    <li>Set your consultation hours and fees</li>
                    <li>Start accepting patient appointments</li>
                </ol>
                
                <p>We're excited to have you as part of our healthcare community!</p>
                
                <div class="footer">
                    <p>Quick Care Connect & AI Healthcare Assistance</p>
                    <p>This is an automated message. Please do not reply to this email.</p>
                </div>
            </div>
        </div>
    </body>
    </html>
    """
    
    send_email(doctor_email, subject, template)

def send_password_reset_email(user_email, user_name, reset_token):
    """Send password reset email"""
    subject = "Password Reset - Quick Care Connect"
    
    from flask import url_for
    try:
        reset_link = url_for('auth.reset_password', token=reset_token, _external=True)
    except Exception:
        reset_link = f"http://localhost:5000/auth/reset-password/{reset_token}"
    
    template = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <title>Password Reset</title>
        <style>
            body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
            .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
            .header {{ background: linear-gradient(135deg, #10b981 0%, #059669 100%); color: white; padding: 30px; text-align: center; border-radius: 10px 10px 0 0; }}
            .content {{ background: #f8f9fa; padding: 30px; border-radius: 0 0 10px 10px; }}
            .reset-box {{ background: white; padding: 20px; border-radius: 8px; margin: 20px 0; border-left: 4px solid #10b981; text-align: center; }}
            .footer {{ text-align: center; margin-top: 30px; color: #666; font-size: 14px; }}
            .btn {{ display: inline-block; background: #10b981; color: white; padding: 12px 24px; text-decoration: none; border-radius: 5px; margin: 10px 0; }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>Password Reset Request</h1>
                <p>Reset your Quick Care Connect password</p>
            </div>
            <div class="content">
                <p>Dear {user_name},</p>
                <p>We received a request to reset your password for your Quick Care Connect account.</p>
                
                <div class="reset-box">
                    <h3>Reset Your Password</h3>
                    <p>Click the button below to reset your password. This link will expire in 1 hour.</p>
                    <a href="{reset_link}" class="btn">Reset Password</a>
                </div>
                
                <p><strong>Security Note:</strong></p>
                <ul>
                    <li>This link will expire in 1 hour for security reasons</li>
                    <li>If you didn't request this reset, please ignore this email</li>
                    <li>Your password will remain unchanged until you create a new one</li>
                </ul>
                
                <p>If you have any questions or need assistance, please contact our support team.</p>
                
                <div class="footer">
                    <p>Quick Care Connect & AI Healthcare Assistance</p>
                    <p>This is an automated message. Please do not reply to this email.</p>
                </div>
            </div>
        </div>
    </body>
    </html>
    """
    
    send_email(user_email, subject, template)

def send_manual_payment_admin_notification(patient_name, doctor_name, appointment_date, charges, payment_method="Manual Payment"):
    """Send an email to the admin notifying them that a manual payment proof has been uploaded"""
    subject = f"Manual Payment Uploaded - Please Verify"
    
    date_str = appointment_date if isinstance(appointment_date, str) else appointment_date.strftime('%B %d, %Y')
    
    template = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <style>
            body {{ font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; line-height: 1.6; color: #334155; margin: 0; padding: 0; background-color: #f8fafc; }}
            .container {{ max-width: 600px; margin: 0 auto; background-color: #ffffff; border-radius: 8px; overflow: hidden; box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1); margin-top: 20px; margin-bottom: 20px; border: 1px solid #e2e8f0; }}
            .header {{ background-color: #10b981; color: #ffffff; padding: 24px; text-align: center; }}
            .header h2 {{ margin: 0; font-size: 24px; font-weight: 600; letter-spacing: -0.025em; }}
            .content {{ padding: 32px; }}
            .content h3 {{ color: #0f172a; font-size: 20px; font-weight: 600; margin-top: 0; }}
            .details-card {{ background-color: #f0fdf4; border-radius: 8px; padding: 20px; margin: 24px 0; border: 1px solid rgba(16, 185, 129, 0.3); }}
            .detail-row {{ margin-bottom: 12px; display: flex; }}
            .detail-label {{ font-weight: 600; width: 140px; color: #065f46; }}
            .detail-value {{ color: #047857; font-weight: 500; }}
            .footer {{ background-color: #f8fafc; padding: 16px; text-align: center; font-size: 14px; color: #94a3b8; border-top: 1px solid #e2e8f0; }}
        </style>
    </head>
    <body>
        <div style="padding: 20px;">
            <div class="container">
                <div class="header">
                    <h2>Manual Payment Uploaded</h2>
                </div>
                <div class="content">
                    <h3>Hello Admin,</h3>
                    <p>A patient has just submitted a manual payment screenshot via <strong>{payment_method}</strong>. This payment is currently pending and requires your manual verification.</p>

                    <div class="details-card">
                        <div class="detail-row">
                            <div class="detail-label">Patient:</div>
                            <div class="detail-value">{patient_name}</div>
                        </div>
                        <div class="detail-row">
                            <div class="detail-label">Doctor:</div>
                            <div class="detail-value">Dr. {doctor_name}</div>
                        </div>
                        <div class="detail-row">
                            <div class="detail-label">Appointment:</div>
                            <div class="detail-value">{date_str}</div>
                        </div>
                        <div class="detail-row">
                            <div class="detail-label">Payment Method:</div>
                            <div class="detail-value">{payment_method}</div>
                        </div>
                        <div class="detail-row">
                            <div class="detail-label">Amount Paid:</div>
                            <div class="detail-value">Rs. {charges}</div>
                        </div>
                    </div>

                    <p>Please log in to the admin dashboard at your earliest convenience to review the proof and approve or reject the payment.</p>
                </div>
                <div class="footer">
                    <p>Quick Care Connect Admin System</p>
                </div>
            </div>
        </div>
    </body>
    </html>
    """
    
    # We will assume a static admin email handle for now
    send_email('Zohaibabdulmajeed123@gmail.com', subject, template)

def send_appointment_approved_email(patient_email, patient_name, doctor_name, appointment_date, appointment_time, charges):
    """Send an email to the patient notifying them that their appointment has been approved by the doctor and requires payment"""
    subject = f"Appointment Approved! Action Required - Quick Care Connect"
    
    # Format time explicitly for readability
    if isinstance(appointment_time, str):
        time_str = appointment_time
    else:
        time_str = appointment_time.strftime('%I:%M %p')
        
    date_str = appointment_date if isinstance(appointment_date, str) else appointment_date.strftime('%A, %b %d, %Y')
    
    try:
        from flask import url_for
        payment_link = url_for('patients.appointments', _external=True)
    except Exception:
        payment_link = "http://localhost:5000/patients/appointments"
        
    template = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <style>
            body {{ font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; line-height: 1.6; color: #334155; margin: 0; padding: 0; background-color: #f8fafc; }}
            .container {{ max-width: 600px; margin: 0 auto; background-color: #ffffff; border-radius: 8px; overflow: hidden; box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1); margin-top: 20px; margin-bottom: 20px; border: 1px solid #e2e8f0; }}
            .header {{ background-color: #10b981; color: #ffffff; padding: 24px; text-align: center; }}
            .header h2 {{ margin: 0; font-size: 24px; font-weight: 600; letter-spacing: -0.025em; }}
            .content {{ padding: 32px; }}
            .content h3 {{ color: #0f172a; font-size: 20px; font-weight: 600; margin-top: 0; }}
            .details-card {{ background-color: #f1f5f9; border-radius: 8px; padding: 20px; margin: 24px 0; border: 1px solid #e2e8f0; }}
            .details-card h4 {{ margin-top: 0; margin-bottom: 16px; color: #334155; font-size: 16px; border-bottom: 1px solid #cbd5e1; padding-bottom: 8px; }}
            .detail-row {{ margin-bottom: 12px; display: flex; }}
            .detail-label {{ font-weight: 600; width: 140px; color: #475569; }}
            .detail-value {{ color: #1e293b; font-weight: 500; }}
            .warning-box {{ background-color: #fef2f2; border-left: 4px solid #ef4444; padding: 12px 16px; color: #991b1b; margin-top: 20px; border-radius: 4px; font-size: 14px; font-weight: 500; }}
            .btn-primary {{ display: inline-block; padding: 12px 24px; background-color: #10b981; color: #ffffff !important; text-decoration: none; border-radius: 6px; font-weight: 500; text-align: center; width: auto; margin-top: 16px; }}
            .footer {{ background-color: #f8fafc; padding: 16px; text-align: center; font-size: 14px; color: #94a3b8; border-top: 1px solid #e2e8f0; }}
            .footer p {{ margin: 4px 0; }}
        </style>
    </head>
    <body>
        <div style="padding: 20px;">
            <div class="container">
                <div class="header">
                    <h2>Appointment Approved!</h2>
                </div>
                <div class="content">
                    <h3>Dear {patient_name},</h3>
                    <p>Good news! Your appointment request has been approved by <strong>{doctor_name}</strong>.</p>
                    <p>To confirm your slot permanently, please complete your payment of <strong>Rs. {charges}</strong>.</p>

                    <div class="warning-box">
                        ⚠️ Please make this payment within the next 30 minutes, or the appointment will be cancelled automatically to free up the slot.
                    </div>

                    <div class="details-card">
                        <h4>📅 Appointment Details</h4>
                        <div class="detail-row">
                            <div class="detail-label">Doctor:</div>
                            <div class="detail-value">{doctor_name}</div>
                        </div>
                        <div class="detail-row">
                            <div class="detail-label">Date:</div>
                            <div class="detail-value">{date_str}</div>
                        </div>
                        <div class="detail-row">
                            <div class="detail-label">Time:</div>
                            <div class="detail-value">{time_str}</div>
                        </div>
                        <div class="detail-row">
                            <div class="detail-label">Total Amount:</div>
                            <div class="detail-value">Rs. {charges}</div>
                        </div>
                    </div>

                </div>
                <div class="footer">
                    <p>Quick Care Connect &copy; {dt.datetime.now().year if 'dt' in locals() else '2026'}</p>
                    <p>This is an automated notification. Please do not reply.</p>
                </div>
            </div>
        </div>
    </body>
    </html>
    """
    
    send_email(patient_email, subject, template)
