"""
Migration Script: Add payment_deadline column to appointments table
Purpose: Implements dynamic payment timer system following industry standards
Date: 2026-02-14
"""

import sqlite3
import os
from datetime import datetime

# Database path (using quickcare_dev.db in instance folder)
DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'instance', 'quickcare_dev.db')

def migrate():
    """Add payment_deadline column to appointments table"""
    
    if not os.path.exists(DB_PATH):
        print(f"❌ Database not found at: {DB_PATH}")
        return
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    print("Starting migration: Adding payment_deadline column...")
    
    try:
        # Check if column already exists
        cursor.execute("PRAGMA table_info(appointments)")
        columns = [column[1] for column in cursor.fetchall()]
        
        if 'payment_deadline' in columns:
            print("✓ payment_deadline column already exists")
        else:
            # Add the column
            cursor.execute("""
                ALTER TABLE appointments 
                ADD COLUMN payment_deadline TIMESTAMP NULL
            """)
            conn.commit()
            print("✓ payment_deadline column added successfully")
        
        print("\n✅ Migration completed successfully!")
        print("\nNext steps:")
        print("1. Update approve_appointment() to calculate payment_deadline")
        print("2. Update upload_payment() to validate deadline")
        print("3. Add frontend countdown timer")
        
    except sqlite3.Error as e:
        print(f"❌ Error during migration: {e}")
        conn.rollback()
    finally:
        conn.close()

if __name__ == '__main__':
    migrate()
