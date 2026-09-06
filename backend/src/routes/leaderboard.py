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
from ..db.users import Users
from ..dependencies.auth import get_current_user
from ..services.session_service import get_leaderboard, get_user_leaderboard_position
from ..schemas.leaderboard_schemas import LeaderboardEntry, LeaderboardResponse, MyLeaderboardPosition

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
            stamp=row["stamp"],
            created_at=row["created_at"],
        )
        for i, row in enumerate(rows)
    ]
    return LeaderboardResponse(total=total, limit=limit, offset=offset, entries=entries)


@leaderboard_router.get("/leaderboard/me", response_model=MyLeaderboardPosition | None)
async def get_my_leaderboard_position_route(
    db: AsyncSession = Depends(get_db_sqlalchemy),
    curr_user: Users = Depends(get_current_user),
):
    """
    The signed-in caller's own leaderboard standing (their latest roast's
    rank), for the "your rank" banner on the leaderboard page. Requires
    auth -- there's no meaningful "my rank" for an anonymous request.
    Returns null (200, not 404) when the user has no eligible roast yet;
    that's an expected, normal state (e.g. just signed up), not an error.
    """
    position = await get_user_leaderboard_position(db=db, user_id=curr_user.id)
    if position is None:
        return None
    return MyLeaderboardPosition(**position)
