"""
Background job to check for expired appointments and handle no-show scenarios.
Runs every 5 minutes to detect appointments that have passed their expiry window.
"""

from datetime import datetime, timedelta
from app import db
from app.models import Appointment, Doctor, DoctorTransaction, Refund
from flask import current_app


def check_expired_appointments():
    """
    Detect and handle expired appointments based on who joined the video call.
    
    Scenarios:
    1. Mutual No-Show: Neither joined -> Doctor penalty + Patient refund
    2. Patient No-Show: Only doctor joined -> Payment to doctor
    3. Doctor No-Show: Only patient joined -> Double doctor penalty + Patient refund
    """
    try:
        now = datetime.now()

        # Step 0: If slot has started and payment is still submitted (not approved),
        # auto-close appointment and move payment to disputed review.
        timeout_disputes = Appointment.query.filter(
            Appointment.status.in_(['pending', 'approved']),
            Appointment.payment_status == 'submitted',
        ).all()

        for appt in timeout_disputes:
            slot_start = datetime.combine(appt.appointment_date, appt.appointment_time)
            if now <= slot_start:
                continue

            appt.status = 'cancelled'
            appt.payment_status = 'disputed'
            appt.cancellation_reason = (
                f'Appointment slot started at {slot_start.strftime("%I:%M %p on %d %b %Y")} '
                f'before payment approval. Case moved to disputed review.'
            )
            print(f"[PAYMENT TIMEOUT] Appointment #{appt.id} moved to disputed review")
        
        # Find approved appointments that are past the expiry window (30 min after appointment time)
        expiry_buffer = timedelta(minutes=30)
        
        # Query appointments that:
        # - Status is 'approved' (not completed/cancelled)
        # - Appointment datetime + 30 mins < current time
        expired_appointments = Appointment.query.filter(
            Appointment.status == 'approved',
            Appointment.payment_status == 'approved',
            Appointment.appointment_type == 'video'
        ).all()
        
        for appt in expired_appointments:
            # Calculate appointment datetime
            appt_datetime = datetime.combine(appt.appointment_date, appt.appointment_time)
            expiry_time = appt_datetime + expiry_buffer
            
            # Skip if not expired yet
            if now < expiry_time:
                continue
            
            patient_joined = appt.patient_joined_video
            doctor_joined = appt.doctor_joined_video
            
            print(f"[EXPIRY] Processing appointment #{appt.id} - Patient: {patient_joined}, Doctor: {doctor_joined}")
            
            # SCENARIO 1: Mutual No-Show (Both missed)
            if not patient_joined and not doctor_joined:
                handle_mutual_noshow(appt)
            
            # SCENARIO 2: Patient No-Show (Doctor waited)
            elif doctor_joined and not patient_joined:
                handle_patient_noshow(appt)
            
            # SCENARIO 3: Doctor No-Show (Patient waited) - CRITICAL
            elif patient_joined and not doctor_joined:
                handle_doctor_noshow(appt)
            
            # Both joined - should have been completed normally, skip
            else:
                print(f"[EXPIRY] Both parties joined appointment #{appt.id} but not marked complete")
        
        db.session.commit()
        print(f"[EXPIRY CHECK] Completed at {now.strftime('%Y-%m-%d %H:%M:%S')}")
        
    except Exception as e:
        import traceback
        print(f"[ERROR] Expiry check failed: {str(e)}")
        traceback.print_exc()
        db.session.rollback()


def handle_mutual_noshow(appointment):
    """
    Both doctor and patient missed the appointment.
    - Patient: Full refund (Refund record for admin to process)
    - Doctor: No penalty
    """
    appointment.status = 'expired_mutual_noshow'
    from app.services.accounts_service import create_refund
    create_refund(appointment, reason='mutual_no_show', amount=appointment.charges)
    db.session.commit()
    print(f"[MUTUAL NO-SHOW] Appointment #{appointment.id} - Refund record created for patient")
    
    # TODO: Send notifications
    # notify_patient_refund_manual(appointment)
    # notify_doctor_mutual_noshow(appointment)


def handle_patient_noshow(appointment):
    """
    Patient missed, doctor was waiting.
    - Doctor: 80% of charges (20% platform commission)
    - No refund to patient
    """
    appointment.status = 'expired_patient_noshow'
    from app.services.accounts_service import transfer_to_doctor_noshow
    transfer_to_doctor_noshow(
        appointment,
        amount=appointment.charges,
        description=f"Patient no-show compensation for appointment #{appointment.id}",
        record_platform_commission=True,
    )
    db.session.commit()
    print(f"[PATIENT NO-SHOW] Appointment #{appointment.id} - 80% to doctor, 20% platform")
    
    # TODO: Send notification to patient
    # notify_patient_noshow_penalty(appointment)


def handle_doctor_noshow(appointment):
    """
    Doctor missed, patient was waiting.
    - Patient: Full refund (Refund record for admin to process)
    - Doctor: Penalty 20% of fee
    """
    appointment.status = 'expired_provider_failure'
    penalty_percentage = 0.20
    penalty_amount = round(appointment.charges * penalty_percentage, 2)
    deduct_doctor_penalty(
        appointment,
        reason=f"PROVIDER FAILURE - Patient waiting for appointment #{appointment.id} (20% fee penalty)",
        penalty_amount=penalty_amount
    )
    from app.services.accounts_service import create_refund
    create_refund(appointment, reason='doctor_no_show', amount=appointment.charges)
    db.session.commit()
    print(f"[PROVIDER FAILURE] Appointment #{appointment.id} - Doctor penalized PKR {penalty_amount}; refund record created for patient")
    
    # TODO: Send notifications
    # notify_patient_full_refund(appointment)
    # alert_admin_provider_failure(appointment)


def deduct_doctor_penalty(appointment, reason, penalty_amount):
    """Deduct penalty from doctor's balance and record transaction."""
    doctor = appointment.doctor
    doctor.balance -= penalty_amount
    doctor.total_penalties += penalty_amount
    
    # Record transaction
    transaction = DoctorTransaction(
        doctor_id=doctor.id,
        appointment_id=appointment.id,
        transaction_type='penalty',
        amount=-penalty_amount,
        description=reason,
        status='completed'
    )
    db.session.add(transaction)
    print(f"[PENALTY] Doctor {doctor.id} balance: PKR {doctor.balance}")


