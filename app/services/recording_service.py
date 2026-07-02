"""
Video call recording service using Agora Cloud Recording.
Recording starts on mutual connection (both doctor + patient) and stops when either leaves.
HLS output (.m3u8) is uploaded to S3-compatible storage (DigitalOcean Spaces, vendor 11).
"""
import base64
import time
import requests
from datetime import datetime
from flask import current_app
from app import db
from app.models import Appointment, VideoCallRecording

RECORDER_UID = 999999
DEFAULT_AGORA_API_BASE = 'https://api.sd-rtn.com/v1/apps'


def _agora_api_base() -> str:
    """Agora REST base URL (sd-rtn.com works when api.agora.io is blocked on the host)."""
    return (current_app.config.get('AGORA_API_BASE') or DEFAULT_AGORA_API_BASE).rstrip('/')


# Back-compat for diagnostics scripts
AGORA_API_BASE = DEFAULT_AGORA_API_BASE
AGORA_POST_RETRIES = 3
# After doctor starts the call, wait before server-side backup (avoids empty channel)
MEDIA_SETTLE_SECONDS = 8


def _agora_post(url, body, timeout=15):
    """POST to Agora Cloud Recording API with retries on transient network/DNS errors."""
    last_err = None
    for attempt in range(AGORA_POST_RETRIES):
        try:
            return requests.post(url, json=body, headers=_auth_header(), timeout=timeout)
        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as exc:
            last_err = exc
            if attempt + 1 < AGORA_POST_RETRIES:
                time.sleep(1.5 * (attempt + 1))
    raise last_err


def _is_enabled():
    """Check if recording is enabled and Agora + storage credentials are present."""
    if not current_app.config.get('AGORA_ENABLE_RECORDING'):
        return False
    cid = current_app.config.get('AGORA_CUSTOMER_ID', '').strip()
    secret = current_app.config.get('AGORA_CUSTOMER_SECRET', '').strip()
    bucket = current_app.config.get('AGORA_RECORDING_STORAGE_BUCKET', '').strip()
    access_key = current_app.config.get('AGORA_RECORDING_STORAGE_ACCESS_KEY', '').strip()
    secret_key = current_app.config.get('AGORA_RECORDING_STORAGE_SECRET_KEY', '').strip()
    if not cid or not secret or not bucket or not access_key or not secret_key:
        return False
    vendor = int(current_app.config.get('AGORA_RECORDING_STORAGE_VENDOR', 1))
    if vendor == 11:
        endpoint = (
            current_app.config.get('AGORA_RECORDING_STORAGE_ENDPOINT')
            or current_app.config.get('DO_SPACES_ENDPOINT', '')
        ).strip()
        if not endpoint:
            return False
    return True


def _auth_header():
    cid = current_app.config.get('AGORA_CUSTOMER_ID', '')
    secret = current_app.config.get('AGORA_CUSTOMER_SECRET', '')
    creds = base64.b64encode(f'{cid}:{secret}'.encode()).decode()
    return {'Authorization': f'Basic {creds}'}


def _get_recorder_token(appointment_id):
    from agora_token_builder import RtcTokenBuilder
    app_id = current_app.config.get('AGORA_APP_ID')
    cert = current_app.config.get('AGORA_APP_CERTIFICATE')
    if not app_id or not cert:
        return None
    channel = f'appointment_{appointment_id}'
    privilege_ts = int(time.time()) + 86400
    return RtcTokenBuilder.buildTokenWithUid(
        app_id, cert, channel, RECORDER_UID, 1, privilege_ts
    )


def _build_storage_config(appointment_id):
    """Agora storageConfig — vendor 11 + extensionParams for DigitalOcean Spaces."""
    vendor = int(current_app.config.get('AGORA_RECORDING_STORAGE_VENDOR', 1))
    storage = {
        'vendor': vendor,
        'region': int(current_app.config.get('AGORA_RECORDING_STORAGE_REGION', 0)),
        'bucket': current_app.config.get('AGORA_RECORDING_STORAGE_BUCKET'),
        'accessKey': current_app.config.get('AGORA_RECORDING_STORAGE_ACCESS_KEY'),
        'secretKey': current_app.config.get('AGORA_RECORDING_STORAGE_SECRET_KEY'),
        'fileNamePrefix': [
            current_app.config.get('AGORA_RECORDING_FILE_PREFIX', 'recordings'),
            f'appt_{appointment_id}',
        ],
    }
    if vendor == 11:
        endpoint = (
            current_app.config.get('AGORA_RECORDING_STORAGE_ENDPOINT')
            or current_app.config.get('DO_SPACES_ENDPOINT', '')
        ).strip().rstrip('/')
        if endpoint.startswith('https://'):
            endpoint = endpoint[len('https://'):]
        elif endpoint.startswith('http://'):
            endpoint = endpoint[len('http://'):]
        if endpoint:
            storage['extensionParams'] = {'endpoint': endpoint}
    return storage


def _normalize_file_list(raw_list):
    """Flatten Agora stop response fileList into a list of filename strings."""
    if not raw_list:
        return []
    if isinstance(raw_list, dict):
        inner = raw_list.get('fileList') or raw_list.get('filename')
        if inner is None:
            single = raw_list.get('filename')
            return [single] if single else []
        raw_list = inner
    if not isinstance(raw_list, list):
        raw_list = [raw_list]

    names = []
    for item in raw_list:
        if isinstance(item, dict):
            name = item.get('filename') or item.get('fileName') or item.get('file_name')
            if name:
                names.append(str(name))
        elif item:
            names.append(str(item))
    return names


def _pick_playlist_key(filenames):
    """Prefer .m3u8 playlist key; fall back to first file."""
    for name in filenames:
        if name.lower().endswith('.m3u8'):
            return name
    return filenames[0] if filenames else None


def _build_recording_config(appointment):
    """
    Landscape composite layout similar to the live video call UI:
    doctor full screen + patient picture-in-picture (bottom-left).
    Without transcodingConfig Agora defaults to a tall/portrait canvas (narrow strip).
    """
    doctor_uid = str(appointment.doctor.user_id)
    patient_uid = str(appointment.patient.user_id)
    return {
        'channelType': 0,
        'streamTypes': 2,
        'transcodingConfig': {
            'width': 1280,
            'height': 720,
            'fps': 15,
            'bitrate': 1500,
            'mixedVideoLayout': 3,
            'backgroundColor': '#000000',
            'layoutConfig': [
                {
                    'uid': doctor_uid,
                    'x_axis': 0.0,
                    'y_axis': 0.0,
                    'width': 1.0,
                    'height': 1.0,
                    'alpha': 1.0,
                    'render_mode': 1,
                },
                {
                    'uid': patient_uid,
                    'x_axis': 0.02,
                    'y_axis': 0.68,
                    'width': 0.26,
                    'height': 0.26,
                    'alpha': 1.0,
                    'render_mode': 1,
                },
            ],
        },
    }


def _recording_preconditions(appointment):
    """True only when the live call has started (not waiting room) and both joined."""
    if not appointment:
        return False
    if appointment.appointment_type != 'video':
        return False
    if not appointment.is_call_active:
        return False
    if not (appointment.doctor_joined_video and appointment.patient_joined_video):
        return False
    return True


def maybe_start_recording(appointment_id, *, from_client=False):
    """
    Start recording when safe. Client triggers (after publish/remote video) skip the
    settle delay; server backup (poll) waits MEDIA_SETTLE_SECONDS after call_started_at
    so we never record an empty waiting-room channel (old 435 bug).
    """
    if not _is_enabled():
        return False

    appointment = Appointment.query.get(appointment_id)
    if not _recording_preconditions(appointment):
        return False

    if not from_client:
        started = getattr(appointment, 'call_started_at', None)
        if not started:
            return False
        from app.utils.timezone import pkt_now_naive
        if (pkt_now_naive() - started).total_seconds() < MEDIA_SETTLE_SECONDS:
            return False

    try_start_recording(appointment_id)
    active = VideoCallRecording.query.filter_by(
        appointment_id=appointment_id, status='recording'
    ).first()
    return active is not None


def try_start_recording(appointment_id):
    if not _is_enabled():
        return

    try:
        appointment = Appointment.query.get(appointment_id)
        if not appointment:
            return
        if not _recording_preconditions(appointment):
            return
        active = VideoCallRecording.query.filter_by(
            appointment_id=appointment_id, status='recording'
        ).first()
        if active:
            return

        app_id = current_app.config.get('AGORA_APP_ID')
        channel = f'appointment_{appointment_id}'
        token = _get_recorder_token(appointment_id)
        if not token:
            current_app.logger.warning('Recording: missing token for appt %s', appointment_id)
            return

        storage = _build_storage_config(appointment_id)

        acquire_url = f'{_agora_api_base()}/{app_id}/cloud_recording/acquire'
        acquire_body = {
            'cname': channel,
            'uid': str(RECORDER_UID),
            'clientRequest': {},
        }
        r = _agora_post(acquire_url, acquire_body, timeout=15)
        if r.status_code != 200:
            current_app.logger.warning('Recording acquire failed for appt %s: %s', appointment_id, r.text)
            return
        resource_id = r.json().get('resourceId')
        if not resource_id:
            return

        start_url = f'{_agora_api_base()}/{app_id}/cloud_recording/resourceid/{resource_id}/mode/mix/start'
        start_body = {
            'cname': channel,
            'uid': str(RECORDER_UID),
            'clientRequest': {
                'token': token,
                'storageConfig': storage,
                'recordingConfig': _build_recording_config(appointment),
                'recordingFileConfig': {'avFileType': ['hls']},
            },
        }
        r2 = _agora_post(start_url, start_body, timeout=20)
        if r2.status_code != 200:
            current_app.logger.warning('Recording start failed for appt %s: %s', appointment_id, r2.text)
            return
        sid = r2.json().get('sid')
        if not sid:
            return

        rec = VideoCallRecording(
            appointment_id=appointment_id,
            agora_resource_id=resource_id,
            agora_sid=sid,
            status='recording',
        )
        db.session.add(rec)
        db.session.commit()
        current_app.logger.info('Recording started for appointment %s sid=%s', appointment_id, sid)
    except Exception as e:
        current_app.logger.warning('Recording start error for appt %s: %s', appointment_id, str(e))


def stop_recording(appointment_id):
    if not _is_enabled():
        return

    try:
        active = VideoCallRecording.query.filter_by(
            appointment_id=appointment_id, status='recording'
        ).first()
        if not active:
            return

        app_id = current_app.config.get('AGORA_APP_ID')
        channel = f'appointment_{appointment_id}'
        stop_url = (
            f'{_agora_api_base()}/{app_id}/cloud_recording/resourceid/{active.agora_resource_id}'
            f'/sid/{active.agora_sid}/mode/mix/stop'
        )
        stop_body = {
            'uid': str(RECORDER_UID),
            'cname': channel,
            'clientRequest': {},
        }
        r = _agora_post(stop_url, stop_body, timeout=20)
        active.status = 'stopping'
        active.ended_at = datetime.utcnow()
        if active.started_at and active.ended_at:
            active.duration_seconds = max(
                0, int((active.ended_at - active.started_at).total_seconds())
            )
        if r.status_code == 200:
            data = r.json()
            resource = data.get('serverResponse') or data.get('resource') or {}
            flist = resource.get('fileList') or data.get('fileList') or []
            filenames = _normalize_file_list(flist)
            playlist_key = _pick_playlist_key(filenames)
            if playlist_key:
                active.file_path = playlist_key
                active.file_url = None  # private bucket — presign at playback time
            active.status = 'ready'
            db.session.commit()
            current_app.logger.info(
                'Recording stopped for appointment %s key=%s', appointment_id, playlist_key
            )
        else:
            err_text = (r.text or '').strip()
            err_code = None
            try:
                err_json = r.json()
                err_code = err_json.get('code')
                err_text = err_json.get('reason') or err_text
            except Exception:
                pass
            if err_code == 435 or 'no recorded data' in err_text.lower():
                active.status = 'empty'
                active.error_message = err_text or 'no recorded data'
            else:
                active.status = 'failed'
                active.error_message = (err_text or f'HTTP {r.status_code}')[:500]
            db.session.commit()
            current_app.logger.warning(
                'Recording stop for appt %s: status=%s code=%s %s',
                appointment_id, active.status, err_code, err_text,
            )
    except Exception as e:
        db.session.rollback()
        current_app.logger.warning('Recording stop error for appt %s: %s', appointment_id, str(e))


def get_recordings_for_appointment(appointment_id):
    return VideoCallRecording.query.filter_by(appointment_id=appointment_id).order_by(
        VideoCallRecording.started_at.desc()
    ).all()
