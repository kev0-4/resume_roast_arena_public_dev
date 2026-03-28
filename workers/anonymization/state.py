'''
mark_anonymizing(...)
mark_anonymized(...)
mark_failed(...)
'''

"""
State transitions for anonymization stage.

Responsibilities:
- Update session status
- Maintain consistency of lifecycle
- No business logic, no side effects beyond DB mutation
"""

from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime

from backend.src.db.sessions import Sessions, JobStatusEnum


# ------------------------------------------------------------
# ANONYMIZING
# ------------------------------------------------------------
async def mark_anonymizing(
    *,
    db: AsyncSession,
    session: Sessions,
) -> Sessions:
    """
    Transition:
    NORMALIZED → ANONYMIZING
    """

    session.status = JobStatusEnum.ANONYMIZING
    session.updated_at = datetime.utcnow()

    db.add(session)
    return session


# ------------------------------------------------------------
# ANONYMIZED
# ------------------------------------------------------------
async def mark_anonymized(
    *,
    db: AsyncSession,
    session: Sessions,
) -> Sessions:
    """
    Transition:
    ANONYMIZING → ANONYMIZED
    """

    session.status = JobStatusEnum.ANONYMIZED
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
    session.error_reason = error_reason
    session.updated_at = datetime.utcnow()

    db.add(session)
    return session  