"""
Database migration script to add optional photo attachment support on answer replies.
"""

import os
import sqlite3


def get_db_path():
    project_root = os.path.dirname(os.path.dirname(__file__))

    # Prefer explicit local DB env overrides used by app config.
    db_uri = os.environ.get('DEV_DATABASE_URL') or os.environ.get('DATABASE_URL')
    if db_uri and db_uri.startswith('sqlite:///'):
        db_file = db_uri.replace('sqlite:///', '', 1)
        if not os.path.isabs(db_file):
            return os.path.join(project_root, 'instance', db_file)
        return db_file

    return os.path.join(project_root, 'instance', 'quickcare_dev.db')


def table_exists(cursor, table_name):
    cursor.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (table_name,)
    )
    return cursor.fetchone() is not None


def column_exists(cursor, table_name, column_name):
    cursor.execute(f"PRAGMA table_info({table_name})")
    columns = cursor.fetchall()
    return any(col[1] == column_name for col in columns)


def run_migration():
    db_path = get_db_path()
    if not os.path.exists(db_path):
        print(f"Database not found at: {db_path}")
        return

    conn = sqlite3.connect(db_path)
    try:
        cursor = conn.cursor()

        if not table_exists(cursor, 'answer_replies'):
            print('Table answer_replies not found. Run add_answer_replies migration first.')
            return

        if column_exists(cursor, 'answer_replies', 'photo_path'):
            print('- answer_replies.photo_path already exists')
        else:
            cursor.execute("ALTER TABLE answer_replies ADD COLUMN photo_path VARCHAR(255)")
            print('+ Added answer_replies.photo_path')

        conn.commit()
        print('\nMigration completed successfully.')
    except Exception as exc:
        conn.rollback()
        print(f"\nMigration failed: {exc}")
        raise
    finally:
        conn.close()


if __name__ == '__main__':
    print('Starting migration: add_answer_reply_photo')
    run_migration()
