"""
Tests against real Postgres (no mocks -- same philosophy as
backend/src/routes/test_leaderboard.py). Same asyncio.run()-per-test +
engine.dispose() pattern as that file, for the same reason (the module-
level async engine singleton binds to whichever event loop first touches
it).

Every ORM object's id is captured into a plain variable IMMEDIATELY after
its own creation/commit, never read again from the object later -- the
same MissingGreenlet gotcha documented throughout this codebase's other
tests: SQLAlchemy's default expire_on_commit=True expires EVERY tracked
object's attributes on ANY commit in that session, not just the object
being committed, so touching user.id again after a *later* commit (e.g.
create_resume_session's own internal commit) raises MissingGreenlet
outside an awaited context.

The pure transcript-list helpers (new_transcript_entry, record_turn_answer,
append_question_turn) need no DB at all and are tested directly.
"""

import asyncio
import uuid
from datetime import datetime, timedelta

import pytest

from ..db.session import AsyncSessionLocal, engine
from ..services.session_service import create_sessions as create_resume_session
from ..services.user_service import get_or_create_users_from_claims
from . import service as interview_service
from ..db.interview_sessions import InterviewStatusEnum


def _run(coro_fn):
    async def wrapped():
        try:
            await coro_fn()
        finally:
            await engine.dispose()

    asyncio.run(wrapped())


async def _make_user_id(db, suffix: str):
    user = await get_or_create_users_from_claims(
        {
            "uid": f"interview-svc-test-{suffix}",
            "email": f"interview-svc-test-{suffix}@example.com",
            "email_verified": True,
            "display_name": f"InterviewSvcTest{suffix}",
            "picture": "",
            "is_anonymous": False,
        },
        db,
    )
    return user.id


async def _make_resume_session_id(db, user_id):
    resume_session = await create_resume_session(user_id=user_id, db=db)
    return resume_session.id


# ---------------------------------------------------------------------------
# Pure transcript helpers -- no DB
# ---------------------------------------------------------------------------


class TestNewTranscriptEntry:
    def test_shape(self):
        entry = interview_service.new_transcript_entry(0, "Q text", "path/to/audio.wav")
        assert entry["turn"] == 0
        assert entry["question_text"] == "Q text"
        assert entry["question_audio_path"] == "path/to/audio.wav"
        assert entry["answer_transcript"] is None
        assert entry["answer_audio_path"] is None
        assert entry["reaction_text"] is None


class TestRecordTurnAnswer:
    def test_fills_in_matching_turn(self):
        transcript = [interview_service.new_transcript_entry(0, "Q0", "a0.wav")]
        updated = interview_service.record_turn_answer(
            transcript, 0, answer_transcript="My answer", answer_audio_path="ans0.wav", reaction_text="Reaction"
        )
        assert updated[0]["answer_transcript"] == "My answer"
        assert updated[0]["answer_audio_path"] == "ans0.wav"
        assert updated[0]["reaction_text"] == "Reaction"

    def test_does_not_mutate_input(self):
        transcript = [interview_service.new_transcript_entry(0, "Q0", "a0.wav")]
        interview_service.record_turn_answer(
            transcript, 0, answer_transcript="X", answer_audio_path="y", reaction_text="z"
        )
        assert transcript[0]["answer_transcript"] is None

    def test_only_targets_the_matching_turn(self):
        transcript = [
            interview_service.new_transcript_entry(0, "Q0", "a0.wav"),
            interview_service.new_transcript_entry(1, "Q1", "a1.wav"),
        ]
        updated = interview_service.record_turn_answer(
            transcript, 1, answer_transcript="Ans1", answer_audio_path="ans1.wav", reaction_text="R1"
        )
        assert updated[0]["answer_transcript"] is None
        assert updated[1]["answer_transcript"] == "Ans1"

    def test_raises_on_unknown_turn(self):
        transcript = [interview_service.new_transcript_entry(0, "Q0", "a0.wav")]
        with pytest.raises(ValueError):
            interview_service.record_turn_answer(
                transcript, 5, answer_transcript="X", answer_audio_path="y", reaction_text="z"
            )


class TestAppendQuestionTurn:
    def test_appends_new_entry(self):
        transcript = [interview_service.new_transcript_entry(0, "Q0", "a0.wav")]
        updated = interview_service.append_question_turn(
            transcript, turn=1, question_text="Q1", question_audio_path="a1.wav"
        )
        assert len(updated) == 2
        assert updated[1]["turn"] == 1
        assert updated[1]["question_text"] == "Q1"

    def test_does_not_mutate_input(self):
        transcript = [interview_service.new_transcript_entry(0, "Q0", "a0.wav")]
        interview_service.append_question_turn(transcript, turn=1, question_text="Q1", question_audio_path="a1.wav")
        assert len(transcript) == 1


# ---------------------------------------------------------------------------
# DB CRUD + leaderboard, real Postgres
# ---------------------------------------------------------------------------


def test_create_and_get_interview_session():
    async def run():
        async with AsyncSessionLocal() as db:
            user_id = await _make_user_id(db, f"create-{uuid.uuid4().hex[:6]}")
            resume_session_id = await _make_resume_session_id(db, user_id)

            interview = await interview_service.create_interview_session(
                db=db,
                user_id=user_id,
                resume_session_id=resume_session_id,
                job_description="Backend engineer role.",
                max_turns=7,
            )
            interview_id = interview.id
            assert interview.status == InterviewStatusEnum.IN_PROGRESS.value
            assert interview.turn_count == 0
            assert interview.max_turns == 7

            fetched = await interview_service.get_interview_session(db, interview_id)
            assert fetched is not None
            assert fetched.id == interview_id

    _run(run)


def test_get_interview_session_returns_none_for_unknown_id():
    async def run():
        async with AsyncSessionLocal() as db:
            result = await interview_service.get_interview_session(db, uuid.uuid4())
            assert result is None

    _run(run)


def test_advance_turn_count_increments():
    async def run():
        async with AsyncSessionLocal() as db:
            user_id = await _make_user_id(db, f"advance-{uuid.uuid4().hex[:6]}")
            resume_session_id = await _make_resume_session_id(db, user_id)
            interview = await interview_service.create_interview_session(
                db=db, user_id=user_id, resume_session_id=resume_session_id, job_description="JD", max_turns=7
            )
            updated = await interview_service.advance_turn_count(db, interview)
            assert updated.turn_count == 1

    _run(run)


def test_finalize_interview_sets_completed_status_and_score():
    from .schemas import InterviewScoreResponse

    async def run():
        async with AsyncSessionLocal() as db:
            user_id = await _make_user_id(db, f"finalize-{uuid.uuid4().hex[:6]}")
            resume_session_id = await _make_resume_session_id(db, user_id)
            interview = await interview_service.create_interview_session(
                db=db, user_id=user_id, resume_session_id=resume_session_id, job_description="JD", max_turns=7
            )
            score = InterviewScoreResponse(
                score=8, strengths=["Specific."], weaknesses=["Could be terser."], next_steps=["Practice."]
            )
            updated = await interview_service.finalize_interview(db, interview, score)
            assert updated.status == InterviewStatusEnum.COMPLETED.value
            assert updated.score == 8
            assert updated.strengths == ["Specific."]
            assert updated.completed_at is not None

    _run(run)


def test_mark_interview_failed():
    async def run():
        async with AsyncSessionLocal() as db:
            user_id = await _make_user_id(db, f"fail-{uuid.uuid4().hex[:6]}")
            resume_session_id = await _make_resume_session_id(db, user_id)
            interview = await interview_service.create_interview_session(
                db=db, user_id=user_id, resume_session_id=resume_session_id, job_description="JD", max_turns=7
            )
            updated = await interview_service.mark_interview_failed(
                db, interview, error_code="GEMINI_ERROR", error_message="boom"
            )
            assert updated.status == InterviewStatusEnum.FAILED.value
            assert updated.error_code == "GEMINI_ERROR"

    _run(run)


async def _make_completed_interview_id(db, user_id, resume_session_id, *, score, completed_at=None):
    from .schemas import InterviewScoreResponse

    interview = await interview_service.create_interview_session(
        db=db, user_id=user_id, resume_session_id=resume_session_id, job_description="JD", max_turns=7
    )
    updated = await interview_service.finalize_interview(
        db, interview, InterviewScoreResponse(score=score, strengths=["s"], weaknesses=["w"], next_steps=["n"])
    )
    interview_id = updated.id
    if completed_at is not None:
        updated.completed_at = completed_at
        db.add(updated)
        await db.commit()
    return interview_id


def test_leaderboard_ranks_by_score_descending():
    async def run():
        async with AsyncSessionLocal() as db:
            user_id = await _make_user_id(db, f"lb-{uuid.uuid4().hex[:6]}")
            resume_session_id = await _make_resume_session_id(db, user_id)

            low = await _make_completed_interview_id(db, user_id, resume_session_id, score=3)
            high = await _make_completed_interview_id(db, user_id, resume_session_id, score=9)
            mid = await _make_completed_interview_id(db, user_id, resume_session_id, score=6)

            rows, total = await interview_service.get_interview_leaderboard(db=db, limit=1000, offset=0)
            ids_in_order = [r["id"] for r in rows]

            assert ids_in_order.index(high) < ids_in_order.index(mid) < ids_in_order.index(low)
            assert total >= 3

    _run(run)


def test_leaderboard_excludes_in_progress_interviews():
    async def run():
        async with AsyncSessionLocal() as db:
            user_id = await _make_user_id(db, f"inprog-{uuid.uuid4().hex[:6]}")
            resume_session_id = await _make_resume_session_id(db, user_id)

            in_progress = await interview_service.create_interview_session(
                db=db, user_id=user_id, resume_session_id=resume_session_id, job_description="JD", max_turns=7
            )
            in_progress_id = in_progress.id
            rows, _total = await interview_service.get_interview_leaderboard(db=db, limit=1000, offset=0)
            ids_in_order = [r["id"] for r in rows]
            assert in_progress_id not in ids_in_order

    _run(run)


def test_get_user_interview_leaderboard_position_returns_best_score():
    async def run():
        async with AsyncSessionLocal() as db:
            user_id = await _make_user_id(db, f"best-{uuid.uuid4().hex[:6]}")
            resume_session_id = await _make_resume_session_id(db, user_id)

            await _make_completed_interview_id(db, user_id, resume_session_id, score=4)
            await _make_completed_interview_id(db, user_id, resume_session_id, score=9)

            position = await interview_service.get_user_interview_leaderboard_position(db=db, user_id=user_id)
            assert position is not None
            assert position["score"] == 9
            assert position["rank"] >= 1

    _run(run)


def test_get_user_interview_leaderboard_position_none_when_no_completed_interview():
    async def run():
        async with AsyncSessionLocal() as db:
            user_id = await _make_user_id(db, f"none-{uuid.uuid4().hex[:6]}")
            position = await interview_service.get_user_interview_leaderboard_position(db=db, user_id=user_id)
            assert position is None

    _run(run)


def test_leaderboard_tie_broken_by_earlier_completed_at():
    async def run():
        async with AsyncSessionLocal() as db:
            user_id = await _make_user_id(db, f"tie-{uuid.uuid4().hex[:6]}")
            resume_session_id = await _make_resume_session_id(db, user_id)
            now = datetime.utcnow()

            earlier = await _make_completed_interview_id(
                db, user_id, resume_session_id, score=7, completed_at=now - timedelta(minutes=5)
            )
            later = await _make_completed_interview_id(db, user_id, resume_session_id, score=7, completed_at=now)

            rows, _total = await interview_service.get_interview_leaderboard(db=db, limit=1000, offset=0)
            ids_in_order = [r["id"] for r in rows]
            assert ids_in_order.index(earlier) < ids_in_order.index(later)

    _run(run)
