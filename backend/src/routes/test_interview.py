"""
Tests against real Postgres + real Azurite (same philosophy as
test_public_data.py -- no mocks for infra). The two real Gemini calls
(llm_client, tts_client) ARE monkeypatched here, deliberately: a live
conversational feature calling the real API on every CI run would be
slow, cost money, and be flaky against network conditions -- this is a
new pattern for this codebase's test suite (nothing mocks Gemini
elsewhere), justified specifically because it lets these tests exercise
the turn_count/max_turns/idempotency/ownership logic for real without
depending on model output quality, which is exactly what needs to stay
fast and free in CI. The real Gemini/TTS call shape itself was verified
separately via a real, throwaway (uncommitted) script.

`from src.routes.interview import ...` / `from src.interview import
llm_client as interview_llm_module` (not backend.src...) -- same absolute-
import gotcha documented in test_leaderboard.py's own module docstring:
create_app() wires everything via `from src...`, so a monkeypatch on the
backend.src... module identity would be silently a no-op.

Every ORM object's id is captured into a plain variable immediately after
its own commit, never re-read from the object after a LATER commit on the
same session -- the MissingGreenlet gotcha documented throughout this
codebase's tests.
"""

import asyncio
import json
import uuid

import pytest
from fastapi.testclient import TestClient

from backend.src.db.session import AsyncSessionLocal, engine
from backend.src.services.session_service import create_sessions as create_resume_session, get_session
from backend.src.services.user_service import get_or_create_users_from_claims
from backend.src.services.blob import initialize_blob_storage, upload_anonymized, upload_roast
from backend.src.db.sessions import JobStatusEnum
from backend.src.db.interview_sessions import InterviewStatusEnum
from backend.src import create_app

from src.dependencies.auth import get_current_user
from src.interview import llm_client as interview_llm_module
from src.interview import tts_client as interview_tts_module
from src.interview.schemas import InterviewTurnResponse, InterviewScoreResponse


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
            "uid": f"interview-route-test-{suffix}",
            "email": f"interview-route-test-{suffix}@example.com",
            "email_verified": True,
            "display_name": f"InterviewRouteTest{suffix}",
            "picture": "",
            "is_anonymous": False,
        },
        db,
    )
    return user.id


ANONYMIZED_FIXTURE = {
    "content": {"blocks": {"experience": [{"text": "Built a caching layer for the checkout service."}]}},
}

ROAST_FIXTURE = {
    "verdict": "Competent but forgettable.",
    "roast": "The experience section is fine, but nothing here sticks.",
    "fixes": ["Quantify your impact.", "Cut the buzzwords."],
    "highlights": [{"quote": "team player", "comment": "Everyone says this."}],
    "quality_flags": ["GENERIC_BULLETS"],
}


async def _make_done_resume_session_id(db, user_id) -> str:
    initialize_blob_storage()
    session = await create_resume_session(user_id=user_id, db=db)
    session_id = session.id
    upload_anonymized(session_id=str(session_id), data=ANONYMIZED_FIXTURE)
    upload_roast(session_id=str(session_id), data=ROAST_FIXTURE)
    session = await get_session(session_id=session_id, db=db)
    session.status = JobStatusEnum.DONE.value
    db.add(session)
    await db.commit()
    return str(session_id)


class _FakeCurrUser:
    def __init__(self, user_id):
        self.id = user_id


def _patch_llm_and_tts(monkeypatch, *, is_final_turn=False):
    async def fake_generate_opening_question(prompt):
        return (
            InterviewTurnResponse(
                answer_transcript="", reaction_text="", next_question="What did you actually build?", is_final_turn=False
            ),
            {"input_tokens": 10, "output_tokens": 5},
            "fake-model",
        )

    async def fake_generate_turn_response(prompt, audio_bytes, audio_mime_type):
        return (
            InterviewTurnResponse(
                answer_transcript="I built a caching layer.",
                reaction_text="Vague. What kind of cache?",
                next_question="What eviction policy did you use?",
                is_final_turn=is_final_turn,
            ),
            {"input_tokens": 20, "output_tokens": 10},
            "fake-model",
        )

    async def fake_generate_score(prompt):
        return (
            InterviewScoreResponse(score=7, strengths=["Specific."], weaknesses=["Vague on scale."], next_steps=["Quantify."]),
            {"input_tokens": 30, "output_tokens": 15},
            "fake-model",
        )

    async def fake_synthesize_speech(text, *, voice_name="Kore"):
        return b"RIFF....WAVEfmt fake audio bytes", "audio/wav"

    monkeypatch.setattr(interview_llm_module, "generate_opening_question", fake_generate_opening_question)
    monkeypatch.setattr(interview_llm_module, "generate_turn_response", fake_generate_turn_response)
    monkeypatch.setattr(interview_llm_module, "generate_score", fake_generate_score)
    monkeypatch.setattr(interview_tts_module, "synthesize_speech", fake_synthesize_speech)


class TestStartInterview:
    def test_success(self, monkeypatch):
        _patch_llm_and_tts(monkeypatch)
        holder = {}

        async def setup():
            async with AsyncSessionLocal() as db:
                user_id = await _make_user_id(db, f"start-{uuid.uuid4().hex[:6]}")
                resume_session_id = await _make_done_resume_session_id(db, user_id)
                holder["user_id"] = user_id
                holder["resume_session_id"] = resume_session_id

        _run(setup)

        app = create_app()
        app.dependency_overrides[get_current_user] = lambda: _FakeCurrUser(holder["user_id"])
        with TestClient(app) as client:
            resp = client.post(
                "/api/v1/interview/start",
                json={"resume_session_id": holder["resume_session_id"], "job_description": "Backend engineer role at a startup."},
            )

        assert resp.status_code == 201
        body = resp.json()
        assert body["status"] == InterviewStatusEnum.IN_PROGRESS.value
        assert body["turn_number"] == 0
        assert body["question_text"] == "What did you actually build?"
        assert body["question_audio_url"].endswith("/audio/0/prompt")

    def test_404_when_resume_session_not_found(self, monkeypatch):
        _patch_llm_and_tts(monkeypatch)
        holder = {}

        async def setup():
            async with AsyncSessionLocal() as db:
                holder["user_id"] = await _make_user_id(db, f"start404-{uuid.uuid4().hex[:6]}")

        _run(setup)

        app = create_app()
        app.dependency_overrides[get_current_user] = lambda: _FakeCurrUser(holder["user_id"])
        with TestClient(app) as client:
            resp = client.post(
                "/api/v1/interview/start",
                json={"resume_session_id": str(uuid.uuid4()), "job_description": "Some job description text."},
            )
        assert resp.status_code == 404

    def test_403_when_not_owner(self, monkeypatch):
        _patch_llm_and_tts(monkeypatch)
        holder = {}

        async def setup():
            async with AsyncSessionLocal() as db:
                owner_id = await _make_user_id(db, f"owner-{uuid.uuid4().hex[:6]}")
                other_id = await _make_user_id(db, f"other-{uuid.uuid4().hex[:6]}")
                holder["resume_session_id"] = await _make_done_resume_session_id(db, owner_id)
                holder["other_id"] = other_id

        _run(setup)

        app = create_app()
        app.dependency_overrides[get_current_user] = lambda: _FakeCurrUser(holder["other_id"])
        with TestClient(app) as client:
            resp = client.post(
                "/api/v1/interview/start",
                json={"resume_session_id": holder["resume_session_id"], "job_description": "Some job description text."},
            )
        assert resp.status_code == 403

    def test_409_when_resume_not_done(self, monkeypatch):
        _patch_llm_and_tts(monkeypatch)
        holder = {}

        async def setup():
            async with AsyncSessionLocal() as db:
                user_id = await _make_user_id(db, f"notdone-{uuid.uuid4().hex[:6]}")
                session = await create_resume_session(user_id=user_id, db=db)
                holder["user_id"] = user_id
                holder["resume_session_id"] = str(session.id)

        _run(setup)

        app = create_app()
        app.dependency_overrides[get_current_user] = lambda: _FakeCurrUser(holder["user_id"])
        with TestClient(app) as client:
            resp = client.post(
                "/api/v1/interview/start",
                json={"resume_session_id": holder["resume_session_id"], "job_description": "Some job description text."},
            )
        assert resp.status_code == 409

    def test_422_when_job_description_too_short(self, monkeypatch):
        _patch_llm_and_tts(monkeypatch)
        holder = {}

        async def setup():
            async with AsyncSessionLocal() as db:
                user_id = await _make_user_id(db, f"short-{uuid.uuid4().hex[:6]}")
                holder["user_id"] = user_id
                holder["resume_session_id"] = await _make_done_resume_session_id(db, user_id)

        _run(setup)

        app = create_app()
        app.dependency_overrides[get_current_user] = lambda: _FakeCurrUser(holder["user_id"])
        with TestClient(app) as client:
            resp = client.post(
                "/api/v1/interview/start",
                json={"resume_session_id": holder["resume_session_id"], "job_description": "too short"},
            )
        assert resp.status_code == 422


def _start_interview(app, user_id, resume_session_id) -> dict:
    app.dependency_overrides[get_current_user] = lambda: _FakeCurrUser(user_id)
    with TestClient(app) as client:
        resp = client.post(
            "/api/v1/interview/start",
            json={"resume_session_id": resume_session_id, "job_description": "Backend engineer role at a startup."},
        )
    assert resp.status_code == 201
    return resp.json()


class TestSubmitTurn:
    def test_success_non_final_advances_turn_count(self, monkeypatch):
        _patch_llm_and_tts(monkeypatch, is_final_turn=False)
        holder = {}

        async def setup():
            async with AsyncSessionLocal() as db:
                user_id = await _make_user_id(db, f"turn-{uuid.uuid4().hex[:6]}")
                holder["user_id"] = user_id
                holder["resume_session_id"] = await _make_done_resume_session_id(db, user_id)

        _run(setup)

        app = create_app()
        start_body = _start_interview(app, holder["user_id"], holder["resume_session_id"])
        interview_id = start_body["interview_id"]

        with TestClient(app) as client:
            resp = client.post(
                f"/api/v1/interview/{interview_id}/turn",
                data={"turn_number": 0},
                files={"file": ("answer.webm", b"fake audio bytes", "audio/webm")},
            )

        assert resp.status_code == 200
        body = resp.json()
        assert body["is_final"] is False
        assert body["status"] == InterviewStatusEnum.IN_PROGRESS.value
        assert body["score"] is None
        assert body["next_question"] == "What eviction policy did you use?"

    def test_success_final_turn_completes_and_scores(self, monkeypatch):
        _patch_llm_and_tts(monkeypatch, is_final_turn=True)
        holder = {}

        async def setup():
            async with AsyncSessionLocal() as db:
                user_id = await _make_user_id(db, f"final-{uuid.uuid4().hex[:6]}")
                holder["user_id"] = user_id
                holder["resume_session_id"] = await _make_done_resume_session_id(db, user_id)

        _run(setup)

        app = create_app()
        start_body = _start_interview(app, holder["user_id"], holder["resume_session_id"])
        interview_id = start_body["interview_id"]

        with TestClient(app) as client:
            resp = client.post(
                f"/api/v1/interview/{interview_id}/turn",
                data={"turn_number": 0},
                files={"file": ("answer.webm", b"fake audio bytes", "audio/webm")},
            )

        assert resp.status_code == 200
        body = resp.json()
        assert body["is_final"] is True
        assert body["status"] == InterviewStatusEnum.COMPLETED.value
        assert body["score"] == 7
        assert body["strengths"] == ["Specific."]

    def test_404_for_non_owner(self, monkeypatch):
        _patch_llm_and_tts(monkeypatch)
        holder = {}

        async def setup():
            async with AsyncSessionLocal() as db:
                owner_id = await _make_user_id(db, f"towner-{uuid.uuid4().hex[:6]}")
                other_id = await _make_user_id(db, f"tother-{uuid.uuid4().hex[:6]}")
                holder["owner_id"] = owner_id
                holder["other_id"] = other_id
                holder["resume_session_id"] = await _make_done_resume_session_id(db, owner_id)

        _run(setup)

        app = create_app()
        start_body = _start_interview(app, holder["owner_id"], holder["resume_session_id"])
        interview_id = start_body["interview_id"]

        app.dependency_overrides[get_current_user] = lambda: _FakeCurrUser(holder["other_id"])
        with TestClient(app) as client:
            resp = client.post(
                f"/api/v1/interview/{interview_id}/turn",
                data={"turn_number": 0},
                files={"file": ("answer.webm", b"fake audio bytes", "audio/webm")},
            )
        assert resp.status_code == 404

    def test_409_when_turn_number_mismatch(self, monkeypatch):
        _patch_llm_and_tts(monkeypatch)
        holder = {}

        async def setup():
            async with AsyncSessionLocal() as db:
                user_id = await _make_user_id(db, f"mismatch-{uuid.uuid4().hex[:6]}")
                holder["user_id"] = user_id
                holder["resume_session_id"] = await _make_done_resume_session_id(db, user_id)

        _run(setup)

        app = create_app()
        start_body = _start_interview(app, holder["user_id"], holder["resume_session_id"])
        interview_id = start_body["interview_id"]

        with TestClient(app) as client:
            resp = client.post(
                f"/api/v1/interview/{interview_id}/turn",
                data={"turn_number": 5},  # interview.turn_count is actually 0
                files={"file": ("answer.webm", b"fake audio bytes", "audio/webm")},
            )
        assert resp.status_code == 409

    def test_409_when_already_completed(self, monkeypatch):
        _patch_llm_and_tts(monkeypatch, is_final_turn=True)
        holder = {}

        async def setup():
            async with AsyncSessionLocal() as db:
                user_id = await _make_user_id(db, f"redo-{uuid.uuid4().hex[:6]}")
                holder["user_id"] = user_id
                holder["resume_session_id"] = await _make_done_resume_session_id(db, user_id)

        _run(setup)

        app = create_app()
        start_body = _start_interview(app, holder["user_id"], holder["resume_session_id"])
        interview_id = start_body["interview_id"]

        with TestClient(app) as client:
            first = client.post(
                f"/api/v1/interview/{interview_id}/turn",
                data={"turn_number": 0},
                files={"file": ("answer.webm", b"fake audio bytes", "audio/webm")},
            )
            assert first.status_code == 200
            assert first.json()["status"] == InterviewStatusEnum.COMPLETED.value

            second = client.post(
                f"/api/v1/interview/{interview_id}/turn",
                data={"turn_number": 1},
                files={"file": ("answer.webm", b"fake audio bytes", "audio/webm")},
            )
        assert second.status_code == 409


class TestGetInterview:
    def test_returns_transcript_and_404_for_non_owner(self, monkeypatch):
        _patch_llm_and_tts(monkeypatch)
        holder = {}

        async def setup():
            async with AsyncSessionLocal() as db:
                owner_id = await _make_user_id(db, f"gowner-{uuid.uuid4().hex[:6]}")
                other_id = await _make_user_id(db, f"gother-{uuid.uuid4().hex[:6]}")
                holder["owner_id"] = owner_id
                holder["other_id"] = other_id
                holder["resume_session_id"] = await _make_done_resume_session_id(db, owner_id)

        _run(setup)

        app = create_app()
        start_body = _start_interview(app, holder["owner_id"], holder["resume_session_id"])
        interview_id = start_body["interview_id"]

        app.dependency_overrides[get_current_user] = lambda: _FakeCurrUser(holder["owner_id"])
        with TestClient(app) as client:
            resp = client.get(f"/api/v1/interview/{interview_id}")
        assert resp.status_code == 200
        body = resp.json()
        assert body["job_description"] == "Backend engineer role at a startup."
        assert len(body["transcript"]) == 1
        assert body["transcript"][0]["question_text"] == "What did you actually build?"

        app.dependency_overrides[get_current_user] = lambda: _FakeCurrUser(holder["other_id"])
        with TestClient(app) as client:
            resp = client.get(f"/api/v1/interview/{interview_id}")
        assert resp.status_code == 404


class TestEligibility:
    def test_true_for_owner_of_done_session(self, monkeypatch):
        holder = {}

        async def setup():
            async with AsyncSessionLocal() as db:
                user_id = await _make_user_id(db, f"elig-{uuid.uuid4().hex[:6]}")
                holder["user_id"] = user_id
                holder["resume_session_id"] = await _make_done_resume_session_id(db, user_id)
                session = await get_session(session_id=holder["resume_session_id"], db=db)
                slug = f"elig{uuid.uuid4().hex[:6]}"
                session.slug = slug
                db.add(session)
                await db.commit()
                holder["slug"] = slug

        _run(setup)

        app = create_app()
        app.dependency_overrides[get_current_user] = lambda: _FakeCurrUser(holder["user_id"])
        with TestClient(app) as client:
            resp = client.get(f"/api/v1/interview/eligibility?slug={holder['slug']}")
        assert resp.status_code == 200
        body = resp.json()
        assert body["eligible"] is True
        assert body["resume_session_id"] == holder["resume_session_id"]

    def test_false_for_non_owner(self, monkeypatch):
        holder = {}

        async def setup():
            async with AsyncSessionLocal() as db:
                owner_id = await _make_user_id(db, f"eowner-{uuid.uuid4().hex[:6]}")
                other_id = await _make_user_id(db, f"eother-{uuid.uuid4().hex[:6]}")
                resume_session_id = await _make_done_resume_session_id(db, owner_id)
                session = await get_session(session_id=resume_session_id, db=db)
                slug = f"eneg{uuid.uuid4().hex[:6]}"
                session.slug = slug
                db.add(session)
                await db.commit()
                holder["other_id"] = other_id
                holder["slug"] = slug

        _run(setup)

        app = create_app()
        app.dependency_overrides[get_current_user] = lambda: _FakeCurrUser(holder["other_id"])
        with TestClient(app) as client:
            resp = client.get(f"/api/v1/interview/eligibility?slug={holder['slug']}")
        assert resp.status_code == 200
        assert resp.json()["eligible"] is False

    def test_false_when_slug_unknown(self, monkeypatch):
        holder = {}

        async def setup():
            async with AsyncSessionLocal() as db:
                holder["user_id"] = await _make_user_id(db, f"eunknown-{uuid.uuid4().hex[:6]}")

        _run(setup)

        app = create_app()
        app.dependency_overrides[get_current_user] = lambda: _FakeCurrUser(holder["user_id"])
        with TestClient(app) as client:
            resp = client.get("/api/v1/interview/eligibility?slug=does-not-exist")
        assert resp.status_code == 200
        assert resp.json()["eligible"] is False


class TestInterviewLeaderboardRoutes:
    def test_leaderboard_and_my_position(self, monkeypatch):
        _patch_llm_and_tts(monkeypatch, is_final_turn=True)
        holder = {}

        async def setup():
            async with AsyncSessionLocal() as db:
                user_id = await _make_user_id(db, f"lbroute-{uuid.uuid4().hex[:6]}")
                holder["user_id"] = user_id
                holder["resume_session_id"] = await _make_done_resume_session_id(db, user_id)

        _run(setup)

        app = create_app()
        start_body = _start_interview(app, holder["user_id"], holder["resume_session_id"])
        interview_id = start_body["interview_id"]

        with TestClient(app) as client:
            turn_resp = client.post(
                f"/api/v1/interview/{interview_id}/turn",
                data={"turn_number": 0},
                files={"file": ("answer.webm", b"fake audio bytes", "audio/webm")},
            )
        assert turn_resp.json()["status"] == InterviewStatusEnum.COMPLETED.value

        with TestClient(app) as client:
            lb_resp = client.get("/interview-leaderboard?limit=100")
        assert lb_resp.status_code == 200
        lb_body = lb_resp.json()
        assert any(e["score"] == 7 for e in lb_body["entries"])

        app.dependency_overrides[get_current_user] = lambda: _FakeCurrUser(holder["user_id"])
        with TestClient(app) as client:
            me_resp = client.get("/interview-leaderboard/me")
        assert me_resp.status_code == 200
        me_body = me_resp.json()
        assert me_body is not None
        assert me_body["score"] == 7

    def test_my_position_none_when_no_completed_interview(self, monkeypatch):
        holder = {}

        async def setup():
            async with AsyncSessionLocal() as db:
                holder["user_id"] = await _make_user_id(db, f"lbnone-{uuid.uuid4().hex[:6]}")

        _run(setup)

        app = create_app()
        app.dependency_overrides[get_current_user] = lambda: _FakeCurrUser(holder["user_id"])
        with TestClient(app) as client:
            resp = client.get("/interview-leaderboard/me")
        assert resp.status_code == 200
        assert resp.json() is None
