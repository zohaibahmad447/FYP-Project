"""Utility functions for generating time slots from time ranges"""
from datetime import datetime, timedelta, date
from app.utils.timezone import get_pakistan_today, get_pakistan_time

# Standard gap between bookable appointment times (minutes)
APPOINTMENT_SLOT_INTERVAL_MINUTES = 30

# Only paid, active appointments reserve a slot for other patients
SLOT_RESERVATION_STATUSES = (
    'pending',
    'approved',
    'completed',
    'completed_pending_review',
    'disputed',
)


def find_reserved_appointment(doctor_id, appointment_date, appointment_time, exclude_appointment_id=None):
    """
    Return an appointment that currently holds this slot.
    Unpaid bookings do not reserve the slot until payment is approved.
    """
    from app.models import Appointment

    query = Appointment.query.filter(
        Appointment.doctor_id == doctor_id,
        Appointment.appointment_date == appointment_date,
        Appointment.appointment_time == appointment_time,
        Appointment.payment_status == 'approved',
        Appointment.status.in_(SLOT_RESERVATION_STATUSES),
    )
    if exclude_appointment_id is not None:
        query = query.filter(Appointment.id != exclude_appointment_id)
    return query.first()


def slot_is_reserved(doctor_id, appointment_date, appointment_time, exclude_appointment_id=None):
    return find_reserved_appointment(
        doctor_id, appointment_date, appointment_time, exclude_appointment_id
    ) is not None


def generate_slots_from_range(start_time_str, end_time_str, duration_minutes):
    """
    Generate time slots from a time range and duration.
    
    Args:
        start_time_str: Start time in 'HH:MM' format (e.g., '09:00')
        end_time_str: End time in 'HH:MM' format (e.g., '17:00')
        duration_minutes: Duration of each slot in minutes (e.g., 30)
    
    Returns:
        List of time strings in 'HH:MM' format
    """
    try:
        # Parse start and end times
        start_time = datetime.strptime(start_time_str, '%H:%M').time()
        end_time = datetime.strptime(end_time_str, '%H:%M').time()
        
        # Convert to datetime for easier calculation
        start_datetime = datetime.combine(datetime.today(), start_time)
        end_datetime = datetime.combine(datetime.today(), end_time)
        
        # Handle case where end time is next day (e.g., 23:00 to 01:00)
        if end_datetime <= start_datetime:
            end_datetime += timedelta(days=1)
        
        slots = []
        current_time = start_datetime
        
        # Generate slots until we reach or exceed end time
        while current_time < end_datetime:
            # Check if adding duration would exceed end time
            next_time = current_time + timedelta(minutes=duration_minutes)
            if next_time > end_datetime:
                break
            
            slots.append(current_time.strftime('%H:%M'))
            current_time = next_time
        
        return slots
    
    except (ValueError, TypeError) as e:
        print(f"Error generating slots: {e}")
        return []


def get_slot_info(doctor_time_slots, day_name, slot_time):
    """
    Get hospital and price information for a specific slot.
    
    Args:
        doctor_time_slots: Doctor's time_slots JSON structure
        day_name: Day of week (e.g., 'monday')
        slot_time: Slot time in 'HH:MM' format
    
    Returns:
        Dict with hospital, physical_price, video_price, or None if not found
    """
    if not doctor_time_slots or day_name not in doctor_time_slots:
        return None
    
    day_config = doctor_time_slots[day_name]
    
    # Handle new structure (time range based)
    if isinstance(day_config, dict) and 'start_time' in day_config:
        # Check if slot_time falls within the time range
        start_time_str = day_config.get('start_time', '')
        end_time_str = day_config.get('end_time', '')
        duration = day_config.get('duration', 30)
        
        # Generate slots to check if our slot is valid
        generated_slots = generate_slots_from_range(start_time_str, end_time_str, duration)
        
        if slot_time in generated_slots:
            return {
                'hospital': day_config.get('hospital', ''),
                'physical_price': day_config.get('physical_price'),
                'video_price': day_config.get('video_price'),
                'duration': duration
            }
    
    # Handle old structure (list of individual slots) for backwards compatibility
    elif isinstance(day_config, list):
        for slot in day_config:
            if isinstance(slot, dict) and slot.get('time') == slot_time:
                return {
                    'hospital': slot.get('hospital', ''),
                    'physical_price': slot.get('physical_price'),
                    'video_price': slot.get('video_price')
                }
            elif slot == slot_time:
                return {
                    'hospital': '',
                    'physical_price': None,
                    'video_price': None
                }
    
    return None


def find_next_available_date(doctor_time_slots, doctor_id, appointment_type='physical', start_date=None, max_days=60):
    """
    Find the next available appointment date for a doctor.
    
    Args:
        doctor_time_slots: Doctor's time_slots JSON structure
        doctor_id: Doctor ID to check existing appointments
        appointment_type: 'physical' or 'video' (for filtering slots if needed)
        start_date: Date to start searching from (default: today)
        max_days: Maximum days to search ahead (default: 60)
    
    Returns:
        Date object for next available appointment, or None if none found
    """
    if not doctor_time_slots:
        return None
    
    from app.models import Appointment
    
    if start_date is None:
        start_date = get_pakistan_today()
    
    current_date = start_date
    end_date = start_date + timedelta(days=max_days)
    current_time = get_pakistan_time()
    
    # Check up to max_days ahead
    while current_date <= end_date:
        day_name = current_date.strftime('%A').lower()
        
        # Check if doctor has slots for this day
        if day_name in doctor_time_slots:
            day_config = doctor_time_slots[day_name]
            
            # Get available slots for this day
            available_slots = []
            
            # Handle new structure (time range based)
            if isinstance(day_config, dict) and 'start_time' in day_config:
                start_time_str = day_config.get('start_time', '')
                end_time_str = day_config.get('end_time', '')
                duration = day_config.get('duration', 30)
                
                generated_slots = generate_slots_from_range(start_time_str, end_time_str, duration)
                
                for slot_time_str in generated_slots:
                    try:
                        slot_time_obj = datetime.strptime(slot_time_str, '%H:%M').time()
                    except (ValueError, TypeError):
                        continue
                    
                    # For today, skip slots that have already passed
                    if current_date == get_pakistan_today():
                        if slot_time_obj <= current_time:
                            continue
                    
                    # Check if this slot is already booked
                    existing_appointment = find_reserved_appointment(
                        doctor_id, current_date, slot_time_obj
                    )
                    
                    if not existing_appointment:
                        available_slots.append(slot_time_obj)
            
            # Handle old structure (list of individual slots)
            elif isinstance(day_config, list):
                for time_slot in day_config:
                    if isinstance(time_slot, dict):
                        slot_time = time_slot.get('time', '')
                    else:
                        slot_time = time_slot
                    
                    try:
                        slot_time_obj = datetime.strptime(slot_time, '%H:%M').time()
                    except (ValueError, TypeError):
                        continue
                    
                    # For today, skip slots that have already passed
                    if current_date == get_pakistan_today():
                        if slot_time_obj <= current_time:
                            continue
                    
                    # Check if this slot is already booked
                    existing_appointment = find_reserved_appointment(
                        doctor_id, current_date, slot_time_obj
                    )
                    
                    if not existing_appointment:
                        available_slots.append(slot_time_obj)
            
            # If we found available slots for this day, return the date
            if available_slots:
                return current_date
        
        # Move to next day
        current_date += timedelta(days=1)
    
    return None
