"""Create admin_panel_grants table; ensure existing admins are super."""
from sqlalchemy import text
from app.database import db


def ensure_admin_rbac_schema():
    with db.engine.connect() as conn:
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS admin_panel_grants (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                admin_id INTEGER NOT NULL,
                panel_key VARCHAR(50) NOT NULL,
                can_view BOOLEAN DEFAULT 1,
                can_create BOOLEAN DEFAULT 0,
                can_edit BOOLEAN DEFAULT 0,
                can_delete BOOLEAN DEFAULT 0,
                can_approve BOOLEAN DEFAULT 0,
                FOREIGN KEY(admin_id) REFERENCES admins(id) ON DELETE CASCADE,
                UNIQUE(admin_id, panel_key)
            )
        """))
        conn.commit()

        try:
            conn.execute(text("""
                UPDATE admins SET admin_level = 'super'
                WHERE admin_level IS NULL OR admin_level = '' OR admin_level = 'moderator'
            """))
            conn.commit()
        except Exception:
            conn.rollback()

        try:
            cols = [row[1] for row in conn.execute(text("PRAGMA table_info(admins)")).fetchall()]
            if 'staff_role' not in cols:
                conn.execute(text("ALTER TABLE admins ADD COLUMN staff_role VARCHAR(50)"))
                conn.commit()
        except Exception:
            conn.rollback()


def ensure_legacy_super_admins():
    """Create super Admin profiles for role=admin users missing from admins table."""
    with db.engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT u.id FROM users u
            LEFT JOIN admins a ON a.user_id = u.id
            WHERE u.role = 'admin' AND a.id IS NULL
        """)).fetchall()

        for (user_id,) in rows:
            conn.execute(
                text("""
                    INSERT INTO admins (user_id, admin_level, permissions, created_at)
                    VALUES (:uid, 'super', '{}', datetime('now'))
                """),
                {"uid": user_id},
            )

        conn.execute(text("""
            UPDATE admins SET admin_level = 'super'
            WHERE admin_level IS NULL OR admin_level = '' OR admin_level = 'moderator'
        """))
        conn.commit()


def migrate_legacy_staff_roles():
    """Merge retired role keys into current ones."""
    with db.engine.connect() as conn:
        conn.execute(text("""
            UPDATE admins SET staff_role = 'doctors_manager'
            WHERE staff_role IN ('doctors_accounts_manager', 'doctor_verification_officer')
        """))
        conn.execute(text("""
            UPDATE admins SET staff_role = 'accountant'
            WHERE staff_role = 'payment_officer'
        """))
        conn.commit()
