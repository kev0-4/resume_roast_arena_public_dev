"""
Tests against real Postgres (same philosophy as every other test this
session -- no mocks), plus CORS checks against the real FastAPI app via
TestClient. Same asyncio.run()-per-test + engine.dispose() pattern as
workers/cleanup/test_sweep.py for the setup half of each test.

Covers two changes made together to unblock the frontend actually calling
this API: CORS middleware (didn't exist before) and GET /sessions/{id}
returning slug + error fields (needed for the processing-page polling
flow to know where to redirect on success and what to show on failure).

Every TestClient usage here is a `with TestClient(app) as client:` block --
that's required, not stylistic: TestClient runs the app on its own event
loop in a background thread, and without going through its context
manager (which fires the app's lifespan shutdown hook -- see
backend/src/__init__.py's `lifespan`, added specifically for this) a
second TestClient elsewhere in the suite making its own real DB call
reliably hits `RuntimeError: ... attached to a different loop`.
"""

import asyncio
import uuid

from fastapi.testclient import TestClient

from backend.src.db.session import AsyncSessionLocal, engine
from backend.src.services.session_service import create_sessions, get_session
from backend.src.services.user_service import get_or_create_users_from_claims
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
            "uid": f"sessions-status-test-{suffix}",
            "email": f"sessions-status-test-{suffix}@example.com",
            "email_verified": True,
            "display_name": f"SessionsStatusTest{suffix}",
            "picture": "",
            "is_anonymous": False,
        },
        db,
    )


def test_session_status_includes_slug_and_error_fields():
    session_id_holder = {}
    slug = f"statustest{uuid.uuid4().hex[:6]}"

    async def setup():
        async with AsyncSessionLocal() as db:
            user = await _make_user(db, f"done-{slug}")
            session = await create_sessions(user_id=user.id, db=db)
            session_id = session.id
            session = await get_session(db=db, session_id=session_id)
            session.status = "DONE"
            session.slug = slug
            db.add(session)
            await db.commit()
            session_id_holder["id"] = str(session_id)

    _run(setup)

    app = create_app()
    with TestClient(app) as client:
        resp = client.get(f"/api/v1/sessions/{session_id_holder['id']}")

    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "DONE"
    assert body["slug"] == slug
    assert body["error_code"] is None
    assert body["error_message"] is None


def test_session_status_surfaces_error_fields_on_failure():
    session_id_holder = {}
    suffix = uuid.uuid4().hex[:6]

    async def setup():
        async with AsyncSessionLocal() as db:
            user = await _make_user(db, f"failed-{suffix}")
            session = await create_sessions(user_id=user.id, db=db)
            session_id = session.id
            session = await get_session(db=db, session_id=session_id)
            session.status = "FAILED"
            session.error_code = "EXTRACTION_FAILED"
            session.error_message = "Tika could not parse this file"
            db.add(session)
            await db.commit()
            session_id_holder["id"] = str(session_id)

    _run(setup)

    app = create_app()
    with TestClient(app) as client:
        resp = client.get(f"/api/v1/sessions/{session_id_holder['id']}")

    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "FAILED"
    assert body["slug"] is None
    assert body["error_code"] == "EXTRACTION_FAILED"
    assert body["error_message"] == "Tika could not parse this file"


def test_cors_allows_configured_frontend_origin():
    app = create_app()
    with TestClient(app) as client:
        resp = client.options(
            "/api/v1/sessions/00000000-0000-0000-0000-000000000000",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "GET",
            },
        )

    assert resp.status_code == 200
    assert resp.headers.get("access-control-allow-origin") == "http://localhost:3000"


def test_cors_rejects_unlisted_origin():
    app = create_app()
    with TestClient(app) as client:
        resp = client.options(
            "/api/v1/sessions/00000000-0000-0000-0000-000000000000",
            headers={
                "Origin": "http://evil.example.com",
                "Access-Control-Request-Method": "GET",
            },
        )

    # starlette's CORS middleware still returns 200 for a disallowed
    # preflight, it just omits the allow-origin header -- the browser is
    # what actually enforces the block based on that header being absent.
    assert "access-control-allow-origin" not in resp.headers
