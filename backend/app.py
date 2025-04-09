from chalice import Chalice, Response, UnauthorizedError, BadRequestError
from chalicelib import storage_service, textract_service
from chalicelib.user_service import UserService
from chalicelib.token_utils import verify_token
import base64
import uuid
import boto3
from urllib.parse import unquote

app = Chalice(app_name='cloudcomputingproject')
app.debug = True

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
    user_id = get_authenticated_user_id()
    body = app.current_request.json_body

    image_data = body.get('image')
    file_ext = body.get('extension', 'jpg')

    if not image_data:
        raise BadRequestError("Missing 'image' field (base64 encoded).")

    try:
        binary_data = base64.b64decode(image_data)
    except Exception:
        raise BadRequestError("Invalid base64 string.")

    file_name = f"uploads/{user_id}/{uuid.uuid4()}.{file_ext}"

    s3.put_object(
        Bucket=BUCKET_NAME,
        Key=file_name,
        Body=binary_data,
        ContentType=f'image/{file_ext}',
        ACL='private'
    )

    return {
        "message": "Upload successful",
        "file_name": file_name,
        "s3_key": file_name
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
