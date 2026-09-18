"""
Tests for GET /health/pipeline — the stuck-work detector the watchdog reads.

Against real Postgres, no mocks, following the same asyncio.run()-per-test
plus engine.dispose() pattern as test_leaderboard.py and
workers/cleanup/test_sweep.py (see either module docstring for why: the
module-level async engine binds to whichever event loop first touches it).

Why this endpoint exists: /health/ checks that the backend can reach
Postgres, Redis and Blob — and stays green while a worker is dead and every
upload sits half-finished forever. A dead worker was invisible.

The property that matters most is the 503, because that IS the alerting
contract. The watchdog decides purely on the status code; if a stalled
pipeline ever answers 200, no email is sent and nobody finds out.

**These tests never mutate rows they did not create.** The endpoint's verdict
depends on global table state, so the obvious shortcut is to retire whatever
is already stuck in the shared dev database first. An earlier draft did
exactly that and broke four tests in workers/cleanup/test_sweep.py, which
legitimately depend on sessions this file had no business touching. So
instead: measure a baseline, add known rows, and assert on the DELTA and on
invariants that hold whatever else is in the table.

Sessions are built by setting status/updated_at directly on the ORM object,
bypassing update_session_status's transition validation, exactly as
test_leaderboard.py and test_sweep.py do — these tests care about the
columns the query reads, not how a session legitimately reaches a status.

Run with:  python -m pytest backend/src/routes/test_status_pipeline.py -v
"""

import asyncio
from datetime import datetime, timedelta

from fastapi.testclient import TestClient

from backend.src.db.session import AsyncSessionLocal, engine
from backend.src.services.session_service import create_sessions, get_session
from backend.src.services.user_service import get_or_create_users_from_claims
from backend.src import create_app
from backend.src.routes.status import STUCK_AFTER_MINUTES, STUCK_TOLERATED


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
            "uid": f"pipeline-health-user-{suffix}",
            "email": f"pipeline-health-{suffix}@example.com",
            "email_verified": True,
            "display_name": f"PipelineHealth{suffix}",
            "picture": "",
            "is_anonymous": False,
        },
        db,
    )


async def _make_session(db, user_id, *, status: str, stale_minutes: int):
    """A session parked in `status`, last touched `stale_minutes` ago."""
    session = await create_sessions(user_id=user_id, db=db)
    session_id = session.id
    session = await get_session(db=db, session_id=session_id)
    session.status = status
    session.updated_at = datetime.utcnow() - timedelta(minutes=stale_minutes)
    db.add(session)
    await db.commit()
    return session_id


def _get_pipeline():
    app = create_app()
    with TestClient(app) as client:
        return client.get("/api/v1/health/pipeline")


def _seed(suffix, rows):
    """rows = [(status, stale_minutes, count), ...]"""
    async def run():
        async with AsyncSessionLocal() as db:
            user = await _make_user(db, suffix)
            user_id = user.id
            for status, stale, count in rows:
                for _ in range(count):
                    await _make_session(db, user_id, status=status,
                                        stale_minutes=stale)

    _run(run)


class TestWhatCountsAsStuck:
    def test_work_in_progress_right_now_is_never_counted(self):
        # The false-positive guard that decides whether the alert gets
        # trusted: a busy pipeline must look identical to an idle one.
        before = _get_pipeline().json()
        _seed("recent", [("SCORING", 1, STUCK_TOLERATED + 5)])
        after = _get_pipeline().json()

        assert after["stuck_total"] == before["stuck_total"]
        assert (after["stuck_by_status"].get("SCORING", 0)
                == before["stuck_by_status"].get("SCORING", 0))

    def test_finished_work_is_never_counted(self):
        # DONE and FAILED are terminal — they sit untouched forever by
        # design, so age means nothing for them.
        before = _get_pipeline().json()
        _seed("terminal", [
            ("DONE", STUCK_AFTER_MINUTES * 100, STUCK_TOLERATED + 5),
            ("FAILED", STUCK_AFTER_MINUTES * 100, STUCK_TOLERATED + 5),
        ])
        after = _get_pipeline().json()

        assert after["stuck_total"] == before["stuck_total"]

    def test_old_in_flight_work_is_counted(self):
        before = _get_pipeline().json()
        n = 4
        _seed("counted", [("ANONYMIZING", STUCK_AFTER_MINUTES + 10, n)])
        after = _get_pipeline().json()

        assert after["stuck_total"] == before["stuck_total"] + n
        assert (after["stuck_by_status"].get("ANONYMIZING", 0)
                == before["stuck_by_status"].get("ANONYMIZING", 0) + n)

    def test_work_just_under_the_threshold_is_not_counted(self):
        # Boundary: the cutoff must be the threshold, not "roughly".
        before = _get_pipeline().json()
        _seed("boundary", [("QUEUED", STUCK_AFTER_MINUTES - 2, 3)])
        after = _get_pipeline().json()

        assert after["stuck_total"] == before["stuck_total"]


class TestAlertingContract:
    def test_a_stalled_pipeline_returns_503(self):
        """
        The entire alerting contract. The watchdog decides on the status
        code alone — if this ever answers 200 while work is stalled, no
        email is sent and a dead worker goes unnoticed.

        Seeded relative to the current baseline so it crosses the threshold
        regardless of what else is already in the table.
        """
        baseline = _get_pipeline().json()["stuck_total"]
        need = max(0, STUCK_TOLERATED - baseline) + 4
        _seed("stalled", [("SCORING", STUCK_AFTER_MINUTES + 10, need)])

        res = _get_pipeline()
        body = res.json()
        assert body["stuck_total"] > body["tolerated"]
        assert res.status_code == 503, "a stalled pipeline MUST fail the watchdog"
        assert body["status"] == "Degraded"

    def test_verdict_always_agrees_with_the_numbers(self):
        # Invariant, true in any table state: the words and the numbers can
        # never disagree, or the alert says one thing and the body another.
        body = _get_pipeline().json()
        healthy = body["status"] == "Healthy"
        assert healthy == (body["stuck_total"] <= body["tolerated"])

    def test_status_code_always_agrees_with_the_verdict(self):
        res = _get_pipeline()
        body = res.json()
        if body["status"] == "Healthy":
            assert res.status_code == 200
        else:
            assert res.status_code == 503


class TestFaultLocalisation:
    def test_names_the_stage_that_stopped(self):
        # This is what turns an alert into an action: the stage holding the
        # most stuck work names the worker to go and look at.
        baseline = _get_pipeline().json()
        biggest = max(baseline["stuck_by_status"].values(), default=0)
        _seed("stage", [("ROASTING", STUCK_AFTER_MINUTES + 10, biggest + 6)])

        body = _get_pipeline().json()
        assert body["likely_stalled_stage"] == "ROASTING"

    def test_breakdown_separates_stages(self):
        before = _get_pipeline().json()["stuck_by_status"]
        _seed("mixed", [
            ("NORMALIZING", STUCK_AFTER_MINUTES + 10, 3),
            ("RENDERING", STUCK_AFTER_MINUTES + 10, 2),
        ])
        after = _get_pipeline().json()["stuck_by_status"]

        assert after.get("NORMALIZING", 0) == before.get("NORMALIZING", 0) + 3
        assert after.get("RENDERING", 0) == before.get("RENDERING", 0) + 2


class TestResponseContract:
    def test_carries_the_fields_the_watchdog_and_reader_need(self):
        body = _get_pipeline().json()
        for field in ("status", "stuck_total", "stuck_by_status",
                      "likely_stalled_stage", "threshold_minutes",
                      "tolerated", "checked_at"):
            assert field in body, f"missing {field}"
        assert body["threshold_minutes"] == STUCK_AFTER_MINUTES
        assert body["tolerated"] == STUCK_TOLERATED

    def test_checked_at_is_parseable(self):
        datetime.fromisoformat(_get_pipeline().json()["checked_at"])

    def test_dependency_health_stays_a_separate_endpoint(self):
        # They must stay separate: /health/ is the probe-shaped one, and a
        # probe failing because a *different* service is stuck would
        # restart the wrong container.
        app = create_app()
        with TestClient(app) as client:
            dep = client.get("/api/v1/health/")
        assert "stuck_total" not in dep.json()
        assert "entities" in dep.json()
