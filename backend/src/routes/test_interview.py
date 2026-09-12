"""
Tests against real Postgres + real Azurite (same philosophy as
test_public_data.py -- no mocks for infra). The two real Gemini
interactions ARE monkeypatched here, deliberately:

- create_ephemeral_token mints a real billable credential against Google.
- generate_score costs money and its output is non-deterministic.

Neither can run on every CI push, and neither is what these tests are
about: what needs covering is ownership, status transitions, idempotency,
de-duplication and the empty-transcript path, all of which are entirely
ours. The real call shapes were verified separately against the live API.

Note what is NOT tested here and cannot be: the interview itself. The
conversation happens over a WebSocket between the candidate's browser and
Gemini, so no server-side test can observe it. That gap is covered by
manual verification with a real microphone, which is the step whose
absence sank the previous build.

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
import datetime
import uuid

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
from src.interview.schemas import InterviewScoreResponse


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


FAKE_TOKEN = "auth_tokens/fake-ephemeral-token"


def _patch_gemini(monkeypatch, *, score=7):
    """Replaces both real Gemini interactions. Returns a call counter so
    tests can assert scoring is NOT paid for twice."""
    calls = {"score": 0, "token": 0}

    async def fake_create_ephemeral_token():
        calls["token"] += 1
        expires_at = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(minutes=11)
        return FAKE_TOKEN, expires_at

    async def fake_generate_score(prompt):
        calls["score"] += 1
        return (
            InterviewScoreResponse(
                score=score, strengths=["Specific."], weaknesses=["Vague on scale."], next_steps=["Quantify."]
            ),
            {"input_tokens": 30, "output_tokens": 15},
            "fake-model",
        )

    monkeypatch.setattr(interview_llm_module, "create_ephemeral_token", fake_create_ephemeral_token)
    monkeypatch.setattr(interview_llm_module, "generate_score", fake_generate_score)
    return calls


def _start_interview(app, user_id, resume_session_id) -> dict:
    app.dependency_overrides[get_current_user] = lambda: _FakeCurrUser(user_id)
    with TestClient(app) as client:
        resp = client.post(
            "/api/v1/interview/start",
            json={"resume_session_id": resume_session_id, "job_description": "Backend engineer role at a startup."},
        )
    assert resp.status_code == 201, resp.text
    return resp.json()


def _chunks(*pairs, start_seq=0):
    """(speaker, text) pairs -> the wire shape the browser posts."""
    return [
        {
            "seq": start_seq + i,
            "speaker": speaker,
            "text": text,
            "is_final": True,
            "at": "2026-01-01T00:00:00Z",
        }
        for i, (speaker, text) in enumerate(pairs)
    ]


A_REAL_CONVERSATION = _chunks(
    ("interviewer", "You say you built a caching layer. What kind?"),
    ("candidate", "Redis, read-through, in front of the checkout service."),
    ("interviewer", "What was the hit rate?"),
    ("candidate", "Around ninety percent after we fixed the key scheme."),
)


class TestStartInterview:
    def test_returns_a_token_and_system_instruction(self, monkeypatch):
        _patch_gemini(monkeypatch)
        holder = {}

        async def setup():
            async with AsyncSessionLocal() as db:
                user_id = await _make_user_id(db, f"start-{uuid.uuid4().hex[:6]}")
                holder["user_id"] = user_id
                holder["resume_session_id"] = await _make_done_resume_session_id(db, user_id)

        _run(setup)

        app = create_app()
        body = _start_interview(app, holder["user_id"], holder["resume_session_id"])

        assert body["token"] == FAKE_TOKEN
        assert body["model"]
        assert body["expires_at"]
        # The instruction must carry the interview context, because the
        # browser never gets to assemble it itself.
        assert "caching layer" in body["system_instruction"]
        assert "Competent but forgettable." in body["system_instruction"]
        assert "Open the interview yourself" in body["system_instruction"]

    def test_never_leaks_the_real_api_key(self, monkeypatch):
        _patch_gemini(monkeypatch)
        holder = {}

        async def setup():
            async with AsyncSessionLocal() as db:
                user_id = await _make_user_id(db, f"leak-{uuid.uuid4().hex[:6]}")
                holder["user_id"] = user_id
                holder["resume_session_id"] = await _make_done_resume_session_id(db, user_id)

        _run(setup)

        app = create_app()
        body = _start_interview(app, holder["user_id"], holder["resume_session_id"])

        from src.config import GEMINI_API_KEY

        serialized = str(body)
        assert GEMINI_API_KEY is None or GEMINI_API_KEY not in serialized

    def test_404_when_resume_session_not_found(self, monkeypatch):
        _patch_gemini(monkeypatch)
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
        _patch_gemini(monkeypatch)
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
        _patch_gemini(monkeypatch)
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
        _patch_gemini(monkeypatch)
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


class TestPostTranscript:
    def _setup(self, monkeypatch, suffix):
        _patch_gemini(monkeypatch)
        holder = {}

        async def setup():
            async with AsyncSessionLocal() as db:
                user_id = await _make_user_id(db, f"{suffix}-{uuid.uuid4().hex[:6]}")
                holder["user_id"] = user_id
                holder["resume_session_id"] = await _make_done_resume_session_id(db, user_id)

        _run(setup)
        app = create_app()
        holder["app"] = app
        holder["interview_id"] = _start_interview(app, holder["user_id"], holder["resume_session_id"])["interview_id"]
        return holder

    def test_accepts_and_accumulates_chunks(self, monkeypatch):
        h = self._setup(monkeypatch, "tx")
        app = h["app"]

        with TestClient(app) as client:
            first = client.post(
                f"/api/v1/interview/{h['interview_id']}/transcript",
                json={"chunks": A_REAL_CONVERSATION[:2]},
            )
            second = client.post(
                f"/api/v1/interview/{h['interview_id']}/transcript",
                json={"chunks": A_REAL_CONVERSATION[2:]},
            )

        assert first.status_code == 200, first.text
        assert first.json() == {"accepted": 2, "total_chunks": 2}
        assert second.json() == {"accepted": 2, "total_chunks": 4}

    def test_replayed_batch_is_deduplicated(self, monkeypatch):
        # The browser retries a batch it failed to deliver. The same seqs
        # arrive twice and must not be double-recorded.
        h = self._setup(monkeypatch, "dedupe")
        app = h["app"]

        with TestClient(app) as client:
            client.post(
                f"/api/v1/interview/{h['interview_id']}/transcript", json={"chunks": A_REAL_CONVERSATION}
            )
            replay = client.post(
                f"/api/v1/interview/{h['interview_id']}/transcript", json={"chunks": A_REAL_CONVERSATION}
            )

        assert replay.json() == {"accepted": 0, "total_chunks": 4}

    def test_404_for_non_owner(self, monkeypatch):
        h = self._setup(monkeypatch, "txowner")
        app = h["app"]

        holder = {}

        async def make_other():
            async with AsyncSessionLocal() as db:
                holder["other_id"] = await _make_user_id(db, f"txother-{uuid.uuid4().hex[:6]}")

        _run(make_other)

        app.dependency_overrides[get_current_user] = lambda: _FakeCurrUser(holder["other_id"])
        with TestClient(app) as client:
            resp = client.post(
                f"/api/v1/interview/{h['interview_id']}/transcript", json={"chunks": A_REAL_CONVERSATION}
            )
        assert resp.status_code == 404

    def test_409_once_the_interview_is_complete(self, monkeypatch):
        h = self._setup(monkeypatch, "txdone")
        app = h["app"]

        with TestClient(app) as client:
            client.post(f"/api/v1/interview/{h['interview_id']}/transcript", json={"chunks": A_REAL_CONVERSATION})
            client.post(f"/api/v1/interview/{h['interview_id']}/complete", json={})
            late = client.post(
                f"/api/v1/interview/{h['interview_id']}/transcript",
                json={"chunks": _chunks(("candidate", "One more thing."), start_seq=99)},
            )
        assert late.status_code == 409

    def test_422_on_unknown_speaker(self, monkeypatch):
        h = self._setup(monkeypatch, "txspeaker")
        with TestClient(h["app"]) as client:
            resp = client.post(
                f"/api/v1/interview/{h['interview_id']}/transcript",
                json={"chunks": [{"seq": 0, "speaker": "narrator", "text": "hi", "is_final": True, "at": "x"}]},
            )
        assert resp.status_code == 422


class TestCompleteInterview:
    def _setup(self, monkeypatch, suffix, *, score=7):
        calls = _patch_gemini(monkeypatch, score=score)
        holder = {"calls": calls}

        async def setup():
            async with AsyncSessionLocal() as db:
                user_id = await _make_user_id(db, f"{suffix}-{uuid.uuid4().hex[:6]}")
                holder["user_id"] = user_id
                holder["resume_session_id"] = await _make_done_resume_session_id(db, user_id)

        _run(setup)
        app = create_app()
        holder["app"] = app
        holder["interview_id"] = _start_interview(app, holder["user_id"], holder["resume_session_id"])["interview_id"]
        return holder

    def test_scores_a_real_conversation(self, monkeypatch):
        h = self._setup(monkeypatch, "done")

        with TestClient(h["app"]) as client:
            client.post(f"/api/v1/interview/{h['interview_id']}/transcript", json={"chunks": A_REAL_CONVERSATION})
            resp = client.post(f"/api/v1/interview/{h['interview_id']}/complete", json={})

        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["status"] == InterviewStatusEnum.COMPLETED.value
        assert body["score"] == 7
        assert body["strengths"] == ["Specific."]

    def test_is_idempotent_and_does_not_pay_twice(self, monkeypatch):
        # The end button, the countdown and the socket close can all fire
        # at once, so this genuinely gets called more than once.
        h = self._setup(monkeypatch, "idem")

        with TestClient(h["app"]) as client:
            client.post(f"/api/v1/interview/{h['interview_id']}/transcript", json={"chunks": A_REAL_CONVERSATION})
            first = client.post(f"/api/v1/interview/{h['interview_id']}/complete", json={})
            second = client.post(f"/api/v1/interview/{h['interview_id']}/complete", json={})

        assert first.json() == second.json()
        assert h["calls"]["score"] == 1

    def test_silent_session_is_abandoned_not_scored(self, monkeypatch):
        # Joined and left without speaking. Grading silence would cost a
        # Gemini call and put a meaningless score on the leaderboard.
        h = self._setup(monkeypatch, "silent")

        with TestClient(h["app"]) as client:
            client.post(
                f"/api/v1/interview/{h['interview_id']}/transcript",
                json={"chunks": _chunks(("interviewer", "So, tell me what you built."))},
            )
            resp = client.post(f"/api/v1/interview/{h['interview_id']}/complete", json={})

        assert resp.status_code == 409
        assert h["calls"]["score"] == 0

        app = h["app"]
        app.dependency_overrides[get_current_user] = lambda: _FakeCurrUser(h["user_id"])
        with TestClient(app) as client:
            detail = client.get(f"/api/v1/interview/{h['interview_id']}")
        assert detail.json()["status"] == InterviewStatusEnum.ABANDONED.value

    def test_completely_empty_session_is_abandoned(self, monkeypatch):
        h = self._setup(monkeypatch, "empty")
        with TestClient(h["app"]) as client:
            resp = client.post(f"/api/v1/interview/{h['interview_id']}/complete", json={})
        assert resp.status_code == 409
        assert h["calls"]["score"] == 0

    def test_404_for_non_owner(self, monkeypatch):
        h = self._setup(monkeypatch, "cowner")
        holder = {}

        async def make_other():
            async with AsyncSessionLocal() as db:
                holder["other_id"] = await _make_user_id(db, f"cother-{uuid.uuid4().hex[:6]}")

        _run(make_other)

        h["app"].dependency_overrides[get_current_user] = lambda: _FakeCurrUser(holder["other_id"])
        with TestClient(h["app"]) as client:
            resp = client.post(f"/api/v1/interview/{h['interview_id']}/complete", json={})
        assert resp.status_code == 404


class TestGetInterview:
    def test_returns_merged_utterances_and_404s_for_others(self, monkeypatch):
        _patch_gemini(monkeypatch)
        holder = {}

        async def setup():
            async with AsyncSessionLocal() as db:
                user_id = await _make_user_id(db, f"get-{uuid.uuid4().hex[:6]}")
                holder["user_id"] = user_id
                holder["other_id"] = await _make_user_id(db, f"getother-{uuid.uuid4().hex[:6]}")
                holder["resume_session_id"] = await _make_done_resume_session_id(db, user_id)

        _run(setup)

        app = create_app()
        interview_id = _start_interview(app, holder["user_id"], holder["resume_session_id"])["interview_id"]

        # Fragments of one sentence, as the Live API actually emits them.
        fragments = _chunks(
            ("interviewer", "You say you built"),
            ("interviewer", " a caching layer."),
            ("candidate", "I did."),
        )
        with TestClient(app) as client:
            client.post(f"/api/v1/interview/{interview_id}/transcript", json={"chunks": fragments})
            resp = client.get(f"/api/v1/interview/{interview_id}")

        assert resp.status_code == 200
        body = resp.json()
        assert body["job_description"] == "Backend engineer role at a startup."
        assert len(body["transcript"]) == 2
        assert body["transcript"][0]["text"] == "You say you built a caching layer."
        assert body["transcript"][1]["speaker"] == "candidate"

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
        _patch_gemini(monkeypatch)
        holder = {}

        async def setup():
            async with AsyncSessionLocal() as db:
                user_id = await _make_user_id(db, f"lbroute-{uuid.uuid4().hex[:6]}")
                holder["user_id"] = user_id
                holder["resume_session_id"] = await _make_done_resume_session_id(db, user_id)

        _run(setup)

        app = create_app()
        interview_id = _start_interview(app, holder["user_id"], holder["resume_session_id"])["interview_id"]

        with TestClient(app) as client:
            client.post(f"/api/v1/interview/{interview_id}/transcript", json={"chunks": A_REAL_CONVERSATION})
            complete = client.post(f"/api/v1/interview/{interview_id}/complete", json={})
        assert complete.json()["status"] == InterviewStatusEnum.COMPLETED.value

        with TestClient(app) as client:
            lb_resp = client.get("/interview-leaderboard?limit=100")
        assert lb_resp.status_code == 200
        assert any(e["score"] == 7 for e in lb_resp.json()["entries"])

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
