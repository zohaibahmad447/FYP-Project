"""Admin panel RBAC — panels, permissions, endpoint guards."""
from __future__ import annotations

from functools import wraps
from typing import Dict, Optional, Tuple

from flask import flash, redirect, request, url_for, jsonify

# Panel registry (assignable to staff; 'staff' is super-admin only)
ADMIN_PANELS: Dict[str, dict] = {
    'dashboard': {
        'label': 'Dashboard',
        'description': 'Overview stats and quick links',
        'icon': 'fa-tachometer-alt',
    },
    'doctors': {
        'label': 'Doctors',
        'description': 'Doctor approvals, appeals, suspensions',
        'icon': 'fa-user-md',
    },
    'patients': {
        'label': 'Patients',
        'description': 'Patient profiles and history',
        'icon': 'fa-users',
    },
    'appointments': {
        'label': 'Appointments',
        'description': 'Appointments and call recordings',
        'icon': 'fa-calendar-check',
    },
    'accounts': {
        'label': 'Accounts',
        'description': 'Refunds, payouts, financial overview',
        'icon': 'fa-chart-line',
    },
    'payments': {
        'label': 'Payment Approvals',
        'description': 'Manual payment screenshot review',
        'icon': 'fa-money-bill-wave',
    },
    'diseases': {
        'label': 'Diseases Info',
        'description': 'Disease content management',
        'icon': 'fa-info-circle',
    },
    'blogs': {
        'label': 'Blogs',
        'description': 'Blog moderation',
        'icon': 'fa-newspaper',
    },
    'qa': {
        'label': 'Q&A',
        'description': 'Community Q&A moderation',
        'icon': 'fa-question-circle',
    },
    'reviews': {
        'label': 'Reviews',
        'description': 'Patient review visibility',
        'icon': 'fa-star',
    },
}

PERMISSION_ACTIONS = {
    'view': 'View (read-only access)',
    'create': 'Create',
    'edit': 'Edit',
    'delete': 'Delete',
    'approve': 'Approve / reject actions',
}

# Predefined staff job roles (sub-admins are identified by role, not personal name)
STAFF_ROLES: Dict[str, dict] = {
    'accountant': {
        'label': 'Accountant',
        'description': 'Accounts, refunds, payouts, and payment approvals',
        'icon': 'fa-calculator',
        'accent': '#0ea5e9',
        'default_grants': {
            'accounts': {'view': True, 'approve': True},
            'payments': {'view': True, 'approve': True},
        },
    },
    'doctors_manager': {
        'label': 'Doctors Manager',
        'description': 'Doctor approvals, registrations, appeals, financials, and payouts',
        'icon': 'fa-user-md',
        'accent': '#10b981',
        'default_grants': {
            'doctors': {'view': True, 'approve': True},
            'accounts': {'view': True, 'edit': True, 'approve': True},
            'payments': {'view': True},
        },
    },
    'patient_support_manager': {
        'label': 'Patient Support Manager',
        'description': 'Patient profiles, history, and appointments',
        'icon': 'fa-hands-helping',
        'accent': '#f59e0b',
        'default_grants': {
            'patients': {'view': True, 'edit': True},
            'appointments': {'view': True},
        },
    },
    'appointment_coordinator': {
        'label': 'Appointment Coordinator',
        'description': 'Appointments and call recordings',
        'icon': 'fa-calendar-check',
        'accent': '#06b6d4',
        'default_grants': {
            'appointments': {'view': True, 'edit': True},
        },
    },
    'content_moderator': {
        'label': 'Content Moderator',
        'description': 'Blogs, Q&A, diseases, and reviews',
        'icon': 'fa-newspaper',
        'accent': '#ec4899',
        'default_grants': {
            'blogs': {'view': True, 'approve': True, 'delete': True},
            'qa': {'view': True, 'delete': True},
            'diseases': {'view': True, 'edit': True},
            'reviews': {'view': True, 'edit': True},
        },
    },
    'operations_viewer': {
        'label': 'Operations Viewer',
        'description': 'Read-only dashboard overview',
        'icon': 'fa-chart-pie',
        'accent': '#64748b',
        'default_grants': {
            'dashboard': {'view': True},
        },
    },
}


def get_staff_role_label(admin_profile) -> str:
    if not admin_profile:
        return 'Staff Admin'
    key = admin_profile.staff_role or ''
    legacy_labels = {
        'doctors_accounts_manager': 'Doctors Manager',
        'doctor_verification_officer': 'Doctors Manager',
        'payment_officer': 'Accountant',
    }
    if key in legacy_labels:
        return legacy_labels[key]
    meta = STAFF_ROLES.get(key)
    if meta:
        return meta['label']
    if admin_profile.user:
        return admin_profile.user.name
    return 'Staff Admin'


def staff_role_default_grants_json() -> dict:
    """For form JS — suggested panels per role."""
    out = {}
    for key, meta in STAFF_ROLES.items():
        out[key] = meta.get('default_grants', {})
    return out


def validate_staff_role(role_key: str) -> bool:
    return bool(role_key and role_key in STAFF_ROLES)

ENDPOINT_PERMISSIONS: Dict[str, Tuple[str, str]] = {
    'admin.dashboard': ('dashboard', 'view'),
    'admin.suspended_doctors': ('doctors', 'view'),
    'admin.doctors': ('doctors', 'view'),
    'admin.view_doctor_details': ('doctors', 'view'),
    'admin.get_doctor_details_json': ('doctors', 'view'),
    'admin.approve_doctor': ('doctors', 'approve'),
    'admin.reject_doctor': ('doctors', 'approve'),
    'admin.process_appeal': ('doctors', 'approve'),
    'admin.appeals': ('doctors', 'view'),
    'admin.rejected_doctors': ('doctors', 'view'),
    'admin.patients': ('patients', 'view'),
    'admin.view_patient': ('patients', 'view'),
    'admin.view_patient_appointments': ('patients', 'view'),
    'admin.view_patient_medical_history': ('patients', 'view'),
    'admin.appointments': ('appointments', 'view'),
    'admin.appointment_recordings': ('appointments', 'view'),
    'admin.recording_watch': ('appointments', 'view'),
    'admin.recording_download': ('appointments', 'view'),
    'admin.recording_hls_asset': ('appointments', 'view'),
    'admin.recording_hls_segment': ('appointments', 'view'),
    'admin.payments': ('payments', 'view'),
    'admin.approve_payment': ('payments', 'approve'),
    'admin.reject_payment': ('payments', 'approve'),
    'admin.approve_disputed_payment': ('payments', 'approve'),
    'admin.reject_disputed_payment': ('payments', 'approve'),
    'admin.accounts': ('accounts', 'view'),
    'admin.accounts_payment_flow': ('accounts', 'view'),
    'admin.accounts_refunds': ('accounts', 'view'),
    'admin.refund_mark_processed': ('accounts', 'approve'),
    'admin.accounts_payouts': ('accounts', 'view'),
    'admin.payout_approve': ('accounts', 'approve'),
    'admin.payout_reject': ('accounts', 'approve'),
    'admin.doctor_financials': ('accounts', 'view'),
    'admin.diseases': ('diseases', 'view'),
    'admin.add_disease': ('diseases', 'create'),
    'admin.edit_disease': ('diseases', 'edit'),
    'admin.delete_disease': ('diseases', 'delete'),
    'admin.blogs': ('blogs', 'view'),
    'admin.delete_blog': ('blogs', 'delete'),
    'admin.approve_blog': ('blogs', 'approve'),
    'admin.reject_blog': ('blogs', 'approve'),
    'admin.qa': ('qa', 'view'),
    'admin.delete_question': ('qa', 'delete'),
    'admin.delete_answer': ('qa', 'delete'),
    'admin.reviews': ('reviews', 'view'),
    'admin.toggle_review_visibility': ('reviews', 'edit'),
    'admin.approve_review': ('reviews', 'approve'),
    'admin.reject_review': ('reviews', 'approve'),
}


def get_admin_profile(user):
    if not user or user.role != 'admin':
        return None
    return user.admin_profile


def is_super_admin(user) -> bool:
    if not user or user.role != 'admin':
        return False
    profile = get_admin_profile(user)
    # Legacy admins (role=admin, no profile row) are treated as super admin
    if not profile:
        return True
    level = (profile.admin_level or 'super').strip().lower()
    return level != 'staff'


def _grant_map(admin_profile) -> dict:
    if not admin_profile:
        return {}
    return {g.panel_key: g for g in admin_profile.panel_grants}


def has_panel_permission(user, panel_key: str, action: str = 'view') -> bool:
    if not user or user.role != 'admin':
        return False
    if is_super_admin(user):
        return True
    grant = _grant_map(user.admin_profile).get(panel_key)
    if not grant or not grant.can_view:
        return False
    if action == 'view':
        return True
    return bool(getattr(grant, f'can_{action}', False))


def admin_can(user, panel_key: str, action: str = 'view') -> bool:
    return has_panel_permission(user, panel_key, action)


def get_accessible_panel_keys(user) -> list:
    if is_super_admin(user):
        return list(ADMIN_PANELS.keys())
    grants = user.admin_profile.panel_grants if user and user.admin_profile else []
    return [g.panel_key for g in grants if g.can_view and g.panel_key in ADMIN_PANELS]


def get_admin_landing_endpoint(user) -> str:
    """First page a sub-admin should see after login."""
    if is_super_admin(user):
        return 'admin.dashboard'
    for key in ADMIN_PANELS:
        if has_panel_permission(user, key, 'view'):
            if key == 'dashboard':
                return 'admin.dashboard'
            if key == 'doctors':
                return 'admin.doctors'
            if key == 'patients':
                return 'admin.patients'
            if key == 'appointments':
                return 'admin.appointments'
            if key == 'accounts':
                return 'admin.accounts'
            if key == 'payments':
                return 'admin.payments'
            if key == 'diseases':
                return 'admin.diseases'
            if key == 'blogs':
                return 'admin.blogs'
            if key == 'qa':
                return 'admin.qa'
            if key == 'reviews':
                return 'admin.reviews'
    return 'admin.no_access'


def super_admin_required(f):
    """Only super admin (staff management, etc.)."""
    @wraps(f)
    def wrapped(*args, **kwargs):
        from app.utils.auth import get_current_user

        user = get_current_user()
        if not user or not is_super_admin(user):
            flash('Only the super administrator can access this section.', 'error')
            if user and user.role == 'admin':
                return redirect(url_for(get_admin_landing_endpoint(user)))
            return redirect(url_for('home.index'))
        return f(*args, **kwargs)
    return wrapped


def _is_ajax_request() -> bool:
    return (
        request.headers.get('X-Requested-With') == 'XMLHttpRequest'
        or request.headers.get('Content-Type') == 'application/json'
        or request.is_json
        or (request.path or '').endswith('-json')
    )


def register_admin_rbac(admin_bp):
    """Attach before_request guard to admin blueprint."""

    @admin_bp.before_request
    def enforce_admin_panel_permissions():
        from app.utils.auth import get_current_user

        endpoint = request.endpoint or ''
        if not endpoint.startswith('admin.'):
            return None

        # Staff management — super admin only
        if endpoint.startswith('admin.staff_'):
            user = get_current_user()
            if not user or not is_super_admin(user):
                if _is_ajax_request():
                    return jsonify({'error': 'Super admin required'}), 403
                flash('Only the super administrator can manage staff.', 'error')
                if user and user.role == 'admin':
                    return redirect(url_for(get_admin_landing_endpoint(user)))
                return redirect(url_for('home.index'))
            return None

        user = get_current_user()
        if not user or user.role != 'admin':
            return None  # admin_required on route handles login

        if is_super_admin(user):
            return None

        if endpoint == 'admin.no_access':
            return None

        spec = ENDPOINT_PERMISSIONS.get(endpoint)
        if not spec:
            if _is_ajax_request():
                return jsonify({'error': 'Permission denied'}), 403
            flash('You do not have permission to access this admin area.', 'error')
            return redirect(url_for(get_admin_landing_endpoint(user)))

        panel_key, action = spec
        if has_panel_permission(user, panel_key, action):
            return None

        if _is_ajax_request():
            return jsonify({'error': 'Permission denied'}), 403
        flash(f'You do not have permission for this action on {ADMIN_PANELS.get(panel_key, {}).get("label", panel_key)}.', 'error')
        return redirect(url_for(get_admin_landing_endpoint(user)))


def parse_panel_grants_from_form(form) -> list:
    """Build grant dicts from POST checkboxes panel_{key}_view etc."""
    grants = []
    for panel_key in ADMIN_PANELS:
        prefix = f'panel_{panel_key}_'
        if form.get(f'{prefix}assigned') != 'on':
            continue
        grants.append({
            'panel_key': panel_key,
            'can_view': form.get(f'{prefix}view') == 'on',
            'can_create': form.get(f'{prefix}create') == 'on',
            'can_edit': form.get(f'{prefix}edit') == 'on',
            'can_delete': form.get(f'{prefix}delete') == 'on',
            'can_approve': form.get(f'{prefix}approve') == 'on',
        })
    return grants


def save_panel_grants(admin_profile, grant_rows: list) -> None:
    from app.models import AdminPanelGrant
    from app.database import db

    AdminPanelGrant.query.filter_by(admin_id=admin_profile.id).delete()
    for row in grant_rows:
        if not row.get('can_view'):
            continue
        db.session.add(AdminPanelGrant(
            admin_id=admin_profile.id,
            panel_key=row['panel_key'],
            can_view=True,
            can_create=bool(row.get('can_create')),
            can_edit=bool(row.get('can_edit')),
            can_delete=bool(row.get('can_delete')),
            can_approve=bool(row.get('can_approve')),
        ))
