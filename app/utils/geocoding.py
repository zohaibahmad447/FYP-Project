"""Address geocoding via Geoapify (used for doctor practice maps)."""
from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Optional, Tuple


def geocode_address(
    address: str,
    api_key: str,
    *,
    country_code: str = 'pk',
) -> Tuple[Optional[float], Optional[float], Optional[str]]:
    """
    Resolve a free-text address to coordinates.

    Returns (lat, lon, formatted_label) or (None, None, None) on failure.
    """
    address = (address or '').strip()
    if not address or not api_key:
        return None, None, None

    params = urllib.parse.urlencode({
        'text': address,
        'apiKey': api_key,
        'limit': 1,
        'filter': f'countrycode:{country_code}',
    })
    url = f'https://api.geoapify.com/v1/geocode/search?{params}'

    try:
        with urllib.request.urlopen(url, timeout=8) as response:
            payload = json.loads(response.read().decode('utf-8'))
    except (urllib.error.URLError, json.JSONDecodeError, TimeoutError, ValueError):
        return None, None, None

    features = payload.get('features') or []
    if not features:
        return None, None, None

    props = features[0].get('properties') or {}
    lat = props.get('lat')
    lon = props.get('lon')
    if lat is None or lon is None:
        return None, None, None

    label = props.get('formatted') or address
    return float(lat), float(lon), label
