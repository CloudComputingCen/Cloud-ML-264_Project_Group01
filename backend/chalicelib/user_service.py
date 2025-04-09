import boto3

class UserService:
    def __init__(self, user_pool_id, client_id, region='us-east-1'):
        self.client = boto3.client('cognito-idp', region_name=region)
        self.user_pool_id = user_pool_id
        self.client_id = client_id

    def signup_user(self, email, password):
        try:
            # Step 1: Create the user
            self.client.sign_up(
                ClientId=self.client_id,
                Username=email,
                Password=password,
                UserAttributes=[
                    {'Name': 'email', 'Value': email}
                ]
            )

            # By pass the email verification so that when testing and presenting we dont need to verify
            self.client.admin_confirm_sign_up(
                UserPoolId=self.user_pool_id,
                Username=email
            )

            self.client.admin_update_user_attributes(
                UserPoolId=self.user_pool_id,
                Username=email,
                UserAttributes=[
                    {'Name': 'email_verified', 'Value': 'true'}
                ]
            )

            return {'status': 'ok', 'message': 'User signed up and auto-confirmed successfully.'}

        except self.client.exceptions.UsernameExistsException:
            return {'status': 'error', 'message': 'User already exists'}
        except Exception as e:
            return {'status': 'error', 'message': str(e)}

    def login_user(self, email, password):
        try:
            response = self.client.initiate_auth(
                ClientId=self.client_id,
                AuthFlow='USER_PASSWORD_AUTH',
                AuthParameters={
                    'USERNAME': email,
                    'PASSWORD': password
                }
            )
            return {
                'status': 'ok',
                'tokens': response['AuthenticationResult']
            }
        except self.client.exceptions.NotAuthorizedException:
            return {'status': 'error', 'message': 'Incorrect username or password'}
        except self.client.exceptions.UserNotConfirmedException:
            return {'status': 'error', 'message': 'User not confirmed. Please verify your email.'}
        except Exception as e:
            return {'status': 'error', 'message': str(e)}
