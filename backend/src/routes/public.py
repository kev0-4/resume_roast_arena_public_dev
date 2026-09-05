"""
backend/src/routes/public.py

The Public Link Service -- the one fully public, unauthenticated route in
the app. Resolves a short slug to the shareable roast card PNG.

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
"""

from fastapi import APIRouter, Depends, HTTPException, Response, status
from datetime import datetime, timedelta
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.session import get_db_sqlalchemy
from ..db.users import Users
from ..services.session_service import get_session_by_slug
from ..services.blob import read_blob
from ..config import ANONYMOUS_ROAST_TTL_DAYS

public_router = APIRouter()


@public_router.get("/r/{slug}")
async def get_public_roast_card(slug: str, db: AsyncSession = Depends(get_db_sqlalchemy)):
    session = await get_session_by_slug(db=db, slug=slug)
    if session is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Roast not found")

    user = await db.get(Users, session.user_id)

    if user is not None and user.is_anonymous:
        age = datetime.utcnow() - session.created_at
        if age > timedelta(days=ANONYMOUS_ROAST_TTL_DAYS):
            raise HTTPException(status_code=status.HTTP_410_GONE, detail="This roast has expired")

    png_bytes = read_blob(session.render_blob_path)
    return Response(content=png_bytes, media_type="image/png")
