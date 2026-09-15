"""
Tests against real Postgres + real Azurite (same philosophy as every other
test this session) -- sessions are backdated via a direct created_at update
after creation, since there's no practical way to wait out a real 24h/30d
TTL.

No pytest-asyncio in this codebase yet (and no existing async test pattern
to match) -- each test is a plain sync function that runs its async body
via asyncio.run(), the same pattern every manual e2e script this session
already uses.

Important: session_id is always captured as a plain value right after
create_sessions() returns, and every later lookup goes through
get_session(session_id=...) again rather than re-touching attributes on
the original ORM object. Any commit on that same db handle (create_sessions'
own internal commit, a manual commit, the sweep functions' commits) expires
ORM object attributes by default; touching an expired attribute afterward
(e.g. session.id) triggers an implicit lazy-reload that SQLAlchemy's asyncio
mode doesn't support outside an explicit await, raising MissingGreenlet.
"""

import asyncio
import uuid
from datetime import datetime, timedelta

from google.genai import errors as genai_errors
from sqlalchemy import select

from backend.src.db.session import AsyncSessionLocal, engine
from backend.src.db.sessions import JobStatusEnum
from backend.src.db.interview_sessions import InterviewSessions, InterviewStatusEnum
from backend.src.services.session_service import create_sessions, get_session
from backend.src.services.user_service import get_or_create_users_from_claims, create_anonymous_user
from backend.src.services.blob import (
    initialize_blob_storage,
    upload_raw,
    upload_roast,
    upload_render,
    upload_anonymized,
    upload_interview_transcript,
    blob_exists,
)
from backend.src.interview import service as interview_service
from backend.src.interview import llm_client as interview_llm_module
from backend.src.interview.schemas import InterviewScoreResponse

from workers.cleanup.sweep import (
    cleanup_raw_uploads,
    cleanup_expired_anonymous_sessions,
    finalize_stale_interviews,
)


async def _make_logged_in_user(db, suffix: str):
    return await get_or_create_users_from_claims(
        {
            "uid": f"cleanup-test-user-{suffix}",
            "email": f"cleanup-test-{suffix}@example.com",
            "email_verified": True,
            "display_name": f"CleanupTest{suffix}",
            "picture": "",
            "is_anonymous": False,
        },
        db,
    )


async def _backdate(db, session_id, **timedelta_kwargs):
    session = await get_session(db=db, session_id=session_id)
    session.created_at = datetime.utcnow() - timedelta(**timedelta_kwargs)
    db.add(session)
    await db.commit()


def _run(coro_fn):
    """
    Runs coro_fn() in its own event loop and disposes the shared async
    engine before that loop closes. The engine/connection pool in
    backend.src.db.session is a module-level singleton bound to whichever
    event loop first touches it -- asyncio.run() tears that loop down at
    the end of every test function, so without disposing here the next
    test's asyncio.run() (a *different* loop) reuses orphaned connections
    and asyncpg breaks ("another operation is in progress" / MissingGreenlet).
    """
    async def wrapped():
        try:
            await coro_fn()
        finally:
            await engine.dispose()

    asyncio.run(wrapped())


def test_raw_cleanup_deletes_old_blob_and_sets_flag():
    async def run():
        initialize_blob_storage()
        async with AsyncSessionLocal() as db:
            user = await _make_logged_in_user(db, "raw-old")
            session = await create_sessions(user_id=user.id, db=db)
            session_id = session.id

            raw_path = upload_raw(session_id=str(session_id), filename="r.pdf", file_bytes=b"pdf-bytes")
            session = await get_session(db=db, session_id=session_id)
            session.raw_blob_path = raw_path
            db.add(session)
            await db.commit()

            await _backdate(db, session_id, hours=25)

            assert blob_exists(raw_path) is True

            count = await cleanup_raw_uploads(db)

            assert count >= 1
            assert blob_exists(raw_path) is False
            refreshed = await get_session(db=db, session_id=session_id)
            assert refreshed.raw_deleted_at is not None

    _run(run)


def test_raw_cleanup_skips_recent_session():
    async def run():
        initialize_blob_storage()
        async with AsyncSessionLocal() as db:
            user = await _make_logged_in_user(db, "raw-fresh")
            session = await create_sessions(user_id=user.id, db=db)
            session_id = session.id

            raw_path = upload_raw(session_id=str(session_id), filename="r.pdf", file_bytes=b"pdf-bytes")
            session = await get_session(db=db, session_id=session_id)
            session.raw_blob_path = raw_path
            db.add(session)
            await db.commit()
            # created_at defaults to now() -- no backdating

            await cleanup_raw_uploads(db)

            assert blob_exists(raw_path) is True
            refreshed = await get_session(db=db, session_id=session_id)
            assert refreshed.raw_deleted_at is None

    _run(run)


def test_raw_cleanup_skips_already_cleaned_session():
    async def run():
        initialize_blob_storage()
        async with AsyncSessionLocal() as db:
            user = await _make_logged_in_user(db, "raw-already")
            session = await create_sessions(user_id=user.id, db=db)
            session_id = session.id

            await _backdate(db, session_id, hours=25)

            already_cleaned_at = datetime.utcnow() - timedelta(hours=1)
            session = await get_session(db=db, session_id=session_id)
            session.raw_deleted_at = already_cleaned_at
            db.add(session)
            await db.commit()

            await cleanup_raw_uploads(db)

            refreshed = await get_session(db=db, session_id=session_id)
            # unchanged -- the sweep must not re-touch an already-flagged session
            assert refreshed.raw_deleted_at == already_cleaned_at

    _run(run)


def test_anon_cleanup_deletes_old_session_and_all_blobs():
    async def run():
        initialize_blob_storage()
        async with AsyncSessionLocal() as db:
            user = await create_anonymous_user(db)
            session = await create_sessions(user_id=user.id, db=db)
            session_id = session.id

            raw_path = upload_raw(session_id=str(session_id), filename="r.pdf", file_bytes=b"x")
            roast_path = upload_roast(
                session_id=str(session_id),
                data={"verdict": "x", "roast": "x", "fixes": ["x"]},
            )
            render_path = upload_render(session_id=str(session_id), png_bytes=b"\x89PNG\r\n")

            session = await get_session(db=db, session_id=session_id)
            session.raw_blob_path = raw_path
            db.add(session)
            await db.commit()

            await _backdate(db, session_id, days=31)

            count = await cleanup_expired_anonymous_sessions(db)

            assert count >= 1
            assert blob_exists(raw_path) is False
            assert blob_exists(roast_path) is False
            assert blob_exists(render_path) is False
            refreshed = await get_session(db=db, session_id=session_id)
            assert refreshed is None

    _run(run)


def test_anon_cleanup_skips_recent_session():
    async def run():
        initialize_blob_storage()
        async with AsyncSessionLocal() as db:
            user = await create_anonymous_user(db)
            session = await create_sessions(user_id=user.id, db=db)
            session_id = session.id
            # created_at defaults to now() -- no backdating

            await cleanup_expired_anonymous_sessions(db)

            refreshed = await get_session(db=db, session_id=session_id)
            assert refreshed is not None

    _run(run)


def test_anon_cleanup_skips_logged_in_user_regardless_of_age():
    async def run():
        initialize_blob_storage()
        async with AsyncSessionLocal() as db:
            user = await _make_logged_in_user(db, "anon-skip")
            session = await create_sessions(user_id=user.id, db=db)
            session_id = session.id

            await _backdate(db, session_id, days=31)

            await cleanup_expired_anonymous_sessions(db)

            refreshed = await get_session(db=db, session_id=session_id)
            assert refreshed is not None

    _run(run)


# ---------------------------------------------------------------------------
# finalize_stale_interviews -- the sweep that ends interviews a closed tab
# never ended. Gemini's generate_score is monkeypatched (it costs money and
# is non-deterministic); everything else is real Postgres + Azurite, same as
# every sweep above.
# ---------------------------------------------------------------------------


ANONYMIZED_FIXTURE = {
    "content": {"blocks": {"experience": [{"text": "Built a caching layer for the checkout service."}]}},
}

ROAST_FIXTURE = {
    "verdict": "Competent but forgettable.",
    "roast": "The experience section is fine, but nothing here sticks.",
    "fixes": ["Quantify your impact."],
    "highlights": [],
    "quality_flags": [],
}


def _patch_score(monkeypatch, *, score=7, fail_with=None):
    """
    Replaces the one real Gemini call this sweep can make. Returns a counter
    so a test can assert that silence was never paid to grade.
    """
    calls = {"score": 0}

    async def fake_generate_score(prompt):
        calls["score"] += 1
        if fail_with is not None:
            raise fail_with
        return (
            InterviewScoreResponse(
                score=score, strengths=["Specific."], weaknesses=["Vague on scale."], next_steps=["Quantify."]
            ),
            {"input_tokens": 30, "output_tokens": 15},
            "fake-model",
        )

    monkeypatch.setattr(interview_llm_module, "generate_score", fake_generate_score)
    return calls


async def _make_done_resume_session_id(db, user_id):
    """A resume the interviewer can actually be rebuilt from, blobs and all."""
    session = await create_sessions(user_id=user_id, db=db)
    session_id = session.id
    upload_anonymized(session_id=str(session_id), data=ANONYMIZED_FIXTURE)
    upload_roast(session_id=str(session_id), data=ROAST_FIXTURE)
    session = await get_session(db=db, session_id=session_id)
    session.status = JobStatusEnum.DONE.value
    db.add(session)
    await db.commit()
    return session_id


def _interview_chunks(*pairs):
    return [
        {"seq": i, "speaker": speaker, "text": text, "is_final": True, "at": "2026-01-01T00:00:00Z"}
        for i, (speaker, text) in enumerate(pairs)
    ]


SPOKE = _interview_chunks(
    ("interviewer", "You say you built a caching layer. What kind?"),
    ("candidate", "Redis, read-through, in front of the checkout service."),
)

SILENCE = _interview_chunks(
    ("interviewer", "You say you built a caching layer. What kind?"),
    ("interviewer", "Take your time."),
)


async def _make_interview(db, suffix, *, chunks, stale_minutes=None, status=None):
    """
    An interview row plus its transcript blob, optionally backdated so the
    sweep sees it as dead. Returns the id as a plain UUID -- never re-read
    off the ORM object after a later commit (the MissingGreenlet trap in
    this module's docstring).
    """
    user = await _make_logged_in_user(db, suffix)
    user_id = user.id
    resume_session_id = await _make_done_resume_session_id(db, user_id)

    interview = await interview_service.create_interview_session(
        db,
        user_id=user_id,
        resume_session_id=resume_session_id,
        job_description="Backend engineer role at a startup.",
    )
    interview_id = interview.id

    blob_path = upload_interview_transcript(str(interview_id), chunks)
    row = (await db.execute(select(InterviewSessions).where(InterviewSessions.id == interview_id))).scalar_one()
    row.transcript_blob_path = blob_path
    if status is not None:
        row.status = status
        if status == InterviewStatusEnum.COMPLETED.value:
            # A COMPLETED interview always carries a score and a completion
            # time -- finalize_interview writes all three together. Setting
            # the status alone would fabricate a row production cannot
            # produce, and the interview leaderboard (which reasonably
            # assumes COMPLETED implies scored) 500s on it.
            row.score = 7
            row.completed_at = datetime.utcnow()
    if stale_minutes is not None:
        # Set explicitly so the column's own onupdate=now() does not
        # override it -- SQLAlchemy applies onupdate only when the column
        # is absent from the UPDATE's SET clause.
        row.updated_at = datetime.utcnow() - timedelta(minutes=stale_minutes)
    db.add(row)
    await db.commit()
    return interview_id


async def _interview_state(db, interview_id):
    row = (await db.execute(select(InterviewSessions).where(InterviewSessions.id == interview_id))).scalar_one()
    return row.status, row.score


def test_stale_interview_with_real_speech_is_scored_not_discarded(monkeypatch):
    # The whole reason this scores rather than blanket-abandoning: someone
    # whose tab died near the end keeps the interview they actually sat
    # through, and the one-per-week slot it cost them.
    calls = _patch_score(monkeypatch, score=8)

    async def run():
        initialize_blob_storage()
        async with AsyncSessionLocal() as db:
            interview_id = await _make_interview(
                db, f"sweep-scored-{uuid.uuid4().hex[:6]}", chunks=SPOKE, stale_minutes=61
            )

            counts = await finalize_stale_interviews(db)

            assert counts["scored"] >= 1
            status, score = await _interview_state(db, interview_id)
            assert status == InterviewStatusEnum.COMPLETED.value
            assert score == 8
            # >= rather than == 1: the sweep is global by design, and a
            # long-lived dev database has other genuinely stale interviews
            # in it that this run correctly finalizes too. The "never pay
            # twice for one interview" invariant is owned by
            # test_already_finished_interview_is_never_re_finalized.
            assert calls["score"] >= 1

    _run(run)


def test_stale_interview_with_no_candidate_speech_is_abandoned(monkeypatch):
    calls = _patch_score(monkeypatch)

    async def run():
        initialize_blob_storage()
        async with AsyncSessionLocal() as db:
            interview_id = await _make_interview(
                db, f"sweep-silent-{uuid.uuid4().hex[:6]}", chunks=SILENCE, stale_minutes=61
            )

            counts = await finalize_stale_interviews(db)

            assert counts["abandoned"] >= 1
            status, score = await _interview_state(db, interview_id)
            assert status == InterviewStatusEnum.ABANDONED.value
            assert score is None
            assert calls["score"] == 0, "grading silence must never cost a Gemini call"

    _run(run)


def test_interview_inside_the_window_is_left_alone(monkeypatch):
    # This window IS the rejoin window: an interview someone stepped away
    # from five minutes ago is still theirs to walk back into.
    _patch_score(monkeypatch)

    async def run():
        initialize_blob_storage()
        async with AsyncSessionLocal() as db:
            interview_id = await _make_interview(
                db, f"sweep-fresh-{uuid.uuid4().hex[:6]}", chunks=SPOKE, stale_minutes=5
            )

            await finalize_stale_interviews(db)

            status, _ = await _interview_state(db, interview_id)
            assert status == InterviewStatusEnum.IN_PROGRESS.value

    _run(run)


def test_already_finished_interview_is_never_re_finalized(monkeypatch):
    # Guards against the sweep re-scoring -- and re-paying for -- an
    # interview that already reached a terminal state.
    calls = _patch_score(monkeypatch)

    async def run():
        initialize_blob_storage()
        async with AsyncSessionLocal() as db:
            interview_id = await _make_interview(
                db,
                f"sweep-done-{uuid.uuid4().hex[:6]}",
                chunks=SPOKE,
                stale_minutes=500,
                status=InterviewStatusEnum.COMPLETED.value,
            )

            await finalize_stale_interviews(db)

            status, _ = await _interview_state(db, interview_id)
            assert status == InterviewStatusEnum.COMPLETED.value
            assert calls["score"] == 0

    _run(run)


def test_scoring_outage_defers_instead_of_abandoning(monkeypatch):
    # A Gemini outage must not be the thing that permanently abandons
    # someone's interview -- it stays IN_PROGRESS for the next sweep.
    outage = genai_errors.APIError(503, {"error": {"message": "unavailable", "status": "UNAVAILABLE"}})
    calls = _patch_score(monkeypatch, fail_with=outage)

    async def run():
        initialize_blob_storage()
        async with AsyncSessionLocal() as db:
            interview_id = await _make_interview(
                db, f"sweep-outage-{uuid.uuid4().hex[:6]}", chunks=SPOKE, stale_minutes=61
            )

            counts = await finalize_stale_interviews(db)

            assert counts["deferred"] >= 1
            status, score = await _interview_state(db, interview_id)
            assert status == InterviewStatusEnum.IN_PROGRESS.value
            assert score is None
            assert calls["score"] == 1

    _run(run)
