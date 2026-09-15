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
import json
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
from src.interview.schemas import InterviewScoreResponse, ExerciseReview
from src.interview.planner import InterviewPlan, PlannedRound


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


def _patch_gemini(monkeypatch, *, score=7, plan_rounds=None, review_score=6):
    """
    Replaces every real Gemini interaction. Returns a call counter so tests
    can assert scoring is NOT paid for twice.

    generate_plan MUST be patched here even though /start tolerates a
    planner failure: without it the suite makes a real API call per
    started interview. That is slow, costs money, and is invisible --
    /start swallows the failure and falls back, so the tests still pass
    while quietly depending on a key CI deliberately does not set.
    """
    calls = {"score": 0, "token": 0, "plan": 0, "review": 0}

    calls["voices"] = []

    async def fake_create_ephemeral_token(system_instruction, voice=None):
        # Captured so a test can assert the interview context is pinned
        # into the TOKEN, not merely handed to the client -- and that every
        # segment of one interview asks for the same voice.
        calls["token"] += 1
        calls["instruction"] = system_instruction
        calls["voices"].append(voice)
        expires_at = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(minutes=11)
        return FAKE_TOKEN, expires_at

    async def fake_generate_score(prompt):
        calls["score"] += 1
        # Captured so tests can assert what scoring was actually TOLD about
        # skips and early endings -- that's the negative marking.
        calls["scoring_prompt"] = prompt
        return (
            InterviewScoreResponse(
                score=score, strengths=["Specific."], weaknesses=["Vague on scale."], next_steps=["Quantify."]
            ),
            {"input_tokens": 30, "output_tokens": 15},
            "fake-model",
        )

    async def fake_generate_plan(prompt):
        calls["plan"] += 1
        calls["plan_prompt"] = prompt
        rounds = plan_rounds if plan_rounds is not None else [
            {"kind": "CONVERSATION", "question_id": "", "minutes": 8, "focus": "Resume."},
        ]
        return (
            InterviewPlan(vertical="swe", rationale="test plan", rounds=[PlannedRound(**r) for r in rounds]),
            {"input_tokens": 800, "output_tokens": 200},
            "fake-model",
        )

    async def fake_review_submission(prompt):
        calls["review"] += 1
        calls["review_prompt"] = prompt
        return (
            ExerciseReview(
                correct=True,
                complexity="O(n log n)",
                strengths=["Sorted first."],
                problems=["Did not handle empty input."],
                interviewer_notes="Press on the empty-input case.",
                score=review_score,
            ),
            {"input_tokens": 400, "output_tokens": 120},
            "fake-model",
        )

    monkeypatch.setattr(interview_llm_module, "create_ephemeral_token", fake_create_ephemeral_token)
    monkeypatch.setattr(interview_llm_module, "generate_score", fake_generate_score)
    monkeypatch.setattr(interview_llm_module, "generate_plan", fake_generate_plan)
    monkeypatch.setattr(interview_llm_module, "review_submission", fake_review_submission)
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
    def test_pins_the_instruction_into_the_token(self, monkeypatch):
        # Regression guard for a bug found by probing the real API: minting
        # a token whose constraints name only the model makes the server
        # apply its own TEXT default and reject the AUDIO session at
        # connect. The config -- and so the instruction -- has to be pinned
        # into the token itself.
        calls = _patch_gemini(monkeypatch)
        holder = {}

        async def setup():
            async with AsyncSessionLocal() as db:
                user_id = await _make_user_id(db, f"pin-{uuid.uuid4().hex[:6]}")
                holder["user_id"] = user_id
                holder["resume_session_id"] = await _make_done_resume_session_id(db, user_id)

        _run(setup)

        app = create_app()
        body = _start_interview(app, holder["user_id"], holder["resume_session_id"])

        assert calls["token"] == 1
        assert calls["instruction"] == body["system_instruction"]
        assert "caching layer" in calls["instruction"]

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

        # The interviewer needs the authority to end the session and to
        # move past a question; both are tools, so they must reach the client.
        tool_names = {fn["name"] for tool in body["tools"] for fn in tool["function_declarations"]}
        assert tool_names == {"end_interview", "skip_question", "begin_round"}

        # The reference pane shows the resume, and must NOT leak the roast --
        # that would name every weak spot before it's asked about.
        assert "caching layer" in body["resume_text"]
        assert "Competent but forgettable." not in body["resume_text"]

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

    def test_skipped_questions_reach_the_scorer(self, monkeypatch):
        h = self._setup(monkeypatch, "skips")

        with TestClient(h["app"]) as client:
            client.post(f"/api/v1/interview/{h['interview_id']}/transcript", json={"chunks": A_REAL_CONVERSATION})
            resp = client.post(
                f"/api/v1/interview/{h['interview_id']}/complete",
                json={"skipped_questions": 3},
            )

        assert resp.status_code == 200
        prompt = h["calls"]["scoring_prompt"]
        assert "declined to answer 3 questions" in prompt
        assert "weigh heavily against the score" in prompt

    def test_no_conduct_block_when_nothing_went_wrong(self, monkeypatch):
        h = self._setup(monkeypatch, "clean")

        with TestClient(h["app"]) as client:
            client.post(f"/api/v1/interview/{h['interview_id']}/transcript", json={"chunks": A_REAL_CONVERSATION})
            client.post(f"/api/v1/interview/{h['interview_id']}/complete", json={"skipped_questions": 0})

        assert "HOW THE CANDIDATE CONDUCTED THEMSELVES" not in h["calls"]["scoring_prompt"]

    def test_time_wasting_end_is_still_scored_and_reaches_the_leaderboard(self, monkeypatch):
        # The product decision: being thrown out produces a genuinely bad
        # score rather than a free escape from a bad interview.
        h = self._setup(monkeypatch, "wasted")

        with TestClient(h["app"]) as client:
            client.post(f"/api/v1/interview/{h['interview_id']}/transcript", json={"chunks": A_REAL_CONVERSATION})
            resp = client.post(
                f"/api/v1/interview/{h['interview_id']}/complete",
                json={
                    "skipped_questions": 0,
                    "ended_early": {"reason": "Kept asking about lasagna.", "category": "TIME_WASTING"},
                },
            )

        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == InterviewStatusEnum.COMPLETED.value
        prompt = h["calls"]["scoring_prompt"]
        assert "ENDED this interview early for time-wasting" in prompt
        assert "Kept asking about lasagna." in prompt

    def test_complete_category_is_not_treated_as_a_negative(self, monkeypatch):
        h = self._setup(monkeypatch, "ranitscourse")

        with TestClient(h["app"]) as client:
            client.post(f"/api/v1/interview/{h['interview_id']}/transcript", json={"chunks": A_REAL_CONVERSATION})
            client.post(
                f"/api/v1/interview/{h['interview_id']}/complete",
                json={"ended_early": {"reason": "Covered enough ground.", "category": "COMPLETE"}},
            )

        prompt = h["calls"]["scoring_prompt"]
        assert "is NOT itself a negative" in prompt
        assert "time-wasting" not in prompt


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


CODE_ROUND_PLAN = [
    {"kind": "CONVERSATION", "question_id": "", "minutes": 8, "focus": "Resume."},
    {"kind": "EXERCISE", "question_id": "merge-intervals", "minutes": 10, "focus": "Arrays."},
]
MCQ_ROUND_PLAN = [
    {"kind": "CONVERSATION", "question_id": "", "minutes": 8, "focus": "Resume."},
    {"kind": "EXERCISE", "question_id": "mcq-ib-technicals", "minutes": 4, "focus": "Technicals."},
]


class TestRounds:
    def _setup(self, monkeypatch, suffix, plan_rounds, review_score=6):
        calls = _patch_gemini(monkeypatch, plan_rounds=plan_rounds, review_score=review_score)
        holder = {"calls": calls}

        async def setup():
            async with AsyncSessionLocal() as db:
                user_id = await _make_user_id(db, f"{suffix}-{uuid.uuid4().hex[:6]}")
                holder["user_id"] = user_id
                holder["resume_session_id"] = await _make_done_resume_session_id(db, user_id)

        _run(setup)
        app = create_app()
        holder["app"] = app
        holder["start"] = _start_interview(app, holder["user_id"], holder["resume_session_id"])
        holder["interview_id"] = holder["start"]["interview_id"]
        return holder

    def test_agenda_is_returned_at_start(self, monkeypatch):
        h = self._setup(monkeypatch, "agenda", CODE_ROUND_PLAN)
        agenda = h["start"]["agenda"]
        assert [a["label"] for a in agenda] == ["Conversation", "Coding"]

    def test_round_question_never_leaks_the_answer_key(self, monkeypatch):
        # An MCQ whose answers reach the browser is not a test.
        h = self._setup(monkeypatch, "leak", MCQ_ROUND_PLAN)
        app = h["app"]

        with TestClient(app) as client:
            # Round 0 is the conversation; the exercise is round 1.
            client.post(f"/api/v1/interview/{h['interview_id']}/advance", json={})
            resp = client.get(f"/api/v1/interview/{h['interview_id']}/round/1")

        assert resp.status_code == 200, resp.text
        body = resp.json()
        serialized = json.dumps(body)
        assert '"answer"' not in serialized
        assert '"why"' not in serialized
        assert "rubric" not in serialized
        # But it must still carry what the candidate needs to answer.
        assert len(body["question"]["questions"]) == 4
        assert len(body["question"]["questions"][0]["options"]) == 4

    def test_cannot_skip_ahead_to_a_later_round(self, monkeypatch):
        h = self._setup(monkeypatch, "skip", CODE_ROUND_PLAN)
        with TestClient(h["app"]) as client:
            resp = client.get(f"/api/v1/interview/{h['interview_id']}/round/1")
        assert resp.status_code == 409

    def test_mcq_is_scored_deterministically_without_a_model(self, monkeypatch):
        h = self._setup(monkeypatch, "mcq", MCQ_ROUND_PLAN)
        app = h["app"]

        with TestClient(app) as client:
            client.post(f"/api/v1/interview/{h['interview_id']}/advance", json={})
            # mcq-ib-technicals answer key is [1, 1, 2, 1]; get three right.
            resp = client.post(
                f"/api/v1/interview/{h['interview_id']}/round/1/submit",
                json={"mcq_answers": [1, 1, 2, 0], "seconds_taken": 90},
            )

        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert h["calls"]["review"] == 0, "MCQ must not spend a model call"
        assert [d["correct"] for d in body["mcq_detail"]] == [True, True, True, False]
        assert 1 <= body["score"] <= 10

    def test_submitted_round_cannot_be_replayed(self, monkeypatch):
        h = self._setup(monkeypatch, "replay", MCQ_ROUND_PLAN)
        with TestClient(h["app"]) as client:
            client.post(f"/api/v1/interview/{h['interview_id']}/advance", json={})
            first = client.post(
                f"/api/v1/interview/{h['interview_id']}/round/1/submit", json={"mcq_answers": [0, 0, 0, 0]}
            )
            # A second attempt at a better score must be refused.
            second = client.post(
                f"/api/v1/interview/{h['interview_id']}/round/1/submit", json={"mcq_answers": [1, 1, 2, 1]}
            )
        assert first.status_code == 200
        assert second.status_code == 409

    def test_code_round_result_hides_the_interviewer_notes(self, monkeypatch):
        # Those notes are the debrief's ammunition -- showing them would let
        # the candidate prepare for the exact question coming next.
        h = self._setup(monkeypatch, "notes", CODE_ROUND_PLAN)
        app = h["app"]

        with TestClient(app) as client:
            client.post(f"/api/v1/interview/{h['interview_id']}/advance", json={})
            resp = client.post(
                f"/api/v1/interview/{h['interview_id']}/round/1/submit",
                json={"answer": "def merge_intervals(x): return x", "language": "python", "pasted": True},
            )

        assert resp.status_code == 200
        body = resp.json()
        assert h["calls"]["review"] == 1
        assert "interviewer_notes" not in json.dumps(body)
        assert "Press on the empty-input case." not in json.dumps(body)
        assert body["problems"] == ["Did not handle empty input."]

    def test_a_second_interview_does_not_repeat_the_first_question(self, monkeypatch):
        # The bug: the planner is given the resume and the job description
        # and nothing else. One real account ran eight interviews from ONE
        # resume against eight DIFFERENT job descriptions and was handed
        # lru-cache-design five times.
        # From `src.*`, not `backend.src.*`: the two are distinct module
        # objects under this suite's dual sys.path, and a dependency
        # override only matches the exact function the app was built with.
        # Same reason get_current_user is imported the way it is above.
        from src.dependencies.rate_limit import check_interview_start_rate_limit

        h = self._setup(monkeypatch, "norepeat", CODE_ROUND_PLAN)
        app = h["app"]
        # One interview per account per week, and this test needs two.
        app.dependency_overrides[check_interview_start_rate_limit] = lambda: None

        first_question = h["start"]["agenda"]
        assert [a["label"] for a in first_question] == ["Conversation", "Coding"]

        second = _start_interview(app, h["user_id"], h["resume_session_id"])

        # The catalogue handed to the planner the second time must not
        # contain the question already spent on the first interview.
        prompt = h["calls"]["plan_prompt"]
        assert "merge-intervals" not in prompt, (
            "the second interview offered the planner a question this candidate has already sat"
        )
        assert "lru-cache-design" in prompt, "unseen questions must still be offered"
        assert second["interview_id"] != h["interview_id"]

    def test_a_graded_exercise_reaches_the_final_scorer(self, monkeypatch):
        # The bug this guards: round_results was stored, shown to the
        # candidate, fed to the debrief -- and never passed to scoring. One
        # real interview scored 10/10 on its coding round and came out with
        # a final score of 1, because the scorer was handed the transcript
        # and nothing else. That made the whole exercise feature decorative
        # as far as the leaderboard was concerned.
        h = self._setup(monkeypatch, "roundscore", CODE_ROUND_PLAN, review_score=10)
        app = h["app"]

        with TestClient(app) as client:
            client.post(f"/api/v1/interview/{h['interview_id']}/transcript", json={"chunks": A_REAL_CONVERSATION})
            client.post(f"/api/v1/interview/{h['interview_id']}/advance", json={})
            submit = client.post(
                f"/api/v1/interview/{h['interview_id']}/round/1/submit",
                json={"answer": "def merge_intervals(x): return x", "language": "python", "seconds_taken": 300},
            )
            complete = client.post(f"/api/v1/interview/{h['interview_id']}/complete", json={})

        assert submit.status_code == 200, submit.text
        assert submit.json()["score"] == 10
        assert complete.status_code == 200, complete.text

        prompt = h["calls"]["scoring_prompt"]
        assert "EXERCISES THEY ACTUALLY SAT" in prompt
        assert "10/10" in prompt
        assert "MUST move the final score" in prompt
        # The grader's findings travel with the score, so the scorer can
        # weigh a 10 that failed a hidden case differently from a clean one.
        assert "Did not handle empty input." in prompt
        assert "Press on the empty-input case." in prompt

    def test_conversation_only_interview_gets_no_exercise_block(self, monkeypatch):
        # An HR or IB candidate the planner correctly gave no exercise must
        # not be told they sat none -- that reads as a gap and would cap a
        # whole vertical for a decision the product made for them.
        h = self._setup(
            monkeypatch,
            "convonly",
            [{"kind": "CONVERSATION", "question_id": "", "minutes": 8, "focus": "Resume."}],
        )
        with TestClient(h["app"]) as client:
            client.post(f"/api/v1/interview/{h['interview_id']}/transcript", json={"chunks": A_REAL_CONVERSATION})
            resp = client.post(f"/api/v1/interview/{h['interview_id']}/complete", json={})

        assert resp.status_code == 200, resp.text
        assert "EXERCISES THEY ACTUALLY SAT" not in h["calls"]["scoring_prompt"]

    def test_one_voice_for_the_whole_interview(self, monkeypatch):
        # The interviewer must not become a different person after the
        # coding round. Every segment mints its own token, so they have to
        # agree on a voice without anything being stored.
        h = self._setup(monkeypatch, "onevoice", CODE_ROUND_PLAN)
        app = h["app"]

        with TestClient(app) as client:
            client.post(f"/api/v1/interview/{h['interview_id']}/advance", json={})
            client.post(
                f"/api/v1/interview/{h['interview_id']}/round/1/submit",
                json={"answer": "def merge_intervals(x): return x", "language": "python"},
            )
            client.post(f"/api/v1/interview/{h['interview_id']}/voice-token", json={})

        voices = h["calls"]["voices"]
        assert len(voices) >= 2, "expected a token at /start and another for the debrief"
        assert all(v == voices[0] for v in voices), f"voice changed mid-interview: {voices}"
        assert voices[0], "a voice must actually be chosen, not left to the API default"

    def test_different_interviews_get_different_voices(self, monkeypatch):
        # Variety across interviews is the point of deriving it rather than
        # pinning one globally. Sampled over many ids so this cannot pass by
        # luck on a single collision.
        from src.interview.llm_client import voice_for_interview
        from src.config import GEMINI_LIVE_VOICES

        picked = {voice_for_interview(uuid.uuid4()) for _ in range(300)}
        assert len(picked) > 1, "every interview drew the same voice"
        assert picked <= set(GEMINI_LIVE_VOICES)
        # A hash spread over 300 draws should reach most of a 20-voice list.
        assert len(picked) >= len(GEMINI_LIVE_VOICES) // 2

    def test_the_same_interview_always_resolves_to_one_voice(self, monkeypatch):
        from src.interview.llm_client import voice_for_interview

        interview_id = uuid.uuid4()
        assert len({voice_for_interview(interview_id) for _ in range(20)}) == 1
        # str and UUID forms must agree -- routes pass both.
        assert voice_for_interview(interview_id) == voice_for_interview(str(interview_id))

    def test_interviewer_is_told_its_own_agenda(self, monkeypatch):
        # Observed failure: asked to move to a coding round, the
        # interviewer replied "I have no coding round scheduled for you
        # today" while two exercises were scheduled. It had a begin_round
        # tool and no idea whether there was anything to begin.
        h = self._setup(monkeypatch, "agenda-known", CODE_ROUND_PLAN)
        instruction = h["calls"]["instruction"]

        assert "TODAY'S AGENDA" in instruction
        assert "Merge overlapping intervals" in instruction, "the scheduled exercise must be named"
        assert "Coding exercise" in instruction, "and its format stated"
        assert "you are here" in instruction
        assert "call begin_round to move to the next item" in instruction

    def test_interviewer_is_forbidden_from_narrating_the_next_screen(self, monkeypatch):
        # Observed: having finished the last round, the interviewer told the
        # candidate "the system will move you directly to the design
        # challenge next." No such round exists anywhere. Knowing the
        # agenda was not enough -- it had to be told not to predict the
        # screen at all, because it does not control it.
        h = self._setup(monkeypatch, "no-narrate", CODE_ROUND_PLAN)
        instruction = h["calls"]["instruction"]

        assert "NEVER NARRATE WHAT THE SCREEN IS ABOUT TO DO" in instruction
        assert "the system will move you to" in instruction
        assert "no design challenge" in instruction.lower() or "There was no design challenge" in instruction
        assert "call end_interview" in instruction

    def test_conversation_only_interview_is_told_there_is_nothing_next(self, monkeypatch):
        # The opposite failure: promising an exercise that does not exist.
        h = self._setup(
            monkeypatch,
            "agenda-empty",
            [{"kind": "CONVERSATION", "question_id": "", "minutes": 10, "focus": "Resume."}],
        )
        instruction = h["calls"]["instruction"]
        assert "There is nothing scheduled after this" in instruction
        assert "Do not promise the candidate an exercise" in instruction

    def test_agenda_follows_the_candidate_into_the_debrief(self, monkeypatch):
        h = self._setup(monkeypatch, "agenda-debrief", CODE_ROUND_PLAN)
        app = h["app"]

        with TestClient(app) as client:
            client.post(f"/api/v1/interview/{h['interview_id']}/advance", json={})
            client.post(
                f"/api/v1/interview/{h['interview_id']}/round/1/submit",
                json={"answer": "def merge_intervals(x): return x", "language": "python"},
            )
            voice = client.post(f"/api/v1/interview/{h['interview_id']}/voice-token", json={})

        instruction = voice.json()["system_instruction"]
        assert "TODAY'S AGENDA" in instruction
        # Round 1 is done, so nothing remains and it must not invent more.
        assert "There is nothing scheduled after this" in instruction

    def test_hidden_expected_values_never_reach_the_client(self, monkeypatch):
        # This is what makes hidden tests hidden rather than merely
        # undisplayed: the inputs must travel (the code runs in the
        # browser) but the expected outputs must not, or tweaking until the
        # visible tests go green is enough to game the round.
        from src.interview.catalogue import get_question, public_question

        entry = get_question("merge-intervals")
        pub = public_question(entry)
        cases = pub["harness"]["cases"]

        hidden = [c for c in cases if c.get("hidden")]
        visible = [c for c in cases if not c.get("hidden")]
        assert hidden, "expected some hidden cases"
        assert visible, "expected some visible cases"

        for case in hidden:
            assert "expected" not in case, f"hidden case {case.get('name')!r} leaked its expected value"
            # The inputs still have to be there or the code cannot be run.
            assert case.get("args") is not None or case.get("ops") is not None

        # Visible cases keep theirs: the worked examples print them anyway.
        for case in visible:
            assert "expected" in case

    def test_reported_outputs_are_graded_against_server_side_expectations(self, monkeypatch):
        from src.interview.catalogue import get_question
        from src.interview import service

        entry = get_question("merge-intervals")
        cases = entry["harness"]["cases"]

        # Claim every case produced exactly what it should.
        honest = [
            {"name": c["name"], "got": json.dumps(c["expected"], separators=(",", ":"))} for c in cases
        ]
        graded = service.grade_reported_cases(entry, honest)
        assert graded["hidden_passed"] == graded["hidden_total"] > 0
        assert graded["visible_passed"] == graded["visible_total"] > 0

        # Now claim a hidden case produced nonsense.
        hidden_name = next(c["name"] for c in cases if c.get("hidden"))
        lying = [
            {
                "name": c["name"],
                "got": json.dumps("nope" if c["name"] == hidden_name else c["expected"], separators=(",", ":")),
            }
            for c in cases
        ]
        graded = service.grade_reported_cases(entry, lying)
        assert graded["hidden_passed"] == graded["hidden_total"] - 1
        assert hidden_name in graded["failed_hidden"]

    def test_conduct_reaches_the_reviewer_and_the_debrief(self, monkeypatch):
        # The paste flag was being written to the database and read by
        # nothing -- recorded but invisible, which is the same as absent.
        h = self._setup(monkeypatch, "conduct", CODE_ROUND_PLAN)
        app = h["app"]

        with TestClient(app) as client:
            client.post(f"/api/v1/interview/{h['interview_id']}/transcript", json={"chunks": A_REAL_CONVERSATION})
            client.post(f"/api/v1/interview/{h['interview_id']}/advance", json={})
            client.post(
                f"/api/v1/interview/{h['interview_id']}/round/1/submit",
                json={
                    "answer": "def merge_intervals(x): return x",
                    "language": "python",
                    "seconds_taken": 37,
                    "pasted": True,
                    "runs": 4,
                    "failed_runs": 3,
                },
            )
            voice = client.post(f"/api/v1/interview/{h['interview_id']}/voice-token", json={})

        # The reviewer was told.
        review_prompt = h["calls"]["review_prompt"]
        assert "PASTED" in review_prompt
        assert "37s" in review_prompt
        assert "4 time(s)" in review_prompt

        # And so was the interviewer, for the debrief.
        instruction = voice.json()["system_instruction"]
        assert "PASTED" in instruction
        assert "Do not accuse them" in instruction

    def test_voice_token_reseeds_with_the_submission_and_review(self, monkeypatch):
        h = self._setup(monkeypatch, "reseed", CODE_ROUND_PLAN)
        app = h["app"]

        with TestClient(app) as client:
            client.post(
                f"/api/v1/interview/{h['interview_id']}/transcript", json={"chunks": A_REAL_CONVERSATION}
            )
            client.post(f"/api/v1/interview/{h['interview_id']}/advance", json={})
            client.post(
                f"/api/v1/interview/{h['interview_id']}/round/1/submit",
                json={"answer": "def merge_intervals(x): return sorted(x)", "language": "python"},
            )
            resp = client.post(f"/api/v1/interview/{h['interview_id']}/voice-token", json={})

        assert resp.status_code == 200, resp.text
        instruction = resp.json()["system_instruction"]
        # Carries the conversation (ephemeral tokens ignore resumption
        # handles, so this is the ONLY way it remembers).
        assert "Redis, read-through" in instruction
        assert "do NOT restart the interview" in instruction.lower() or "not restart" in instruction.lower()
        # Carries the submission and the review's notes.
        assert "sorted(x)" in instruction
        assert "Press on the empty-input case." in instruction

    def test_interview_without_a_plan_still_works(self, monkeypatch):
        # Every interview created before this feature has plan = NULL.
        h = self._setup(monkeypatch, "legacy", CODE_ROUND_PLAN)
        interview_id = h["interview_id"]

        async def wipe_plan():
            async with AsyncSessionLocal() as db:
                from sqlalchemy import text

                await db.execute(
                    text('UPDATE "InterviewSessions" SET plan = NULL WHERE id = :i'), {"i": interview_id}
                )
                await db.commit()

        _run(wipe_plan)

        with TestClient(h["app"]) as client:
            # No exercise rounds exist, so asking for one 404s rather than
            # exploding, and voice still mints.
            missing = client.get(f"/api/v1/interview/{interview_id}/round/0")
            voice = client.post(f"/api/v1/interview/{interview_id}/voice-token", json={})

        assert missing.status_code == 409  # round 0 is a conversation
        assert voice.status_code == 200


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
        body = lb_resp.json()
        # Deliberately NOT "is our score-7 row in the top 100": the route
        # caps limit at 100 and this suite has run against the same dev
        # database enough times that over a hundred higher scores exist, so
        # that assertion fails on accumulation rather than on a defect.
        # The board is checked for shape and ordering; that THIS interview
        # scored 7 is asserted through /me below, which is user-scoped and
        # cannot be crowded out.
        assert body["total"] >= 1
        assert len(body["entries"]) <= 100
        scores = [e["score"] for e in body["entries"]]
        assert scores == sorted(scores, reverse=True), "leaderboard must be ordered by score"

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
