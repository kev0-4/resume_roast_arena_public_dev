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

The pure transcript helpers (merge_transcript_chunks, merge_into_utterances)
need no DB at all and are tested directly.
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


def _chunk(seq, speaker, text, at="2026-01-01T00:00:00Z"):
    return {"seq": seq, "speaker": speaker, "text": text, "is_final": True, "at": at}


class TestMergeTranscriptChunks:
    def test_appends_new_chunks(self):
        existing = [_chunk(0, "interviewer", "Hello.")]
        merged = interview_service.merge_transcript_chunks(existing, [_chunk(1, "candidate", "Hi.")])
        assert [c["seq"] for c in merged] == [0, 1]

    def test_deduplicates_replayed_seq(self):
        # The browser re-sends a batch it failed to deliver, so the same
        # seq genuinely arrives twice. First write must win.
        existing = [_chunk(0, "interviewer", "Original.")]
        merged = interview_service.merge_transcript_chunks(existing, [_chunk(0, "interviewer", "Replayed.")])
        assert len(merged) == 1
        assert merged[0]["text"] == "Original."

    def test_orders_by_seq_regardless_of_arrival_order(self):
        merged = interview_service.merge_transcript_chunks([], [_chunk(5, "candidate", "b"), _chunk(2, "candidate", "a")])
        assert [c["seq"] for c in merged] == [2, 5]

    def test_does_not_mutate_input(self):
        existing = [_chunk(0, "interviewer", "Hello.")]
        interview_service.merge_transcript_chunks(existing, [_chunk(1, "candidate", "Hi.")])
        assert len(existing) == 1

    def test_skips_chunks_with_no_seq(self):
        merged = interview_service.merge_transcript_chunks([], [{"speaker": "candidate", "text": "orphan"}])
        assert merged == []


class TestMergeIntoUtterances:
    def test_merges_consecutive_same_speaker_fragments(self):
        # This is the real shape the Live API emits: one sentence arriving
        # as several fragments, already carrying their own spacing.
        chunks = [
            _chunk(0, "interviewer", "So you say"),
            _chunk(1, "interviewer", " you led that migration."),
            _chunk(2, "candidate", "I did."),
        ]
        merged = interview_service.merge_into_utterances(chunks)
        assert len(merged) == 2
        assert merged[0] == {"speaker": "interviewer", "text": "So you say you led that migration.", "at": merged[0]["at"]}
        assert merged[1]["text"] == "I did."

    def test_starts_a_new_utterance_when_the_speaker_changes_back(self):
        chunks = [
            _chunk(0, "interviewer", "Q1"),
            _chunk(1, "candidate", "A1"),
            _chunk(2, "interviewer", "Q2"),
        ]
        merged = interview_service.merge_into_utterances(chunks)
        assert [u["speaker"] for u in merged] == ["interviewer", "candidate", "interviewer"]

    def test_drops_whitespace_only_fragments(self):
        chunks = [_chunk(0, "candidate", "   "), _chunk(1, "candidate", "Real answer.")]
        merged = interview_service.merge_into_utterances(chunks)
        assert len(merged) == 1
        assert merged[0]["text"] == "Real answer."

    def test_empty_transcript(self):
        assert interview_service.merge_into_utterances([]) == []


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
            )
            interview_id = interview.id
            assert interview.status == InterviewStatusEnum.IN_PROGRESS.value
            assert interview.turn_count == 0
            # Vestigial column, written as zero -- no turns exist any more.
            assert interview.max_turns == 0

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


def test_mark_interview_abandoned():
    async def run():
        async with AsyncSessionLocal() as db:
            user_id = await _make_user_id(db, f"abandon-{uuid.uuid4().hex[:6]}")
            resume_session_id = await _make_resume_session_id(db, user_id)
            interview = await interview_service.create_interview_session(
                db=db, user_id=user_id, resume_session_id=resume_session_id, job_description="JD"
            )
            updated = await interview_service.mark_interview_abandoned(db, interview)
            assert updated.status == InterviewStatusEnum.ABANDONED.value
            assert updated.completed_at is not None
            assert updated.score is None

    _run(run)


def test_leaderboard_excludes_abandoned_interviews():
    async def run():
        async with AsyncSessionLocal() as db:
            user_id = await _make_user_id(db, f"abandon-lb-{uuid.uuid4().hex[:6]}")
            resume_session_id = await _make_resume_session_id(db, user_id)
            interview = await interview_service.create_interview_session(
                db=db, user_id=user_id, resume_session_id=resume_session_id, job_description="JD"
            )
            abandoned = await interview_service.mark_interview_abandoned(db, interview)
            abandoned_id = abandoned.id

            rows, _total = await interview_service.get_interview_leaderboard(db=db, limit=1000, offset=0)
            assert abandoned_id not in [r["id"] for r in rows]

    _run(run)


def test_finalize_interview_sets_completed_status_and_score():
    from .schemas import InterviewScoreResponse

    async def run():
        async with AsyncSessionLocal() as db:
            user_id = await _make_user_id(db, f"finalize-{uuid.uuid4().hex[:6]}")
            resume_session_id = await _make_resume_session_id(db, user_id)
            interview = await interview_service.create_interview_session(
                db=db, user_id=user_id, resume_session_id=resume_session_id, job_description="JD"
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
                db=db, user_id=user_id, resume_session_id=resume_session_id, job_description="JD"
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
        db=db, user_id=user_id, resume_session_id=resume_session_id, job_description="JD"
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
                db=db, user_id=user_id, resume_session_id=resume_session_id, job_description="JD"
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
