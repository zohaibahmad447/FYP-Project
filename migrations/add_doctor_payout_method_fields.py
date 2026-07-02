"""
Migration: Add method-specific payout destination fields to doctor_payout_requests.

Adds columns:
- payout_method
- account_title
- provider_name
- account_number
- iban
- visa_card_holder_name
- visa_card_last4
- visa_recipient_id
"""

import os
import sqlite3


def add_doctor_payout_method_fields():
    """Add payout method and destination snapshot fields."""
    db_path = os.path.join(
        os.path.dirname(os.path.dirname(__file__)),
        'instance',
        'quickcare_dev.db',
    )

    if not os.path.exists(db_path):
        print(f"Database not found at: {db_path}")
        return

    fields = [
        ('payout_method', 'VARCHAR(30)'),
        ('account_title', 'VARCHAR(120)'),
        ('provider_name', 'VARCHAR(120)'),
        ('account_number', 'VARCHAR(64)'),
        ('iban', 'VARCHAR(64)'),
        ('visa_card_holder_name', 'VARCHAR(120)'),
        ('visa_card_last4', 'VARCHAR(4)'),
        ('visa_recipient_id', 'VARCHAR(120)'),
    ]

    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        for field_name, field_type in fields:
            try:
                cursor.execute(
                    f"ALTER TABLE doctor_payout_requests ADD COLUMN {field_name} {field_type}"
                )
                print(f"Added column: {field_name}")
            except sqlite3.OperationalError as exc:
                if 'duplicate column name' in str(exc).lower():
                    print(f"Column already exists: {field_name}")
                else:
                    raise

        conn.commit()
        conn.close()
        print('Doctor payout method fields migration completed.')
    except Exception as exc:
        print(f"Migration failed: {exc}")


if __name__ == '__main__':
    add_doctor_payout_method_fields()
