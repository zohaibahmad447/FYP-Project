"""
Database migration script for Q&A MVP enhancements.
Adds anonymous posting/view tracking fields and engagement tables.
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


def column_exists(cursor, table_name, column_name):
    cursor.execute(f"PRAGMA table_info({table_name})")
    columns = cursor.fetchall()
    return any(col[1] == column_name for col in columns)


def add_questions_columns(cursor):
    updates = [
        ('is_anonymous', "ALTER TABLE questions ADD COLUMN is_anonymous BOOLEAN DEFAULT 0"),
        ('view_count', "ALTER TABLE questions ADD COLUMN view_count INTEGER DEFAULT 0"),
        ('last_activity_at', "ALTER TABLE questions ADD COLUMN last_activity_at DATETIME"),
    ]

    for column_name, sql in updates:
        if column_exists(cursor, 'questions', column_name):
            print(f"- questions.{column_name} already exists")
            continue
        cursor.execute(sql)
        print(f"+ Added questions.{column_name}")


def create_question_bookmarks_table(cursor):
    if table_exists(cursor, 'question_bookmarks'):
        print('- question_bookmarks already exists')
        return

    cursor.execute(
        """
        CREATE TABLE question_bookmarks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            question_id INTEGER NOT NULL,
            patient_id INTEGER NOT NULL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            CONSTRAINT uq_question_bookmark_patient UNIQUE (question_id, patient_id),
            FOREIGN KEY(question_id) REFERENCES questions(id),
            FOREIGN KEY(patient_id) REFERENCES patients(id)
        )
        """
    )
    cursor.execute(
        "CREATE INDEX idx_question_bookmarks_question ON question_bookmarks(question_id)"
    )
    cursor.execute(
        "CREATE INDEX idx_question_bookmarks_patient ON question_bookmarks(patient_id)"
    )
    print('+ Created question_bookmarks table')


def create_answer_helpful_votes_table(cursor):
    if table_exists(cursor, 'answer_helpful_votes'):
        print('- answer_helpful_votes already exists')
        return

    cursor.execute(
        """
        CREATE TABLE answer_helpful_votes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            answer_id INTEGER NOT NULL,
            patient_id INTEGER NOT NULL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            CONSTRAINT uq_answer_helpful_vote_patient UNIQUE (answer_id, patient_id),
            FOREIGN KEY(answer_id) REFERENCES answers(id),
            FOREIGN KEY(patient_id) REFERENCES patients(id)
        )
        """
    )
    cursor.execute(
        "CREATE INDEX idx_answer_helpful_votes_answer ON answer_helpful_votes(answer_id)"
    )
    cursor.execute(
        "CREATE INDEX idx_answer_helpful_votes_patient ON answer_helpful_votes(patient_id)"
    )
    print('+ Created answer_helpful_votes table')


def backfill_last_activity(cursor):
    cursor.execute(
        """
        UPDATE questions
        SET last_activity_at = COALESCE(
            (
                SELECT MAX(a.created_at)
                FROM answers a
                WHERE a.question_id = questions.id AND a.is_deleted = 0
            ),
            created_at
        )
        WHERE last_activity_at IS NULL
        """
    )
    print('+ Backfilled questions.last_activity_at values')


def run_migration():
    db_path = get_db_path()
    if not os.path.exists(db_path):
        print(f"Database not found at: {db_path}")
        return

    conn = sqlite3.connect(db_path)
    try:
        cursor = conn.cursor()
        add_questions_columns(cursor)
        create_question_bookmarks_table(cursor)
        create_answer_helpful_votes_table(cursor)
        backfill_last_activity(cursor)
        conn.commit()
        print('\nMigration completed successfully.')
    except Exception as exc:
        conn.rollback()
        print(f"\nMigration failed: {exc}")
        raise
    finally:
        conn.close()


if __name__ == '__main__':
    print('Starting migration: add_qa_mvp_features')
    run_migration()
