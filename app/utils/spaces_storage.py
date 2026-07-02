"""DigitalOcean Spaces helpers — presigned URLs for private recording playback."""
from __future__ import annotations

from typing import Optional

import boto3
from botocore.config import Config
from flask import current_app


def _spaces_configured() -> bool:
    required = (
        'DO_SPACES_BUCKET',
        'DO_SPACES_ENDPOINT',
        'DO_SPACES_ACCESS_KEY',
        'DO_SPACES_SECRET_KEY',
    )
    return all((current_app.config.get(key) or '').strip() for key in required)


def get_spaces_client():
    """Build boto3 S3 client pointed at DO Spaces."""
    return boto3.client(
        's3',
        region_name=current_app.config.get('DO_SPACES_REGION') or 'us-east-1',
        endpoint_url=current_app.config.get('DO_SPACES_ENDPOINT', '').rstrip('/'),
        aws_access_key_id=current_app.config.get('DO_SPACES_ACCESS_KEY'),
        aws_secret_access_key=current_app.config.get('DO_SPACES_SECRET_KEY'),
        config=Config(
            signature_version='s3v4',
            connect_timeout=5,
            read_timeout=30,
            retries={'max_attempts': 2},
        ),
    )


def get_presigned_playback_url(object_key: Optional[str], expires: Optional[int] = None) -> Optional[str]:
    """
    Return a short-lived HTTPS URL for a private Spaces object (e.g. .m3u8 playlist).
    Returns None if Spaces is not configured or key is empty.
    """
    key = (object_key or '').strip().lstrip('/')
    if not key or not _spaces_configured():
        return None

    ttl = expires or int(current_app.config.get('DO_SPACES_PRESIGN_EXPIRES', 3600))
    bucket = current_app.config.get('DO_SPACES_BUCKET')

    try:
        return get_spaces_client().generate_presigned_url(
            ClientMethod='get_object',
            Params={'Bucket': bucket, 'Key': key},
            ExpiresIn=ttl,
        )
    except Exception as exc:
        current_app.logger.warning('Spaces presign failed for %s: %s', key, exc)
        return None


def is_hls_playlist(object_key: Optional[str]) -> bool:
    return bool(object_key) and str(object_key).lower().endswith('.m3u8')


def fetch_spaces_object(key: str) -> Optional[bytes]:
    """Download object bytes from Spaces; returns None on failure."""
    key = (key or '').strip().lstrip('/')
    if not key or not _spaces_configured():
        return None
    bucket = current_app.config.get('DO_SPACES_BUCKET')
    try:
        obj = get_spaces_client().get_object(Bucket=bucket, Key=key)
        return obj['Body'].read()
    except Exception as exc:
        current_app.logger.warning('Spaces get_object failed for %s: %s', key, exc)
        return None


def playlist_base_prefix(playlist_key: str) -> str:
    """Directory prefix for segment keys referenced in a playlist (e.g. recordings/appt_14/)."""
    key = playlist_key.strip().lstrip('/')
    if '/' not in key:
        return ''
    return key.rsplit('/', 1)[0] + '/'


def list_objects_under_prefix(prefix: str) -> list[str]:
    """List object keys in Spaces under a prefix (for HLS segment bundles)."""
    pref = (prefix or '').strip().lstrip('/')
    if not pref or not _spaces_configured():
        return []
    if not pref.endswith('/'):
        pref += '/'
    bucket = current_app.config.get('DO_SPACES_BUCKET')
    keys: list[str] = []
    try:
        client = get_spaces_client()
        paginator = client.get_paginator('list_objects_v2')
        for page in paginator.paginate(Bucket=bucket, Prefix=pref):
            for obj in page.get('Contents', []):
                key = (obj.get('Key') or '').strip()
                if key:
                    keys.append(key)
    except Exception as exc:
        current_app.logger.warning('Spaces list_objects failed for %s: %s', pref, exc)
    return keys


def list_recording_bundle_keys(playlist_key: str) -> list[str]:
    """Return the playlist and all sibling objects (e.g. .m3u8 + .ts segments)."""
    key = (playlist_key or '').strip().lstrip('/')
    if not key:
        return []
    prefix = playlist_base_prefix(key)
    if not prefix:
        return [key]
    keys = list_objects_under_prefix(prefix)
    if key not in keys:
        keys.append(key)
    return sorted(keys, key=lambda k: (0 if k.lower().endswith('.m3u8') else 1, k))


def build_hls_playlist_presigned(playlist_key: str, expires: Optional[int] = None) -> Optional[str]:
    """
    Rewrite an HLS playlist so each .ts segment line is a presigned Spaces URL.
    Browser loads segments directly from DO (avoids blocking the single gunicorn worker).
    """
    raw = fetch_spaces_object(playlist_key)
    if raw is None:
        return None
    base = playlist_base_prefix(playlist_key)
    lines = []
    for line in raw.decode('utf-8', errors='replace').splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith('#') and '.ts' in stripped:
            seg_name = stripped.split('/')[-1]
            seg_key = f'{base}{seg_name}'
            seg_url = get_presigned_playback_url(seg_key, expires=expires)
            if not seg_url:
                return None
            lines.append(seg_url)
        else:
            lines.append(line)
    return '\n'.join(lines) + '\n'


def ensure_spaces_cors() -> bool:
    """Allow browser HLS segment fetches from the app origin (idempotent)."""
    if not _spaces_configured():
        return False
    raw = (current_app.config.get('DO_SPACES_CORS_ORIGINS') or '').strip()
    if not raw:
        raw = 'https://quickcares.me,https://www.quickcares.me'
    origins = [o.strip() for o in raw.split(',') if o.strip()]
    bucket = current_app.config.get('DO_SPACES_BUCKET')
    try:
        get_spaces_client().put_bucket_cors(
            Bucket=bucket,
            CORSConfiguration={
                'CORSRules': [{
                    'AllowedHeaders': ['*'],
                    'AllowedMethods': ['GET', 'HEAD'],
                    'AllowedOrigins': origins,
                    'ExposeHeaders': ['ETag', 'Content-Length', 'Content-Type'],
                    'MaxAgeSeconds': 3600,
                }],
            },
        )
        return True
    except Exception as exc:
        current_app.logger.warning('Spaces CORS update failed: %s', exc)
        return False
