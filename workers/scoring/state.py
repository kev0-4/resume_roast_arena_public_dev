"""
workers/scoring/state.py

State transitions for scoring stage.

Responsibilities:
- Update session status
- Maintain lifecycle consistency
- No business logic
"""

from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime

from backend.src.db.sessions import Sessions, JobStatusEnum


# ------------------------------------------------------------
# SCORING
# ------------------------------------------------------------
async def mark_scoring(
    *,
    db: AsyncSession,
    session: Sessions,
) -> Sessions:
    """
    Transition:
    ANONYMIZED → SCORING
    """

    session.status = JobStatusEnum.SCORING
    session.updated_at = datetime.utcnow()

    db.add(session)
    return session


# ------------------------------------------------------------
# SCORED
# ------------------------------------------------------------
async def mark_scored(
    *,
    db: AsyncSession,
    session: Sessions,
) -> Sessions:
    """
    Transition:
    SCORING → SCORED
    """

    session.status = JobStatusEnum.SCORED
    session.updated_at = datetime.utcnow()

    db.add(session)
    return session


# ------------------------------------------------------------
# FAILED
# ------------------------------------------------------------
async def mark_failed(
    *,
    db: AsyncSession,
    session: Sessions,
    error_code: str,
    error_reason: str,
) -> Sessions:
    """
    Transition:
    ANY → FAILED
    """

    session.status = JobStatusEnum.FAILED
    session.error_code = error_code
    session.error_message = error_reason
    session.updated_at = datetime.utcnow()

    db.add(session)
    return session