"""
Background job to auto-complete appointments after 24-hour review period expires
"""
from app.models import Appointment
from app.database import db
from app.utils.timezone import pkt_now_naive
from app.utils.appointment_status import finalize_appointment_completion, repair_stuck_confirmed_appointments


def process_completion_reviews():
    """
    1. Repair any appointments patient confirmed but status stuck on completed_pending_review
    2. Auto-complete when 24h review window expires without dispute (patient silent = satisfied)
    """
    current_time = pkt_now_naive()

    repaired = repair_stuck_confirmed_appointments()
    if repaired:
        print(f'[AUTO-COMPLETE] Repaired {repaired} stuck confirmed appointment(s)')

    expired_reviews = Appointment.query.filter(
        Appointment.status == 'completed_pending_review',
        Appointment.patient_completed == False,
        Appointment.patient_disputed == False,
        Appointment.completion_review_deadline <= current_time,
    ).all()

    finalized = 0
    for appointment in expired_reviews:
        if finalize_appointment_completion(appointment, when=current_time):
            finalized += 1
            print(f'[AUTO-COMPLETE] Appointment #{appointment.id} — 24-hour review period expired')

    if finalized:
        print(f'✓ Auto-completed {finalized} appointment(s)')
    elif not repaired:
        print('No appointments need auto-completion')
