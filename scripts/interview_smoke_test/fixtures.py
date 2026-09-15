"""
scripts/interview_smoke_test/fixtures.py

Seeds a fresh, fixed DONE resume+roast session directly via the DB and
blob helpers the backend itself uses -- the same pattern
backend/src/routes/test_interview.py's _make_done_resume_session_id uses,
not a copy of it, since a divergence here would test a fixture the real
code doesn't actually produce.

Skips the extraction pipeline entirely (no upload, no worker hops): this
is a controlled fixture for a SMOKE TEST of the interview flow, not a
test of ingestion. It writes a SWE-flavoured resume on purpose -- the
planner is explicitly biased toward including an exercise for a role that
writes code or SQL, and this smoke test exists specifically to reach the
begin_round / round-submit path.

Creates a NEW session on every call rather than caching one: two DB rows
and two blob writes cost nothing, and it removes a whole class of
"was this fixture still valid" staleness bugs for free.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "backend"))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(REPO_ROOT / "workers" / ".env")

from backend.src.db.session import AsyncSessionLocal  # noqa: E402
from backend.src.db.sessions import JobStatusEnum  # noqa: E402
from backend.src.services.blob import (  # noqa: E402
    initialize_blob_storage,
    upload_anonymized,
    upload_roast,
)
from backend.src.services.session_service import create_sessions, get_session  # noqa: E402
from backend.src.services.user_service import get_or_create_users_from_claims  # noqa: E402

# Enough structural content across two sections that the planner reads
# this as a real engineering resume, not a one-line stub it might treat
# as too thin to plan an exercise for.
ANONYMIZED_FIXTURE = {
    "content": {
        "blocks": {
            "experience": [
                {
                    "text": (
                        "Backend engineer, checkout platform. Rebuilt the payment retry "
                        "queue on top of a sliding-window rate limiter, cutting duplicate "
                        "charges by 90%. Wrote the SQL migration that backfilled 40M rows "
                        "of order history with zero downtime."
                    )
                },
                {
                    "text": (
                        "Owned the product catalogue service: a Python/FastAPI API backed "
                        "by Postgres, with an LRU-cached read path in front of the search "
                        "index to keep p99 latency under 50ms."
                    )
                },
            ],
            "skills": [{"text": "Python, SQL, Postgres, Redis, distributed systems"}],
        }
    },
}

ROAST_FIXTURE = {
    "verdict": "Solid engineering depth, thin on scale numbers.",
    "roast": (
        "The work is real -- a rate limiter and a cache-backed read path are "
        "genuine systems, not resume filler -- but almost nothing here is "
        "quantified beyond one percentage. State the actual scale: how many "
        "requests per second, how many rows, how many nines of uptime."
    ),
    "fixes": ["Add throughput numbers to every bullet.", "Name the scale of the migration."],
    "highlights": [
        {"quote": "cutting duplicate charges by 90%", "comment": "The one bullet that is actually quantified."}
    ],
    "quality_flags": [],
}

JOB_DESCRIPTION = (
    "Backend engineer, Python. You will write production Python services, design "
    "and query Postgres schemas directly, and be expected to reason about "
    "concurrency and data structures in a live technical conversation."
)


async def seed_resume_session(db_user_id) -> str:
    initialize_blob_storage()
    async with AsyncSessionLocal() as db:
        session = await create_sessions(user_id=db_user_id, db=db)
        session_id = str(session.id)
        upload_anonymized(session_id=session_id, data=ANONYMIZED_FIXTURE)
        upload_roast(session_id=session_id, data=ROAST_FIXTURE)
        session = await get_session(session_id=session.id, db=db)
        session.status = JobStatusEnum.DONE.value
        db.add(session)
        await db.commit()
    return session_id


async def get_or_create_db_user_id(firebase_uid: str, email: str):
    """
    The DB Users.id, matching exactly what the real API will resolve the
    same firebase_uid/email to via get_current_user -- if these diverge,
    the interview route 403s ("Not your resume") because the seeded
    session and the authenticated request end up owned by different rows.
    """
    async with AsyncSessionLocal() as db:
        user = await get_or_create_users_from_claims(
            {
                "uid": firebase_uid,
                "email": email,
                "email_verified": True,
                "display_name": "Interview Smoke Test",
                "picture": "",
                "is_anonymous": False,
            },
            db,
        )
        return user.id


if __name__ == "__main__":
    import asyncio

    from auth import TEST_ACCOUNT_EMAIL, mint_id_token

    async def main():
        _, uid = mint_id_token()
        db_user_id = await get_or_create_db_user_id(uid, TEST_ACCOUNT_EMAIL)
        session_id = await seed_resume_session(db_user_id)
        print(f"[fixtures] seeded resume session {session_id} for db user {db_user_id}")

    asyncio.run(main())
