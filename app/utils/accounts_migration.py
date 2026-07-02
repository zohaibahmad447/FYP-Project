"""One-time migration: add accounts columns to existing tables. Safe to run every startup."""
from sqlalchemy import text
from app.database import db


def ensure_accounts_schema():
    """Add accounts-related columns if missing. Ignores 'duplicate column' errors."""
    alter_columns = [
        ('appointments', 'platform_commission_percent', 'FLOAT DEFAULT 20.0'),
        ('appointments', 'platform_commission_amount', 'FLOAT'),
        ('appointments', 'doctor_earning_credited_at', 'DATETIME'),
        ('appointments', 'refund_policy_applied', 'VARCHAR(20)'),
        ('appointments', 'video_call_duration_seconds', 'INTEGER'),
        ('doctor_transactions', 'commission_deducted', 'FLOAT'),
    ]
    with db.engine.connect() as conn:
        for table, column, col_type in alter_columns:
            try:
                conn.execute(text(f'ALTER TABLE {table} ADD COLUMN {column} {col_type}'))
                conn.commit()
            except Exception as e:
                conn.rollback()
                if 'duplicate column' not in str(e).lower() and 'already exists' not in str(e).lower():
                    raise
