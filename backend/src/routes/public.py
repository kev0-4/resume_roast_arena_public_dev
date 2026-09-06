"""
backend/src/routes/public.py

The Public Link Service -- the fully public, unauthenticated routes in
the app. Resolves a short slug to either the shareable roast card PNG
(GET /r/{slug}) or the full analysis behind it (GET /r/{slug}/data).

A session can only ever have a slug once it's DONE (the renderer worker
generates it as the very last step), so slug-exists implies DONE -- no
separate "not ready yet" branch needed.

TTL: anonymous users' roasts expire after ANONYMOUS_ROAST_TTL_DAYS (config.py,
default 30) from session creation (per the original MVP spec's "roast
metadata TTL 30 days for anonymous") -- this is the same constant
workers/cleanup/sweep.py uses to actually delete the data, kept in one
place so the "expired" check here and the real deletion never drift apart.
Logged-in users: no expiry enforced yet -- spec says "configurable
retention" but nothing configures it yet, so deliberately not inventing a
number here.

Performance notes for /r/{slug}/data (see its own docstring for the rest):
this route is the one place in the app where a single request does two
blob reads plus a DB rank query -- and it's sitting behind a link whose
entire purpose is to be shared and clicked by many people at once, so
per-request cost here matters more than almost anywhere else in the app.
- Blob reads run via asyncio.to_thread (the Azure SDK's blob client is
  synchronous) so a slow blob download never blocks the event loop from
  serving other requests -- fixed on the PNG route below too, which had
  the same blocking call.
- The two blob reads (scored.json + roast.json) run concurrently via
  asyncio.gather instead of one after another.
- Rank is computed via a single indexed COUNT query (get_session_rank),
  not by paginating/scanning the leaderboard.
- The response sets a short Cache-Control -- everything except `rank`/
  `total_ranked` is permanently immutable once a session reaches DONE,
  and a few seconds of rank staleness is a completely acceptable
  tradeoff for how much repeated load it saves on a link that might
  suddenly get hit hundreds of times after being shared somewhere.
"""

import asyncio
import json
from fastapi import APIRouter, Depends, HTTPException, Response, status
from datetime import datetime, timedelta
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.session import get_db_sqlalchemy
from ..db.sessions import Sessions as SessionModel
from ..db.users import Users
from ..services.session_service import get_session_by_slug, get_session_rank
from ..services.blob import read_blob
from ..config import ANONYMOUS_ROAST_TTL_DAYS
from ..schemas.public_schemas import RoastAnalysisResponse

public_router = APIRouter()

_DATA_CACHE_CONTROL = "public, max-age=30, stale-while-revalidate=60"


async def _resolve_live_session(slug: str, db: AsyncSession) -> SessionModel:
    """
    Shared by both routes below: 404 if the slug doesn't exist, 410 if it
    belongs to an anonymous user whose roast has aged out. Kept in one
    place so the PNG route and the data route can never disagree about
    whether a given link is still live.
    """
    session = await get_session_by_slug(db=db, slug=slug)
    if session is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Roast not found")

    user = await db.get(Users, session.user_id)
    if user is not None and user.is_anonymous:
        age = datetime.utcnow() - session.created_at
        if age > timedelta(days=ANONYMOUS_ROAST_TTL_DAYS):
            raise HTTPException(status_code=status.HTTP_410_GONE, detail="This roast has expired")

    return session


def _compute_stamp(summary: dict) -> str:
    """
    Mirrors workers/renderer/pipeline/card_data.py's compute_stamp exactly
    -- duplicated rather than imported because backend/ and workers/ are
    separately deployable services with their own import roots (backend
    reaching into workers/ would break that boundary for one tiny pure
    function). Keep in sync if the stamp formula ever changes.
    """
    critical = summary.get("critical_issues", 0)
    high = summary.get("high_issues", 0)
    total_issues = summary.get("total_issues", 0)
    total_strengths = summary.get("total_strengths", 0)

    if critical > 0 or high >= 2:
        return "ROASTED"
    if total_issues == 0 and total_strengths >= 3:
        return "SOLID"
    return "MID"


@public_router.get("/r/{slug}")
async def get_public_roast_card(slug: str, db: AsyncSession = Depends(get_db_sqlalchemy)):
    session = await _resolve_live_session(slug, db)
    png_bytes = await asyncio.to_thread(read_blob, session.render_blob_path)
    return Response(content=png_bytes, media_type="image/png")


@public_router.get("/r/{slug}/data", response_model=RoastAnalysisResponse)
async def get_public_roast_analysis(slug: str, db: AsyncSession = Depends(get_db_sqlalchemy)):
    """
    The full analysis behind a roast card -- score breakdown, real
    metrics, the LLM's verdict/roast/fixes, grounded quote highlights,
    and this session's live leaderboard rank. Powers the result page (the
    PNG route above only ever served the flattened card image).
    """
    session = await _resolve_live_session(slug, db)

    scored_blob_path = f"scored/{session.id}/scored.json"
    roast_blob_path = f"roast/{session.id}/roast.json"

    async def _read_json(blob_path: str) -> dict:
        raw = await asyncio.to_thread(read_blob, blob_path)
        return json.loads(raw)

    scored, roast, (rank, total_ranked) = await asyncio.gather(
        _read_json(scored_blob_path),
        _read_json(roast_blob_path),
        get_session_rank(db=db, composite_score=session.composite_score, created_at=session.created_at),
    )

    summary = scored["summary"]

    response = RoastAnalysisResponse(
        slug=session.slug,
        composite_score=session.composite_score,
        stamp=_compute_stamp(summary),
        created_at=session.created_at,
        rank=rank,
        total_ranked=total_ranked,
        summary=summary,
        metrics=scored.get("metrics", {}),
        verdict=roast["verdict"],
        roast=roast["roast"],
        fixes=roast["fixes"],
        highlights=roast.get("highlights", []),
    )
    return Response(
        content=response.model_dump_json(),
        media_type="application/json",
        headers={"Cache-Control": _DATA_CACHE_CONTROL},
    )
