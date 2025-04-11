import boto3
import json
from datetime import datetime, timezone
from botocore.exceptions import ClientError

# Initialize clients
ses = boto3.client('ses', region_name='us-east-1')
s3 = boto3.client('s3')
cognito = boto3.client('cognito-idp', region_name='us-east-1')

# Constants
BUCKET_NAME = 'contentcen301247017.aws.ai'
USER_POOL_ID = 'us-east-1_uQZV1V7mr'

def get_user_ids_from_s3():
    try:
        response = s3.list_objects_v2(Bucket=BUCKET_NAME, Prefix='uploads/', Delimiter='/')
        prefixes = response.get('CommonPrefixes', [])
        return [prefix['Prefix'].split('/')[1] for prefix in prefixes]
    except Exception as e:
        print(f"[ERROR] Failed to list user folders in S3: {e}")
        return []

def get_user_email(user_id):
    try:
        response = cognito.admin_get_user(
            UserPoolId=USER_POOL_ID,
            Username=user_id
        )
        for attr in response['UserAttributes']:
            if attr['Name'] == 'email':
                return attr['Value']
        return None
    except ClientError as e:
        print(f"[ERROR] Fetching email for {user_id}: {e}")
        return None

def send_email(to_address, subject, body):
    try:
        response = ses.send_email(
            Source='ethan@szabadka.ca',
            Destination={'ToAddresses': [to_address]},
            Message={
                'Subject': {'Data': subject},
                'Body': {'Text': {'Data': body}},
            },
        )
        print(f"[INFO] Email sent to {to_address}! Message ID: {response['MessageId']}")
    except ClientError as e:
        print(f"[ERROR] Sending email to {to_address}: {e.response['Error']['Message']}")

def check_reminders(event, context):
    user_ids = get_user_ids_from_s3()
    now = datetime.now(timezone.utc)

    if not user_ids:
        print("[INFO] No user folders found under uploads/")
        return {"status": "No users found."}

    for user_id in user_ids:
        print(f"\n[INFO] Processing user: {user_id}")
        reminder_key = f"uploads/{user_id}/reminders.json"

        try:
            obj = s3.get_object(Bucket=BUCKET_NAME, Key=reminder_key)
            reminders = json.loads(obj['Body'].read())
            print(f"[INFO] Found {len(reminders)} reminder(s) for user {user_id}")
        except s3.exceptions.NoSuchKey:
            print(f"[INFO] No reminders.json for user {user_id}")
            continue
        except Exception as e:
            print(f"[ERROR] Failed to read reminder file for {user_id}: {e}")
            continue

        user_email = get_user_email(user_id)
        if not user_email:
            print(f"[WARN] No email for user {user_id}. Skipping.")
            continue

        updated_reminders = []
        for reminder in reminders:
            try:
                reminder_time = datetime.fromisoformat(reminder["reminder_time"].replace("Z", "+00:00"))
                if reminder_time <= now:
                    print(f"[INFO] Sending reminder for file: {reminder['file_name']} to {user_email}")
                    subject = f"📬 Reminder: {reminder['file_name']} is due!"
                    body = f"""
                        Hello,
                        
                        This is a reminder that your document **{reminder['file_name']}** is due on {reminder_time.strftime('%Y-%m-%d %H:%M:%S')} UTC.
                        
                        Please take any necessary actions.
                        
                        Thanks,
                        Your Reminder App
                    """
                    send_email(user_email, subject, body)
                    # ❗ Remove after sending
                else:
                    updated_reminders.append(reminder)
            except Exception as e:
                print(f"[ERROR] Processing a reminder for user {user_id}: {e}")
                updated_reminders.append(reminder)

        try:
            s3.put_object(
                Bucket=BUCKET_NAME,
                Key=reminder_key,
                Body=json.dumps(updated_reminders).encode('utf-8'),
                ContentType='application/json'
            )
            print(f"[INFO] Updated reminders.json for {user_id}. Remaining: {len(updated_reminders)}")
        except Exception as e:
            print(f"[ERROR] Updating reminders.json for {user_id}: {e}")

    return {"status": "Processed reminders"}

def lambda_handler(event, context):
    return check_reminders(event, context)
