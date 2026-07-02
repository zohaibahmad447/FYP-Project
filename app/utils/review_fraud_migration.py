"""Add review fraud / IP tracking columns."""
from sqlalchemy import text
from app.database import db


def ensure_review_fraud_schema():
    columns = [
        ('reviews', 'submitter_ip_hash', 'VARCHAR(64)'),
        ('reviews', 'geo_city', 'VARCHAR(100)'),
        ('reviews', 'geo_region', 'VARCHAR(100)'),
        ('reviews', 'flag_reasons', 'TEXT'),
        ('reviews', 'fraud_status', "VARCHAR(20) DEFAULT 'clear'"),
    ]
    with db.engine.connect() as conn:
        for table, column, col_type in columns:
            try:
                conn.execute(text(f'ALTER TABLE {table} ADD COLUMN {column} {col_type}'))
                conn.commit()
            except Exception as exc:
                conn.rollback()
                err = str(exc).lower()
                if 'duplicate column' not in err and 'already exists' not in err:
                    raise

        try:
            conn.execute(text("""
                UPDATE reviews SET fraud_status = 'clear'
                WHERE fraud_status IS NULL OR fraud_status = ''
            """))
            conn.commit()
        except Exception:
            conn.rollback()
