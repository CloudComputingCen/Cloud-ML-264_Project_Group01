import jwt
import requests

COGNITO_REGION = 'us-east-1'
USER_POOL_ID = 'us-east-1_uQZV1V7mr'
COGNITO_ISSUER = f'https://cognito-idp.{COGNITO_REGION}.amazonaws.com/{USER_POOL_ID}'
JWKS_URL = f'{COGNITO_ISSUER}/.well-known/jwks.json'

# Cache keys
_jwk_cache = None

def get_jwk_keys():
    global _jwk_cache
    if _jwk_cache is None:
        response = requests.get(JWKS_URL)
        _jwk_cache = response.json()
    return _jwk_cache

def verify_token(token):
    try:
        jwks = get_jwk_keys()
        headers = jwt.get_unverified_header(token)
        key = next(k for k in jwks['keys'] if k['kid'] == headers['kid'])

        public_key = jwt.algorithms.RSAAlgorithm.from_jwk(key)

        payload = jwt.decode(
            token,
            public_key,
            algorithms=['RS256'],
            issuer=COGNITO_ISSUER, 
            options={"verify_aud": False}
        )

        # Still enforce access token use
        if payload.get("token_use") != "access":
            print("Rejected: not an access token")
            return None

        return payload

    except Exception as e:
        print(f"TOKEN VERIFICATION FAILED: {e}")
        return None


