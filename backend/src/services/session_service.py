from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import func, select
import uuid
from typing import Optional
import datetime
from ..db.sessions import Sessions as SessionModel
from ..db.sessions import JobStatusEnum



async def create_sessions(user_id: str | uuid.UUID, db: AsyncSession) -> SessionModel:
    session_id = uuid.uuid4()
    session = SessionModel(
        id = session_id,
        user_id = user_id,
        status=JobStatusEnum.UPLOADED,
        raw_blob_path=" ",
    )
    db.add(session)
    try:
        await db.commit()
        await db.refresh(session)
    except:
        await db.rollback()
        raise
    return session
   



async def get_session(session_id : uuid.UUID | str, db: AsyncSession) ->SessionModel | None:

    stmt = (
        select(SessionModel)
        .where(SessionModel.id == session_id)
    )
    result = await db.execute(stmt)
    session = result.scalar_one_or_none()
    return session


ALLOWED_TRANSITIONS = {
    JobStatusEnum.UPLOADED: {JobStatusEnum.QUEUED, JobStatusEnum.FAILED},
    JobStatusEnum.QUEUED: {JobStatusEnum.PROCESSING, JobStatusEnum.FAILED},
    JobStatusEnum.PROCESSING: {JobStatusEnum.DONE, JobStatusEnum.FAILED},
}

async def update_session_status(db:AsyncSession, session: SessionModel,new_status) -> SessionModel:
    current_status = session.status
    if new_status not in ALLOWED_TRANSITIONS.get(current_status, set()):
        raise ValueError(
            f"Invalid status transition: {current_status} → {new_status}"
        )
    session.status = new_status
    session.updated_at = datetime.datetime.utcnow()
    try:
        await db.commit()
        await db.refresh(session)
    except:
        await db.rollback()
        raise
    return session

async def update_session_raw_blob_path(db: AsyncSession,session:SessionModel,raw_blob_path: str) ->SessionModel:
    session.raw_blob_path = raw_blob_path
    session.updated_at = datetime.datetime.utcnow()
    try:
        await db.commit()
        await db.refresh(session)
    except:
        await db.rollback()
        raise
    return session