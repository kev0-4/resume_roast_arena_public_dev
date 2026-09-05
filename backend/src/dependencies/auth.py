'''
Middleware Dependency that run perfore multiple routes, check if token is valid, and if token is valid fetches user details
'''

from fastapi import Request, HTTPException, status, Depends
from ..services.firebase_auth import verify_id_token
from ..services.user_service import get_or_create_users_from_claims
from sqlalchemy.ext.asyncio import AsyncSession
from ..db.session import get_db_sqlalchemy
from ..utils.telemetry import emit_event, with_trace

async def get_current_user(request: Request, db: AsyncSession = Depends(get_db_sqlalchemy)):
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        emit_event(
            "auth.failure",
            {
                "reason": "invalid_or_missing_token",
                "trace_id": 00,
                "status": "WARNING",
                "route": "dependency.get_current_user"
            }
        )

        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid Authorization header",
        )
    token = auth_header.split("Bearer ")[1]
    decoded = await verify_id_token(token)
    if not decoded:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or Expireed token",
        )
    curr_user = await get_or_create_users_from_claims(decoded, db)
    if not curr_user:
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
        "route": "dependency.get_current_user"
    }
)


    return curr_user


async def get_current_user_optional(request: Request, db: AsyncSession = Depends(get_db_sqlalchemy)):
    """
    Like get_current_user, but returns None instead of raising when no
    Authorization header is present at all -- for routes (e.g. /ingest) that
    support anonymous use. A *present but invalid* token still raises 401:
    a bad token is a client bug, not intentional anonymous use.
    """
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        return None
    return await get_current_user(request, db)

