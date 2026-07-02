"""Review fraud signals: IP hashing, geo hint, and rule-based flags."""
from __future__ import annotations

import hashlib
import json
import re
import urllib.request
from datetime import timedelta
from typing import List, Optional, Tuple

from flask import current_app, request

from app.database import db
from app.models import Review
from app.utils.timezone import pkt_now_naive

# Human-readable labels for admin UI
FLAG_REASON_LABELS = {
    'ip_repeat_doctor': 'Same network already reviewed this doctor recently',
    'ip_burst_doctor': 'Too many reviews for this doctor from one network (48h)',
    'ip_multi_account': 'Multiple patient accounts using the same network',
    'duplicate_comment': 'Very similar review text from the same network',
}

FRAUD_STATUS_LABELS = {
    'clear': 'Clear',
    'flagged': 'Flagged — hidden pending review',
    'blocked': 'Blocked — hidden (high risk)',
}


def get_client_ip() -> str:
    """Best-effort client IP (supports nginx X-Forwarded-For)."""
    forwarded = (request.headers.get('X-Forwarded-For') or '').strip()
    if forwarded:
        return forwarded.split(',')[0].strip()
    real_ip = (request.headers.get('X-Real-IP') or '').strip()
    if real_ip:
        return real_ip
    return request.remote_addr or ''


def hash_ip(ip: str) -> str:
    """One-way hash; raw IP is not stored."""
    if not ip:
        return ''
    secret = current_app.config.get('SECRET_KEY') or 'review-ip-salt'
    return hashlib.sha256(f'{secret}:review-ip:{ip}'.encode()).hexdigest()


def _is_private_ip(ip: str) -> bool:
    if not ip:
        return True
    if ip in ('127.0.0.1', '::1', 'localhost'):
        return True
    if ip.startswith('192.168.') or ip.startswith('10.') or ip.startswith('172.'):
        return True
    return False


def lookup_geo(ip: str) -> Tuple[Optional[str], Optional[str]]:
    """City/region from public IP (best effort; no extra packages)."""
    if _is_private_ip(ip):
        return None, None
    try:
        url = f'http://ip-api.com/json/{ip}?fields=status,city,regionName'
        with urllib.request.urlopen(url, timeout=2.5) as resp:
            data = json.loads(resp.read().decode('utf-8'))
        if data.get('status') == 'success':
            return data.get('city') or None, data.get('regionName') or None
    except Exception:
        pass
    return None, None


def _normalize_comment(text: Optional[str]) -> str:
    if not text:
        return ''
    t = text.lower().strip()
    t = re.sub(r'\s+', ' ', t)
    return t[:200]


def evaluate_review_fraud(
    ip_hash: str,
    patient_id: int,
    doctor_id: int,
    comment: Optional[str] = None,
) -> Tuple[List[str], str, bool]:
    """
    Returns (flag_reasons, fraud_status, should_hide).
    should_hide=True → review not public until admin approves.
    """
    flags: List[str] = []
    if not ip_hash:
        return flags, 'clear', False

    now = pkt_now_naive()
    thirty_days_ago = now - timedelta(days=30)
    forty_eight_hours_ago = now - timedelta(hours=48)
    ninety_days_ago = now - timedelta(days=90)

    same_doctor_recent = Review.query.filter(
        Review.submitter_ip_hash == ip_hash,
        Review.doctor_id == doctor_id,
        Review.created_at >= thirty_days_ago,
    ).count()
    if same_doctor_recent >= 1:
        flags.append('ip_repeat_doctor')

    burst_count = Review.query.filter(
        Review.submitter_ip_hash == ip_hash,
        Review.doctor_id == doctor_id,
        Review.created_at >= forty_eight_hours_ago,
    ).count()
    if burst_count >= 2:
        flags.append('ip_burst_doctor')

    prior_patient_rows = (
        db.session.query(Review.patient_id)
        .filter(
            Review.submitter_ip_hash == ip_hash,
            Review.created_at >= ninety_days_ago,
        )
        .distinct()
        .all()
    )
    patient_ids = {row[0] for row in prior_patient_rows}
    patient_ids.add(patient_id)
    if len(patient_ids) >= 3:
        flags.append('ip_multi_account')

    norm = _normalize_comment(comment)
    if norm and len(norm) >= 12:
        recent_same_ip = Review.query.filter(
            Review.submitter_ip_hash == ip_hash,
            Review.created_at >= ninety_days_ago,
        ).all()
        for other in recent_same_ip:
            other_norm = _normalize_comment(other.comment)
            if other_norm and other_norm == norm:
                flags.append('duplicate_comment')
                break

    if not flags:
        return flags, 'clear', False

    fraud_status = 'flagged'
    should_hide = True

    if 'ip_multi_account' in flags and len(patient_ids) >= 4:
        fraud_status = 'blocked'
    if 'ip_burst_doctor' in flags and burst_count >= 4:
        fraud_status = 'blocked'

    return flags, fraud_status, should_hide


def flag_reason_label(key: str) -> str:
    return FLAG_REASON_LABELS.get(key, key.replace('_', ' ').title())


def fraud_status_label(status: str) -> str:
    return FRAUD_STATUS_LABELS.get(status or 'clear', status or 'Clear')


def public_reviews_query():
    """Reviews safe to show on doctor profiles and rating averages."""
    return Review.query.filter(
        Review.is_visible.is_(True),
        db.or_(Review.fraud_status == 'clear', Review.fraud_status.is_(None)),
    )
