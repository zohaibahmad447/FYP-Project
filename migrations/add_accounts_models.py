"""
Migration: Add accounts models and appointment columns.
Run with: python migrations/add_accounts_models.py
Do NOT start the Flask app (scheduler would query DB before columns exist).
"""
import os
import sys
import sqlite3

# Use dev database path (same as config)
BASE = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
raw = os.environ.get('DEV_DATABASE_URL') or 'sqlite:///quickcare_dev.db'
if raw.startswith('sqlite:///'):
    DB_PATH = os.path.join(BASE, raw.replace('sqlite:///', '').lstrip('/'))
else:
    print("Set DEV_DATABASE_URL to sqlite:/// path or run ALTER manually.")
    sys.exit(1)

def run_migration():
    path = DB_PATH
    if not os.path.exists(path):
        alt = os.path.join(BASE, 'quickcare.db')
        if os.path.exists(alt):
            path = alt
            print("Using", path)
        else:
            print("DB not found at", DB_PATH, "or", alt, "- run the app once to create it, then run this migration.")
            return
    conn = sqlite3.connect(path)
    cur = conn.cursor()
    # New tables are created by db.create_all() when app runs; we only add columns here
    for table, column, col_type in [
        ('appointments', 'platform_commission_percent', 'FLOAT DEFAULT 20.0'),
        ('appointments', 'platform_commission_amount', 'FLOAT'),
        ('appointments', 'doctor_earning_credited_at', 'DATETIME'),
        ('appointments', 'refund_policy_applied', 'VARCHAR(20)'),
        ('appointments', 'video_call_duration_seconds', 'INTEGER'),
        ('doctor_transactions', 'commission_deducted', 'FLOAT'),
    ]:
        try:
            cur.execute(f"ALTER TABLE {table} ADD COLUMN {column} {col_type}")
            conn.commit()
            print(f"  Added {table}.{column}")
        except sqlite3.OperationalError as e:
            if 'duplicate column' in str(e).lower():
                print(f"  {table}.{column} already exists")
            else:
                print(f"  Skip {table}.{column}: {e}")
    # Create new tables if not exist (simple CREATE TABLE for SQLite)
    for name, sql in [
        ('platform_revenues', '''CREATE TABLE IF NOT EXISTS platform_revenues (
            id INTEGER PRIMARY KEY,
            appointment_id INTEGER,
            amount FLOAT NOT NULL,
            source VARCHAR(50) NOT NULL,
            created_at DATETIME,
            FOREIGN KEY(appointment_id) REFERENCES appointments(id)
        )'''),
        ('refunds', '''CREATE TABLE IF NOT EXISTS refunds (
            id INTEGER PRIMARY KEY,
            appointment_id INTEGER NOT NULL,
            patient_id INTEGER NOT NULL,
            amount FLOAT NOT NULL,
            reason VARCHAR(50) NOT NULL,
            status VARCHAR(20) DEFAULT 'pending',
            processed_at DATETIME,
            admin_notes TEXT,
            created_at DATETIME,
            FOREIGN KEY(appointment_id) REFERENCES appointments(id),
            FOREIGN KEY(patient_id) REFERENCES patients(id)
        )'''),
        ('refund_payout_details', '''CREATE TABLE IF NOT EXISTS refund_payout_details (
            id INTEGER PRIMARY KEY,
            refund_id INTEGER NOT NULL UNIQUE,
            payment_method VARCHAR(30) NOT NULL,
            account_title VARCHAR(120) NOT NULL,
            account_number VARCHAR(64),
            iban VARCHAR(64),
            bank_name VARCHAR(120),
            wallet_provider VARCHAR(40),
            wallet_number VARCHAR(30),
            patient_note TEXT,
            admin_proof_path VARCHAR(255),
            admin_proof_note TEXT,
            submitted_at DATETIME,
            updated_at DATETIME,
            FOREIGN KEY(refund_id) REFERENCES refunds(id)
        )'''),
        ('doctor_payout_requests', '''CREATE TABLE IF NOT EXISTS doctor_payout_requests (
            id INTEGER PRIMARY KEY,
            doctor_id INTEGER NOT NULL,
            amount FLOAT NOT NULL,
            status VARCHAR(20) DEFAULT 'pending',
            requested_at DATETIME,
            processed_at DATETIME,
            admin_notes TEXT,
            FOREIGN KEY(doctor_id) REFERENCES doctors(id)
        )'''),
    ]:
        try:
            cur.execute(sql)
            conn.commit()
            print(f"  Table {name} OK")
        except Exception as e:
            print(f"  Table {name}: {e}")
    conn.close()
    print("Migration complete.")

if __name__ == '__main__':
    run_migration()
