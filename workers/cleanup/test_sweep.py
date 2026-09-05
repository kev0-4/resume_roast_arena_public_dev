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
from datetime import datetime, timedelta

from backend.src.db.session import AsyncSessionLocal, engine
from backend.src.services.session_service import create_sessions, get_session
from backend.src.services.user_service import get_or_create_users_from_claims, create_anonymous_user
from backend.src.services.blob import (
    initialize_blob_storage,
    upload_raw,
    upload_roast,
    upload_render,
    blob_exists,
)

from workers.cleanup.sweep import cleanup_raw_uploads, cleanup_expired_anonymous_sessions


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
