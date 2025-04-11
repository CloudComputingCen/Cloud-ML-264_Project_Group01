import boto3
import json
from datetime import datetime, timezone
from botocore.exceptions import ClientError

# Initialize clients
ses = boto3.client('ses', region_name='us-east-1')
s3 = boto3.client('s3')
cognito = boto3.client('cognito-idp', region_name='us-east-1')

# Constants
BUCKET_NAME = 'contentcen301273661.aws.ai'
USER_POOL_ID = 'us-east-1_EdL4SZhvX'

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
        print(f"Error fetching user email: {e}")
        return None

def send_email(to_address, subject, body):
    try:
        response = ses.send_email(
            Source='kmetsanou@gmail.com',
            Destination={'ToAddresses': [to_address]},
            Message={
                'Subject': {'Data': subject},
                'Body': {'Text': {'Data': body}},
            },
        )
        print(f"Email sent! Message ID: {response['MessageId']}")
    except ClientError as e:
        print(f"Error sending email: {e.response['Error']['Message']}")

def check_reminders(event, context):
    # Simulate iterating over multiple users — in real usage, get user list from S3 folder prefixes or a database
    user_ids = ['sample_user_id_1', 'sample_user_id_2']  # You would loop over real users here

    now = datetime.now(timezone.utc)

    for user_id in user_ids:
        reminder_key = f"uploads/{user_id}/reminders.json"

        try:
            obj = s3.get_object(Bucket=BUCKET_NAME, Key=reminder_key)
            reminders = json.loads(obj['Body'].read())
        except s3.exceptions.NoSuchKey:
            continue

        # Fetch user's email from Cognito
        user_email = get_user_email(user_id)
        if not user_email:
            continue  # Skip if email not found

        updated_reminders = []
        for reminder in reminders:
            reminder_time = datetime.fromisoformat(reminder["reminder_time"].replace("Z", "+00:00"))
            if reminder_time <= now:
                subject = f"📬 Reminder: {reminder['file_name']} is due!"
                body = f"""
Hello,

This is a reminder that your document **{reminder['file_name']}** is due on {reminder_time.strftime('%Y-%m-%d %H:%M:%S')} UTC.

Please take any necessary actions.

Thanks,
Your Reminder App
                """
                send_email(user_email, subject, body)
            else:
                updated_reminders.append(reminder)  # Keep future reminders

        # Save updated reminders
        s3.put_object(
            Bucket=BUCKET_NAME,
            Key=reminder_key,
            Body=json.dumps(updated_reminders).encode('utf-8'),
            ContentType='application/json'
        )

    return {"status": "Processed reminders"}
def lambda_handler(event, context):
    return check_reminders(event, context)
