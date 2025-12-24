from sqlalchemy.ext.asyncio import AsyncSession
from backend.src.db.sessions import JobStatusEnum, Sessions
from backend.src.utils.telemetry import emit_event
from backend.src.db.sessions import JobStatusEnum
import enum
import datetime


async def mark_normalizing(db: AsyncSession, session: Sessions) -> Sessions:
    current_status = session.status
    if current_status != JobStatusEnum.EXTRACTED:
        emit_event(
            "session.status.invalid_transition",
            {
                "session_id": str(session.id),
                "current_status": current_status,
                "attempted_status": JobStatusEnum.EXTRACTED,
                "reason": f"cannot mark as NORMALIZING from {current_status} status",
                "status": "WARNING"
            }
        )
        return None

    session.status = JobStatusEnum.NORMALIZING
    session.updated_at = datetime.datetime.utcnow()

    try:
        await db.commit()
        await db.refresh(session)
        emit_event(
            "session.status.marked_normalizing",
            {
                "session_id": str(session.id),
                "previous_status": current_status,
                "new_status": JobStatusEnum.NORMALIZING,
                "reason": "session marked as normalizing successfully",
                "status": "INFO"
            }
        )
    except Exception as e:
        await db.rollback()
        emit_event(
            "session.status.update_failure",
            {
                "session_id": str(session.id),
                "attempted_status": JobStatusEnum.NORMALIZING,
                "reason": f"failed to update session status: {str(e)}",
                "error_type": type(e).__name__,
                "status": "ERROR"
            }
        )
        raise
    return session


async def mark_normalized(db: AsyncSession, session: Sessions) -> Sessions:
    current_status = session.status
    if current_status != JobStatusEnum.NORMALIZING | JobStatusEnum.EXTRACTED:
        emit_event(
            "session.status.invalid_transition",
            {
                "session_id": str(session.id),
                "current_status": current_status,
                "attempted_status": JobStatusEnum.NORMALIZED,
                "reason": f"cannot mark as NORMALIZED from {current_status} status",
                "status": "WARNING"
            }
        )
        return None

    session.status = JobStatusEnum.NORMALIZED
    session.updated_at = datetime.datetime.utcnow()
    try:
        await db.commit()
        await db.refresh(session)
        emit_event(
            "session.status.marked_normalized",
            {
                "session_id": str(session.id),
                "previous_status": current_status,
                "new_status": JobStatusEnum.NORMALIZED,
                "reason": "session marked as normalized successfully",
                "status": "INFO"
            }
        )
    except Exception as e:
        await db.rollback()
        emit_event(
            "session.status.update_failure",
            {
                "session_id": str(session.id),
                "attempted_status": JobStatusEnum.NORMALIZED,
                "reason": f"failed to update session status: {str(e)}",
                "error_type": type(e).__name__,
                "status": "ERROR"
            }
        )
        raise
    return session


async def mark_failed(
    *,
    db: AsyncSession,
    session: Sessions,
    error_code: str,
    error_reason: str
) -> Sessions:
    previous_status = session.status
    session.status = JobStatusEnum.FAILED
    session.error_code = error_code
    session.error_message = error_reason
    session.updated_at = datetime.datetime.utcnow()

    try:
        await db.commit()
        await db.refresh(session)
        emit_event(
            "session.status.marked_failed",
            {
                "session_id": str(session.id),
                "previous_status": previous_status,
                "new_status": JobStatusEnum.FAILED,
                "error_code": error_code,
                "error_message": error_reason,
                "reason": "session marked as failed",
                "status": "ERROR"
            }
        )
    except Exception as e:
        await db.rollback()
        emit_event(
            "session.status.update_failure",
            {
                "session_id": str(session.id),
                "attempted_status": JobStatusEnum.FAILED,
                "reason": f"failed to mark session as failed: {str(e)}",
                "error_type": type(e).__name__,
                "status": "ERROR"
            }
        )
        raise

    return session
