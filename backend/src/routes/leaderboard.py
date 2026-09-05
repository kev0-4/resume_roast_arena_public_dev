"""
backend/src/routes/leaderboard.py

Public, unauthenticated ranking of shareable roasts by
Sessions.composite_score -- the leaderboard flagged as a planned future
feature back in section 29 of the migration docs when composite_score was
first added, deliberately kept as a real stored/queryable column for
exactly this. See backend/src/services/session_service.py:get_leaderboard
for the eligibility/ordering rules (mirrors public.py's slug+DONE+TTL
scoping so a leaderboard entry and its /r/{slug} card never disagree about
whether a roast is still live).

No frontend rendering here (same as the rest of this backend -- the roast
card itself is a server-rendered PNG, not a page this API builds) -- this
is the JSON data endpoint a future frontend would consume.
"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.session import get_db_sqlalchemy
from ..services.session_service import get_leaderboard
from ..schemas.leaderboard_schemas import LeaderboardEntry, LeaderboardResponse

leaderboard_router = APIRouter()


@leaderboard_router.get("/leaderboard", response_model=LeaderboardResponse)
async def get_leaderboard_route(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db_sqlalchemy),
):
    rows, total = await get_leaderboard(db=db, limit=limit, offset=offset)
    entries = [
        LeaderboardEntry(
            rank=offset + i + 1,
            slug=row["slug"],
            display_name=row["display_name"] or "Anonymous Applicant",
            composite_score=row["composite_score"],
            created_at=row["created_at"],
        )
        for i, row in enumerate(rows)
    ]
    return LeaderboardResponse(total=total, limit=limit, offset=offset, entries=entries)
