"""Utility functions to organize practice schedules by hospital/clinic"""


def organize_by_practice(time_slots):
    """
    Organize time slots by practice/hospital/clinic.
    
    Args:
        time_slots: Dictionary with day names as keys and day configs as values
    
    Returns:
        Dictionary organized by practice name:
        {
            "Hospital Name": {
                "location": "Area, City",
                "physical_price": 1200,
                "video_price": 1000,
                "days": {
                    "monday": {"start_time": "09:00", "end_time": "17:00", "duration": 30},
                    ...
                }
            },
            ...
        }
    """
    practices = {}
    
    if not time_slots:
        return practices
    
    for day, day_config in time_slots.items():
        if not isinstance(day_config, dict) or 'start_time' not in day_config:
            continue
        
        hospital = day_config.get('hospital', '').strip() or 'Default Practice'
        location = day_config.get('location', '').strip()
        
        if hospital not in practices:
            practices[hospital] = {
                'location': location,
                'physical_price': day_config.get('physical_price'),
                'video_price': day_config.get('video_price'),
                'days': {}
            }
        
        # Add day to this practice
        practices[hospital]['days'][day] = {
            'start_time': day_config.get('start_time'),
            'end_time': day_config.get('end_time'),
            'duration': day_config.get('duration', 30)
        }
        
        # Update location and prices if not already set
        if location and not practices[hospital]['location']:
            practices[hospital]['location'] = location
        if day_config.get('physical_price') and not practices[hospital]['physical_price']:
            practices[hospital]['physical_price'] = day_config.get('physical_price')
        if day_config.get('video_price') and not practices[hospital]['video_price']:
            practices[hospital]['video_price'] = day_config.get('video_price')
    
    return practices


def convert_practices_to_time_slots(practices):
    """
    Convert practices structure back to time_slots structure.
    
    Args:
        practices: Dictionary organized by practice name
    
    Returns:
        Dictionary with day names as keys (time_slots format)
    """
    time_slots = {}
    
    for practice_name, practice_data in practices.items():
        location = practice_data.get('location', '')
        physical_price = practice_data.get('physical_price')
        video_price = practice_data.get('video_price')
        days = practice_data.get('days', {})
        
        for day, day_config in days.items():
            time_slots[day] = {
                'start_time': day_config.get('start_time'),
                'end_time': day_config.get('end_time'),
                'duration': day_config.get('duration', 30),
                'hospital': practice_name
            }
            
            if location:
                time_slots[day]['location'] = location
            if physical_price:
                time_slots[day]['physical_price'] = physical_price
            if video_price:
                time_slots[day]['video_price'] = video_price
    
    return time_slots

