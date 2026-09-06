"""
Tests against real Postgres (same philosophy as every other test this
session -- no mocks). Same asyncio.run()-per-test + engine.dispose()
pattern as workers/cleanup/test_sweep.py (see that file's module docstring
for why: the module-level async engine singleton binds to whichever event
loop first touches it, and each test's own asyncio.run() is a different
loop).

Sessions here are built by creating a real session then setting
status/slug/composite_score directly on the ORM object and committing --
bypassing update_session_status's transition validation (which only knows
about the UPLOADED->QUEUED->PROCESSING->DONE chain, not the full real
pipeline's intermediate statuses) the same way _backdate in test_sweep.py
bypasses it to set created_at directly. This is fine for these tests: the
leaderboard query only cares about the final columns (slug,
composite_score, created_at, user), not how a session got there.

The one route test below uses `with TestClient(app) as client:` (not a
bare `TestClient(app)`) -- required, not stylistic. See
test_sessions_status.py's module docstring for why.
"""

import asyncio
import uuid
from datetime import datetime, timedelta

from fastapi.testclient import TestClient

from backend.src.db.session import AsyncSessionLocal, engine
from backend.src.services.session_service import create_sessions, get_session, get_leaderboard
from backend.src.services.user_service import get_or_create_users_from_claims, create_anonymous_user
from backend.src.config import ANONYMOUS_ROAST_TTL_DAYS
from backend.src import create_app

# NOT backend.src.dependencies.auth -- create_app() (backend/src/__init__.py)
# wires its routers via `from src.routes...` (absolute, matching conftest.py
# putting backend/ on sys.path as well as the repo root), so the
# get_current_user object FastAPI actually registered as a dependency is
# src.dependencies.auth's, a different module identity than
# backend.src.dependencies.auth even though it's the same file. Overriding
# the wrong one is silently a no-op -- dependency_overrides matches by
# object identity, not by behavior, so the real dependency still runs.
from src.dependencies.auth import get_current_user


def _run(coro_fn):
    async def wrapped():
        try:
            await coro_fn()
        finally:
            await engine.dispose()

    asyncio.run(wrapped())


async def _make_logged_in_user(db, suffix: str):
    return await get_or_create_users_from_claims(
        {
            "uid": f"leaderboard-test-user-{suffix}",
            "email": f"leaderboard-test-{suffix}@example.com",
            "email_verified": True,
            "display_name": f"LeaderboardTest{suffix}",
            "picture": "",
            "is_anonymous": False,
        },
        db,
    )


async def _make_public_session(db, user_id, *, score, slug=None, created_at=None, stamp=None):
    session = await create_sessions(user_id=user_id, db=db)
    session_id = session.id
    session = await get_session(db=db, session_id=session_id)
    session.status = "DONE"
    session.composite_score = score
    session.stamp = stamp
    session.slug = slug or f"lb{uuid.uuid4().hex[:6]}"
    if created_at is not None:
        session.created_at = created_at
    db.add(session)
    await db.commit()
    return session_id


def test_ranks_by_score_descending():
    async def run():
        async with AsyncSessionLocal() as db:
            user = await _make_logged_in_user(db, "rank")
            user_id = user.id
            low = await _make_public_session(db, user_id, score=40)
            high = await _make_public_session(db, user_id, score=95)
            mid = await _make_public_session(db, user_id, score=70)

            # limit=1000, not 100 -- this suite has run against the same
            # real dev Postgres many times over, and a low score (40) can
            # get crowded out of a top-100 window by now-accumulated rows
            # from earlier runs. This test only cares about relative
            # order, not pagination, so a generous limit is the right fix
            # (not deleting historical rows, which other tests may still
            # reference).
            rows, total = await get_leaderboard(db=db, limit=1000, offset=0)
            ids_in_order = [r["id"] for r in rows]

            assert ids_in_order.index(high) < ids_in_order.index(mid) < ids_in_order.index(low)
            assert total >= 3

    _run(run)


def test_ties_broken_by_created_at_ascending():
    async def run():
        async with AsyncSessionLocal() as db:
            user = await _make_logged_in_user(db, "tie")
            user_id = user.id
            now = datetime.utcnow()
            earlier = await _make_public_session(db, user_id, score=77, created_at=now - timedelta(minutes=5))
            later = await _make_public_session(db, user_id, score=77, created_at=now)

            # limit=1000, not 100 -- see test_ranks_by_score_descending's
            # comment above; this suite has run against the same real dev
            # Postgres so many times that a mid-range score (77) can get
            # crowded out of a top-100 window by now-accumulated rows.
            rows, _ = await get_leaderboard(db=db, limit=1000, offset=0)
            ids_in_order = [r["id"] for r in rows]

            assert ids_in_order.index(earlier) < ids_in_order.index(later)

    _run(run)


def test_excludes_sessions_without_slug():
    async def run():
        async with AsyncSessionLocal() as db:
            user = await _make_logged_in_user(db, "noslug")
            session = await create_sessions(user_id=user.id, db=db)
            session_id = session.id
            session = await get_session(db=db, session_id=session_id)
            session.status = "SCORING"
            session.composite_score = 88
            # no slug set -- never reached DONE
            db.add(session)
            await db.commit()

            rows, _ = await get_leaderboard(db=db, limit=1000, offset=0)
            ids = [r["id"] for r in rows]

            assert session_id not in ids

    _run(run)


def test_excludes_expired_anonymous_sessions():
    async def run():
        async with AsyncSessionLocal() as db:
            anon_user = await create_anonymous_user(db)
            anon_user_id = anon_user.id
            expired_at = datetime.utcnow() - timedelta(days=ANONYMOUS_ROAST_TTL_DAYS + 1)
            expired_id = await _make_public_session(db, anon_user_id, score=91, created_at=expired_at)

            fresh_anon = await create_anonymous_user(db)
            fresh_anon_id = fresh_anon.id
            fresh_id = await _make_public_session(db, fresh_anon_id, score=91)

            rows, _ = await get_leaderboard(db=db, limit=1000, offset=0)
            ids = [r["id"] for r in rows]

            assert expired_id not in ids
            assert fresh_id in ids

    _run(run)


def test_logged_in_user_never_excluded_by_age():
    async def run():
        async with AsyncSessionLocal() as db:
            user = await _make_logged_in_user(db, "oldbutloggedin")
            old_at = datetime.utcnow() - timedelta(days=ANONYMOUS_ROAST_TTL_DAYS + 100)
            old_id = await _make_public_session(db, user.id, score=60, created_at=old_at)

            rows, _ = await get_leaderboard(db=db, limit=1000, offset=0)
            ids = [r["id"] for r in rows]

            assert old_id in ids

    _run(run)


def test_pagination_limit_and_offset():
    async def run():
        async with AsyncSessionLocal() as db:
            user = await _make_logged_in_user(db, "page")
            user_id = user.id
            for score in (10, 20, 30, 40, 50):
                await _make_public_session(db, user_id, score=score)

            page1, total = await get_leaderboard(db=db, limit=2, offset=0)
            page2, _ = await get_leaderboard(db=db, limit=2, offset=2)

            assert len(page1) == 2
            assert len(page2) == 2
            assert total >= 5
            page1_scores = [r["composite_score"] for r in page1]
            page2_scores = [r["composite_score"] for r in page2]
            assert page1_scores[0] >= page1_scores[1] >= page2_scores[0]

    _run(run)


def test_route_returns_ranked_entries_with_display_names():
    route_slug = f"routetest{uuid.uuid4().hex[:6]}"

    async def setup():
        async with AsyncSessionLocal() as db:
            user = await _make_logged_in_user(db, f"route-{route_slug}")
            user_id = user.id
            await _make_public_session(db, user_id, score=99, slug=route_slug)

    _run(setup)

    app = create_app()
    with TestClient(app) as client:
        resp = client.get("/leaderboard", params={"limit": 100, "offset": 0})

    assert resp.status_code == 200
    body = resp.json()
    assert body["limit"] == 100
    assert body["offset"] == 0
    assert body["total"] >= 1
    assert any(e["slug"] == route_slug and e["composite_score"] == 99 for e in body["entries"])
    assert all(e["rank"] >= 1 for e in body["entries"])
    assert any(e["slug"] == route_slug and e["display_name"] == f"LeaderboardTestroute-{route_slug}" for e in body["entries"])


def test_get_leaderboard_includes_stamp():
    async def run():
        async with AsyncSessionLocal() as db:
            user = await _make_logged_in_user(db, "stamp")
            stamped_id = await _make_public_session(db, user.id, score=85, stamp="SOLID")

            rows, _ = await get_leaderboard(db=db, limit=1000, offset=0)
            row = next(r for r in rows if r["id"] == stamped_id)
            assert row["stamp"] == "SOLID"

    _run(run)


def test_route_my_position_requires_auth():
    app = create_app()
    with TestClient(app) as client:
        resp = client.get("/leaderboard/me")

    assert resp.status_code == 401


def test_route_my_position_null_when_no_eligible_session():
    async def make_user():
        async with AsyncSessionLocal() as db:
            user = await _make_logged_in_user(db, f"me-none-{uuid.uuid4().hex[:6]}")
            return user.id

    holder = {}

    async def run():
        holder["user_id"] = await make_user()

    _run(run)
    user_id = holder["user_id"]

    class _FakeCurrUser:
        id = user_id

    app = create_app()
    app.dependency_overrides[get_current_user] = lambda: _FakeCurrUser()
    with TestClient(app) as client:
        resp = client.get("/leaderboard/me")

    assert resp.status_code == 200
    assert resp.json() is None


def test_route_my_position_returns_best_session_rank():
    route_slug = f"me{uuid.uuid4().hex[:6]}"

    async def setup():
        async with AsyncSessionLocal() as db:
            user = await _make_logged_in_user(db, f"me-{route_slug}")
            user_id = user.id
            now = datetime.utcnow()
            # newer session should be ignored in favor of the older, higher-
            # scoring one below -- "your rank" is your best roast, not
            # necessarily your most recent one
            await _make_public_session(db, user_id, score=10, created_at=now)
            await _make_public_session(
                db, user_id, score=90, slug=route_slug, created_at=now - timedelta(days=1), stamp="SOLID"
            )
            return user_id

    holder = {}

    async def run():
        holder["user_id"] = await setup()

    _run(run)
    user_id = holder["user_id"]

    # A plain stand-in with just `.id`, not the real (now-detached) Users
    # instance -- the route only ever reads curr_user.id, and the ORM object
    # would raise DetachedInstanceError on any attribute access anyway:
    # the commit inside _make_public_session (same db session as the user
    # was created in) expires every instance in that session's identity map,
    # user included, and there's no session left to refresh from once the
    # `async with AsyncSessionLocal()` block above has exited. Same class of
    # gotcha documented throughout this codebase's other tests.
    class _FakeCurrUser:
        id = user_id

    app = create_app()
    app.dependency_overrides[get_current_user] = lambda: _FakeCurrUser()
    with TestClient(app) as client:
        resp = client.get("/leaderboard/me")

    assert resp.status_code == 200
    body = resp.json()
    assert body is not None
    assert body["slug"] == route_slug
    assert body["composite_score"] == 90
    assert body["stamp"] == "SOLID"
    assert body["rank"] >= 1
    assert body["total"] >= body["rank"]


def test_route_my_position_ties_broken_by_earlier_created_at():
    earlier_slug = f"metie{uuid.uuid4().hex[:6]}"

    async def setup():
        async with AsyncSessionLocal() as db:
            user = await _make_logged_in_user(db, f"me-tie-{earlier_slug}")
            user_id = user.id
            now = datetime.utcnow()
            # same score, different created_at -- "best" should pick the
            # earlier one, matching get_leaderboard's own tiebreak
            # (composite_score DESC, created_at ASC) so "my rank" always
            # agrees with which entry the leaderboard itself would show
            await _make_public_session(db, user_id, score=70, slug=earlier_slug, created_at=now - timedelta(hours=1))
            await _make_public_session(db, user_id, score=70, created_at=now)
            return user_id

    holder = {}

    async def run():
        holder["user_id"] = await setup()

    _run(run)
    user_id = holder["user_id"]

    class _FakeCurrUser:
        id = user_id

    app = create_app()
    app.dependency_overrides[get_current_user] = lambda: _FakeCurrUser()
    with TestClient(app) as client:
        resp = client.get("/leaderboard/me")

    assert resp.status_code == 200
    body = resp.json()
    assert body is not None
    assert body["slug"] == earlier_slug
