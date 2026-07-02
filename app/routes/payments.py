"""
Safepay Payment Gateway Integration
Handles secure card payment via Safepay and manual wallet screenshot upload.
"""

from flask import (
    Blueprint,
    request,
    redirect,
    url_for,
    flash,
    current_app,
    jsonify,
    render_template,
)
from app.models import Appointment
from app.database import db
from app.utils.auth import patient_required, get_current_user
from datetime import datetime
import hashlib
import hmac
import requests as http_requests
from app.utils.appointment_workflow import on_payment_marked_approved

payments_bp = Blueprint('payments', __name__)

SAFEPAY_HEADERS = {
    'Content-Type': 'application/json',
    'Accept': 'application/json',
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36',
}


def _safepay_base_url():
    return current_app.config.get('SAFEPAY_BASE_URL', 'https://sandbox.api.getsafepay.com')


def _safepay_checkout_url():
    return current_app.config.get('SAFEPAY_CHECKOUT_URL') or _safepay_base_url()


def _safepay_api_key():
    return current_app.config.get('SAFEPAY_API_KEY', '')


def _safepay_environment():
    return current_app.config.get('SAFEPAY_ENVIRONMENT', 'sandbox')


@payments_bp.route('/api/payment-status/<int:appointment_id>')
@patient_required
def payment_status_api(appointment_id):
    """
    JSON endpoint polled by JavaScript every few seconds.
    Returns the current payment status and, if still pending,
    checks Safepay's tracker API to detect if payment completed.
    """
    user = get_current_user()
    patient = user.patient_profile
    appointment = Appointment.query.filter_by(
        id=appointment_id, patient_id=patient.id
    ).first_or_404()

    # Already approved — job done
    if appointment.payment_status == 'approved':
        return jsonify({'status': 'approved'})

    # Check Safepay tracker if we have a pending token
    if (appointment.payment_screenshot and
            appointment.payment_screenshot.startswith('safepay_pending_')):
        tracker_token = appointment.payment_screenshot.replace('safepay_pending_', '')
        try:
            resp = http_requests.get(
                f'{_safepay_base_url()}/order/v1/{tracker_token}',
                headers=SAFEPAY_HEADERS,
                timeout=5
            )
            if resp.status_code == 200:
                state = resp.json().get('data', {}).get('state', '')
                current_app.logger.info(
                    f'[SAFEPAY POLL] Appt #{appointment_id} tracker state: {state}'
                )
                if state in ('TRACKER_ENDED', 'PAYMENT_SUCCESSFUL', 'CHARGED'):
                    if mark_appointment_paid(appointment, tracker_token):
                        return jsonify({'status': 'approved', 'just_verified': True})
                    return jsonify({'status': 'cancelled', 'slot_conflict': True})
                return jsonify({'status': 'pending', 'tracker_state': state})
        except Exception as e:
            current_app.logger.error(f'[SAFEPAY POLL] Error: {e}')

    return jsonify({'status': appointment.payment_status})

def verify_tracker_payment(tracker_token):
    """
    Call Safepay's Tracker API to check if a payment was actually completed.
    Returns True if payment state is TRACKER_ENDED (paid), False otherwise.
    """
    try:
        resp = http_requests.get(
            f'{_safepay_base_url()}/order/v1/{tracker_token}',
            headers=SAFEPAY_HEADERS,
            timeout=10
        )
        if resp.status_code == 200:
            data = resp.json()
            state = data.get('data', {}).get('state', '')
            current_app.logger.info(f'[SAFEPAY] Tracker {tracker_token} state: {state}')
            # TRACKER_ENDED = payment captured successfully
            return state in ('TRACKER_ENDED', 'PAYMENT_SUCCESSFUL', 'CHARGED')
        else:
            current_app.logger.warning(
                f'[SAFEPAY] Tracker lookup failed: {resp.status_code} {resp.text[:200]}'
            )
    except Exception as e:
        current_app.logger.error(f'[SAFEPAY] Tracker verify error: {e}')
    return False


def _safepay_return_interstitial(
    appointment_id,
    status,
    heading,
    message,
    close_delay_ms=2200,
):
    """
    Minimal page shown in the payment popup after Safepay redirects back.
    Notifies the opener tab via postMessage, then attempts window.close().
    """
    return_url = url_for(
        'appointments.view_appointment',
        appointment_id=appointment_id,
        _external=True,
    )
    return render_template(
        'payments/safepay_return_interstitial.html',
        appointment_id=appointment_id,
        status=status,
        heading=heading,
        message=message,
        close_delay_ms=close_delay_ms,
        return_url=return_url,
    )


def mark_appointment_paid(appointment, tracker_token):
    """Helper to set appointment payment status to approved."""
    if appointment.payment_status == 'approved':
        return False

    from app.utils.slots import find_reserved_appointment

    conflict = find_reserved_appointment(
        appointment.doctor_id,
        appointment.appointment_date,
        appointment.appointment_time,
        exclude_appointment_id=appointment.id,
    )
    if conflict:
        appointment.payment_status = 'approved'
        appointment.payment_approved_at = datetime.utcnow()
        appointment.payment_screenshot = f'safepay_txn_{tracker_token}'
        appointment.status = 'cancelled'
        appointment.cancellation_reason = (
            'This slot was taken by another patient who completed payment first. '
            'Refund will be processed.'
        )
        try:
            from app.services.accounts_service import create_refund
            create_refund(appointment, reason='slot_unavailable', amount=appointment.charges)
        except Exception as e:
            current_app.logger.error(f'[PAYMENT] Refund record failed for appt #{appointment.id}: {e}')
        db.session.commit()
        current_app.logger.warning(
            f'[SAFEPAY] Appointment #{appointment.id} paid but slot conflict; cancelled for refund.'
        )
        return False

    appointment.payment_status = 'approved'
    appointment.payment_approved_at = datetime.utcnow()
    appointment.payment_screenshot = f'safepay_txn_{tracker_token}'
    on_payment_marked_approved(appointment)
    db.session.commit()
    current_app.logger.info(
        f'[SAFEPAY] Appointment #{appointment.id} marked as PAID. Tracker: {tracker_token}'
    )
    return True


@payments_bp.route('/safepay/checkout/<int:appointment_id>')
@patient_required
def safepay_checkout(appointment_id):
    """
    Step 1: Call Safepay's Order API to initialize a payment tracker.
    Step 2: Save the tracker token in the appointment record.
    Step 3: Redirect the patient to Safepay's hosted checkout page.
    """
    user = get_current_user()
    patient = user.patient_profile

    appointment = Appointment.query.filter_by(
        id=appointment_id,
        patient_id=patient.id
    ).first_or_404()

    if appointment.status != 'pending':
        flash('Payment is no longer required for this appointment.', 'error')
        return redirect(url_for('appointments.view_appointment', appointment_id=appointment_id))

    if appointment.payment_status == 'approved':
        flash('This appointment has already been paid.', 'info')
        return redirect(url_for('appointments.view_appointment', appointment_id=appointment_id))

    if appointment.payment_status == 'submitted':
        flash('Your payment is already under review.', 'info')
        return redirect(url_for('appointments.view_appointment', appointment_id=appointment_id))

    from app.utils.slots import slot_is_reserved
    if slot_is_reserved(
        appointment.doctor_id,
        appointment.appointment_date,
        appointment.appointment_time,
        exclude_appointment_id=appointment.id,
    ):
        flash('This time slot was just taken by another patient. Please book a different time.', 'error')
        return redirect(url_for('appointments.view_appointment', appointment_id=appointment_id))

    if not _safepay_api_key():
        flash('Payment gateway is not configured. Please contact support.', 'error')
        return redirect(url_for('appointments.view_appointment', appointment_id=appointment_id))

    # Amount in smallest currency unit
    amount_paisas = int(float(appointment.charges) * 100)

    return_url = url_for('payments.safepay_return',
                         appointment_id=appointment_id, _external=True)

    try:
        # Step 1: Create a tracker token via Safepay Order API
        response = http_requests.post(
            f'{_safepay_base_url()}/order/v1/init',
            headers=SAFEPAY_HEADERS,
            json={
                'client': _safepay_api_key(),
                'environment': _safepay_environment(),
                'amount': amount_paisas,
                'currency': 'PKR'
            },
            timeout=10
        )
        response.raise_for_status()
        data = response.json()
        tracker = data['data']['token']

    except http_requests.exceptions.HTTPError:
        current_app.logger.error(
            f'[SAFEPAY HTTP] Status: {response.status_code}, Response: {response.text}'
        )
        flash('Payment gateway is temporarily unavailable. Please try again.', 'error')
        return redirect(url_for('appointments.view_appointment', appointment_id=appointment_id))
    except Exception as e:
        current_app.logger.error(f'[SAFEPAY] Tracker creation failed: {e}')
        flash('Payment gateway is temporarily unavailable. Please try again.', 'error')
        return redirect(url_for('appointments.view_appointment', appointment_id=appointment_id))

    # Step 2: Save tracker token in payment_screenshot field so return route can verify it
    appointment.payment_screenshot = f'safepay_pending_{tracker}'
    db.session.commit()
    current_app.logger.info(f'[SAFEPAY] Created tracker {tracker} for appointment #{appointment_id}')

    # Step 3: Redirect to Safepay's hosted checkout
    # NOTE: Safepay uses 'beacon' (NOT 'token') as the session identifier param.
    from urllib.parse import quote
    checkout_url = (
        f"{_safepay_checkout_url()}/checkout/pay"
        f"?env={_safepay_environment()}"
        f"&beacon={tracker}"
        f"&redirect_url={quote(return_url, safe='')}"
    )
    current_app.logger.info(f'[SAFEPAY] Redirecting to checkout: {checkout_url}')
    return redirect(checkout_url)


@payments_bp.route('/safepay/return/<int:appointment_id>')
@patient_required
def safepay_return(appointment_id):
    """
    Safepay redirects here after the patient clicks 'Close' on the
    Transaction Submitted page. We verify payment status via the Tracker API
    using the token we saved during checkout.
    """
    user = get_current_user()
    patient = user.patient_profile

    appointment = Appointment.query.filter_by(
        id=appointment_id,
        patient_id=patient.id
    ).first_or_404()

    # Log all received params for debugging
    current_app.logger.info(
        f'[SAFEPAY RETURN] Appointment #{appointment_id} | Args: {dict(request.args)}'
    )

    # If already paid (e.g. via webhook), close popup and refresh opener
    if appointment.payment_status == 'approved':
        return _safepay_return_interstitial(
            appointment_id,
            'already_paid',
            'Payment confirmed',
            'Your appointment is already paid. Returning you to Quick Care…',
            close_delay_ms=1800,
        )

    # Retrieve the tracker token we saved during checkout
    tracker_token = None
    if appointment.payment_screenshot and appointment.payment_screenshot.startswith('safepay_pending_'):
        tracker_token = appointment.payment_screenshot.replace('safepay_pending_', '')

    # Also check if Safepay passed ref/tracker in query params (some versions do)
    query_tracker = (
        request.args.get('reference') or
        request.args.get('tracker') or
        request.args.get('beacon') or
        request.args.get('token')
    )
    if query_tracker and not tracker_token:
        tracker_token = query_tracker

    if not tracker_token:
        current_app.logger.error(
            f'[SAFEPAY] No tracker token found for appointment #{appointment_id}'
        )
        return _safepay_return_interstitial(
            appointment_id,
            'error',
            'Could not verify automatically',
            'We could not link this session to your payment. If you were charged, '
            'contact support with your receipt. You can close this window and '
            'check your appointment page.',
            close_delay_ms=4500,
        )

    # Verify payment with Safepay API
    is_paid = verify_tracker_payment(tracker_token)

    if is_paid:
        mark_appointment_paid(appointment, tracker_token)
        return _safepay_return_interstitial(
            appointment_id,
            'paid',
            'Payment successful',
            'Your card payment was verified. This window will close and your '
            'appointment page will refresh.',
            close_delay_ms=2200,
        )

    # Payment may still be processing – give user feedback
    current_app.logger.warning(
        f'[SAFEPAY] Tracker {tracker_token} not yet TRACKER_ENDED for appointment #{appointment_id}'
    )
    return _safepay_return_interstitial(
        appointment_id,
        'processing',
        'Processing',
        'Safepay is still finalizing your payment. Your appointment page will '
        'refresh; if status is not updated yet, wait a few seconds and refresh again.',
        close_delay_ms=3500,
    )


@payments_bp.route('/safepay/webhook', methods=['POST'])
def safepay_webhook():
    """
    Safepay server-side webhook notification.
    Called by Safepay when a payment is completed, regardless of browser redirect.
    This ensures our DB is always updated even if the user closes their browser.
    """
    try:
        payload = request.get_json(silent=True) or {}
        current_app.logger.info(f'[SAFEPAY WEBHOOK] Received: {payload}')

        tracker_token = (
            payload.get('tracker_token') or
            payload.get('reference') or
            payload.get('token')
        )
        state = payload.get('state', '')

        if not tracker_token:
            return jsonify({'status': 'ignored', 'reason': 'no tracker'}), 200

        if state not in ('TRACKER_ENDED', 'PAYMENT_SUCCESSFUL'):
            return jsonify({'status': 'ignored', 'reason': f'state={state}'}), 200

        # Find the appointment with this pending tracker
        appointment = Appointment.query.filter(
            Appointment.payment_screenshot == f'safepay_pending_{tracker_token}'
        ).first()

        if not appointment:
            current_app.logger.warning(
                f'[SAFEPAY WEBHOOK] No appointment found for tracker {tracker_token}'
            )
            return jsonify({'status': 'not_found'}), 200

        mark_appointment_paid(appointment, tracker_token)
        return jsonify({'status': 'ok'}), 200

    except Exception as e:
        current_app.logger.error(f'[SAFEPAY WEBHOOK] Error: {e}')
        return jsonify({'status': 'error'}), 500


@payments_bp.route('/safepay/cancel/<int:appointment_id>')
@patient_required
def safepay_cancel(appointment_id):
    """
    Called if the user goes back/cancels on the Safepay checkout page.
    """
    return _safepay_return_interstitial(
        appointment_id,
        'cancelled',
        'Payment cancelled',
        'You can return to your appointment and choose a payment method again whenever you are ready.',
        close_delay_ms=2200,
    )
