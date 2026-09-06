"""
Tests against real Postgres + real Azurite (same philosophy as every
other test this session -- no mocks). Same asyncio.run()-per-test +
engine.dispose() pattern as workers/cleanup/test_sweep.py; every
TestClient use is `with TestClient(app) as client:` (required, not
stylistic -- see test_sessions_status.py's module docstring for why: it
fires the app's lifespan shutdown hook, which is what disposes the
shared async engine cleanly between tests).
"""

import asyncio
import uuid
from datetime import datetime, timedelta

from fastapi.testclient import TestClient

from backend.src.db.session import AsyncSessionLocal, engine
from backend.src.services.session_service import create_sessions, get_session, get_session_rank
from backend.src.services.user_service import get_or_create_users_from_claims, create_anonymous_user
from backend.src.services.blob import initialize_blob_storage, upload_scored, upload_roast
from backend.src.config import ANONYMOUS_ROAST_TTL_DAYS
from backend.src import create_app


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
            "uid": f"public-data-test-{suffix}",
            "email": f"public-data-test-{suffix}@example.com",
            "email_verified": True,
            "display_name": f"PublicDataTest{suffix}",
            "picture": "",
            "is_anonymous": False,
        },
        db,
    )


SCORED_FIXTURE = {
    "summary": {
        "total_issues": 2,
        "critical_issues": 0,
        "high_issues": 1,
        "medium_issues": 1,
        "low_issues": 0,
        "total_strengths": 2,
    },
    "metrics": {"word_count": 312, "avg_sentence_length": 18.4, "lexical_diversity": 0.52},
}

ROAST_FIXTURE = {
    "verdict": "Competent but forgettable.",
    "roast": "The experience section is fine, but nothing here sticks.",
    "fixes": ["Quantify your impact.", "Cut the buzzwords."],
    "highlights": [{"quote": "team player", "comment": "Everyone says this. Nobody proves it."}],
}


async def _make_full_session(db, user_id, *, score, slug):
    initialize_blob_storage()
    session = await create_sessions(user_id=user_id, db=db)
    session_id = session.id
    upload_scored(session_id=str(session_id), data=SCORED_FIXTURE)
    upload_roast(session_id=str(session_id), data=ROAST_FIXTURE)
    session = await get_session(db=db, session_id=session_id)
    session.status = "DONE"
    session.slug = slug
    session.composite_score = score
    db.add(session)
    await db.commit()
    return session_id


class TestGetSessionRank:
    def test_rank_and_total_reflect_real_data(self):
        async def run():
            async with AsyncSessionLocal() as db:
                user = await _make_user(db, f"rank-{uuid.uuid4().hex[:6]}")
                user_id = user.id
                low_id = await _make_full_session(db, user_id, score=10, slug=f"lo{uuid.uuid4().hex[:6]}")
                mid_id = await _make_full_session(db, user_id, score=50, slug=f"md{uuid.uuid4().hex[:6]}")
                high_id = await _make_full_session(db, user_id, score=90, slug=f"hi{uuid.uuid4().hex[:6]}")

                mid_session = await get_session(db=db, session_id=mid_id)
                rank, total = await get_session_rank(
                    db=db, composite_score=mid_session.composite_score, created_at=mid_session.created_at,
                )
                # exactly one real session (the "high" one) scores above
                # "mid" among the three just created -- rank is at least 2
                # (could be higher if other tests left rows in the shared
                # dev DB, but never lower)
                assert rank >= 2
                assert total >= 3

        _run(run)

    def test_tie_broken_by_created_at(self):
        async def run():
            async with AsyncSessionLocal() as db:
                user = await _make_user(db, f"tie-{uuid.uuid4().hex[:6]}")
                user_id = user.id
                now = datetime.utcnow()
                earlier_id = await _make_full_session(db, user_id, score=77, slug=f"ea{uuid.uuid4().hex[:6]}")
                session = await get_session(db=db, session_id=earlier_id)
                session.created_at = now - timedelta(minutes=5)
                db.add(session)
                await db.commit()

                later_id = await _make_full_session(db, user_id, score=77, slug=f"la{uuid.uuid4().hex[:6]}")
                later_session = await get_session(db=db, session_id=later_id)

                rank, _ = await get_session_rank(
                    db=db, composite_score=later_session.composite_score, created_at=later_session.created_at,
                )
                # the earlier same-score session sorts ahead -- later's
                # rank must be at least 2, never 1
                assert rank >= 2

        _run(run)


class TestPublicDataRoute:
    def test_returns_full_analysis(self):
        ids = {}
        slug = f"pubdata{uuid.uuid4().hex[:6]}"

        async def setup():
            async with AsyncSessionLocal() as db:
                user = await _make_user(db, f"route-{slug}")
                session_id = await _make_full_session(db, user.id, score=62, slug=slug)
                ids["id"] = session_id

        _run(setup)

        app = create_app()
        with TestClient(app) as client:
            resp = client.get(f"/r/{slug}/data")

        assert resp.status_code == 200
        body = resp.json()
        assert body["slug"] == slug
        assert body["composite_score"] == 62
        assert body["stamp"] in ("ROASTED", "SOLID", "MID")
        assert body["rank"] >= 1
        assert body["total_ranked"] >= 1
        assert body["summary"]["total_issues"] == 2
        assert body["metrics"]["word_count"] == 312
        assert body["verdict"] == "Competent but forgettable."
        assert body["fixes"] == ["Quantify your impact.", "Cut the buzzwords."]
        assert body["highlights"][0]["quote"] == "team player"
        assert "public" in resp.headers.get("cache-control", "")

    def test_unknown_slug_404s(self):
        app = create_app()
        with TestClient(app) as client:
            resp = client.get("/r/does-not-exist-at-all/data")
        assert resp.status_code == 404

    def test_expired_anonymous_roast_returns_410(self):
        ids = {}
        slug = f"expired{uuid.uuid4().hex[:6]}"

        async def setup():
            async with AsyncSessionLocal() as db:
                anon_user = await create_anonymous_user(db)
                session_id = await _make_full_session(db, anon_user.id, score=40, slug=slug)
                session = await get_session(db=db, session_id=session_id)
                session.created_at = datetime.utcnow() - timedelta(days=ANONYMOUS_ROAST_TTL_DAYS + 1)
                db.add(session)
                await db.commit()
                ids["id"] = session_id

        _run(setup)

        app = create_app()
        with TestClient(app) as client:
            resp = client.get(f"/r/{slug}/data")
        assert resp.status_code == 410
