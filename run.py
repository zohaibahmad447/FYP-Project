# -*- coding: utf-8 -*-
"""
Quick Care Connect - Main Application Entry Point
This is the main entry point for running the Flask application.
"""
from app import create_app, db, socketio
from app.models import User, Doctor, Patient, Admin, Appointment, MedicalHistory, Question, Answer, Blog, Disease, Refund, PlatformRevenue, DoctorPayoutRequest, VideoCallRecording

app = create_app()

@app.shell_context_processor
def make_shell_context():
    return {
        'User': User,
        'Doctor': Doctor,
        'Patient': Patient,
        'Admin': Admin,
        'Appointment': Appointment,
        'MedicalHistory': MedicalHistory,
        'Question': Question,
        'Answer': Answer,
        'Blog': Blog,
        'Disease': Disease,
        'Refund': Refund,
        'PlatformRevenue': PlatformRevenue,
        'DoctorPayoutRequest': DoctorPayoutRequest,
        'VideoCallRecording': VideoCallRecording,
    }

if __name__ == '__main__':
    socketio.run(app, debug=True, host='0.0.0.0', port=5000, ssl_context=('localhost+3.pem', 'localhost+3-key.pem'), allow_unsafe_werkzeug=True)