from typing import Optional
from pydantic import BaseModel
from datetime import datetime


class LeaderboardEntry(BaseModel):
    rank: int
    slug: str
    display_name: str
    composite_score: int
    stamp: Optional[str] = None
    created_at: datetime


class LeaderboardResponse(BaseModel):
    total: int
    limit: int
    offset: int
    entries: list[LeaderboardEntry]


class MyLeaderboardPosition(BaseModel):
    rank: int
    total: int
    slug: str
    composite_score: int
    stamp: Optional[str] = None
    created_at: datetime
