"""Prescription unlock rules (mutual video time)."""
from __future__ import annotations

from typing import Any

from app.utils.timezone import pkt_now_naive

# Must match video.check_unlock logic (seconds of mutual connection).
MIN_MUTUAL_VIDEO_SECONDS = 180


def try_unlock_prescription_from_mutual_video(appointment: Any) -> bool:
    """
    If both sides had a mutual video window recorded and it lasted long enough,
    set prescription_unlocked on the appointment object.

    Returns True if prescription_unlocked is True after this call (already was, or newly set).
    Returns False if the 3-minute bar was not met or mutual_call_start is missing.
    """
    if getattr(appointment, "prescription_unlocked", False):
        return True
    start = getattr(appointment, "mutual_call_start", None)
    if not start:
        return False
    # mutual_call_start is stored as Pakistan local naive time (pkt_now_naive)
    elapsed = (pkt_now_naive() - start).total_seconds()
    if elapsed >= MIN_MUTUAL_VIDEO_SECONDS:
        appointment.prescription_unlocked = True
        return True
    return False
