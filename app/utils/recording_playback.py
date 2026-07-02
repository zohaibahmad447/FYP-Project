"""Short-lived signed tokens for admin HLS playback (no session cookie per segment)."""
from __future__ import annotations

from typing import Optional

from flask import current_app
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

PLAYBACK_SALT = 'quickcare-recording-playback'
DEFAULT_MAX_AGE = 3600


def _serializer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(
        current_app.config['SECRET_KEY'],
        salt=PLAYBACK_SALT,
    )


def make_playback_token(recording_id: int, max_age: Optional[int] = None) -> str:
  ttl = max_age or int(current_app.config.get('DO_SPACES_PRESIGN_EXPIRES', DEFAULT_MAX_AGE))
  return _serializer().dumps({'rid': int(recording_id), 'ttl': ttl})


def verify_playback_token(recording_id: int, token: Optional[str], max_age: Optional[int] = None) -> bool:
    if not token:
        return False
    try:
        data = _serializer().loads(
            token,
            max_age=max_age or int(current_app.config.get('DO_SPACES_PRESIGN_EXPIRES', DEFAULT_MAX_AGE)),
        )
        return int(data.get('rid', -1)) == int(recording_id)
    except (BadSignature, SignatureExpired, TypeError, ValueError):
        return False
