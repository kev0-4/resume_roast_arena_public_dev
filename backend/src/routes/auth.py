'''
This route has Authentication - firebase implementation
also has their supporting util functions
'''

from fastapi import APIRouter, Response, status, Depends, Request, HTTPException
# from sqlalchemy.orm import Session
from sqlalchemy.ext.asyncio import AsyncSession
from ..db.session import get_db_sqlalchemy
from ..services.user_service import get_or_create_users_from_claims
from ..dependencies.auth import get_current_user
from ..dependencies.auth_helpers import extract_token_from_request
from ..services.firebase_auth import verify_id_token
from ..schemas.auth_schemas import FirebaseAuthRequest, FirebaseAuthResponse
from ..utils.telemetry import emit_event, with_trace

auth_router = APIRouter(
    prefix="/auth"
)


@auth_router.post("/firebase", status_code=status.HTTP_200_OK, response_model=FirebaseAuthResponse)
async def firebase_auth(request: Request, db: AsyncSession = Depends(get_db_sqlalchemy)):
    token = extract_token_from_request(request=request)
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="No token",
        )

    decoded = await verify_id_token(token)
    if not decoded:
        emit_event(
            "auth.failure",
            {
                "reason": "token verification failed",
                "trace_id": 00,
                "status": "WARNING",
                "route": "POST /v1/auth/firebase"
            }
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="unable to authenticate user",
        )
    curr_user = await get_or_create_users_from_claims(decoded, db)
    if not curr_user:
        emit_event(
            "auth.failure",
            {
                "reason": "db failure user Not found",
                "trace_id": 00,
                "status": "WARNING",
                "route": "POST /v1/auth/firebase"
            }
        )

        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="unable to authenticate user",
        )

    emit_event(
        "auth.verified",
        {
            "firebase_uid": curr_user.firebase_uid,
            "user_id": curr_user.id,
            "trace_id": 00,
            "status": "INFO",
            "route": "POST /v1/auth/firebase"
        }
    )
    return {"user": curr_user}


@auth_router.post("/me", status_code=status.HTTP_200_OK)
async def get_profile(curr_user=Depends(get_current_user)):
    return curr_user


@auth_router.post("/test-user-lookup", status_code=status.HTTP_200_OK)
async def test_user_lookup(db: AsyncSession = Depends(get_db_sqlalchemy)):
    ''' This is a test endpoint that checks the lookup function'''
    SAMPLE_CLAIMS = {
        # The unique Firebase User ID
        'uid': '2VRXKpPd3eZj5OdEeZpDccAX4ml79',
        'email': 'test.tandon.btech2022@sitpune.edu.in',
        'email_verified': True,
        'display_name': 'Kevin.Tandon Btech2022',
        'picture': 'https://lh3.googleusercontent.com/a/Random_ahh_url',
        'is_anonymous': False,
        # Additional keys often present in a Firebase token, kept for completeness:
        'iss': 'https://securetoken.google.com/your-project-id',
        'aud': 'your-project-id',
        'sub': '2VRXKpPd3eZj5OdEeZpDccAX4ml2',
        'auth_time': 1678886400,
        'iat': 1678890000,
        'exp': 1678893600,
    }
    try:
        user_record = await get_or_create_users_from_claims(claims=SAMPLE_CLAIMS, db=db)
        if user_record:
            # Successfully found or created the user
            return {
                "message": "User process successful (Found or Created)",
                "user_id": user_record.id,
                "email": user_record.email,
                "firebase_uid": user_record.firebase_uid,
                "created_at": user_record.created_at,
                "metadata": user_record

            }
        else:
            # This would only happen if firebase_uid was missing, based on the service function
            return Response(
                content={"message": "Failed to process user (Missing UID)"},
                status_code=status.HTTP_400_BAD_REQUEST
            )

    except Exception as e:
        # Catch any potential database errors (e.g., connection issue)
        print(f"Database operation failed: {e}")
        return Response(
            content={"message": f"An error occurred during DB operation: {e}"},
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
        )
