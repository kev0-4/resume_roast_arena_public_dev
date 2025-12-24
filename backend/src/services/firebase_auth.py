'''
This file has functions to verify idToken received from frotend to its native fields like uuid, email etc etc
this file also initializes firebase admin sdk with service account json
check tests/Manula_Test_verify_id_token for a test token and standalone script
'''
import firebase_admin
from ..utils.telemetry import emit_event
from firebase_admin import credentials, auth
from pathlib import Path
CURRENT_DIR = Path(__file__).resolve().parent
SERVICE_ACCOUNT_KEY_PATH = CURRENT_DIR / "service-account.json"
# SERVICE_ACCOUNT_KEY_PATH ="backend/src/service-account.json"
print(SERVICE_ACCOUNT_KEY_PATH)
try:
    cred = credentials.Certificate(SERVICE_ACCOUNT_KEY_PATH)
    firebase_admin.initialize_app(cred)
except FileNotFoundError as e:
    print("-----\n-----\n----\n Service accoutn json File Not Found \n-----\n-----\n----- ")
except Exception as e:
    print(
        f"-----\n-----\n----\n Error During firebase admin initialization:\n {e}\n-----\n-----\n----- ")


async def verify_id_token(id_token):

    if not id_token:
        print(f"id_token is invalid/empty: {id_token}")
        return None
    try:
        decode_token = auth.verify_id_token(id_token)
        decoded_claims = decode_token
        uid = decode_token.get('uid')
        email = decode_token.get('email')
        print(f"Token successfully verified for UID: {uid}, Email: {email}")
        emit_event(
            "verification.success",
            {
                "reason": "successfully verified token",
                "trace_id": 00,
                "status": "INFO",
                "route": "services.verify_id_token"
            }
        )
        return {
            "uid": decoded_claims["uid"],
            "email": decoded_claims.get("email"),
            "email_verified": decoded_claims.get("email_verified", False),
            "display_name": decoded_claims.get("name"),
            "picture": decoded_claims.get("picture"),
            "is_anonymous": decoded_claims.get("firebase", {}).get("sign_in_provider") == "anonymous"
        }
    except auth.InvalidIdTokenError as e:
        emit_event(
            "verification.failure",
            {
                "reason": "Invalid verify token",
                "trace_id": 00,
                "status": "WARNING",
                "route": "services.verify_id_token"
            }
        )
        print(f"Verification failed: Invalid ID Token. Error: {e}")
        return None
    except Exception as e:
        emit_event(
            "verification.failure",
            {
                "reason": "failed to verify token",
                "trace_id": 00,
                "status": "WARNING",
                "route": "services.verify_id_token"
            }
        )
        print(f"An unexpeceted error occured during decoding of token: {e}")
        return None
