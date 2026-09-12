"""
backend/src/interview/service.py

DB orchestration for InterviewSessions, plus pure (no I/O) transcript-list
helpers -- mirrors backend/src/services/session_service.py's split between
CRUD functions and the leaderboard ranking queries.

Blob I/O (reading/writing transcript.json, uploading audio) deliberately
stays in the route layer (backend/src/routes/interview.py), matching how
backend/src/routes/public.py does its own asyncio.to_thread(read_blob, ...)
directly rather than through session_service.py -- this module owns the
database, not blob storage.

Transcript entry shape (a plain dict, stored as a JSON list in
transcript.json):
    {
        "turn": int,
        "question_text": str,
        "question_audio_path": str,
        "answer_transcript": str | None,   # filled in once answered
        "answer_audio_path": str | None,
        "reaction_text": str | None,
        "created_at": str (ISO),
    }
"""

import datetime
import uuid
from typing import Any, Dict, List, Optional

from sqlalchemy import func, select, or_
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.interview_sessions import InterviewSessions, InterviewStatusEnum
from ..db.users import Users
from .schemas import InterviewScoreResponse

# ---------------------------------------------------------------------------
# Pure transcript-list helpers (no I/O -- easy to unit test directly)
# ---------------------------------------------------------------------------


def new_transcript_entry(turn: int, question_text: str, question_audio_path: str) -> Dict[str, Any]:
    return {
        "turn": turn,
        "question_text": question_text,
        "question_audio_path": question_audio_path,
        "answer_transcript": None,
        "answer_audio_path": None,
        "reaction_text": None,
        "created_at": datetime.datetime.utcnow().isoformat(),
    }


def record_turn_answer(
    transcript: List[Dict[str, Any]],
    turn_number: int,
    *,
    answer_transcript: str,
    answer_audio_path: str,
    reaction_text: str,
) -> List[Dict[str, Any]]:
    """
    Returns a NEW list with the entry at `turn_number` filled in -- does
    not mutate the input, so callers always work from the return value
    (same immutable-update style the rest of this codebase's transcript/
    artifact handling uses).

    Raises:
        ValueError: if no entry with that turn number exists (shouldn't
                    happen given the route's own turn_number == turn_count
                    check, but this function doesn't trust that alone).
    """
    updated = []
    found = False
    for entry in transcript:
        if entry["turn"] == turn_number:
            entry = {
                **entry,
                "answer_transcript": answer_transcript,
                "answer_audio_path": answer_audio_path,
                "reaction_text": reaction_text,
            }
            found = True
        updated.append(entry)
    if not found:
        raise ValueError(f"No transcript entry for turn {turn_number}")
    return updated


def append_question_turn(
    transcript: List[Dict[str, Any]], *, turn: int, question_text: str, question_audio_path: str
) -> List[Dict[str, Any]]:
    return [*transcript, new_transcript_entry(turn, question_text, question_audio_path)]


# ---------------------------------------------------------------------------
# DB CRUD
# ---------------------------------------------------------------------------


async def create_interview_session(
    db: AsyncSession, *, user_id: str | uuid.UUID, resume_session_id: str | uuid.UUID, job_description: str, max_turns: int
) -> InterviewSessions:
    interview = InterviewSessions(
        id=uuid.uuid4(),
        user_id=user_id,
        resume_session_id=resume_session_id,
        status=InterviewStatusEnum.IN_PROGRESS.value,
        job_description=job_description,
        turn_count=0,
        max_turns=max_turns,
        started_at=datetime.datetime.utcnow(),
    )
    db.add(interview)
    try:
        await db.commit()
        await db.refresh(interview)
    except Exception:
        await db.rollback()
        raise
    return interview


async def get_interview_session(db: AsyncSession, interview_id: str | uuid.UUID) -> Optional[InterviewSessions]:
    stmt = select(InterviewSessions).where(InterviewSessions.id == interview_id)
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def set_transcript_blob_path(db: AsyncSession, interview: InterviewSessions, blob_path: str) -> InterviewSessions:
    interview.transcript_blob_path = blob_path
    interview.updated_at = datetime.datetime.utcnow()
    try:
        await db.commit()
        await db.refresh(interview)
    except Exception:
        await db.rollback()
        raise
    return interview


async def advance_turn_count(db: AsyncSession, interview: InterviewSessions) -> InterviewSessions:
    interview.turn_count += 1
    interview.updated_at = datetime.datetime.utcnow()
    try:
        await db.commit()
        await db.refresh(interview)
    except Exception:
        await db.rollback()
        raise
    return interview


async def finalize_interview(
    db: AsyncSession, interview: InterviewSessions, score_result: InterviewScoreResponse
) -> InterviewSessions:
    interview.status = InterviewStatusEnum.COMPLETED.value
    interview.score = score_result.score
    interview.strengths = score_result.strengths
    interview.weaknesses = score_result.weaknesses
    interview.next_steps = score_result.next_steps
    interview.completed_at = datetime.datetime.utcnow()
    interview.updated_at = datetime.datetime.utcnow()
    try:
        await db.commit()
        await db.refresh(interview)
    except Exception:
        await db.rollback()
        raise
    return interview


async def mark_interview_failed(
    db: AsyncSession, interview: InterviewSessions, *, error_code: str, error_message: str
) -> InterviewSessions:
    interview.status = InterviewStatusEnum.FAILED.value
    interview.error_code = error_code
    interview.error_message = error_message
    interview.updated_at = datetime.datetime.utcnow()
    try:
        await db.commit()
        await db.refresh(interview)
    except Exception:
        await db.rollback()
        raise
    return interview


# ---------------------------------------------------------------------------
# Leaderboard -- mirrors session_service.py's get_leaderboard/get_session_rank/
# get_user_leaderboard_position exactly, scoped to COMPLETED interviews only
# and ordered by score DESC / completed_at ASC instead of composite_score/
# created_at (a different metric, a different tiebreak field, but the same
# shape of query).
# ---------------------------------------------------------------------------


def _interview_eligible_clause():
    return (InterviewStatusEnum.COMPLETED.value == InterviewSessions.status,)


async def get_interview_leaderboard(db: AsyncSession, limit: int = 20, offset: int = 0) -> tuple[list[dict], int]:
    eligible = _interview_eligible_clause()

    count_stmt = (
        select(func.count())
        .select_from(InterviewSessions)
        .join(Users, InterviewSessions.user_id == Users.id)
        .where(*eligible)
    )
    total = (await db.execute(count_stmt)).scalar_one()

    rows_stmt = (
        select(
            InterviewSessions.id,
            InterviewSessions.score,
            InterviewSessions.completed_at,
            Users.display_name,
        )
        .join(Users, InterviewSessions.user_id == Users.id)
        .where(*eligible)
        .order_by(InterviewSessions.score.desc(), InterviewSessions.completed_at.asc())
        .limit(limit)
        .offset(offset)
    )
    result = await db.execute(rows_stmt)
    rows = [
        {
            "id": row.id,
            "score": row.score,
            "completed_at": row.completed_at,
            "display_name": row.display_name,
        }
        for row in result.all()
    ]
    return rows, total


async def get_interview_rank(db: AsyncSession, *, score: int, completed_at: datetime.datetime) -> tuple[int, int]:
    eligible = _interview_eligible_clause()

    sorts_ahead = or_(
        InterviewSessions.score > score,
        (InterviewSessions.score == score) & (InterviewSessions.completed_at < completed_at),
    )

    total_stmt = (
        select(func.count())
        .select_from(InterviewSessions)
        .join(Users, InterviewSessions.user_id == Users.id)
        .where(*eligible)
    )
    ahead_stmt = total_stmt.where(sorts_ahead)

    total = (await db.execute(total_stmt)).scalar_one()
    ahead = (await db.execute(ahead_stmt)).scalar_one()
    return ahead + 1, total


async def get_user_interview_leaderboard_position(db: AsyncSession, *, user_id: str | uuid.UUID) -> Optional[dict]:
    """The signed-in user's single best-scoring COMPLETED interview, ranked."""
    eligible = _interview_eligible_clause()

    best_stmt = (
        select(InterviewSessions.id, InterviewSessions.score, InterviewSessions.completed_at)
        .join(Users, InterviewSessions.user_id == Users.id)
        .where(InterviewSessions.user_id == user_id, *eligible)
        .order_by(InterviewSessions.score.desc(), InterviewSessions.completed_at.asc())
        .limit(1)
    )
    best = (await db.execute(best_stmt)).first()
    if best is None:
        return None

    rank, total = await get_interview_rank(db=db, score=best.score, completed_at=best.completed_at)
    return {
        "rank": rank,
        "total": total,
        "interview_id": best.id,
        "score": best.score,
        "completed_at": best.completed_at,
    }
