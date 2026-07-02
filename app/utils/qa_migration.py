"""One-time migration helpers for Q&A schema updates. Safe to run every startup."""
from sqlalchemy import text
from app.database import db


def ensure_qa_schema():
    """Add Q&A columns if missing. Ignores duplicate-column errors."""
    alter_columns = [
        ('answer_replies', 'photo_path', 'VARCHAR(255)'),
    ]

    with db.engine.connect() as conn:
        for table, column, col_type in alter_columns:
            try:
                conn.execute(text(f'ALTER TABLE {table} ADD COLUMN {column} {col_type}'))
                conn.commit()
            except Exception as exc:
                conn.rollback()
                error_text = str(exc).lower()
                if 'duplicate column' not in error_text and 'already exists' not in error_text:
                    raise