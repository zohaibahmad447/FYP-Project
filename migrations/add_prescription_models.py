"""
Migration to add prescription tables
"""
from app.database import db
from app.models import Prescription, PrescriptionMedicine, PrescriptionTest

def upgrade():
    """Create prescription tables"""
    print("Creating prescriptions table...")
    db.create_all()  # This will create all tables that don't exist yet
    print("✓ Prescription tables created successfully")

def downgrade():
    """Drop prescription tables"""
    print("Dropping prescription tables...")
    db.drop_all()  # Warning: This drops ALL tables
    print("✓ Prescription tables dropped")

if __name__ == '__main__':
    from app import create_app
    app = create_app()
    
    with app.app_context():
        print("Running prescription models migration...")
        upgrade()
        print("Migration complete!")
