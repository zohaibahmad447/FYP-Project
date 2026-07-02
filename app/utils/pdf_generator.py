"""
PDF generation utility for creating professional prescription PDFs
"""
from xhtml2pdf import pisa
from flask import render_template
from datetime import datetime
import os

def generate_prescription_pdf(prescription):
    """
    Generate a professional PDF from prescription data using xhtml2pdf
    
    Args:
        prescription: Prescription model instance
    
    Returns:
        str: Absolute path to the generated PDF file
    """
    # Prepare PDF directory
    from flask import current_app
    pdf_dir = os.path.join(current_app.root_path, 'static', 'prescriptions')
    if not os.path.exists(pdf_dir):
        os.makedirs(pdf_dir)
    
    # Generate PDF filename
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    pdf_filename = f'prescription_{prescription.id}_{timestamp}.pdf'
    pdf_path = os.path.join(pdf_dir, pdf_filename)
    
    # Render HTML template (CSS is now embedded in the template's <head>)
    html_content = render_template('prescriptions/pdf_template.html', prescription=prescription)
    
    # Generate PDF using xhtml2pdf
    with open(pdf_path, "w+b") as result_file:
        pisa_status = pisa.CreatePDF(
            html_content,                
            dest=result_file           
        )
        
    if pisa_status.err:
        print(f"PDF validation errors: {pisa_status.err}")
        # Not explicitly raising to avoid crashing if minor parsing errors occur, 
        # but in a stricter environment, we could log or raise an exception.
    
    # Update prescription record with PDF path
    prescription.pdf_path = os.path.join('static', 'prescriptions', pdf_filename)
    from app.database import db
    db.session.commit()
    
    return pdf_path
