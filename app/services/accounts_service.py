"""
Accounts service: platform commission, doctor earnings, refund records (no patient wallet).
Refunds are admin-processed (bank/card); we only create Refund records.
"""
from datetime import datetime
from flask import current_app
from app.database import db
from app.models import (
    Appointment, Doctor, DoctorTransaction, PlatformRevenue, Refund,
)


def get_commission_percent():
    return getattr(
        current_app.config,
        'PLATFORM_COMMISSION_PERCENT',
        20,
    )


def credit_doctor_after_completion(appointment):
    """
    Idempotent: when appointment is fully completed, credit doctor (80%) and record platform revenue (20%).
    Call from confirm_completion and process_completion_reviews when status becomes 'completed'.
    """
    if appointment.status != 'completed':
        return
    if getattr(appointment, 'doctor_earning_credited_at', None):
        return
    # Already have an earning transaction for this appointment?
    existing = DoctorTransaction.query.filter_by(
        appointment_id=appointment.id,
        transaction_type='earning',
    ).first()
    if existing:
        appointment.doctor_earning_credited_at = existing.created_at
        db.session.commit()
        return

    pct = get_commission_percent() / 100.0
    commission = round(appointment.charges * pct, 2)
    doctor_share = round(appointment.charges - commission, 2)
    appointment.platform_commission_amount = commission
    appointment.platform_commission_percent = get_commission_percent()
    appointment.doctor_earning_credited_at = datetime.utcnow()

    doctor = appointment.doctor
    doctor.balance += doctor_share
    doctor.total_earned += doctor_share

    db.session.add(
        DoctorTransaction(
            doctor_id=doctor.id,
            appointment_id=appointment.id,
            transaction_type='earning',
            amount=doctor_share,
            commission_deducted=commission,
            description=f"Consultation completed (Appointment #{appointment.id})",
            status='completed',
        )
    )
    db.session.add(
        PlatformRevenue(
            appointment_id=appointment.id,
            amount=commission,
            source='commission',
        )
    )
    db.session.commit()


def transfer_to_doctor_noshow(appointment, amount, description, record_platform_commission=True):
    """Add earnings to doctor (e.g. patient no-show) and optionally record platform commission."""
    doctor = appointment.doctor
    pct = get_commission_percent() / 100.0
    commission = round(amount * pct, 2)
    doctor_share = round(amount - commission, 2)
    doctor.balance += doctor_share
    doctor.total_earned += doctor_share
    db.session.add(
        DoctorTransaction(
            doctor_id=doctor.id,
            appointment_id=appointment.id,
            transaction_type='earning',
            amount=doctor_share,
            commission_deducted=commission,
            description=description,
            status='completed',
        )
    )
    if record_platform_commission:
        db.session.add(
            PlatformRevenue(
                appointment_id=appointment.id,
                amount=commission,
                source='commission',
            )
        )


def create_refund(appointment, reason, amount=None):
    """Create a Refund record (admin will process externally). Amount defaults to appointment.charges."""
    if amount is None:
        amount = appointment.charges
    if amount <= 0:
        return None
    refund = Refund(
        appointment_id=appointment.id,
        patient_id=appointment.patient_id,
        amount=round(amount, 2),
        reason=reason,
        status='pending',
    )
    db.session.add(refund)
    return refund


def get_cancellation_refund_policy(appointment, cancelled_at, is_doctor_cancel):
    """
    Returns (refund_amount, policy_label).
    Policy: >24h full; 2-24h partial (config %); <2h none. Doctor cancel = always full.
    cancelled_at: datetime of when cancellation happened (naive or aware).
    """
    from datetime import datetime
    appt_dt = datetime.combine(appointment.appointment_date, appointment.appointment_time)
    if getattr(cancelled_at, 'tzinfo', None):
        cancelled_at = datetime(cancelled_at.year, cancelled_at.month, cancelled_at.day,
                                cancelled_at.hour, cancelled_at.minute, cancelled_at.second)
    hours_until = (appt_dt - cancelled_at).total_seconds() / 3600.0
    full_h = current_app.config.get('CANCELLATION_FULL_REFUND_HOURS', 24)
    partial_h = current_app.config.get('CANCELLATION_PARTIAL_REFUND_HOURS', 2)
    partial_pct = current_app.config.get('PARTIAL_REFUND_PERCENT', 50) / 100.0
    paid = appointment.payment_status == 'approved'
    charges = appointment.charges if paid else 0

    if is_doctor_cancel and paid:
        return charges, 'full'
    if not paid:
        return 0, 'none'
    if hours_until >= full_h:
        return charges, 'full'
    if hours_until >= partial_h:
        return round(charges * partial_pct, 2), 'partial'
    return 0, 'none'
