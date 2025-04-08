from chalice import Chalice
from chalicelib import storage_service
from chalicelib import textract_service

# Chalice app configuration
app = Chalice(app_name='Capabilities')
app.debug = True

# Services initialization
storage_location = 'contentcen301446462.aws.ai'
storage_service = storage_service.StorageService(storage_location)
textract_service = textract_service.TextractService(storage_service)

# Route to extract invoice details using Textract
@app.route('/extract-invoice/{file_name}', cors=True)
def extract_invoice(file_name):
    """Extracts Vendor, Due Date, and Amount Due from PDF or image in S3"""
    data = textract_service.analyze_document(file_name)
    return {
        "fileName": file_name,
        "extractedData": data
    }
