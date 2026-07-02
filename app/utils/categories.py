"""
Medical Categories Utility
Provides consistent medical category names and normalization functions
"""

# ── Premium PNG icon filenames (high-quality line-art icons) ──────────────────
# These are the 9 categories that have dedicated professional icon images.
CATEGORY_ICONS = {
    'Cardiology':          'cardiologist_icon_1773084402110.png',
    'Neurology':           'neurologist_icon_1773084421982.png',
    'Dermatology':         'dermatologist_icon_1773084390002.png',
    'Gynecology':          'gynecologist_icon_1773084347395.png',
    'Pediatrics':          'pediatrician_icon_1773084449308.png',
    'Gastroenterology':    'gastroenterologist_icon_1773084361627.png',
    'Dentistry':           'dentist_icon_1773084374573.png',
    'ENT':                 'ent_icon_1773084435709.png',
    'Urology':             'urologist_icon_1773084463058.png',
}

# ── Font Awesome fallback icons (professional medical style) ──────────────────
# Every category gets a relevant FA icon for when no PNG exists.
CATEGORY_FA_ICONS = {
    'Cardiology':              'fas fa-heartbeat',
    'Neurology':               'fas fa-brain',
    'Dermatology':             'fas fa-hand-sparkles',
    'Gynecology':              'fas fa-female',
    'Pediatrics':              'fas fa-baby',
    'Orthopedics':             'fas fa-bone',
    'Gastroenterology':        'fas fa-stomach',  # FA6 – falls back gracefully
    'Psychiatry':              'fas fa-comment-medical',
    'Psychology':              'fas fa-comment-medical',
    'General Medicine':        'fas fa-stethoscope',
    'Emergency Medicine':      'fas fa-ambulance',
    'Oncology':                'fas fa-ribbon',
    'Endocrinology':           'fas fa-vial',
    'Urology':                 'fas fa-kidneys',
    'Ophthalmology':           'fas fa-eye',
    'ENT':                     'fas fa-head-side-cough',
    'Pulmonology':             'fas fa-lungs',
    'Rheumatology':            'fas fa-bone',
    'Nephrology':              'fas fa-kidneys',
    'Hematology':              'fas fa-tint',
    'Anesthesiology':          'fas fa-syringe',
    'Radiology':               'fas fa-x-ray',
    'Pathology':               'fas fa-microscope',
    'Plastic Surgery':         'fas fa-cut',
    'Cardiac Surgery':         'fas fa-heart',
    'Neurosurgery':            'fas fa-brain',
    'Orthopedic Surgery':      'fas fa-bone',
    'General Surgery':         'fas fa-procedures',
    'Pediatric Surgery':       'fas fa-baby',
    'Sports Medicine':         'fas fa-running',
    'Family Medicine':         'fas fa-house-user',
    'Internal Medicine':       'fas fa-stethoscope',
    'Physical Medicine':       'fas fa-wheelchair',
    'Rehabilitation Medicine': 'fas fa-wheelchair',
    'Occupational Therapy':    'fas fa-hands-helping',
    'Physiotherapy':           'fas fa-walking',
    'Dentistry':               'fas fa-tooth',
    'Orthodontics':            'fas fa-tooth',
    'Periodontics':            'fas fa-tooth',
    'Endodontics':             'fas fa-tooth',
    'Prosthodontics':          'fas fa-tooth',
    'Oral and Maxillofacial Surgery': 'fas fa-tooth',
    'Cosmetic Dentistry':      'fas fa-tooth',
    'Dental Surgery':          'fas fa-tooth',
    'Veterinary Medicine':     'fas fa-paw',
    'Homeopathy':              'fas fa-leaf',
    'Alternative Medicine':    'fas fa-seedling',
    'Nutrition':               'fas fa-apple-alt',
    'Dietetics':               'fas fa-apple-alt',
    'Sexology':                'fas fa-heart',
    'Andrology':               'fas fa-male',
    'Infertility':             'fas fa-baby',
    'Maternal Fetal Medicine':  'fas fa-baby',
    'Neonatology':             'fas fa-baby',
    'Diabetology':             'fas fa-vial',
    'Hepatology':              'fas fa-liver',
    'Audiology':               'fas fa-deaf',
    'Speech Therapy':          'fas fa-comment-dots',
    'Chiropractic':            'fas fa-bone',
    'Acupuncture':             'fas fa-spa',
    'Hypnotherapy':            'fas fa-brain',
    'Hijama':                  'fas fa-tint',
    'Natural Medicine':        'fas fa-leaf',
    'Virology':                'fas fa-virus',
    'Pain Management':         'fas fa-band-aid',
    'Allergy and Immunology':  'fas fa-allergies',
    'Infectious Diseases':     'fas fa-virus',
    'Aesthetic Medicine':      'fas fa-magic',
    'Regenerative Medicine':   'fas fa-dna',
    'Bariatric Surgery':       'fas fa-weight',
    'Breast Surgery':          'fas fa-ribbon',
    'Cosmetic Surgery':        'fas fa-cut',
    'Laparoscopic Surgery':    'fas fa-procedures',
    'Spinal Surgery':          'fas fa-bone',
    'Thoracic Surgery':        'fas fa-lungs',
    'Trauma Surgery':          'fas fa-ambulance',
    'Vascular Surgery':        'fas fa-heartbeat',
    'Liver Transplant Surgery':'fas fa-procedures',
    'Hepatobiliary Surgery':   'fas fa-procedures',
    'Radiation Oncology':      'fas fa-radiation',
    'Medical Oncology':        'fas fa-ribbon',
    'Surgical Oncology':       'fas fa-ribbon',
    'Pediatric Oncology':      'fas fa-ribbon',
    'Reproductive Endocrinology': 'fas fa-baby',
    'Interventional Cardiology':  'fas fa-heartbeat',
    'Pediatric Gastroenterology': 'fas fa-baby',
    'Pediatric Cardiology':       'fas fa-baby',
    'Pediatric Neurology':        'fas fa-baby',
    'Pediatric Orthopedics':      'fas fa-baby',
    'Pediatric Radiology':        'fas fa-baby',
}

# ── Featured specialties (shown in marquee & dropdown) ────────────────────────
# These are the top categories displayed prominently on the landing page.
FEATURED_SPECIALTIES = [
    'Dermatology',
    'Cardiology',
    'Neurology',
    'ENT',
    'Pediatrics',
    'Urology',
    'Gynecology',
    'Gastroenterology',
    'Dentistry',
]

# ── Display categories (shown on Find Doctors page) ──────────────────────────
# Curated list of ~30 most common patient-facing specialties,
# based on Instacare, Marham, and other Pakistani telehealth platforms.
# Rare surgical subspecialties, lab-only fields, and duplicates are excluded.
DISPLAY_CATEGORIES = [
    'Cardiology',
    'Neurology',
    'Dermatology',
    'Gynecology',
    'Pediatrics',
    'Orthopedics',
    'Gastroenterology',
    'Psychiatry',
    'Psychology',
    'General Medicine',
    'Oncology',
    'Endocrinology',
    'Urology',
    'Ophthalmology',
    'ENT',
    'Pulmonology',
    'Nephrology',
    'Dentistry',
    'General Surgery',
    'Physiotherapy',
    'Nutrition',
    'Aesthetic Medicine',
    'Allergy and Immunology',
    'Diabetology',
    'Homeopathy',
    'Sexology',
    'Plastic Surgery',
    'Rheumatology',
    'Infectious Diseases',
    'Pain Management',
]

# Master list of medical categories (proper category names, not person names)
MEDICAL_CATEGORIES = [
    'Cardiology',
    'Neurology',
    'Dermatology',
    'Gynecology',
    'Pediatrics',
    'Orthopedics',
    'Gastroenterology',
    'Psychiatry',
    'General Medicine',
    'Emergency Medicine',
    'Oncology',
    'Endocrinology',
    'Urology',
    'Ophthalmology',
    'ENT',
    'Pulmonology',
    'Rheumatology',
    'Nephrology',
    'Hematology',
    'Anesthesiology',
    'Radiology',
    'Pathology',
    'Plastic Surgery',
    'Cardiac Surgery',
    'Neurosurgery',
    'Orthopedic Surgery',
    'General Surgery',
    'Pediatric Surgery',
    'Sports Medicine',
    'Family Medicine',
    'Internal Medicine',
    'Physical Medicine',
    'Rehabilitation Medicine',
    'Occupational Therapy',
    'Physiotherapy',
    'Dentistry',
    'Orthodontics',
    'Periodontics',
    'Endodontics',
    'Prosthodontics',
    'Oral and Maxillofacial Surgery',
    'Cosmetic Dentistry',
    'Dental Surgery',
    'Veterinary Medicine',
    'Homeopathy',
    'Alternative Medicine',
    'Nutrition',
    'Dietetics',
    'Psychology',
    'Sexology',
    'Andrology',
    'Infertility',
    'Maternal Fetal Medicine',
    'Neonatology',
    'Pediatric Gastroenterology',
    'Pediatric Cardiology',
    'Pediatric Neurology',
    'Pediatric Orthopedics',
    'Pediatric Radiology',
    'Interventional Cardiology',
    'Cardiac Surgery',
    'Thoracic Surgery',
    'Laparoscopic Surgery',
    'Bariatric Surgery',
    'Breast Surgery',
    'Spinal Surgery',
    'Trauma Surgery',
    'Vascular Surgery',
    'Liver Transplant Surgery',
    'Hepatobiliary Surgery',
    'Cosmetic Surgery',
    'Aesthetic Medicine',
    'Regenerative Medicine',
    'Pain Management',
    'Allergy and Immunology',
    'Infectious Diseases',
    'Reproductive Endocrinology',
    'Hepatology',
    'Diabetology',
    'Audiology',
    'Speech Therapy',
    'Chiropractic',
    'Acupuncture',
    'Hypnotherapy',
    'Hijama',
    'Natural Medicine',
    'Virology',
    'Hematology',
    'Oncology',
    'Radiation Oncology',
    'Medical Oncology',
    'Surgical Oncology',
    'Pediatric Oncology'
]

# Mapping from person names/specializations to category names
PERSON_TO_CATEGORY_MAP = {
    # Cardiology
    'cardiologist': 'Cardiology',
    'interventional cardiologist': 'Interventional Cardiology',
    'pediatric cardiologist': 'Pediatric Cardiology',
    'cardiac surgeon': 'Cardiac Surgery',
    
    # Neurology
    'neurologist': 'Neurology',
    'neurosurgeon': 'Neurosurgery',
    'pediatric neuro physician': 'Pediatric Neurology',
    
    # Dermatology
    'dermatologist': 'Dermatology',
    'dermatologist / laser specialist': 'Dermatology',
    
    # Gynecology
    'gynecologist': 'Gynecology',
    'obstetrician': 'Gynecology',
    'aesthetic gynecologist': 'Aesthetic Medicine',
    'infertility consultant': 'Infertility',
    'maternal fetal medicine specialist': 'Maternal Fetal Medicine',
    
    # Pediatrics
    'pediatrician': 'Pediatrics',
    'child specialist': 'Pediatrics',
    'neonatologist': 'Neonatology',
    'neonatologist pediatrician': 'Neonatology',
    'pediatric surgeon': 'Pediatric Surgery',
    'pediatric gastroenterologist': 'Pediatric Gastroenterology',
    'pediatric orthopedic surgeon': 'Pediatric Orthopedics',
    'pediatric radiologist': 'Pediatric Radiology',
    
    # Orthopedics
    'orthopedist': 'Orthopedics',
    'orthopedic surgeon': 'Orthopedic Surgery',
    'spinal surgeon': 'Spinal Surgery',
    
    # Gastroenterology
    'gastroenterologist': 'Gastroenterology',
    
    # Psychiatry
    'psychiatrist': 'Psychiatry',
    'psychologist': 'Psychology',
    
    # General Medicine
    'general physician': 'General Medicine',
    'general practitioner': 'General Medicine',
    'family physician': 'Family Medicine',
    'medical specialist': 'Internal Medicine',
    'internal medicine specialist': 'Internal Medicine',
    'medical officer': 'General Medicine',
    'physician': 'General Medicine',
    
    # Surgery
    'general surgeon': 'General Surgery',
    'plastic surgeon': 'Plastic Surgery',
    'laparoscopic surgeon': 'Laparoscopic Surgery',
    'general laparoscopic surgeon': 'Laparoscopic Surgery',
    'bariatric surgeon': 'Bariatric Surgery',
    'breast surgeon': 'Breast Surgery',
    'trauma surgeon': 'Trauma Surgery',
    'vascular surgeon': 'Vascular Surgery',
    'liver transplant surgeon': 'Liver Transplant Surgery',
    'hepatobiliary & liver transplant surgeon': 'Hepatobiliary Surgery',
    'cosmetic surgeon': 'Cosmetic Surgery',
    'thoracic surgeon': 'Thoracic Surgery',
    'lung surgeon': 'Thoracic Surgery',
    
    # Urology
    'urologist': 'Urology',
    'endourologist': 'Urology',
    'andrologist': 'Andrology',
    
    # Ophthalmology
    'eye specialist': 'Ophthalmology',
    'eye surgeon': 'Ophthalmology',
    'ophthalmologist': 'Ophthalmology',
    
    # ENT
    'ent specialist': 'ENT',
    'ent surgeon': 'ENT',
    
    # Pulmonology
    'pulmonologist': 'Pulmonology',
    'chest specialist': 'Pulmonology',
    'chest respiratory specialist': 'Pulmonology',
    
    # Other specialties
    'endocrinologist': 'Endocrinology',
    'diabetologist': 'Diabetology',
    'oncologist': 'Oncology',
    'rheumatologist': 'Rheumatology',
    'nephrologist': 'Nephrology',
    'hepatologist': 'Hepatology',
    'liver specialist': 'Hepatology',
    'hematologist': 'Hematology',
    'anesthesiologist': 'Anesthesiology',
    'anesthetic': 'Anesthesiology',
    'anesthesia': 'Anesthesiology',
    'radiologist': 'Radiology',
    'sonologist': 'Radiology',
    'pathologist': 'Pathology',
    'virologist': 'Virology',
    'allergy specialist': 'Allergy and Immunology',
    'infectious disease specialist': 'Infectious Diseases',
    'reproductive endocrinologist': 'Reproductive Endocrinology',
    
    # Dentistry
    'dentist': 'Dentistry',
    'dental surgeon': 'Dental Surgery',
    'orthodontist': 'Orthodontics',
    'periodontist': 'Periodontics',
    'endodontist': 'Endodontics',
    'prosthodontist': 'Prosthodontics',
    'oral and maxillofacial surgeon': 'Oral and Maxillofacial Surgery',
    'cosmetic dentistry': 'Cosmetic Dentistry',
    
    # Other
    'physiotherapist': 'Physiotherapy',
    'occupational therapist': 'Occupational Therapy',
    'speech therapist': 'Speech Therapy',
    'audiologist': 'Audiology',
    'dietitian': 'Dietetics',
    'nutritionist': 'Nutrition',
    'chiropractor': 'Chiropractic',
    'acupuncturist': 'Acupuncture',
    'hypnotherapist': 'Hypnotherapy',
    'hijama specialist': 'Hijama',
    'herbalist': 'Alternative Medicine',
    'homeopathy': 'Homeopathy',
    'veterinary doctor': 'Veterinary Medicine',
    'doctor of natural medicine': 'Natural Medicine',
    'orthotist & prosthetist': 'Physical Medicine',
    'rehabilitation medicine': 'Rehabilitation Medicine',
    'sports medicine': 'Sports Medicine',
    'aesthetic medicine specialist': 'Aesthetic Medicine',
    'aesthetic physician': 'Aesthetic Medicine',
    'regenerative medicine': 'Regenerative Medicine',
    'pain management specialist': 'Pain Management',
    'sexologist': 'Sexology',
    'cosmetologist': 'Aesthetic Medicine',
    'eft specialist': 'Alternative Medicine',
    'fitness': 'Sports Medicine',
    'pharmacist': 'General Medicine'
}


def normalize_category(category_input):
    """
    Normalize a category input (person name or specialization) to a proper category name.
    
    Args:
        category_input: String input that could be a person name (e.g., 'Cardiologist') 
                       or category name (e.g., 'Cardiology')
    
    Returns:
        Normalized category name (e.g., 'Cardiology')
    """
    if not category_input:
        return ''
    
    # Strip and convert to lowercase for matching
    input_lower = category_input.strip().lower()
    
    # First, check if it's already a valid category name
    for category in MEDICAL_CATEGORIES:
        if category.lower() == input_lower:
            return category
    
    # Check if it's a person name that needs mapping
    if input_lower in PERSON_TO_CATEGORY_MAP:
        return PERSON_TO_CATEGORY_MAP[input_lower]
    
    # Try partial matching for person names
    for person_name, category in PERSON_TO_CATEGORY_MAP.items():
        if person_name in input_lower or input_lower in person_name:
            return category
    
    # If no match found, try to convert common patterns
    # Remove common suffixes and convert to category format
    input_clean = input_lower
    
    # Remove common person suffixes
    for suffix in ['ist', 'ian', 'ologist', 'surgeon', 'specialist', 'physician', 'doctor']:
        if input_clean.endswith(suffix):
            input_clean = input_clean[:-len(suffix)].strip()
            break
    
    # Capitalize and check if it matches a category
    category_candidate = input_clean.title()
    for category in MEDICAL_CATEGORIES:
        if category.lower() == category_candidate.lower():
            return category
    
    # If still no match, return the input with proper capitalization
    # This allows for new categories to be added
    return category_input.strip().title()


def get_all_categories():
    """Get all available medical categories"""
    return sorted(MEDICAL_CATEGORIES)


def get_category_display_name(category):
    """Get a display-friendly name for a category"""
    normalized = normalize_category(category)
    return normalized if normalized else category


def is_valid_category(category):
    """Check if a category is valid"""
    normalized = normalize_category(category)
    return normalized in MEDICAL_CATEGORIES or normalized.lower() in [c.lower() for c in MEDICAL_CATEGORIES]


def get_category_icon(category):
    """
    Get icon info for a category.
    Returns dict with 'png' (filename or None) and 'fa' (Font Awesome class).
    """
    normalized = normalize_category(category)
    return {
        'png': CATEGORY_ICONS.get(normalized),
        'fa':  CATEGORY_FA_ICONS.get(normalized, 'fas fa-user-md'),
    }


def get_featured_specialties():
    """Get featured specialties with their icon info for marquee/dropdown."""
    result = []
    for cat in FEATURED_SPECIALTIES:
        result.append({
            'name': cat,
            'slug': normalize_category(cat).lower(),
            'png':  CATEGORY_ICONS.get(cat),
            'fa':   CATEGORY_FA_ICONS.get(cat, 'fas fa-user-md'),
        })
    return result
