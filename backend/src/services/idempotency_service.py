'''
verifies idempotency keys, that prevents duplicate requests to be pushed into asb.
uses xIdempotencyKey schema and request.header key for validation
'''
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from uuid import UUID
from typing import Optional
from ..db.xIdempotencyKey import xIdempotencyKey as IdempotencyKey
from ..db.sessions import Sessions
from ..utils.telemetry import emit_event


async def get_session_by_key(db: AsyncSession, key: str | UUID, user_id: UUID | str | None) -> Optional[Sessions]:
    stmt = (
        select(Sessions)
        .join(IdempotencyKey, IdempotencyKey.session_id == Sessions.id)
        .where(
            IdempotencyKey.key == key,
            IdempotencyKey.user_id == user_id,
        )
    )
    result = await db.execute(stmt)
    session = result.scalar_one_or_none()

    if session:
        emit_event(
            "idempotency.key.found",
            {
                "key": str(key),
                "user_id": str(user_id) if user_id else None,
                "session_id": str(session.id),
                "session_status": session.status,
                "reason": "existing session found for idempotency key",
                "status": "INFO"
            }
        )
    else:
        emit_event(
            "idempotency.key.not_found",
            {
                "key": str(key),
                "user_id": str(user_id) if user_id else None,
                "reason": "no existing session for idempotency key",
                "status": "INFO"
            }
        )

    return session


async def create_key_mapping(db: AsyncSession, key: str | UUID, user_id: str | UUID | None, session_id: UUID | str) -> None:
    mapping = IdempotencyKey(key=key, user_id=user_id, session_id=session_id)
    db.add(mapping)
    try:
        await db.flush()
        emit_event(
            "idempotency.mapping.created",
            {
                "key": str(key),
                "user_id": str(user_id) if user_id else None,
                "session_id": str(session_id),
                "reason": "idempotency key mapping created successfully",
                "status": "INFO"
            }
        )
    except IntegrityError as e:
        await db.rollback()
        emit_event(
            "idempotency.mapping.failure",
            {
                "key": str(key),
                "user_id": str(user_id) if user_id else None,
                "session_id": str(session_id),
                "reason": "integrity constraint violation - duplicate key or invalid reference",
                "error_type": type(e).__name__,
                "status": "ERROR"
            }
        )
        raise
    except Exception as e:
        await db.rollback()
        emit_event(
            "idempotency.mapping.failure",
            {
                "key": str(key),
                "user_id": str(user_id) if user_id else None,
                "session_id": str(session_id),
                "reason": f"unexpected error during key mapping creation: {str(e)}",
                "error_type": type(e).__name__,
                "status": "ERROR"
            }
        )
        raise
