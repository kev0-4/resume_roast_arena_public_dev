"""
workers/llm/state.py

State transitions for the LLM roast stage.
Only sets fields and calls db.add(); the processor commits.
"""

from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime

from backend.src.db.sessions import Sessions, JobStatusEnum


async def mark_roasting(
    *,
    db: AsyncSession,
    session: Sessions,
) -> Sessions:
    """SCORED → ROASTING"""
    session.status = JobStatusEnum.ROASTING
    session.updated_at = datetime.utcnow()
    db.add(session)
    return session


async def mark_roasted(
    *,
    db: AsyncSession,
    session: Sessions,
) -> Sessions:
    """ROASTING → ROASTED"""
    session.status = JobStatusEnum.ROASTED
    session.updated_at = datetime.utcnow()
    db.add(session)
    return session


async def mark_failed(
    *,
    db: AsyncSession,
    session: Sessions,
    error_code: str,
    error_reason: str,
) -> Sessions:
    """ANY → FAILED"""
    session.status = JobStatusEnum.FAILED
    session.error_code = error_code
    session.error_message = error_reason
    session.updated_at = datetime.utcnow()
    db.add(session)
    return session
