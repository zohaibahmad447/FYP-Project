from flask import Blueprint, render_template, request, flash, redirect, url_for
from app.models import Disease, Doctor
from app.database import db
from app.utils.categories import get_category_display_name, get_all_categories
from sqlalchemy import func

diseases_bp = Blueprint('diseases', __name__)

@diseases_bp.route('/')
def index():
    """Diseases information listing"""
    page = request.args.get('page', 1, type=int)
    category = request.args.get('category', 'all')
    search = request.args.get('search', '')
    
    query = Disease.query.filter_by(is_active=True)
    
    if category != 'all':
        query = query.filter_by(category=category)
    
    if search:
        query = query.filter(
            func.or_(
                Disease.name.ilike(f'%{search}%'),
                Disease.description.ilike(f'%{search}%'),
                Disease.symptoms.ilike(f'%{search}%')
            )
        )
    
    diseases = query.order_by(Disease.name.asc()).paginate(
        page=page, per_page=12, error_out=False
    )
    
    # Get categories for filter (with count)
    categories_with_count = db.session.query(
        Disease.category,
        func.count(Disease.id).label('count')
    ).filter_by(
        is_active=True
    ).group_by(Disease.category).all()
    
    return render_template('diseases/index.html',
                         diseases=diseases,
                         categories=categories_with_count,
                         current_category=category,
                         search=search)

@diseases_bp.route('/<int:disease_id>')
def view_disease(disease_id):
    """View individual disease information"""
    disease = Disease.query.filter_by(
        id=disease_id,
        is_active=True
    ).first_or_404()
    
    # Get related diseases in same category
    related_diseases = Disease.query.filter(
        Disease.category == disease.category,
        Disease.id != disease.id,
        Disease.is_active == True
    ).order_by(Disease.name.asc()).limit(5).all()
    
    # Get top doctors in this disease's category for the booking funnel
    from app.utils.categories import normalize_category
    disease_cat = normalize_category(disease.category)
    related_doctors = []
    if disease_cat:
        all_approved = Doctor.query.filter_by(is_approved=True, is_verified=True).all()
        for d in all_approved:
            if normalize_category(d.category).lower() == disease_cat.lower():
                related_doctors.append(d)
            if len(related_doctors) >= 3:
                break
    
    return render_template('diseases/view.html',
                         disease=disease,
                         related_diseases=related_diseases,
                         related_doctors=related_doctors)

@diseases_bp.route('/category/<category>')
def diseases_by_category(category):
    """View diseases by category"""
    diseases = Disease.query.filter_by(
        category=category,
        is_active=True
    ).order_by(Disease.name.asc()).all()
    
    return render_template('diseases/category.html',
                         diseases=diseases,
                         category=category)
