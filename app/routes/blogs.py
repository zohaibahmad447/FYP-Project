import re

from flask import Blueprint, render_template, request, flash, redirect, url_for
from app.models import Blog, Doctor
from app.database import db
from sqlalchemy import func

from app.utils.blog_covers import STRIP_INLINE_SLUGS, blog_static_image_path

blogs_bp = Blueprint('blogs', __name__)


def strip_inline_images(content: str) -> str:
    content = re.sub(r'<figure[^>]*>.*?<img\b[^>]*>.*?</figure>', '', content, flags=re.IGNORECASE | re.DOTALL)
    content = re.sub(r'<p[^>]*>\s*<img\b[^>]*>\s*</p>', '', content, flags=re.IGNORECASE | re.DOTALL)
    content = re.sub(r'<img\b[^>]*>', '', content, flags=re.IGNORECASE)
    return content

@blogs_bp.route('/')
def index():
    """Blog listing page"""
    from datetime import datetime
    now = datetime.utcnow()
    
    search = request.args.get('search', '').strip()
    page = request.args.get('page', 1, type=int)
    
    # Filter for published blogs that have already reached their publication date
    query = Blog.query.filter(
        Blog.status == 'published',
        Blog.published_at <= now
    )
    
    if search:
        query = query.filter(
            func.or_(
                Blog.title.ilike(f'%{search}%'),
                Blog.content.ilike(f'%{search}%'),
                Blog.tags.ilike(f'%{search}%'),
                Blog.category.ilike(f'%{search}%')
            )
        )
    
    blogs = query.order_by(Blog.published_at.desc()).paginate(
        page=page, per_page=6, error_out=False
    )

    # Top sidebar contributors: doctors with the most published articles (global, not current page only)
    contributor_rows = (
        db.session.query(Blog.doctor_id, func.count(Blog.id).label("cnt"))
        .filter(
            Blog.status == "published",
            Blog.published_at <= now,
        )
        .group_by(Blog.doctor_id)
        .order_by(func.count(Blog.id).desc())
        .limit(5)
        .all()
    )
    top_contributors = []
    for doctor_id, _cnt in contributor_rows:
        doctor = db.session.get(Doctor, doctor_id)
        if doctor is not None:
            top_contributors.append(doctor)

    return render_template(
        "blogs/index.html",
        blogs=blogs,
        search=search,
        top_contributors=top_contributors,
    )

@blogs_bp.route('/<int:blog_id>')
def view_blog(blog_id):
    """View individual blog post"""
    from datetime import datetime
    from flask import session
    from app.utils.auth import get_current_user
    
    now = datetime.utcnow()
    
    # We must start with a base query
    base_query = Blog.query.filter_by(id=blog_id)
    
    # Identify user context
    user = get_current_user() if 'user_id' in session else None
    
    # Bypass conditions: Admins can view all. Doctors can view their own.
    is_admin = user and user.role == 'admin'
    
    blog = base_query.first_or_404()
    is_author = user and user.role == 'doctor' and user.doctor_profile and user.doctor_profile.id == blog.doctor_id

    hero_static_path = blog_static_image_path(blog)

    # Enforce published strictness if they are neither the admin nor the author
    if not is_admin and not is_author:
        if blog.status != 'published' or (blog.published_at and blog.published_at > now):
            from werkzeug.exceptions import NotFound
            raise NotFound()
    
    render_content = blog.content
    if blog.slug in STRIP_INLINE_SLUGS:
        render_content = strip_inline_images(render_content)

    # Get related blogs by same doctor (strictly published ones only)
    related_blogs = Blog.query.filter(
        Blog.doctor_id == blog.doctor_id,
        Blog.id != blog.id,
        Blog.status == 'published',
        Blog.published_at <= now
    ).order_by(Blog.published_at.desc()).limit(3).all()
    
    return render_template(
        'blogs/view.html',
        blog=blog,
        related_blogs=related_blogs,
        render_content=render_content,
        hero_static_path=hero_static_path,
    )


