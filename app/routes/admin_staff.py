"""Staff admin user management (super admin only)."""
import json
import uuid

from flask import render_template, request, flash, redirect, url_for

from app.database import db
from app.models import User, Admin
from app.routes.admin import admin_bp
from app.utils.auth import admin_required
from app.utils.admin_permissions import (
    ADMIN_PANELS,
    PERMISSION_ACTIONS,
    STAFF_ROLES,
    get_staff_role_label,
    parse_panel_grants_from_form,
    save_panel_grants,
    staff_role_default_grants_json,
    super_admin_required,
    validate_staff_role,
)


def _unique_staff_cnic() -> str:
    for _ in range(20):
        candidate = f"9{uuid.uuid4().int % 10**12:012d}"
        if not User.query.filter_by(cnic=candidate).first():
            return candidate
    raise RuntimeError('Could not generate unique staff CNIC placeholder')


def _staff_admins_query():
    return (
        Admin.query.join(User)
        .filter(User.role == 'admin', Admin.admin_level == 'staff')
        .order_by(Admin.staff_role.asc(), User.email.asc())
    )


def _staff_form_context(staff, form_action, page_title):
    return dict(
        staff=staff,
        panels=ADMIN_PANELS,
        staff_roles=STAFF_ROLES,
        permission_actions=PERMISSION_ACTIONS,
        grant_map={g.panel_key: g for g in staff.panel_grants} if staff else {},
        role_defaults_json=json.dumps(staff_role_default_grants_json()),
        form_action=form_action,
        page_title=page_title,
        get_staff_role_label=get_staff_role_label,
    )


@admin_bp.route('/staff')
@admin_required
@super_admin_required
def staff_list():
    staff_rows = _staff_admins_query().all()
    active_count = sum(1 for row in staff_rows if row.user.is_active)
    return render_template(
        'admin/staff_list.html',
        staff_rows=staff_rows,
        panels=ADMIN_PANELS,
        staff_roles=STAFF_ROLES,
        get_staff_role_label=get_staff_role_label,
        stats={
            'total': len(staff_rows),
            'active': active_count,
            'inactive': len(staff_rows) - active_count,
        },
    )


@admin_bp.route('/staff/new', methods=['GET', 'POST'])
@admin_required
@super_admin_required
def staff_create():
    if request.method == 'POST':
        staff_role = (request.form.get('staff_role') or '').strip()
        email = (request.form.get('email') or '').strip().lower()
        password = request.form.get('password') or ''

        if not validate_staff_role(staff_role):
            flash('Please select a valid staff role.', 'warning')
            return redirect(url_for('admin.staff_create'))

        if not email or not password:
            flash('Email and password are required.', 'warning')
            return redirect(url_for('admin.staff_create'))

        if len(password) < 6:
            flash('Password must be at least 6 characters.', 'warning')
            return redirect(url_for('admin.staff_create'))

        if User.query.filter_by(email=email).first():
            flash('Email is already registered.', 'error')
            return redirect(url_for('admin.staff_create'))

        grant_rows = parse_panel_grants_from_form(request.form)
        if not grant_rows:
            flash('Assign at least one panel with view permission.', 'warning')
            return redirect(url_for('admin.staff_create'))

        role_label = STAFF_ROLES[staff_role]['label']
        user = User(
            name=role_label,
            email=email,
            phone='N/A',
            cnic=_unique_staff_cnic(),
            role='admin',
            is_active=True,
        )
        user.set_password(password)
        db.session.add(user)
        db.session.flush()

        admin_profile = Admin(user_id=user.id, admin_level='staff', staff_role=staff_role)
        db.session.add(admin_profile)
        db.session.flush()
        save_panel_grants(admin_profile, grant_rows)
        db.session.commit()

        flash(f'"{role_label}" account created successfully.', 'success')
        return redirect(url_for('admin.staff_list'))

    return render_template(
        'admin/staff_form.html',
        **_staff_form_context(None, url_for('admin.staff_create'), 'Create staff role'),
    )


@admin_bp.route('/staff/<int:admin_id>/edit', methods=['GET', 'POST'])
@admin_required
@super_admin_required
def staff_edit(admin_id):
    admin_profile = Admin.query.get_or_404(admin_id)
    if admin_profile.admin_level != 'staff':
        flash('Only staff accounts can be edited here.', 'warning')
        return redirect(url_for('admin.staff_list'))

    if request.method == 'POST':
        staff_role = (request.form.get('staff_role') or '').strip()
        password = request.form.get('password') or ''

        if not validate_staff_role(staff_role):
            flash('Please select a valid staff role.', 'warning')
            return redirect(url_for('admin.staff_edit', admin_id=admin_id))

        role_label = STAFF_ROLES[staff_role]['label']
        admin_profile.staff_role = staff_role
        admin_profile.user.name = role_label

        if password:
            if len(password) < 6:
                flash('Password must be at least 6 characters.', 'warning')
                return redirect(url_for('admin.staff_edit', admin_id=admin_id))
            admin_profile.user.set_password(password)

        grant_rows = parse_panel_grants_from_form(request.form)
        if not grant_rows:
            flash('Assign at least one panel with view permission.', 'warning')
            return redirect(url_for('admin.staff_edit', admin_id=admin_id))

        save_panel_grants(admin_profile, grant_rows)
        db.session.commit()
        flash('Staff role and permissions updated.', 'success')
        return redirect(url_for('admin.staff_list'))

    return render_template(
        'admin/staff_form.html',
        **_staff_form_context(
            admin_profile,
            url_for('admin.staff_edit', admin_id=admin_id),
            f'Edit — {get_staff_role_label(admin_profile)}',
        ),
    )


@admin_bp.route('/staff/<int:admin_id>/toggle-active', methods=['POST'])
@admin_required
@super_admin_required
def staff_toggle_active(admin_id):
    admin_profile = Admin.query.get_or_404(admin_id)
    if admin_profile.admin_level != 'staff':
        flash('Cannot change this account here.', 'warning')
        return redirect(url_for('admin.staff_list'))

    user = admin_profile.user
    user.is_active = not user.is_active
    db.session.commit()
    state = 'activated' if user.is_active else 'deactivated'
    flash(f'{get_staff_role_label(admin_profile)} account {state}.', 'info')
    return redirect(url_for('admin.staff_list'))
