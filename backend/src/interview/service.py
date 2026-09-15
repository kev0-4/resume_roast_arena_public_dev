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

Transcript chunk shape (a plain dict, stored as a JSON list in
transcript.json). These are streamed up by the browser DURING the live
call, because the conversation itself happens between the browser and
Gemini and never passes through this server:
    {
        "seq": int,          # client-assigned, monotonic within one interview
        "speaker": str,      # "interviewer" | "candidate"
        "text": str,
        "at": str (ISO),
    }

Chunks are fragments, not whole utterances -- the Live API emits
transcription in small pieces as it goes. merge_transcript_chunks below is
what turns them back into readable speaker turns.
"""

import datetime
import json
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


def merge_transcript_chunks(existing: List[Dict[str, Any]], incoming: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Adds new chunks to the stored transcript, de-duplicated by seq and kept
    in seq order. Returns a NEW list (same immutable-update style as the
    rest of this codebase's artifact handling).

    De-duplication is what makes the endpoint safe to retry: the browser
    keeps a failed batch and re-sends it on the next flush, so the same seq
    genuinely does arrive twice. First write wins -- a replayed seq never
    overwrites what was already recorded.
    """
    by_seq: Dict[int, Dict[str, Any]] = {}
    for chunk in [*existing, *incoming]:
        seq = chunk.get("seq")
        if seq is None or seq in by_seq:
            continue
        by_seq[seq] = chunk
    return [by_seq[seq] for seq in sorted(by_seq)]


def merge_into_utterances(chunks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Collapses fragment chunks into one entry per speaker turn.

    The Live API transcribes continuously, so a single spoken sentence
    arrives as several chunks. Scoring (and anyone reading the transcript
    back) wants utterances, not fragments.

    Fragments carry their own leading/trailing spacing from the API, so
    they are concatenated as-is and stripped once at the end rather than
    joined on a separator -- joining on " " double-spaces most sentences
    and inserts spaces before punctuation.
    """
    utterances: List[Dict[str, Any]] = []
    for chunk in chunks:
        speaker = chunk.get("speaker")
        text = chunk.get("text") or ""
        if not text.strip():
            continue
        if utterances and utterances[-1]["speaker"] == speaker:
            utterances[-1]["text"] += text
        else:
            utterances.append({"speaker": speaker, "text": text, "at": chunk.get("at")})
    for utterance in utterances:
        utterance["text"] = utterance["text"].strip()
    return utterances


# ---------------------------------------------------------------------------
# DB CRUD
# ---------------------------------------------------------------------------


async def create_interview_session(
    db: AsyncSession,
    *,
    user_id: str | uuid.UUID,
    resume_session_id: str | uuid.UUID,
    job_description: str,
    interview_id: uuid.UUID | None = None,
) -> InterviewSessions:
    """
    interview_id may be supplied by the caller so the id exists BEFORE the
    row does. /start needs it to choose the interview's voice, which is
    derived from the id, while still minting the token before writing
    anything -- a mint failure then leaves nothing to clean up.
    """
    # turn_count / max_turns are vestigial: a live conversation has no
    # turns to count, and its length is bounded by the token's expiry
    # instead. The columns are written as zeroes rather than dropped --
    # max_turns is NOT NULL, and a destructive migration is the wrong risk
    # to take while production's automated migration path is this new.
    # Flagged for a later cleanup migration.
    interview = InterviewSessions(
        id=interview_id or uuid.uuid4(),
        user_id=user_id,
        resume_session_id=resume_session_id,
        status=InterviewStatusEnum.IN_PROGRESS.value,
        job_description=job_description,
        turn_count=0,
        max_turns=0,
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


async def set_plan(db: AsyncSession, interview: InterviewSessions, plan: Dict[str, Any]) -> InterviewSessions:
    interview.plan = plan
    interview.current_round = 0
    interview.updated_at = datetime.datetime.utcnow()
    try:
        await db.commit()
        await db.refresh(interview)
    except Exception:
        await db.rollback()
        raise
    return interview


async def questions_already_asked(db: AsyncSession, user_id) -> List[str]:
    """
    Every question id this user has already been planned, oldest first.

    The planner is otherwise given the resume and the job description and
    nothing else, so it has no way to avoid repeating itself -- and it
    does. Across one real account's eight interviews, from one resume
    against eight DIFFERENT job descriptions, `lru-cache-design` was
    chosen five times. A bigger catalogue slows that down; it does not
    stop it, because the model keeps picking the best fit for a resume
    that has not changed.

    Read from `plan` rather than `round_results`: a question the candidate
    was SHOWN has been spent even if they never submitted it, so an
    abandoned interview must not recycle its questions.

    Oldest first, because the caller needs least-recently-seen when it has
    to allow a repeat after all.
    """
    stmt = (
        select(InterviewSessions.plan)
        .where(InterviewSessions.user_id == user_id)
        .where(InterviewSessions.plan.isnot(None))
        .order_by(InterviewSessions.created_at.asc())
    )
    rows = (await db.execute(stmt)).scalars().all()

    ordered: List[str] = []
    for plan in rows:
        for planned in (plan or {}).get("rounds", []):
            question_id = planned.get("question_id")
            if question_id and question_id not in ordered:
                ordered.append(question_id)
    return ordered


async def record_round_result(
    db: AsyncSession, interview: InterviewSessions, result: Dict[str, Any]
) -> InterviewSessions:
    """
    Appends one exercise result and advances the round pointer.

    The pointer lives here rather than on the client so a submission
    cannot be replayed for a second grading, and a client cannot jump
    ahead to a round it prefers. Re-assigned rather than mutated in place:
    SQLAlchemy does not reliably detect in-place mutation of a JSONB list.
    """
    interview.round_results = [*(interview.round_results or []), result]
    interview.current_round = (interview.current_round or 0) + 1
    interview.updated_at = datetime.datetime.utcnow()
    try:
        await db.commit()
        await db.refresh(interview)
    except Exception:
        await db.rollback()
        raise
    return interview


def grade_reported_cases(
    question: Dict[str, Any], reported: List[Dict[str, Any]]
) -> Dict[str, Any]:
    """
    Compares the outputs the browser reported against the expected values,
    which never left this process.

    This is what makes hidden tests genuinely hidden rather than merely
    undisplayed: the candidate's machine ran the code and said what it
    produced, but only the server knows what it should have produced.

    Client-reported, so it inherits the same trust boundary as the
    transcript -- a determined client could lie about its outputs. It is
    not the score on its own; it is evidence handed to the reviewer, and
    the reviewer reads the actual code.
    """
    harness = question.get("harness") or {}
    by_name = {}
    for index, case in enumerate(harness.get("cases", [])):
        by_name[case.get("name") or f"case {index + 1}"] = case

    visible_passed = visible_total = hidden_passed = hidden_total = 0
    failed_hidden: List[str] = []

    for item in reported:
        case = by_name.get(item.get("name"))
        if case is None:
            continue
        expected = json.dumps(case.get("expected"), sort_keys=True, separators=(",", ":"))
        try:
            got = json.dumps(json.loads(item.get("got") or "null"), sort_keys=True, separators=(",", ":"))
        except (ValueError, TypeError):
            got = None
        passed = got == expected

        if case.get("hidden"):
            hidden_total += 1
            hidden_passed += 1 if passed else 0
            if not passed:
                failed_hidden.append(case.get("name", "?"))
        else:
            visible_total += 1
            visible_passed += 1 if passed else 0

    return {
        "visible_passed": visible_passed,
        "visible_total": visible_total,
        "hidden_passed": hidden_passed,
        "hidden_total": hidden_total,
        "failed_hidden": failed_hidden,
    }


def score_mcq(question: Dict[str, Any], answers: List[int]) -> Dict[str, Any]:
    """
    Auto-scores an MCQ round. No model in the loop: the answer key is right
    here, so grading is deterministic, instant and free.

    Unanswered questions score zero rather than raising -- a candidate who
    ran out of time still gets a graded round.
    """
    questions = question.get("questions", [])
    correct = 0
    detail = []
    for index, q in enumerate(questions):
        given = answers[index] if index < len(answers) else None
        hit = given == q["answer"]
        correct += 1 if hit else 0
        detail.append(
            {
                "prompt": q["prompt"],
                "given": given,
                "answer": q["answer"],
                "correct": hit,
                "why": q.get("why", ""),
            }
        )

    total = len(questions) or 1
    return {
        "correct": correct == total,
        "complexity": "n/a",
        "strengths": [f"{correct} of {total} correct."],
        "problems": [f"Got wrong: {d['prompt'][:70]}" for d in detail if not d["correct"]] or [],
        "interviewer_notes": (
            f"Scored {correct}/{total}. Press on: "
            + "; ".join(d["prompt"][:60] for d in detail if not d["correct"])
            if correct < total
            else f"Scored {correct}/{total} -- clean sweep, so push somewhere harder."
        ),
        # Map to the same 1-10 band every other round uses, so blending
        # later does not have to special-case MCQ.
        "score": max(1, round(1 + 9 * (correct / total))),
        "detail": detail,
    }


async def mark_interview_abandoned(db: AsyncSession, interview: InterviewSessions) -> InterviewSessions:
    """
    For a session that produced no candidate speech at all -- joined and
    left, or never unmuted. Deliberately NOT scored: it would cost a Gemini
    call to grade silence, and a score off an empty transcript has no
    business on the leaderboard.
    """
    interview.status = InterviewStatusEnum.ABANDONED.value
    interview.completed_at = datetime.datetime.utcnow()
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
