"""
workers/renderer/state.py

State transitions for the render stage.
Only sets fields and calls db.add(); the processor commits.
"""

from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime

from backend.src.db.sessions import Sessions, JobStatusEnum


async def mark_rendering(
    *,
    db: AsyncSession,
    session: Sessions,
) -> Sessions:
    """ROASTED → RENDERING"""
    session.status = JobStatusEnum.RENDERING
    session.updated_at = datetime.utcnow()
    db.add(session)
    return session


async def mark_done(
    *,
    db: AsyncSession,
    session: Sessions,
    render_blob_path: str,
    composite_score: int,
) -> Sessions:
    """RENDERING → DONE"""
    session.status = JobStatusEnum.DONE
    session.render_blob_path = render_blob_path
    session.composite_score = composite_score
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
