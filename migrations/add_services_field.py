"""
Migration Script: Add services column to doctors table
Purpose: Stores comma-separated services/procedures offered (e.g. "Heart Failure Management, Angiography")
         to display as specialty pills on the doctor listing card (matching Marham-style).
Date: 2026-03-27
"""

import sqlite3
import os

# Database path (using quickcare_dev.db in instance folder)
DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'instance', 'quickcare_dev.db')

def migrate():
    """Add services column to doctors table"""

    if not os.path.exists(DB_PATH):
        print(f"❌ Database not found at: {DB_PATH}")
        return

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    print("Starting migration: Adding services column to doctors table...")

    try:
        # Check if column already exists
        cursor.execute("PRAGMA table_info(doctors)")
        columns = [column[1] for column in cursor.fetchall()]

        if 'services' in columns:
            print("✓ services column already exists — skipping")
        else:
            cursor.execute("""
                ALTER TABLE doctors
                ADD COLUMN services VARCHAR(500) NULL
            """)
            conn.commit()
            print("✓ services column added successfully")

        print("\n✅ Migration completed successfully!")
        print("Doctors can now enter their offered services separated by commas.")

    except sqlite3.Error as e:
        print(f"❌ Error during migration: {e}")
        conn.rollback()
    finally:
        conn.close()

if __name__ == '__main__':
    migrate()
