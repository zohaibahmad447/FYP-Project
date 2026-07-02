"""
Database migration script to add video call state persistence columns to appointments table.
This enables patients to join even if they missed the initial call start signal.
"""
import sqlite3
import os

def add_video_call_columns():
    """Add is_call_active and call_started_at columns to appointments table"""
    
    # Database path (using quickcare_dev.db)
    db_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'instance', 'quickcare_dev.db')
    
    if not os.path.exists(db_path):
        print(f"❌ Database not found at: {db_path}")
        return
    
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Add is_call_active column
        try:
            cursor.execute("ALTER TABLE appointments ADD COLUMN is_call_active BOOLEAN DEFAULT 0")
            print("✓ Added is_call_active column")
        except sqlite3.OperationalError as e:
            if "duplicate column name" in str(e).lower():
                print("✓ is_call_active column already exists")
            else:
                raise
        
        # Add call_started_at column
        try:
            cursor.execute("ALTER TABLE appointments ADD COLUMN call_started_at DATETIME")
            print("✓ Added call_started_at column")
        except sqlite3.OperationalError as e:
            if "duplicate column name" in str(e).lower():
                print("✓ call_started_at column already exists")
            else:
                raise
        
        conn.commit()
        conn.close()
        
        print("\n✅ Migration completed successfully!")
        
    except Exception as e:
        print(f"\n❌ Migration failed: {str(e)}")

if __name__ == '__main__':
    print("Starting migration: Adding video call state persistence columns...\n")
    add_video_call_columns()


if __name__ == '__main__':
    print("Starting migration: Adding video call state persistence columns...\n")
    add_video_call_columns()
