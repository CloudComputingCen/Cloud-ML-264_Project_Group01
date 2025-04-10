from chalice import Chalice, Response, UnauthorizedError, BadRequestError
from chalicelib import storage_service, textract_service
from chalicelib.user_service import UserService
from chalicelib.token_utils import verify_token
import base64
import uuid
import boto3
from urllib.parse import unquote
import json
from datetime import datetime, timedelta, timezone
from chalice import CORSConfig

app = Chalice(app_name='cloudcomputingproject')
app.debug = True
cors_config = CORSConfig(
    allow_origin='*',
    allow_headers=['Authorization', 'Content-Type'],
    max_age=600,
    expose_headers=['Authorization'],
    allow_credentials=True
)

# Reworked Setup
BUCKET_NAME = 'contentcen301247017.aws.ai'
s3 = boto3.client('s3')

# Services
storage_service = storage_service.StorageService(BUCKET_NAME)
textract_service = textract_service.TextractService(storage_service)

user_service = UserService(
    user_pool_id='us-east-1_uQZV1V7mr',
    client_id='1ssdk8buoi35c58r0hlaggrk6e'
)

# Ensure the user is logged in
def get_authenticated_user_id():
    auth_header = app.current_request.headers.get('Authorization')
    if not auth_header or not auth_header.startswith('Bearer '):
        raise UnauthorizedError("Missing or invalid token.")
    
    token = auth_header.split(' ')[1]
    claims = verify_token(token)
    if not claims:
        raise UnauthorizedError("Token verification failed.")
    
    return claims['sub']


#  User nows needs to be authenicated 
@app.route('/extract-invoice/{file_name}', cors=True)
def extract_invoice(file_name):
    from urllib.parse import unquote
    file_name = unquote(file_name) 

    user_id = get_authenticated_user_id()
    expected_prefix = f"uploads/{user_id}/"

    print("Decoded file_name:", file_name)
    print("Expected prefix:", expected_prefix)

    if not file_name.startswith(expected_prefix):
        raise UnauthorizedError("You do not have permission to access this file.")

    data = textract_service.analyze_document(file_name)
    return {
        "fileName": file_name,
        "extractedData": data
    }


# When uploading an image, we use Base64
@app.route('/upload-image', methods=['POST'], cors=True)
def upload_image():
    from datetime import datetime, timedelta, timezone

    user_id = get_authenticated_user_id()
    body = app.current_request.json_body

    image_data = body.get('image')
    file_ext = body.get('extension', 'jpg').lower()

    if not image_data:
        raise BadRequestError("Missing 'image' field (base64 encoded).")

    try:
        binary_data = base64.b64decode(image_data)
    except Exception:
        raise BadRequestError("Invalid base64 string.")

    # Generate unique file name
    file_name = f"uploads/{user_id}/{uuid.uuid4()}.{file_ext}"
    content_type = 'application/pdf' if file_ext == 'pdf' else f'image/{file_ext}'

    # Upload to S3
    s3.put_object(
        Bucket=BUCKET_NAME,
        Key=file_name,
        Body=binary_data,
        ContentType=content_type,
        ACL='private'
    )

    # Analyze with Textract
    extracted_data = textract_service.analyze_document(file_name)

    # Record to save in data.json
    new_record = {
        "file_name": file_name,
        "extracted": extracted_data,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "reminders_enabled": True
    }

    data_file_key = f"uploads/{user_id}/data.json"

    # Load existing invoice metadata
    try:
        existing_obj = s3.get_object(Bucket=BUCKET_NAME, Key=data_file_key)
        existing_data = json.loads(existing_obj['Body'].read())
    except s3.exceptions.NoSuchKey:
        existing_data = []

    existing_data.append(new_record)

    # Save updated invoice metadata
    s3.put_object(
        Bucket=BUCKET_NAME,
        Key=data_file_key,
        Body=json.dumps(existing_data).encode('utf-8'),
        ContentType='application/json',
        ACL='private'
    )

    # Reminder Upload
    reminder_key = f"uploads/{user_id}/reminders.json"
    try:
        obj = s3.get_object(Bucket=BUCKET_NAME, Key=reminder_key)
        reminders = json.loads(obj['Body'].read())
    except s3.exceptions.NoSuchKey:
        reminders = []

    if not any(r["file_name"] == file_name for r in reminders):
        now = datetime.now(timezone.utc)
        due_date_str = extracted_data.get("DueDate")

        # Try to parse due date from extractedData["DueDate"]
        try:
            extracted_due_date = datetime.fromisoformat(due_date_str).replace(tzinfo=timezone.utc)
        except (TypeError, ValueError):
            # Fallback to 24h from now
            extracted_due_date = now + timedelta(days=1)

        # Calculate ideal reminder time
        reminder_time = extracted_due_date - timedelta(hours=24)

        # If ideal time is already in the past, bump to now + 15min
        if reminder_time < now:
            reminder_time = now + timedelta(minutes=15)

        reminders.append({
            "file_name": file_name,
            "created_at": now.isoformat(),
            "due_date": extracted_due_date.isoformat().replace("+00:00", "Z"),
            "reminder_time": reminder_time.isoformat().replace("+00:00", "Z")
        })

        # Save updated reminders
        s3.put_object(
            Bucket=BUCKET_NAME,
            Key=reminder_key,
            Body=json.dumps(reminders).encode('utf-8'),
            ContentType='application/json'
        )

    return {
        "message": "Upload successful",
        "file_name": file_name,
        "extractedData": extracted_data,
        "saved_to": data_file_key,
        "reminder_time": reminder_time.isoformat().replace("+00:00", "Z")
    }




@app.route('/signup', methods=['POST'], cors=True)
def signup():
    body = app.current_request.json_body
    email = body.get('email')
    password = body.get('password')

    if not email or not password:
        return Response(status_code=400, body={'error': 'Email and password required'})

    result = user_service.signup_user(email, password)
    if result['status'] == 'ok':
        return {'message': result['message']}
    else:
        return Response(status_code=400, body={'error': result['message']})


@app.route('/login', methods=['POST'], cors=True)
def login():
    body = app.current_request.json_body
    email = body.get('email')
    password = body.get('password')

    if not email or not password:
        return Response(status_code=400, body={'error': 'Email and password required'})

    result = user_service.login_user(email, password)
    if result['status'] == 'ok':
        return {
            'message': 'Login successful',
            'tokens': result['tokens']
        }
    else:
        return Response(status_code=401, body={'error': result['message']})
    

@app.route('/my-invoices', methods=['GET'], cors=True)
def get_user_invoices():

    user_id = get_authenticated_user_id()
    data_file_key = f"uploads/{user_id}/data.json"

    try:
        # Fetch the existing data.json from S3
        response = s3.get_object(Bucket=BUCKET_NAME, Key=data_file_key)
        data = json.loads(response['Body'].read())
    except s3.exceptions.NoSuchKey:
        # If the file doesn't exist yet, return empty list
        data = []

    return {
        "user_id": user_id,
        "invoices": data
    }

@app.route('/reanalyze/{file_name}', methods=['POST'], cors=True)
def reanalyze_file(file_name):
    user_id = get_authenticated_user_id()
    file_name = unquote(file_name)
    
    if not file_name.startswith(f"uploads/{user_id}/"):
        raise UnauthorizedError("Access denied.")
    
    extracted = textract_service.analyze_document(file_name)

    return {
        'fileName': file_name,
        'extractedData': extracted,
        'status': 'reanalyzed'
    }

@app.route('/latest-invoice', methods=['GET'], cors=True)
def latest_invoice():
    user_id = get_authenticated_user_id()
    prefix = f'uploads/{user_id}/'
    
    response = s3.list_objects_v2(Bucket=BUCKET_NAME, Prefix=prefix)
    files = sorted(
        [obj for obj in response.get('Contents', []) if not obj['Key'].endswith('data.json')],
        key=lambda x: x['LastModified'],
        reverse=True
    )

    if not files:
        return {'message': 'No invoices uploaded yet.'}
    
    latest_file = files[0]['Key']
    extracted_data = textract_service.analyze_document(latest_file)
    
    return {
        'fileName': latest_file,
        'extractedData': extracted_data
    }


# Reminders
@app.route('/create-reminder', methods=['POST'], cors=True)
def create_reminder():
    body = app.current_request.json_body
    user_id = get_authenticated_user_id()
    file_name = body.get("file_name")
    if not file_name:
        raise BadRequestError("Missing file_name.")

    reminder_key = f"uploads/{user_id}/reminders.json"

    try:
        obj = s3.get_object(Bucket=BUCKET_NAME, Key=reminder_key)
        reminders = json.loads(obj['Body'].read())
    except s3.exceptions.NoSuchKey:
        reminders = []

    if any(reminder["file_name"] == file_name for reminder in reminders):
        return {"message": "Reminder already exists for this file."}

    now = datetime.now(timezone.utc)
    reminders.append({
        "file_name": file_name,
        "created_at": now.isoformat(),
        "reminder_time": (now + timedelta(hours=24)).isoformat() + "Z"
    })

    s3.put_object(
        Bucket=BUCKET_NAME,
        Key=reminder_key,
        Body=json.dumps(reminders).encode('utf-8'),
        ContentType='application/json'
    )

    return {"message": "Reminder created."}

@app.route('/get-reminders', methods=['GET'], cors=True)
def get_reminders():
    user_id = get_authenticated_user_id()
    reminder_key = f"uploads/{user_id}/reminders.json"

    try:
        obj = s3.get_object(Bucket=BUCKET_NAME, Key=reminder_key)
        reminders = json.loads(obj['Body'].read())
    except s3.exceptions.NoSuchKey:
        reminders = []

    return {"reminders": reminders}

@app.route('/delete-reminder', methods=['POST'], cors=True)
def delete_reminder():
    body = app.current_request.json_body
    user_id = get_authenticated_user_id()
    file_name = body.get("file_name")

    reminder_key = f"uploads/{user_id}/reminders.json"

    try:
        obj = s3.get_object(Bucket=BUCKET_NAME, Key=reminder_key)
        reminders = json.loads(obj['Body'].read())
    except s3.exceptions.NoSuchKey:
        return {"error": "No reminders found."}

    updated = [r for r in reminders if r["file_name"] != file_name]

    s3.put_object(
        Bucket=BUCKET_NAME,
        Key=reminder_key,
        Body=json.dumps(updated).encode('utf-8'),
        ContentType='application/json'
    )

    return {"message": "Reminder deleted."}
