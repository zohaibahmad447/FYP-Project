"""
Database migration script for Q&A answer replies.
Creates the answer_replies table for follow-up discussion threads.
"""

import os
import sqlite3


def get_db_path():
    return os.path.join(
        os.path.dirname(os.path.dirname(__file__)),
        'instance',
        'quickcare_dev.db'
    )


def table_exists(cursor, table_name):
    cursor.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (table_name,)
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

        if table_exists(cursor, 'answer_replies'):
            print('- answer_replies already exists')
            conn.commit()
            print('\nMigration completed successfully.')
            return

        cursor.execute(
            """
            CREATE TABLE answer_replies (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                answer_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                content TEXT NOT NULL,
                is_deleted BOOLEAN DEFAULT 0,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(answer_id) REFERENCES answers(id),
                FOREIGN KEY(user_id) REFERENCES users(id)
            )
            """
        )
        cursor.execute(
            "CREATE INDEX idx_answer_replies_answer ON answer_replies(answer_id)"
        )
        cursor.execute(
            "CREATE INDEX idx_answer_replies_user ON answer_replies(user_id)"
        )

        conn.commit()
        print('+ Created answer_replies table')
        print('\nMigration completed successfully.')
    except Exception as exc:
        conn.rollback()
        print(f"\nMigration failed: {exc}")
        raise
    finally:
        conn.close()


if __name__ == '__main__':
    print('Starting migration: add_answer_replies')
    run_migration()
