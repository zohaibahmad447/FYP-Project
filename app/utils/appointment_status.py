"""Appointment status labels and completion finalization (single source of truth)."""
from __future__ import annotations

from typing import Tuple

from app.database import db


# DB status -> human label (when no appointment context needed)
STATUS_LABELS = {
    'pending': 'Pending Approval',
    'approved': 'Approved',
    'rejected': 'Rejected',
    'cancelled': 'Cancelled',
    'completed': 'Completed',
    'completed_pending_review': 'Awaiting Patient Review',
    'disputed': 'Under Dispute',
    'no_show': 'No Show',
    'expired_patient_noshow': 'Missed Appointment',
    'expired_provider_failure': 'Doctor Missed',
    'expired_mutual_noshow': 'Mutual No-Show',
}

# Bootstrap badge class suffix: badge-{class}
STATUS_BADGE_CLASS = {
    'pending': 'secondary',
    'approved': 'warning',
    'rejected': 'danger',
    'cancelled': 'danger',
    'completed': 'success',
    'completed_pending_review': 'info',
    'disputed': 'danger',
    'no_show': 'danger',
    'expired_patient_noshow': 'secondary',
    'expired_provider_failure': 'secondary',
    'expired_mutual_noshow': 'secondary',
}


def appointment_status_label(appointment) -> str:
    """User-facing status label considering flags and review progress."""
    status = appointment.status or 'pending'
    if status == 'pending':
        payment_status = getattr(appointment, 'payment_status', None) or 'pending'
        if payment_status in ('pending', 'rejected'):
            return 'Awaiting Payment'
        if payment_status == 'submitted':
            return 'Payment Under Review'
        if payment_status == 'approved':
            return 'Pending Approval'
    if status == 'completed_pending_review':
        if getattr(appointment, 'patient_disputed', False):
            return STATUS_LABELS['disputed']
        if getattr(appointment, 'patient_completed', False):
            return STATUS_LABELS['completed']
        if getattr(appointment, 'review', None) or getattr(appointment, 'patient_review_skipped', False):
            return 'Awaiting Your Confirmation'
        return 'Awaiting Your Review'
    return STATUS_LABELS.get(status, status.replace('_', ' ').title())


def appointment_status_badge_class(appointment) -> str:
    """Bootstrap badge-* class for appointment row."""
    status = appointment.status or 'pending'
    if status == 'pending':
        payment_status = getattr(appointment, 'payment_status', None) or 'pending'
        if payment_status in ('pending', 'rejected'):
            return 'warning'
        if payment_status == 'submitted':
            return 'info'
        if payment_status == 'approved':
            return STATUS_BADGE_CLASS['pending']
    if status == 'completed_pending_review':
        if getattr(appointment, 'patient_completed', False):
            return STATUS_BADGE_CLASS['completed']
        if getattr(appointment, 'review', None) or getattr(appointment, 'patient_review_skipped', False):
            return 'warning'
        return STATUS_BADGE_CLASS['completed_pending_review']
    return STATUS_BADGE_CLASS.get(status, 'info')


def appointment_effective_status(appointment) -> str:
    """Logical status for UI filters (maps stuck confirmed rows to completed)."""
    if appointment.status == 'completed_pending_review' and appointment.patient_completed:
        return 'completed'
    return appointment.status


def finalize_appointment_completion(appointment, *, when=None) -> bool:
    """
    Mark appointment fully completed and credit doctor (idempotent).
    Returns True if transitioned to completed now.
    """
    from app.utils.timezone import pkt_now_naive
    from app.services.accounts_service import credit_doctor_after_completion

    if appointment.status == 'disputed':
        return False
    if appointment.status == 'completed':
        credit_doctor_after_completion(appointment)
        return False

    ts = when or pkt_now_naive()
    appointment.status = 'completed'
    appointment.patient_completed = True
    if not appointment.patient_completed_at:
        appointment.patient_completed_at = ts
    if not appointment.completed_at:
        appointment.completed_at = ts

    db.session.commit()
    credit_doctor_after_completion(appointment)
    return True


def repair_stuck_confirmed_appointments() -> int:
    """Fix rows where patient confirmed but status was never updated."""
    from app.models import Appointment

    stuck = Appointment.query.filter_by(
        status='completed_pending_review',
        patient_completed=True,
        patient_disputed=False,
    ).all()
    count = 0
    for appt in stuck:
        if finalize_appointment_completion(appt):
            count += 1
    return count
