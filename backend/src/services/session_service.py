from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import func, select, or_
import uuid
from typing import Optional
import datetime
from ..db.sessions import Sessions as SessionModel
from ..db.sessions import JobStatusEnum
from ..db.users import Users
from ..config import ANONYMOUS_ROAST_TTL_DAYS



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


async def get_leaderboard(
    db: AsyncSession, limit: int = 20, offset: int = 0
) -> tuple[list[dict], int]:
    """
    Ranks public roasts by Sessions.composite_score (desc), tiebroken by
    created_at (asc, earlier ranks higher). Only sessions with a slug
    qualify -- slug is generated only once a session reaches DONE (see
    public.py), so this is naturally scoped to "roasts that finished and
    are shareable," same population the public link service serves.
    Anonymous sessions past ANONYMOUS_ROAST_TTL_DAYS are excluded --
    mirrors public.py's own 410 check so a leaderboard entry never briefly
    outlives (or precedes) the same roast's public link becoming
    unavailable. Logged-in users are never excluded by age (no retention
    limit configured yet, same as public.py).

    Selects individual columns rather than whole SessionModel rows --
    returning ORM instances here risks the identity-map gotcha documented
    throughout this codebase's tests (an instance already tracked+expired
    elsewhere in the same session raises MissingGreenlet if a caller
    touches an attribute outside an awaited context). Plain scalar columns
    sidestep that entirely.
    """
    cutoff = datetime.datetime.utcnow() - datetime.timedelta(days=ANONYMOUS_ROAST_TTL_DAYS)
    eligible = (
        SessionModel.slug.isnot(None),
        SessionModel.composite_score.isnot(None),
        or_(Users.is_anonymous.is_(False), SessionModel.created_at >= cutoff),
    )

    count_stmt = (
        select(func.count())
        .select_from(SessionModel)
        .join(Users, SessionModel.user_id == Users.id)
        .where(*eligible)
    )
    total = (await db.execute(count_stmt)).scalar_one()

    rows_stmt = (
        select(
            SessionModel.id,
            SessionModel.slug,
            SessionModel.composite_score,
            SessionModel.created_at,
            Users.display_name,
        )
        .join(Users, SessionModel.user_id == Users.id)
        .where(*eligible)
        .order_by(SessionModel.composite_score.desc(), SessionModel.created_at.asc())
        .limit(limit)
        .offset(offset)
    )
    result = await db.execute(rows_stmt)
    rows = [
        {
            "id": row.id,
            "slug": row.slug,
            "composite_score": row.composite_score,
            "created_at": row.created_at,
            "display_name": row.display_name,
        }
        for row in result.all()
    ]
    return rows, total


async def get_session_by_slug(db: AsyncSession, slug: str) -> SessionModel | None:
    stmt = (
        select(SessionModel)
        .where(SessionModel.slug == slug)
    )
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


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