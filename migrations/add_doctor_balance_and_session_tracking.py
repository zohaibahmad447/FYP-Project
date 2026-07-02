"""
Migration: Add doctor balance system and video session tracking
Adds:
- Doctor balance and earnings fields (balance, total_earned, total_withdrawn, total_penalties)
- DoctorTransaction table
- Appointment video session tracking fields (patient_joined_video, doctor_joined_video, etc.)
"""
import sqlite3
import os

def add_doctor_balance_and_session_tracking():
    """Add doctor balance system and video session tracking"""
    
    # Database path (using quickcare_dev.db)
    db_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'instance', 'quickcare_dev.db')
    
    if not os.path.exists(db_path):
        print(f"❌ Database not found at: {db_path}")
        return
    
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Step 1: Add doctor balance fields
        balance_fields = [
            ('balance', 'FLOAT DEFAULT 0.0'),
            ('total_earned', 'FLOAT DEFAULT 0.0'),
            ('total_withdrawn', 'FLOAT DEFAULT 0.0'),
            ('total_penalties', 'FLOAT DEFAULT 0.0')
        ]
        
        for field_name, field_type in balance_fields:
            try:
                cursor.execute(f"ALTER TABLE doctors ADD COLUMN {field_name} {field_type}")
                print(f"✓ Added {field_name} column to doctors")
            except sqlite3.OperationalError as e:
                if "duplicate column name" in str(e).lower():
                    print(f"✓ {field_name} column already exists")
                else:
                    raise
        
        # Step 2: Create doctor_transactions table
        try:
            cursor.execute("""
                CREATE TABLE doctor_transactions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    doctor_id INTEGER NOT NULL,
                    appointment_id INTEGER,
                    transaction_type VARCHAR(50) NOT NULL,
                    amount FLOAT NOT NULL,
                    description TEXT NOT NULL,
                    status VARCHAR(20) DEFAULT 'completed',
                    admin_notes TEXT,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (doctor_id) REFERENCES doctors(id),
                    FOREIGN KEY (appointment_id) REFERENCES appointments(id)
                )
            """)
            print("✓ Created doctor_transactions table")
        except sqlite3.OperationalError as e:
            if "already exists" in str(e).lower():
                print("✓ doctor_transactions table already exists")
            else:
                raise
        
        # Step 3: Add video session tracking fields to appointments
        session_fields = [
            ('patient_joined_video', 'BOOLEAN DEFAULT 0'),
            ('doctor_joined_video', 'BOOLEAN DEFAULT 0'),
            ('patient_joined_at', 'DATETIME'),
            ('doctor_joined_at', 'DATETIME')
        ]
        
        for field_name, field_type in session_fields:
            try:
                cursor.execute(f"ALTER TABLE appointments ADD COLUMN {field_name} {field_type}")
                print(f"✓ Added {field_name} column to appointments")
            except sqlite3.OperationalError as e:
                if "duplicate column name" in str(e).lower():
                    print(f"✓ {field_name} column already exists")
                else:
                    raise
        
        conn.commit()
        conn.close()
        
        print("\n✅ Migration completed successfully!")
        print("   - Doctor balance system ready")
        print("   - DoctorTransaction table created")
        print("   - Video session tracking enabled")
        
    except Exception as e:
        print(f"\n❌ Migration failed: {str(e)}")

if __name__ == '__main__':
    print("Starting migration: Adding doctor balance system and video session tracking...\n")
    add_doctor_balance_and_session_tracking()

