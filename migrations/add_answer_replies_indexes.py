"""
Database migration script to add indexes to answer_replies table.
Improves query performance for lookups by answer_id and user_id.
"""

import os
import sqlite3


def get_db_path():
    return os.path.join(
        os.path.dirname(os.path.dirname(__file__)),
        'instance',
        'quickcare_dev.db'
    )


def index_exists(cursor, index_name):
    cursor.execute(
        "SELECT name FROM sqlite_master WHERE type='index' AND name=?",
        (index_name,)
    )
    return cursor.fetchone() is not None


def run_migration():
    db_path = get_db_path()
    if not os.path.exists(db_path):
        print(f"Database not found at: {db_path}")
        return

    conn = sqlite3.connect(db_path)
    try:
        cursor = conn.cursor()

        # Check and create index on answer_id
        if not index_exists(cursor, 'idx_answer_replies_answer'):
            cursor.execute(
                "CREATE INDEX idx_answer_replies_answer ON answer_replies(answer_id)"
            )
            print('+ Created index: idx_answer_replies_answer')
        else:
            print('- Index idx_answer_replies_answer already exists')

        # Check and create index on user_id
        if not index_exists(cursor, 'idx_answer_replies_user'):
            cursor.execute(
                "CREATE INDEX idx_answer_replies_user ON answer_replies(user_id)"
            )
            print('+ Created index: idx_answer_replies_user')
        else:
            print('- Index idx_answer_replies_user already exists')

        conn.commit()
        print('\nMigration completed successfully.')
    except Exception as exc:
        conn.rollback()
        print(f"\nMigration failed: {exc}")
        raise
    finally:
        conn.close()


if __name__ == '__main__':
    print('Starting migration: add_answer_replies_indexes')
    run_migration()
