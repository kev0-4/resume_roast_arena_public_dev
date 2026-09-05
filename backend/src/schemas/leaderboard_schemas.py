from pydantic import BaseModel
from datetime import datetime


class LeaderboardEntry(BaseModel):
    rank: int
    slug: str
    display_name: str
    composite_score: int
    created_at: datetime


class LeaderboardResponse(BaseModel):
    total: int
    limit: int
    offset: int
    entries: list[LeaderboardEntry]
