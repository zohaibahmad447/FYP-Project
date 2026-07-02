"""
Auto-Cleanup Job: Cancel Expired Unpaid Appointments
Purpose: Automatically cancel appointments where payment deadline has expired
Schedule: Run this script every 10 minutes as a cron job

Usage:
    python -m app.utils.cleanup_expired_payments
    
Cron Job Example (every 10 minutes):
    */10 * * * * cd /path/to/quickcare && python -m app.utils.cleanup_expired_payments
"""

import sys
import os
from datetime import datetime

# Add parent directory to path so we can import app modules
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..'))

from app import create_app
from app.database import db
from app.models import Appointment
from app.utils.timezone import get_pakistan_now, PAKISTAN_TZ

def cleanup_expired_payments():
    """Find and cancel appointments with expired payment deadlines"""
    app = create_app()
    
    with app.app_context():
        current_time = get_pakistan_now()
        
        # Find all approved appointments with pending payment that have expired deadline
        expired_appointments = Appointment.query.filter(
            Appointment.status == 'pending',
            Appointment.payment_status == 'pending',
            Appointment.payment_deadline.isnot(None),
            Appointment.payment_deadline < current_time
        ).all()
        
        if not expired_appointments:
            print(f"[{current_time.strftime('%Y-%m-%d %H:%M:%S')}] No expired payments found.")
            return
        
        print(f"[{current_time.strftime('%Y-%m-%d %H:%M:%S')}] Found {len(expired_appointments)} expired payment(s).")
        
        # Cancel each expired appointment
        cancelled_count = 0
        for appointment in expired_appointments:
            try:
                # Calculate how late the payment is
                # Localize the naive deadline to PKT (it's stored naive but represents PKT time)
                deadline_aware = PAKISTAN_TZ.localize(appointment.payment_deadline)
                time_diff = current_time - deadline_aware
                minutes_late = int(time_diff.total_seconds() / 60)
                
                # Update appointment status
                appointment.status = 'cancelled'
                appointment.cancellation_reason = (
                    f"Payment deadline expired at {appointment.payment_deadline.strftime('%I:%M %p')} "
                    f"on {appointment.payment_deadline.strftime('%d %b %Y')}. "
                    f"No payment received within the required time window."
                )
                
                db.session.commit()
                
                print(f"  ✓ Cancelled Appointment #{appointment.id} "
                      f"(Patient: {appointment.patient.user.name}, "
                      f"Doctor: {appointment.doctor.user.name}, "
                      f"Late by: {minutes_late} mins)")
                
                cancelled_count += 1
                
                # TODO: Send notification to patient
                # - Email notification about cancellation
                # - SMS notification (optional)
                # - In-app notification
                
            except Exception as e:
                db.session.rollback()
                print(f"  ✗ Error cancelling Appointment #{appointment.id}: {e}")
        
        print(f"[{current_time.strftime('%Y-%m-%d %H:%M:%S')}] Successfully cancelled {cancelled_count} appointment(s).")

        # -----------------------------------------------------------------
        # Timeout rule: if slot has started and payment is still submitted
        # (not admin-approved), close appointment and move to disputed review.
        # -----------------------------------------------------------------
        submitted_appointments = Appointment.query.filter(
            Appointment.status.in_(['pending', 'approved']),
            Appointment.payment_status == 'submitted'
        ).all()

        disputed_count = 0
        for appointment in submitted_appointments:
            try:
                # appointment_date/time are stored as local scheduling values (PKT)
                slot_start_naive = datetime.combine(
                    appointment.appointment_date,
                    appointment.appointment_time,
                )
                slot_start = PAKISTAN_TZ.localize(slot_start_naive)

                # Only transition after slot start has passed
                if current_time <= slot_start:
                    continue

                appointment.status = 'cancelled'
                appointment.payment_status = 'disputed'
                appointment.cancellation_reason = (
                    f"Appointment slot started at {slot_start_naive.strftime('%I:%M %p on %d %b %Y')} "
                    f"before payment approval. Moved to disputed review for admin verification."
                )

                db.session.commit()
                disputed_count += 1

                print(
                    f"  ✓ Disputed timeout Appointment #{appointment.id} "
                    f"(Patient: {appointment.patient.user.name}, Doctor: {appointment.doctor.user.name})"
                )
            except Exception as e:
                db.session.rollback()
                print(f"  ✗ Error disputing Appointment #{appointment.id}: {e}")

        if disputed_count:
            print(
                f"[{current_time.strftime('%Y-%m-%d %H:%M:%S')}] "
                f"Moved {disputed_count} submitted payment(s) to disputed timeout review."
            )

if __name__ == '__main__':
    cleanup_expired_payments()
