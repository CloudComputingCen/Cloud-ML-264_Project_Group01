import boto3
import time

class TextractService:
    def __init__(self, storage_service):
        self.client = boto3.client('textract', region_name='us-east-1')
        self.storage = storage_service

    def analyze_document(self, file_name):
        bucket = self.storage.get_storage_location()
        print(f"DEBUG: Bucket = {bucket}, Key = {file_name}")

        is_pdf = file_name.lower().endswith(".pdf")

        if is_pdf:
            # For PDFs (asynchronous)
            response = self.client.start_document_analysis(
                DocumentLocation={'S3Object': {'Bucket': bucket, 'Name': file_name}},
                FeatureTypes=["FORMS"]
            )
            job_id = response['JobId']
            print(f"Started Textract job: {job_id}")

            # Wait until job completes
            while True:
                result = self.client.get_document_analysis(JobId=job_id)
                status = result['JobStatus']
                print(f"Job status: {status}")
                if status == 'SUCCEEDED':
                    break
                elif status == 'FAILED':
                    raise Exception("Textract PDF analysis failed.")
                time.sleep(2)

            blocks = result.get('Blocks', [])

        else:
            # For images (synchronous)
            response = self.client.analyze_document(
                Document={'S3Object': {'Bucket': bucket, 'Name': file_name}},
                FeatureTypes=["FORMS"]
            )
            blocks = response.get('Blocks', [])

        key_map = {}
        value_map = {}
        extracted = {}
        full_text = []

        for block in blocks:
            if block['BlockType'] == 'KEY_VALUE_SET':
                block_id = block['Id']
                if 'KEY' in block.get('EntityTypes', []):
                    key_map[block_id] = block
                if 'VALUE' in block.get('EntityTypes', []):
                    value_map[block_id] = block
            elif block['BlockType'] == 'LINE':
                full_text.append(block['Text'])

        for key_id, key_block in key_map.items():
            key_text = self._get_text(blocks, key_block)
            value_text = ""
            for rel in key_block.get('Relationships', []):
                if rel['Type'] == 'VALUE':
                    val_block = value_map.get(rel['Ids'][0])
                    value_text = self._get_text(blocks, val_block)

            print(f"KEY: {key_text} → VALUE: {value_text}")

            key_lower = key_text.lower()
            if any(k in key_lower for k in ["vendor", "supplier", "biller"]):
                extracted['Vendor'] = value_text
            elif "due date" in key_lower:
                extracted['DueDate'] = value_text
            elif any(k in key_lower for k in ["amount due", "total amount", "total"]):
                extracted['Amount'] = value_text

        # Smart fallback: combine multiple lines to form full vendor name
        if 'Vendor' not in extracted:
            vendor_lines = []
            for line in full_text:
                clean = line.strip()
                lower = clean.lower()
                words = clean.split()

                if (
                    len(words) >= 1 and
                    not any(char.isdigit() for char in clean) and
                    not any(w in lower for w in ['invoice', 'total', 'due', 'date', 'amount', 'number'])
                ):
                    vendor_lines.append(clean.title())

                if len(vendor_lines) >= 2:
                    break

            if vendor_lines:
                extracted['Vendor'] = " ".join(vendor_lines)

        return extracted

    def _get_text(self, blocks, block):
        text = ""
        if 'Relationships' in block:
            for rel in block['Relationships']:
                if rel['Type'] == 'CHILD':
                    for cid in rel['Ids']:
                        word = next((b for b in blocks if b['Id'] == cid and b['BlockType'] == 'WORD'), None)
                        if word:
                            text += word['Text'] + " "
        return text.strip()
