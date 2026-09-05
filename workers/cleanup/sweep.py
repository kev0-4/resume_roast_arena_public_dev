"""
workers/cleanup/sweep.py

TTL enforcement sweeps -- the actual deletion behind the retention policy
the Public Link Service (backend/src/routes/public.py) already checks at
read time.

Two independent sweeps:
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

The anonymous Users row itself is deliberately NOT deleted -- a leftover
anon user with no sessions is harmless orphan data, not in scope here.
"""

import logging
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.src.db.sessions import Sessions
from backend.src.db.users import Users
from backend.src.config import RAW_UPLOAD_TTL_HOURS, ANONYMOUS_ROAST_TTL_DAYS
from backend.src.services.blob import delete_raw, delete_all_session_blobs

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
