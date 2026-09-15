"""
workers/cleanup/sweep.py

TTL enforcement sweeps -- the actual deletion behind the retention policy
the Public Link Service (backend/src/routes/public.py) already checks at
read time.

Three independent sweeps:
1. cleanup_raw_uploads: deletes just the raw/<id>/ blob for every session
   older than RAW_UPLOAD_TTL_HOURS, regardless of status or owner --
   matches the spec literally ("Uploaded raw files auto-delete after 24
   hours"), no carve-out.
2. cleanup_expired_anonymous_sessions: deletes the whole Sessions row and
   every blob prefix for sessions owned by an anonymous user older than
   ANONYMOUS_ROAST_TTL_DAYS. Logged-in users are never touched here --
   spec says "configurable retention" for them but nothing configures it
   yet, so no number was invented (same reasoning already used for the
   Public Link's 410 check).
3. finalize_stale_interviews: ends interviews the browser never ended.
   Unlike the two above this deletes nothing -- it is a correctness sweep,
   not a retention one.

The anonymous Users row itself is deliberately NOT deleted -- a leftover
anon user with no sessions is harmless orphan data, not in scope here.
"""

import logging
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.src.db.sessions import Sessions
from backend.src.db.users import Users
from backend.src.config import (
    RAW_UPLOAD_TTL_HOURS,
    ANONYMOUS_ROAST_TTL_DAYS,
    INTERVIEW_STALE_AFTER_MINUTES,
    INTERVIEW_STALE_SWEEP_BATCH,
)
from backend.src.services.blob import delete_raw, delete_all_session_blobs
from backend.src.interview import finalizer as interview_finalizer
from backend.src.interview import service as interview_service

logger = logging.getLogger(__name__)


async def cleanup_raw_uploads(db: AsyncSession) -> int:
    cutoff = datetime.utcnow() - timedelta(hours=RAW_UPLOAD_TTL_HOURS)
    stmt = select(Sessions).where(
        Sessions.raw_deleted_at.is_(None),
        Sessions.created_at < cutoff,
    )
    result = await db.execute(stmt)
    sessions = result.scalars().all()

    count = 0
    for session in sessions:
        try:
            delete_raw(str(session.id))
        except Exception as e:
            logger.warning(f"Failed to delete raw blob for session {session.id}: {e}")
            continue
        session.raw_deleted_at = datetime.utcnow()
        db.add(session)
        count += 1

    if count:
        await db.commit()
    return count


async def cleanup_expired_anonymous_sessions(db: AsyncSession) -> int:
    cutoff = datetime.utcnow() - timedelta(days=ANONYMOUS_ROAST_TTL_DAYS)
    stmt = (
        select(Sessions)
        .join(Users, Sessions.user_id == Users.id)
        .where(
            Users.is_anonymous.is_(True),
            Sessions.created_at < cutoff,
        )
    )
    result = await db.execute(stmt)
    sessions = result.scalars().all()

    count = 0
    for session in sessions:
        try:
            delete_all_session_blobs(str(session.id))
        except Exception as e:
            logger.warning(f"Failed to delete blobs for session {session.id}: {e}")
            continue
        await db.delete(session)
        count += 1

    if count:
        await db.commit()
    return count


async def finalize_stale_interviews(db: AsyncSession) -> dict:
    """
    Ends interviews whose browser never ended them.

    An interview only ever left IN_PROGRESS when the tab called
    /interview/{id}/complete. Closing the tab does not do that -- the
    client's pagehide handler flushes the transcript and nothing more --
    so every abandoned tab left a row stuck IN_PROGRESS permanently,
    cluttering the candidate's own history and never reaching a score.

    Past INTERVIEW_STALE_AFTER_MINUTES there is provably nothing live to
    return to (the Live token expires in ~11 minutes), so these are safe to
    finalize. What they get is not a blanket ABANDONED: the same rule the
    complete route uses applies, so a transcript with real candidate speech
    is SCORED. Someone whose browser died three minutes from the end keeps
    the interview they sat through -- and the one-per-week slot it cost.

    One bad interview must not stop the sweep, so each is finalized in its
    own try. A Gemini outage (ScoringUnavailable) deliberately leaves the
    row IN_PROGRESS for the next pass rather than abandoning it: transient
    infrastructure trouble is not the candidate's fault.

    Capped per pass (INTERVIEW_STALE_SWEEP_BATCH), oldest first: the first
    run after this ships inherits every interview ever ended by closing a
    tab, and scoring is not free.
    """
    cutoff = datetime.utcnow() - timedelta(minutes=INTERVIEW_STALE_AFTER_MINUTES)
    interview_ids = await interview_service.list_stale_in_progress_interview_ids(
        db, cutoff, limit=INTERVIEW_STALE_SWEEP_BATCH
    )

    counts = {"scored": 0, "abandoned": 0, "deferred": 0}
    for interview_id in interview_ids:
        # Re-fetched per iteration rather than held from one bulk query:
        # each finalize commits, and a commit expires every other ORM object
        # in this session (the MissingGreenlet trap documented in
        # test_sweep.py's module docstring).
        interview = await interview_service.get_interview_session(db, interview_id)
        if interview is None:
            continue
        try:
            outcome, _ = await interview_finalizer.finalize_in_progress_interview(db, interview)
            counts[outcome] += 1
        except interview_finalizer.ScoringUnavailable as e:
            logger.warning(f"Scoring unavailable for stale interview {interview_id}, will retry: {e}")
            counts["deferred"] += 1
        except Exception:
            logger.exception(f"Failed to finalize stale interview {interview_id}")
            counts["deferred"] += 1

    return counts
