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


def _leaderboard_eligible_clause(cutoff: datetime.datetime) -> tuple:
    """
    Shared eligibility rule for both the leaderboard and a single
    session's rank (get_session_rank below) -- kept in one place so the
    two can never drift apart on what counts as "rankable." See
    get_leaderboard's docstring for the reasoning behind each condition.
    """
    return (
        SessionModel.slug.isnot(None),
        SessionModel.composite_score.isnot(None),
        or_(Users.is_anonymous.is_(False), SessionModel.created_at >= cutoff),
    )


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
    eligible = _leaderboard_eligible_clause(cutoff)

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
            SessionModel.stamp,
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
            "stamp": row.stamp,
            "created_at": row.created_at,
            "display_name": row.display_name,
        }
        for row in result.all()
    ]
    return rows, total


async def get_session_rank(
    db: AsyncSession, *, composite_score: int, created_at: datetime.datetime
) -> tuple[int, int]:
    """
    Rank of a single session within the leaderboard, without scanning or
    paginating the whole thing -- returns (rank, total_ranked), 1-indexed.

    Computed as "1 + count of eligible sessions that sort ahead of this
    one", using the exact same tiebreak as get_leaderboard (composite_score
    DESC, then created_at ASC): a session sorts ahead if its score is
    strictly higher, or tied with an earlier created_at. This is the
    standard count-based rank pattern -- cheap regardless of how deep the
    rank is (unlike walking a paginated list to find where a session
    falls) -- and it's answerable from the same partial index
    (ix_sessions_leaderboard, see the leaderboard-perf migration) that
    already backs the leaderboard's own ORDER BY, so it stays fast as the
    table grows exactly the way that index was built to guarantee.
    """
    cutoff = datetime.datetime.utcnow() - datetime.timedelta(days=ANONYMOUS_ROAST_TTL_DAYS)
    eligible = _leaderboard_eligible_clause(cutoff)

    sorts_ahead = or_(
        SessionModel.composite_score > composite_score,
        (SessionModel.composite_score == composite_score) & (SessionModel.created_at < created_at),
    )

    total_stmt = (
        select(func.count())
        .select_from(SessionModel)
        .join(Users, SessionModel.user_id == Users.id)
        .where(*eligible)
    )
    ahead_stmt = total_stmt.where(sorts_ahead)

    total = (await db.execute(total_stmt)).scalar_one()
    ahead = (await db.execute(ahead_stmt)).scalar_one()
    return ahead + 1, total


async def get_user_leaderboard_position(
    db: AsyncSession, *, user_id: str | uuid.UUID
) -> Optional[dict]:
    """
    A signed-in user's own leaderboard standing, for the "your rank"
    banner on the leaderboard page -- distinct from get_session_rank,
    which ranks one *specific* session the caller already knows about.
    Here the caller only knows the user, so this first finds that user's
    single best-scoring eligible session (their strongest roast -- this
    is what a "your rank" banner should show, not a run they've since
    beaten), tiebroken by created_at asc (same tiebreak get_leaderboard
    itself uses, so "best" agrees with how the leaderboard would actually
    rank two tied submissions), then ranks it exactly like
    get_session_rank does. Returns None if the user has no eligible
    session yet (never roasted, or their only roasts aren't shareable/
    are past the anonymous TTL -- though a signed-in user's own sessions
    are never TTL-excluded, since Users.is_anonymous is only ever true
    for the throwaway rows /ingest creates for anonymous uploads).
    """
    cutoff = datetime.datetime.utcnow() - datetime.timedelta(days=ANONYMOUS_ROAST_TTL_DAYS)
    eligible = _leaderboard_eligible_clause(cutoff)

    best_stmt = (
        select(SessionModel.slug, SessionModel.composite_score, SessionModel.stamp, SessionModel.created_at)
        .join(Users, SessionModel.user_id == Users.id)
        .where(SessionModel.user_id == user_id, *eligible)
        .order_by(SessionModel.composite_score.desc(), SessionModel.created_at.asc())
        .limit(1)
    )
    best = (await db.execute(best_stmt)).first()
    if best is None:
        return None

    rank, total = await get_session_rank(
        db=db, composite_score=best.composite_score, created_at=best.created_at
    )
    return {
        "rank": rank,
        "total": total,
        "slug": best.slug,
        "composite_score": best.composite_score,
        "stamp": best.stamp,
        "created_at": best.created_at,
    }


async def get_session_by_slug(db: AsyncSession, slug: str) -> SessionModel | None:
    stmt = (
        select(SessionModel)
        .where(SessionModel.slug == slug)
    )
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def get_user_sessions(
    db: AsyncSession, *, user_id: str | uuid.UUID, limit: int = 20, offset: int = 0
) -> tuple[list[dict], int]:
    """
    A signed-in user's own roast history -- every session they've ever
    started, most recent first, regardless of status. Deliberately not
    scoped to the leaderboard-eligible subset (_leaderboard_eligible_clause)
    the way get_leaderboard/get_user_leaderboard_position are: a history
    page is exactly the place a user *should* be able to see an
    in-progress or FAILED session too, not just the ones that made it all
    the way to a public roast card.

    Selects individual columns rather than whole SessionModel rows, same
    reasoning as get_leaderboard: sidesteps the identity-map gotcha
    documented throughout this codebase's tests.
    """
    count_stmt = select(func.count()).select_from(SessionModel).where(SessionModel.user_id == user_id)
    total = (await db.execute(count_stmt)).scalar_one()

    rows_stmt = (
        select(
            SessionModel.id,
            SessionModel.status,
            SessionModel.slug,
            SessionModel.composite_score,
            SessionModel.stamp,
            SessionModel.error_code,
            SessionModel.error_message,
            SessionModel.created_at,
        )
        .where(SessionModel.user_id == user_id)
        .order_by(SessionModel.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    result = await db.execute(rows_stmt)
    rows = [
        {
            "id": row.id,
            "status": row.status,
            "slug": row.slug,
            "composite_score": row.composite_score,
            "stamp": row.stamp,
            "error_code": row.error_code,
            "error_message": row.error_message,
            "created_at": row.created_at,
        }
        for row in result.all()
    ]
    return rows, total


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