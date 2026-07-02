"""
Prescription routes for creating and managing medical prescriptions
"""
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, send_file
from app.models import Prescription, PrescriptionMedicine, PrescriptionTest, Appointment
from app.database import db
from app.utils.auth import doctor_required, get_current_user
from datetime import datetime
import os

prescriptions_bp = Blueprint('prescriptions', __name__, url_prefix='/prescriptions')

@prescriptions_bp.route('/create/<int:appointment_id>', methods=['GET', 'POST'])
@doctor_required
def create_prescription(appointment_id):
    """Create a new prescription for an appointment"""
    user = get_current_user()
    doctor = user.doctor_profile
    
    # Get the appointment
    appointment = Appointment.query.get_or_404(appointment_id)
    
    # Verify this doctor owns the appointment
    if appointment.doctor_id != doctor.id:
        flash('Unauthorized access to this appointment.', 'error')
        return redirect(url_for('doctors.appointments'))
    
    # Check if prescription already exists
    if appointment.prescription:
        flash('Prescription already exists for this appointment. You can edit it instead.', 'warning')
        return redirect(url_for('prescriptions.view_prescription', prescription_id=appointment.prescription.id))
    
    if request.method == 'POST':
        try:
            # Create prescription
            prescription = Prescription(
                appointment_id=appointment_id,
                vitals_weight=request.form.get('weight') or None,
                vitals_bp=request.form.get('bp') or None,
                vitals_temp=request.form.get('temp') or None,
                vitals_pulse=request.form.get('pulse') or None,
                diagnosis=request.form.get('diagnosis'),
                chief_complaints=request.form.get('complaints') or None,
                advice=request.form.get('advice') or None,
                follow_up_date=datetime.strptime(request.form.get('follow_up_date'), '%Y-%m-%d').date() if request.form.get('follow_up_date') else None,
                follow_up_notes=request.form.get('follow_up_notes') or None
            )
            db.session.add(prescription)
            db.session.flush()  # Get prescription.id
            
            # Add medicines
            medicine_names = request.form.getlist('medicine_name[]')
            medicine_dosages = request.form.getlist('medicine_dosage[]')
            medicine_frequencies = request.form.getlist('medicine_frequency[]')
            medicine_durations = request.form.getlist('medicine_duration[]')
            medicine_instructions = request.form.getlist('medicine_instructions[]')
            
            for i, name in enumerate(medicine_names):
                if name.strip():  # Only add if name is not empty
                    medicine = PrescriptionMedicine(
                        prescription_id=prescription.id,
                        medicine_name=name,
                        dosage=medicine_dosages[i],
                        frequency=medicine_frequencies[i],
                        duration=medicine_durations[i],
                        instructions=medicine_instructions[i] if i < len(medicine_instructions) else '',
                        order=i
                    )
                    db.session.add(medicine)
            
            # Add tests
            test_names = request.form.getlist('test_name[]')
            test_instructions = request.form.getlist('test_instructions[]')
            
            for i, name in enumerate(test_names):
                if name.strip():  # Only add if name is not empty
                    test = PrescriptionTest(
                        prescription_id=prescription.id,
                        test_name=name,
                        instructions=test_instructions[i] if i < len(test_instructions) else '',
                        order=i
                    )
                    db.session.add(test)
            
            db.session.commit()
            flash('Prescription created successfully!', 'success')
            return redirect(url_for('prescriptions.view_prescription', prescription_id=prescription.id))
            
        except Exception as e:
            db.session.rollback()
            flash(f'Error creating prescription: {str(e)}', 'error')
            print(f'Error creating prescription: {e}')
    
    return render_template('prescriptions/create.html', appointment=appointment)

@prescriptions_bp.route('/view/<int:prescription_id>')
def view_prescription(prescription_id):
    """View a prescription"""
    prescription = Prescription.query.get_or_404(prescription_id)
    
    # Check access (doctor or patient of this appointment)
    user = get_current_user()
    appointment = prescription.appointment
    
    has_access = False
    if user.role == 'doctor' and user.doctor_profile:
        doctor_id = user.doctor_profile.id
        if appointment.doctor_id == doctor_id:
            has_access = True
        else:
            # Allow a doctor to review prior prescriptions for patients they have seen.
            has_access = Appointment.query.filter_by(
                doctor_id=doctor_id,
                patient_id=appointment.patient_id,
            ).first() is not None
    elif user.role == 'patient' and appointment.patient_id == user.patient_profile.id:
        has_access = True
    elif user.role == 'admin':
        has_access = True
    
    if not has_access:
        flash('Unauthorized access to this prescription.', 'error')
        return redirect(url_for('home.index'))
    
    return render_template('prescriptions/view.html', prescription=prescription)

@prescriptions_bp.route('/download/<int:prescription_id>')
def download_prescription(prescription_id):
    """Generate and download prescription PDF"""
    prescription = Prescription.query.get_or_404(prescription_id)
    
    # Check access
    user = get_current_user()
    appointment = prescription.appointment
    
    has_access = False
    if user.role == 'doctor' and user.doctor_profile:
        doctor_id = user.doctor_profile.id
        if appointment.doctor_id == doctor_id:
            has_access = True
        else:
            # Allow a doctor to review prior prescriptions for patients they have seen.
            has_access = Appointment.query.filter_by(
                doctor_id=doctor_id,
                patient_id=appointment.patient_id,
            ).first() is not None
    elif user.role == 'patient' and appointment.patient_id == user.patient_profile.id:
        has_access = True
    elif user.role == 'admin':
        has_access = True
    
    if not has_access:
        flash('Unauthorized access to this prescription.', 'error')
        return redirect(url_for('home.index'))
    
    # Generate PDF (we'll implement this in the next step)
    from app.utils.pdf_generator import generate_prescription_pdf
    
    try:
        pdf_path = generate_prescription_pdf(prescription)
        return send_file(pdf_path, as_attachment=False, download_name=f'prescription_{prescription.id}.pdf')
    except Exception as e:
        flash(f'Error generating PDF: {str(e)}', 'error')
        return redirect(url_for('prescriptions.view_prescription', prescription_id=prescription_id))
