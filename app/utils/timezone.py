"""Timezone utility functions for Pakistan Standard Time (PKT)"""
from datetime import datetime, date, time
import pytz

# Pakistan timezone
PAKISTAN_TZ = pytz.timezone('Asia/Karachi')

def get_pakistan_now():
    """Get current datetime in Pakistan timezone"""
    return datetime.now(PAKISTAN_TZ)

def get_pakistan_today():
    """Get current date in Pakistan timezone"""
    return get_pakistan_now().date()

def get_pakistan_time():
    """Get current time in Pakistan timezone"""
    return get_pakistan_now().time()

def to_pakistan_time(dt):
    """Convert a datetime to Pakistan timezone (assumes UTC if naive)"""
    if dt.tzinfo is None:
        # Assume UTC if naive
        dt = pytz.utc.localize(dt)
    return dt.astimezone(PAKISTAN_TZ)

def pakistan_datetime(year, month, day, hour=0, minute=0, second=0):
    """Create a datetime in Pakistan timezone"""
    dt = datetime(year, month, day, hour, minute, second)
    return PAKISTAN_TZ.localize(dt)

def pakistan_date_from_string(date_string, format='%Y-%m-%d'):
    """Parse a date string and return date object (no timezone for date)"""
    return datetime.strptime(date_string, format).date()

def pakistan_time_from_string(time_string, format='%H:%M'):
    """Parse a time string and return time object"""
    return datetime.strptime(time_string, format).time()


def appointment_datetime_pkt(appointment_date, appointment_time):
    """Naive datetime for appointment slot (wall clock in Pakistan)."""
    return datetime.combine(appointment_date, appointment_time)


def pkt_now_naive():
    """Current Pakistan time as naive datetime (matches DB timestamp columns)."""
    return get_pakistan_now().replace(tzinfo=None)

