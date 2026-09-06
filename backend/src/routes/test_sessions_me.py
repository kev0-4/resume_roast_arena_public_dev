"""
Tests against real Postgres (same philosophy as every other test this
session -- no mocks). Same asyncio.run()-per-test + engine.dispose()
pattern as test_sessions_status.py; every TestClient use is a
`with TestClient(app) as client:` block, required not stylistic (see
that file's module docstring for why).

Auth is faked via FastAPI's dependency_overrides rather than a real
Firebase token -- imported from `src.dependencies.auth`, NOT
`backend.src.dependencies.auth`: create_app() (backend/src/__init__.py)
wires its routers via `from src.routes...` (absolute, matching
conftest.py putting backend/ on sys.path as well as the repo root), so
the get_current_user object FastAPI actually registered as a dependency
is src.dependencies.auth's -- a different module identity than
backend.src.dependencies.auth even though it's the same file. Overriding
the wrong one is silently a no-op. Same lesson already documented in
test_leaderboard.py.
"""

import asyncio
import uuid

from fastapi.testclient import TestClient

from backend.src.db.session import AsyncSessionLocal, engine
from backend.src.services.session_service import create_sessions, get_session
from backend.src.services.user_service import get_or_create_users_from_claims
from backend.src import create_app
from src.dependencies.auth import get_current_user


def _run(coro_fn):
    async def wrapped():
        try:
            await coro_fn()
        finally:
            await engine.dispose()

    asyncio.run(wrapped())


async def _make_user(db, suffix: str):
    return await get_or_create_users_from_claims(
        {
            "uid": f"sessions-me-test-{suffix}",
            "email": f"sessions-me-test-{suffix}@example.com",
            "email_verified": True,
            "display_name": f"SessionsMeTest{suffix}",
            "picture": "",
            "is_anonymous": False,
        },
        db,
    )


def _override_with(user_id):
    """
    A plain stand-in with just `.id`, not the real (soon-detached) Users
    ORM instance -- the route only ever reads curr_user.id, and passing
    the ORM object across the AsyncSessionLocal block that created it
    raises DetachedInstanceError on any attribute access once that
    session has closed (the same identity-map gotcha documented
    throughout this codebase's other tests).
    """
    class _FakeCurrUser:
        id = user_id

    return _FakeCurrUser()


def test_requires_auth():
    app = create_app()
    with TestClient(app) as client:
        resp = client.get("/api/v1/sessions/me")
    assert resp.status_code == 401


def test_lists_own_sessions_most_recent_first_regardless_of_status():
    suffix = uuid.uuid4().hex[:6]
    holder = {}

    async def setup():
        async with AsyncSessionLocal() as db:
            user = await _make_user(db, suffix)
            user_id = user.id

            done = await create_sessions(user_id=user_id, db=db)
            done_id = done.id
            done = await get_session(db=db, session_id=done_id)
            done.status = "DONE"
            done.slug = f"me{suffix}"
            done.composite_score = 71
            done.stamp = "MID"
            db.add(done)
            await db.commit()
            # capture right after this session's own commit -- a later
            # commit on the same db session expires every instance in its
            # identity map (done included), and accessing an expired
            # attribute outside an awaited call raises MissingGreenlet
            # under the async engine (no implicit lazy-load bridge here,
            # unlike sync SQLAlchemy)
            holder["done_id"] = str(done_id)

            failed = await create_sessions(user_id=user_id, db=db)
            failed_id = failed.id
            failed = await get_session(db=db, session_id=failed_id)
            failed.status = "FAILED"
            failed.error_code = "EXTRACTION_FAILED"
            failed.error_message = "Could not parse file"
            db.add(failed)
            await db.commit()
            holder["failed_id"] = str(failed_id)

            in_progress = await create_sessions(user_id=user_id, db=db)
            holder["in_progress_id"] = str(in_progress.id)

            holder["user_id"] = user_id

    _run(setup)

    app = create_app()
    app.dependency_overrides[get_current_user] = lambda: _override_with(holder["user_id"])
    with TestClient(app) as client:
        resp = client.get("/api/v1/sessions/me", params={"limit": 100})

    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] >= 3
    ids = [s["session_id"] for s in body["sessions"]]
    # most recent first -- in_progress was created last
    assert ids.index(holder["in_progress_id"]) < ids.index(holder["failed_id"]) < ids.index(holder["done_id"])

    by_id = {s["session_id"]: s for s in body["sessions"]}
    assert by_id[holder["done_id"]]["status"] == "DONE"
    assert by_id[holder["done_id"]]["slug"] == f"me{suffix}"
    assert by_id[holder["done_id"]]["composite_score"] == 71
    assert by_id[holder["done_id"]]["stamp"] == "MID"

    assert by_id[holder["failed_id"]]["status"] == "FAILED"
    assert by_id[holder["failed_id"]]["error_code"] == "EXTRACTION_FAILED"
    assert by_id[holder["failed_id"]]["slug"] is None

    assert by_id[holder["in_progress_id"]]["status"] == "UPLOADED"
    assert by_id[holder["in_progress_id"]]["slug"] is None


def test_never_returns_another_users_sessions():
    holder = {}

    async def setup():
        async with AsyncSessionLocal() as db:
            mine = await _make_user(db, f"mine-{uuid.uuid4().hex[:6]}")
            mine_id = mine.id  # capture before `other`'s creation commits and expires `mine`
            other = await _make_user(db, f"other-{uuid.uuid4().hex[:6]}")
            other_id = other.id
            mine_session = await create_sessions(user_id=mine_id, db=db)
            holder["mine_session_id"] = str(mine_session.id)
            other_session = await create_sessions(user_id=other_id, db=db)
            holder["other_session_id"] = str(other_session.id)
            holder["mine_id"] = mine_id

    _run(setup)

    app = create_app()
    app.dependency_overrides[get_current_user] = lambda: _override_with(holder["mine_id"])
    with TestClient(app) as client:
        resp = client.get("/api/v1/sessions/me", params={"limit": 100})

    assert resp.status_code == 200
    ids = [s["session_id"] for s in resp.json()["sessions"]]
    assert holder["mine_session_id"] in ids
    assert holder["other_session_id"] not in ids


def test_pagination_limit_and_offset():
    holder = {}

    async def setup():
        async with AsyncSessionLocal() as db:
            user = await _make_user(db, f"page-{uuid.uuid4().hex[:6]}")
            user_id = user.id  # capture before the loop's own commits expire `user`
            for _ in range(5):
                await create_sessions(user_id=user_id, db=db)
            holder["user_id"] = user_id

    _run(setup)

    app = create_app()
    app.dependency_overrides[get_current_user] = lambda: _override_with(holder["user_id"])
    with TestClient(app) as client:
        page1 = client.get("/api/v1/sessions/me", params={"limit": 2, "offset": 0}).json()
        page2 = client.get("/api/v1/sessions/me", params={"limit": 2, "offset": 2}).json()

    assert page1["total"] == 5
    assert len(page1["sessions"]) == 2
    assert len(page2["sessions"]) == 2
    ids1 = {s["session_id"] for s in page1["sessions"]}
    ids2 = {s["session_id"] for s in page2["sessions"]}
    assert ids1.isdisjoint(ids2)


def test_stats_reflect_only_scored_sessions():
    holder = {}

    async def setup():
        async with AsyncSessionLocal() as db:
            user = await _make_user(db, f"stats-{uuid.uuid4().hex[:6]}")
            user_id = user.id

            for score in (40, 80, 60):
                s = await create_sessions(user_id=user_id, db=db)
                s_id = s.id
                s = await get_session(db=db, session_id=s_id)
                s.status = "DONE"
                s.composite_score = score
                db.add(s)
                await db.commit()

            # an UPLOADED session with no score at all -- must not count
            # toward total_roasts or skew the average
            await create_sessions(user_id=user_id, db=db)

            holder["user_id"] = user_id

    _run(setup)

    app = create_app()
    app.dependency_overrides[get_current_user] = lambda: _override_with(holder["user_id"])
    with TestClient(app) as client:
        resp = client.get("/api/v1/sessions/me", params={"limit": 100})

    assert resp.status_code == 200
    stats = resp.json()["stats"]
    assert stats["total_roasts"] == 3
    assert stats["best_score"] == 80
    assert stats["average_score"] == 60  # (40 + 80 + 60) / 3


def test_stats_are_null_when_no_scored_sessions():
    holder = {}

    async def setup():
        async with AsyncSessionLocal() as db:
            user = await _make_user(db, f"stats-none-{uuid.uuid4().hex[:6]}")
            holder["user_id"] = user.id

    _run(setup)

    app = create_app()
    app.dependency_overrides[get_current_user] = lambda: _override_with(holder["user_id"])
    with TestClient(app) as client:
        resp = client.get("/api/v1/sessions/me")

    assert resp.status_code == 200
    stats = resp.json()["stats"]
    assert stats["total_roasts"] == 0
    assert stats["best_score"] is None
    assert stats["average_score"] is None
