from flask import Blueprint, request, jsonify
from app.database import db
from app.models import Appointment, Review
from app.utils.auth import get_current_user, patient_required
from app.utils.review_fraud import (
    evaluate_review_fraud,
    get_client_ip,
    hash_ip,
    lookup_geo,
)

reviews_bp = Blueprint('reviews', __name__, url_prefix='/reviews')


@reviews_bp.route('/submit', methods=['POST'])
@patient_required
def submit_review():
    """Patient submits a star rating and written comment after a completed appointment."""
    user = get_current_user()
    patient = user.patient_profile

    data = request.get_json(silent=True) or {}

    appointment_id = data.get('appointment_id')
    rating = data.get('rating')
    tags = data.get('tags', [])
    comment = data.get('comment', '').strip()
    if len(comment) < 5:
        return jsonify({'success': False, 'error': 'Please add a short written comment (at least 5 characters) with your rating.'}), 400

    if not appointment_id or not rating:
        return jsonify({'success': False, 'error': 'appointment_id and rating are required.'}), 400

    try:
        rating = int(rating)
        if not (1 <= rating <= 5):
            raise ValueError
    except (TypeError, ValueError):
        return jsonify({'success': False, 'error': 'rating must be an integer 1–5.'}), 400

    appointment = Appointment.query.filter_by(
        id=appointment_id,
        patient_id=patient.id
    ).first()

    if not appointment:
        return jsonify({'success': False, 'error': 'Appointment not found.'}), 404

    if not appointment.can_review:
        return jsonify({'success': False, 'error': 'You can only review appointments that are still in the review window.'}), 400

    if appointment.review:
        return jsonify({'success': False, 'error': 'You have already reviewed this appointment.'}), 409

    client_ip = get_client_ip()
    ip_hash = hash_ip(client_ip)
    geo_city, geo_region = lookup_geo(client_ip)
    flag_reasons, fraud_status, should_hide = evaluate_review_fraud(
        ip_hash,
        patient.id,
        appointment.doctor_id,
        comment,
    )

    review = Review(
        appointment_id=appointment.id,
        patient_id=patient.id,
        doctor_id=appointment.doctor_id,
        rating=rating,
        tags=tags if isinstance(tags, list) else [],
        comment=comment or None,
        is_visible=not should_hide,
        submitter_ip_hash=ip_hash or None,
        geo_city=geo_city,
        geo_region=geo_region,
        flag_reasons=flag_reasons,
        fraud_status=fraud_status,
    )
    db.session.add(review)

    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500

    if should_hide:
        return jsonify({
            'success': True,
            'message': 'Thank you. Your review was received and is pending a quick trust check before it appears publicly.',
            'pending_moderation': True,
        }), 201

    return jsonify({'success': True, 'message': 'Review submitted. Thank you!'}), 201


@reviews_bp.route('/check/<int:appointment_id>', methods=['GET'])
@patient_required
def check_review(appointment_id):
    """Returns whether this patient has already reviewed the given appointment."""
    user = get_current_user()
    patient = user.patient_profile

    appointment = Appointment.query.filter_by(
        id=appointment_id,
        patient_id=patient.id
    ).first()

    if not appointment:
        return jsonify({'has_review': False}), 404

    return jsonify({'has_review': bool(appointment.review)})
